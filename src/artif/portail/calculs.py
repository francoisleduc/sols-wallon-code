"""Calculs du portail : stocks par catégorie, flux annuels, signalements et bilan des bassins.

Conventions :
- un stock est la situation au 1er janvier ; le flux de l'année N vaut stock(N+1) − stock(N) ;
- la dernière année de flux est provisoire (la dernière matrice cadastrale est incomplète) ;
- les données gardent toute leur précision, l'arrondi se fait à l'affichage (voir nombres.py).
"""
import pandas as pd

from ..config import SAUT_K_MAD, SAUT_SEUIL_MIN_HA, TRAJ_END, TRAJ_START
from .parametres import (ARTIF, CATEGORIES, ECART_PROCHE, ECART_RYTHME_ABSOLU_HA, ECART_RYTHME_RELATIF, PRECISION_HA,
                         PRECISION_PARTS, RECLASS_COUVERTURE, RECLASS_RETOUR, RECLASS_SORTIE_MIN_HA, REFERENCE_COMMUNE,
                         SOLDE_NEGATIF_HA)


# --- Stocks et flux ------------------------------------------------------------
def stocks_categories(spf: pd.DataFrame, superficies: pd.Series, table: pd.DataFrame) -> pd.DataFrame:
    """Hectares par catégorie, indexés par (commune, année). La surface non cadastrée va dans « inconnu »."""
    categorie = table["categorie"]
    inconnues = sorted(set(spf.columns) - set(categorie.index))
    if inconnues:
        raise ValueError(f"Natures absentes de la table des natures : {inconnues}. Classez-les avant de continuer.")
    res = spf.T.groupby(categorie.reindex(spf.columns)).sum().T.reindex(columns=CATEGORIES, fill_value=0.0)
    non_cadastre = (superficies.reindex(res.index) - spf.sum(axis=1)).clip(lower=0)
    res["inconnu"] += non_cadastre
    res["artif"] = res[ARTIF].sum(axis=1)
    return res


def reperes(st: pd.DataFrame, population: pd.Series, communes, annees: list[int]) -> dict:
    """Trois repères année par année, pour une commune ou un groupe de communes (bassin, Wallonie).

    - m² artificialisés par habitant (habitants au 1er janvier, comme les stocks) ;
    - terres agricoles : terres arables et surfaces enherbées du cadastre ;
    - terrains d'activités : industrie et artisanat, commerces, bureaux et services.
    """
    garder = st.index.get_level_values(0).isin(communes)
    s = st[garder].groupby(level=1).sum().loc[annees]
    p = population[population.index.get_level_values(0).isin(communes)].groupby(level=1).sum().loc[annees]

    def serie(v):
        return [round(float(x), PRECISION_HA) for x in v]

    return {
        "population": [int(x) for x in p],
        "artif_ha": serie(s["artif"]),
        "m2_habitant": [round(float(x), PRECISION_PARTS) for x in s["artif"] * 1e4 / p],
        "agricole_ha": serie(s["arable"] + s["herbe"]),
        "industrie_ha": serie(s["indus"]),
        "commerce_ha": serie(s["comm"]),
    }


def flux_annuels(stock: pd.DataFrame) -> pd.DataFrame:
    """Flux N = stock(N+1) − stock(N). `stock` : années en lignes, communes en colonnes ; résultat : communes en lignes."""
    annees_flux = list(stock.index[:-1])
    flux = stock.diff().shift(-1).loc[annees_flux].T
    flux.columns = annees_flux
    return flux


# --- Reclassements cadastraux ---------------------------------------------------
def natures_artificialisees(table: pd.DataFrame, natures) -> tuple[list, list]:
    """Sépare les natures présentes en artificialisées et non artificialisées."""
    artif = [n for n in natures if table.loc[n, "categorie"] in ARTIF]
    return artif, [n for n in natures if n not in artif]


def variations_natures(spf: pd.DataFrame) -> pd.DataFrame:
    """Variation de chaque nature entre l'année N et l'année N+1, rangée sous l'année N (même convention que les flux)."""
    return spf.groupby(level="code_ins").diff().groupby(level="code_ins").shift(-1)


def sorties_retenues(rang: pd.Series, artif: list, non_artif: list, seuil: float) -> tuple[pd.Series, list, float]:
    """Natures artificialisées qui perdent au moins le seuil, tant qu'une seule nature peut en recevoir l'essentiel.

    Retourne les gains des natures non artificialisées, les sorties retenues [(nature, variation)] et leur somme (positive).
    """
    gains = rang[non_artif]
    plafond = gains.max() / RECLASS_COUVERTURE
    pertes = rang[artif][rang[artif] <= -seuil].sort_values()
    retenues, somme = [], 0.0
    for nature, valeur in pertes.items():
        if somme - valeur <= plafond:
            retenues.append((nature, valeur))
            somme -= valeur
    return gains, retenues, somme


def reclassements(spf: pd.DataFrame, flux: pd.DataFrame, table: pd.DataFrame) -> dict[tuple[int, int], dict]:
    """Repère les années où une sortie de la catégorie artificialisée a une contrepartie exacte au cadastre.

    Signature retenue : une ou plusieurs natures artificialisées perdent chacune au moins 10 ha, une seule nature
    non artificialisée gagne au moins 90 % de cette perte, et retirer cette perte réduit au moins de moitié l'écart
    à la médiane de la commune. Les entrées ne sont pas traitées : elles ne se distinguent pas d'un vrai chantier.
    """
    artif, non_artif = natures_artificialisees(table, spf.columns)
    delta = variations_natures(spf)
    mediane = flux.median(axis=1)
    candidats = delta[delta[artif].min(axis=1) <= -RECLASS_SORTIE_MIN_HA]
    trouves = {}
    for (code, an), rang in candidats.iterrows():
        if an not in flux.columns:
            continue
        gains, retenues, somme = sorties_retenues(rang, artif, non_artif, RECLASS_SORTIE_MIN_HA)
        if not retenues:
            continue
        contrepartie = gains[gains >= RECLASS_COUVERTURE * somme].idxmin()
        brut = float(flux.loc[code, an])
        corrige = brut + somme
        if abs(corrige - mediane[code]) > RECLASS_RETOUR * abs(brut - mediane[code]):
            continue
        trouves[(int(code), int(an))] = {
            "annee": int(an), "flux": round(brut, PRECISION_HA), "corrige": round(corrige, PRECISION_HA),
            "sorties": [{"nature": table.loc[n, "libelle"], "ha": round(float(v), PRECISION_HA)} for n, v in retenues],
            "contrepartie": {"nature": table.loc[contrepartie, "libelle"], "ha": round(float(gains[contrepartie]), PRECISION_HA)},
        }
    return trouves


def essai_seuil_reclassement(spf: pd.DataFrame, flux: pd.DataFrame, table: pd.DataFrame, seuil: float) -> dict:
    """Pour la page Méthode : parmi les années qui remplissent les deux premières conditions avec ce seuil de perte,
    combien se rapprochent de la médiane communale une fois la perte retirée ?"""
    artif, non_artif = natures_artificialisees(table, spf.columns)
    delta = variations_natures(spf)
    mediane = flux.median(axis=1)
    oui = total = 0
    for (code, an), rang in delta[delta[artif].min(axis=1) <= -seuil].iterrows():
        if an not in flux.columns:
            continue
        _, retenues, somme = sorties_retenues(rang, artif, non_artif, seuil)
        if retenues:
            brut = float(flux.loc[code, an])
            total += 1
            oui += abs(brut + somme - mediane[code]) < abs(brut - mediane[code])
    return {"ha": seuil, "oui": int(oui), "total": total}


# --- Signalements ----------------------------------------------------------------
def verifications(flux: pd.DataFrame, reclass: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classe chaque année communale (« reclassement », « negatif », « saut » ou vide) et calcule le flux corrigé.

    Un reclassement probable est retiré du flux. Un solde très négatif ou un saut, sans cause identifiée, est
    remplacé par la médiane de la commune. Médiane et écart absolu médian sont calculés sans les années déjà
    expliquées : sinon une commune aux reclassements répétés relève elle-même son seuil et ne signale plus rien.
    """
    types = pd.DataFrame("", index=flux.index, columns=flux.columns, dtype=object)
    corrige = flux.copy()
    for (code, an), r in reclass.items():
        types.loc[code, an] = "reclassement"
        corrige.loc[code, an] = r["corrige"]
    negatif = corrige.le(SOLDE_NEGATIF_HA) & types.eq("")
    types = types.mask(negatif, "negatif")
    sains = corrige.mask(types.ne(""))
    med = sains.median(axis=1)
    mad = sains.sub(med, axis=0).abs().median(axis=1)
    seuil = (SAUT_K_MAD * mad).clip(lower=SAUT_SEUIL_MIN_HA)
    types = types.mask(corrige.sub(med, axis=0).abs().gt(seuil, axis=0) & types.eq(""), "saut")
    remplace = pd.concat([med] * len(flux.columns), axis=1, keys=flux.columns)
    return types, corrige.mask(types.isin(["negatif", "saut"]), remplace)


def sens_rythme(recent: float, passe: float) -> str:
    """« comparable », « plus rapide » ou « plus lent » : le constat de la fiche communale."""
    d = recent - passe
    if abs(d) < ECART_RYTHME_ABSOLU_HA or abs(d) < ECART_RYTHME_RELATIF * abs(passe):
        return "comparable"
    return "plus rapide" if d > 0 else "plus lent"


# --- Trajectoire du SDT et bassins -------------------------------------------------
def part_trajectoire(an: int) -> float:
    """Part de la référence que la trajectoire prévoit l'année `an` : 1 en 2021, 0 en 2050, linéaire entre les deux."""
    return max((TRAJ_END - an) / (TRAJ_END - TRAJ_START), 0.0)


def statut_bassin(ratio: float) -> str:
    """Situation du bassin d'après la seule lecture retenue, le cumul des années définitives."""
    if ratio > 1 + ECART_PROCHE:
        return "au-dessus"
    if ratio < 1 - ECART_PROCHE:
        return "en-dessous"
    return "proche"


def commune_marquante(flux: pd.DataFrame, an: int) -> dict:
    """La commune qui pèse le plus sur le flux de l'année, pour pouvoir expliquer un chiffre surprenant."""
    code = flux[an].abs().idxmax()
    return {"code": int(code), "valeur": round(float(flux.loc[code, an]), PRECISION_HA), "annee": an}


def bilan_bassin(nom: str, cle: str, ref: float, incertitude: float, flux: pd.DataFrame, flux_n: pd.DataFrame) -> dict:
    """Cumul observé et cumul prévu par la trajectoire depuis 2021, pour les communes d'un bassin.

    `flux` et `flux_n` (flux corrigé) : une ligne par commune du bassin, une colonne par année.
    Le ratio retenu (« confirme ») compte les années définitives ; les autres sont des variantes pour la Méthode.
    """
    annees_flux = list(flux.columns)
    total = flux.sum(axis=0)
    total_n = flux_n.sum(axis=0)
    der = annees_flux[-1]
    a_avant = [a for a in annees_flux if TRAJ_START <= a < der]
    a_tout = a_avant + [der]

    def cumul(s, ans):
        return float(s[ans].sum())

    def prevu(r, ans):
        return float(sum(r * part_trajectoire(a) for a in ans))

    ref_propre = float(total[list(range(REFERENCE_COMMUNE[0], REFERENCE_COMMUNE[1] + 1))].mean())
    ratios = {
        "confirme": cumul(total, a_avant) / prevu(ref, a_avant),
        "avec_provisoire": cumul(total, a_tout) / prevu(ref, a_tout),
        "sans_saut": cumul(total_n, a_tout) / prevu(ref, a_tout),
        "reference_recalculee": cumul(total, a_tout) / prevu(ref_propre, a_tout),
    }
    # Les noms « cumul_autorise » et « plafond » sont ceux du format des données, lu par app.js. Le site, lui,
    # parle de ce que « la trajectoire prévoyait » : le SDT est indicatif.
    return {
        "cle": cle, "nom": nom, "reference": ref, "reference_recalculee": round(ref_propre, PRECISION_HA),
        "incertitude": incertitude, "flux": [round(float(total[a]), PRECISION_HA) for a in annees_flux],
        "flux_sans_saut": [round(float(total_n[a]), PRECISION_HA) for a in annees_flux],
        "cumul_observe": round(cumul(total, a_tout), PRECISION_HA), "cumul_autorise": round(prevu(ref, a_tout), PRECISION_HA),
        "cumul_observe_confirme": round(cumul(total, a_avant), PRECISION_HA), "cumul_autorise_confirme": round(prevu(ref, a_avant), PRECISION_HA),
        "ratios": {k: round(v, PRECISION_PARTS) for k, v in ratios.items()},
        "ratio": round(ratios["confirme"], PRECISION_PARTS),
        "statut": statut_bassin(ratios["confirme"]),
        "plafond_derniere_annee": round(ref * part_trajectoire(der), PRECISION_HA),
        "marquante": commune_marquante(flux, der),
    }
