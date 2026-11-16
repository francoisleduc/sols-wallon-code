"""Construction des données du portail, des sources aux fichiers de portail/data/.

Sources :
- SPF Finances, « Occupation du sol », fichiers communaux (CC BY 4.0) ;
- IWEPS, API ouverte, indicateurs 215700_0 à 215700_16 (CC0) ;
- Statbel, superficies communales, population au 1er janvier et limites des secteurs statistiques (CC BY 4.0) ;
- SDT 2024, références par bassin lues sur les graphiques.

Étapes : `calcule()` lit les sources et fait les calculs, `construit()` assemble les fiches communales, les bassins
et les chiffres de la page Méthode, puis écrit le tout. La table nature -> catégorie est déduite des données (voir
references/test_spf_iweps/README.md) : une nature absente de la table arrête la chaîne.
"""
import re
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import pandas as pd

from ..config import SAUT_K_MAD, SAUT_SEUIL_MIN_HA, TRAJ_END, TRAJ_START
from . import acquisition, calculs, export, textes
from .carte import voisins_et_chemins
from .nombres import arrondi
from .parametres import (ARTIF, CATEGORIES, ECART_PROCHE, EXEMPLE_COMMUNE, IWEPS_ORDRE, NATURE_TERRAIN, NON_ARTIF,
                         PRECISION_HA, PRECISION_PARTS, RECLASS_COUVERTURE, RECLASS_RETOUR, RECLASS_SEUILS_TESTES,
                         RECLASS_SORTIE_MIN_HA, REFERENCE_COMMUNE, SOLDE_NEGATIF_HA)


@dataclass
class Donnees:
    """Tout ce que les calculs produisent, avant mise en forme pour le site."""
    communes: pd.DataFrame     # référence des 261 communes, indexée par code INS
    table: pd.DataFrame        # nature -> catégorie
    annees: list[int]          # années de stock (1er janvier)
    spf: pd.DataFrame          # ha par nature, index (commune, année)
    iw: pd.DataFrame           # parts IWEPS en %, index (commune, année)
    sup: pd.Series             # superficie en ha, index (commune, année)
    st: pd.DataFrame           # ha par catégorie, index (commune, année)
    flux: pd.DataFrame         # flux artificialisé, communes x années de flux
    reclass: dict              # {(commune, année): reclassement probable}
    types: pd.DataFrame        # signalement de chaque année communale
    flux_n: pd.DataFrame       # flux corrigé des signalements
    pop: pd.Series             # habitants au 1er janvier, index (commune, année)

    @property
    def annees_flux(self) -> list[int]:
        return list(self.flux.columns)

    @property
    def der(self) -> int:
        return self.annees[-1]

    @property
    def recent(self) -> list[int]:
        """Années comptées depuis le départ de la trajectoire ; la dernière est provisoire."""
        return [a for a in self.annees_flux if a >= TRAJ_START]

    @property
    def passe(self) -> list[int]:
        return list(range(REFERENCE_COMMUNE[0], REFERENCE_COMMUNE[1] + 1))

    @property
    def stock(self) -> pd.DataFrame:
        """Hectares artificialisés, années en lignes, communes en colonnes."""
        return self.st["artif"].unstack(0).sort_index()

    @cached_property
    def parts(self) -> pd.Series:
        """Part artificialisée (%) au dernier 1er janvier."""
        return (self.stock.loc[self.der] / self.sup.xs(self.der, level="annee") * 100).rename("part")

    @property
    def annees_iweps(self) -> list[int]:
        return sorted(self.iw.index.get_level_values(1).unique())


def calcule(refresh: bool = False, zips: Path | None = None) -> Donnees:
    communes = acquisition.communes()
    table = acquisition.table_natures()
    annees = acquisition.annees_spf(refresh, zips)
    spf = acquisition.charge_spf(annees, communes)
    iw = acquisition.charge_iweps(refresh)
    sup = acquisition.superficies(annees)
    st = calculs.stocks_categories(spf, sup, table)
    if st.index.get_level_values(0).nunique() != len(communes):
        raise ValueError("Le nombre de communes ne correspond pas à la liste de référence.")
    flux = calculs.flux_annuels(st["artif"].unstack(0).sort_index())
    reclass = calculs.reclassements(spf, flux, table)
    types, flux_n = calculs.verifications(flux, reclass)
    pop = acquisition.population(annees, refresh)
    return Donnees(communes, table, annees, spf, iw, sup, st, flux, reclass, types, flux_n, pop)


def _cle_bassin(nom: str) -> str:
    """« Liège 1 » -> « liege-1 » : identifiant des bassins dans les adresses du site."""
    ascii_ = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")


def _fiche(code: int, d: Donnees, stats: dict, medianes: pd.Series, flux_bassin_recent: pd.Series, voisins: dict) -> dict:
    """La fiche d'une commune, telle que la lit app.js."""
    rang = d.communes.loc[code]
    nom_bassin = rang["bassin"] if isinstance(rang["bassin"], str) else None
    s = d.st.xs(code, level="code_ins")
    a = d.sup.xs(code, level="code_ins")
    hausse = (s.loc[d.der] / a[d.der] - s.loc[d.annees[0]] / a[d.annees[0]]) * 100   # en points de pourcentage
    moteur = hausse[ARTIF].idxmax()
    an_iw = d.annees_iweps[-1]
    iw_c = d.iw.xs(code, level="code_ins") if code in d.iw.index.get_level_values(0) else None
    f = d.flux.loc[code]
    recent, passe = d.recent, d.passe
    c = {
        "code": int(code), "nom": rang["commune"], "province": rang["province"], "bassin": nom_bassin,
        "bassin_cle": _cle_bassin(nom_bassin) if nom_bassin else None,
        "superficie": arrondi(a[d.der]), "part": round(float(d.parts[code]), PRECISION_PARTS),
        "part_iweps": round(float(iw_c.loc[an_iw, "artif"]), 1) if iw_c is not None else None,
        "mediane_bassin": round(float(medianes[nom_bassin]), PRECISION_PARTS) if nom_bassin else None,
        "hausse_points": round(float(hausse["artif"]), PRECISION_PARTS), "moteur": [moteur, round(float(hausse[moteur]), PRECISION_PARTS)],
        "hausses": {k: round(float(hausse[k]), PRECISION_PARTS) for k in CATEGORIES},
        "rythme_recent": round(float(f[recent].mean()), PRECISION_PARTS), "rythme_passe": round(float(f[passe].mean()), PRECISION_PARTS),
        "rythme_recent_sans_saut": round(float(d.flux_n.loc[code, recent].mean()), PRECISION_PARTS),
        "rythme_passe_sans_saut": round(float(d.flux_n.loc[code, passe].mean()), PRECISION_PARTS),
        "sauts": [(int(y), round(float(f[y]), PRECISION_HA)) for y in d.annees_flux if d.types.loc[code, y] in ("negatif", "saut")],
        "reclassements": [d.reclass[(int(code), int(y))] for y in d.annees_flux if d.types.loc[code, y] == "reclassement"],
        "flux": [round(float(f[y]), PRECISION_HA) for y in d.annees_flux],
        "part_bassin_pct": round(float(f[recent].sum() / flux_bassin_recent[nom_bassin] * 100), PRECISION_PARTS)
        if nom_bassin and flux_bassin_recent[nom_bassin] > 0 else None,
        "voisins": [{"code": v, "nom": d.communes.loc[v, "commune"], "part": arrondi(d.parts[v])} for v in voisins.get(code, [])],
        "parts_estimees": {k: [round(float(s.loc[y, k] / a[y] * 100), PRECISION_PARTS) for y in d.annees] for k in CATEGORIES + ["artif"]},
        "parts_iweps": {k: [round(float(iw_c.loc[y, k]), 2) for y in d.annees_iweps] for k in IWEPS_ORDRE} if iw_c is not None else None,
        "ha_estimes": {k: round(float(s.loc[d.der, k]), PRECISION_HA) for k in CATEGORIES + ["artif"]},
        "reperes": calculs.reperes(d.st, d.pop, [code], d.annees),
    }
    c["phrases"] = textes.phrases(c, stats)
    return c


def _ligne_carte(c: dict, d: Donnees, chemin: str) -> dict:
    """Ce que la carte et le tableau des communes montrent d'une commune (dans index.json)."""
    f = d.flux.loc[c["code"]]
    return {
        "code": c["code"], "nom": c["nom"], "bassin": c["bassin"], "bassin_cle": c["bassin_cle"], "province": c["province"],
        "part": arrondi(d.parts[c["code"]]), "rythme": arrondi(f[d.recent].mean()), "ecart": arrondi(f[d.recent].mean() - f[d.passe].mean()),
        "signal": next(p["signal"] for p in c["phrases"] if p["regle"] == "rythme"),
        "saut": bool(c["sauts"] or c["reclassements"]), "chemin": chemin,
    }


def _bassins(d: Donnees, fiches: dict) -> tuple[list[dict], dict]:
    """Bilan de chaque bassin et de l'ensemble couvert par le SDT, avec la liste de leurs communes."""
    ref = acquisition.trajectoires(d.communes["bassin"].dropna().unique())
    bassins = []
    for nom in ref.index:
        membres = d.communes.index[d.communes["bassin"] == nom]
        b = calculs.bilan_bassin(nom, _cle_bassin(nom), float(ref.loc[nom, "artif_nette_moy_10ans_ha_an"]),
                                 float(ref.loc[nom, "incertitude_lecture_ha_an"]), d.flux.loc[membres], d.flux_n.loc[membres])
        b["reperes"] = calculs.reperes(d.st, d.pop, membres, d.annees)
        b["communes"] = sorted(
            ({"code": int(k), "nom": fiches[k]["nom"], "rythme": arrondi(d.flux.loc[k, d.recent].mean()), "cumul": arrondi(d.flux.loc[k, d.recent].sum()),
              "part": arrondi(d.parts[k]), "saut": bool(fiches[k]["sauts"] or fiches[k]["reclassements"])} for k in membres),
            key=lambda x: acquisition.norme(x["nom"]))
        bassins.append(b)
    bassins.sort(key=lambda b: b["nom"])
    couvertes = d.communes.index[d.communes["bassin"].notna()]
    wallonie = calculs.bilan_bassin("Wallonie, hors Communauté germanophone", "wallonie", float(ref["artif_nette_moy_10ans_ha_an"].sum()),
                                    float(ref["incertitude_lecture_ha_an"].sum()), d.flux.loc[couvertes], d.flux_n.loc[couvertes])
    return bassins, wallonie


def _exemple_methode(d: Donnees, fiches: dict, code: int = EXEMPLE_COMMUNE) -> dict:
    """Tous les chiffres de l'exemple de la page Méthode, pour qu'aucun ne soit écrit à la main."""
    der, avant = d.annees[-1], d.annees[-2]
    an_iw = d.annees_iweps[-1]
    surfaces = d.spf.loc[(code, der)].sort_values(ascending=False)
    mouvements = (d.spf.loc[(code, der)] - d.spf.loc[(code, avant)])
    mouvements = mouvements.reindex(mouvements.abs().sort_values(ascending=False).index)
    t = d.table

    def decrire(n):
        return {"nature": t.loc[n, "libelle"], "nature_en": textes.nature_en(t.loc[n, "libelle"]),
                "categorie": textes.LIBELLES[t.loc[n, "categorie"]], "categorie_en": textes.LIBELLES_EN[t.loc[n, "categorie"]],
                "artificialise": bool(t.loc[n, "categorie"] in ARTIF)}

    terrain = d.spf[NATURE_TERRAIN]
    return {
        "code": code, "nom": fiches[code]["nom"], "bassin": fiches[code]["bassin"], "bassin_cle": fiches[code]["bassin_cle"],
        "annee": der, "annee_avant": avant, "nb_natures": int((surfaces > 0).sum()),
        "premieres": [{**decrire(n), "ha": arrondi(v)} for n, v in surfaces.head(6).items()],
        "stock": arrondi(d.st.loc[(code, der), "artif"]), "stock_avant": arrondi(d.st.loc[(code, avant), "artif"]),
        "superficie": arrondi(d.sup.loc[(code, der)]), "part": fiches[code]["part"],
        "part_iweps": round(float(d.iw.loc[(code, an_iw), "artif"]), 1),
        "flux": round(float(d.flux.loc[code, avant]), PRECISION_HA), "flux_corrige": round(float(d.flux_n.loc[code, avant]), PRECISION_HA),
        "mediane": round(float(d.flux.loc[code].median()), PRECISION_HA),
        "mouvements": [{**decrire(n), "ha": round(float(v), PRECISION_HA), "avant": round(float(d.spf.loc[(code, avant), n]), PRECISION_HA),
                        "apres": round(float(d.spf.loc[(code, der), n]), PRECISION_HA)} for n, v in mouvements.head(5).items()],
        "terrain_gain_wallonie": round(float(terrain.xs(der, level="annee").sum() - terrain.xs(d.annees[0], level="annee").sum())),
        "rythme_recent": fiches[code]["rythme_recent"], "rythme_passe": fiches[code]["rythme_passe"],
        "rythme_recent_corrige": fiches[code]["rythme_recent_sans_saut"], "rythme_passe_corrige": fiches[code]["rythme_passe_sans_saut"],
    }


def _verifications(d: Donnees) -> dict:
    """Compte des signalements et seuils de la détection, cités sur la page Méthode."""
    types = d.types
    return {
        "reclassements": {"annees": len(d.reclass), "communes": len({k[0] for k in d.reclass})},
        "negatifs": {"annees": int(types.eq("negatif").sum().sum()), "communes": int(types.eq("negatif").any(axis=1).sum())},
        "sauts": {"annees": int(types.eq("saut").sum().sum()), "communes": int(types.eq("saut").any(axis=1).sum())},
        "couples": int(types.size),
        "seuils": {"sortie_ha": RECLASS_SORTIE_MIN_HA, "couverture_pct": round(RECLASS_COUVERTURE * 100), "retour_pct": round(RECLASS_RETOUR * 100),
                   "negatif_ha": SOLDE_NEGATIF_HA, "saut_ha": SAUT_SEUIL_MIN_HA, "saut_mad": SAUT_K_MAD},
        "test_seuil": [calculs.essai_seuil_reclassement(d.spf, d.flux, d.table, s) for s in RECLASS_SEUILS_TESTES],
    }


def construit(refresh: bool = False, zips: Path | None = None) -> dict:
    """Calcule et écrit toutes les données du site. Retourne aussi les tables intermédiaires, pour les contrôles."""
    d = calcule(refresh, zips)
    chemins, voisins, frontieres, vue = voisins_et_chemins(d.communes)
    stats = {
        "annee_stock": d.der, "annee_iweps": d.annees_iweps[-1], "premiere_annee": d.annees[0],
        "recent": [d.recent[0], d.recent[-1]], "passe": list(REFERENCE_COMMUNE),
        "mediane_wallonie": float(d.parts.median()),
    }
    medianes = d.parts.groupby(d.communes["bassin"]).median()
    flux_bassin_recent = d.flux[d.recent].sum(axis=1).groupby(d.communes["bassin"]).sum()

    fiches, lignes = {}, []
    for code in sorted(d.communes.index):
        fiches[code] = _fiche(code, d, stats, medianes, flux_bassin_recent, voisins)
        lignes.append(_ligne_carte(fiches[code], d, chemins[code]))
    bassins, wallonie = _bassins(d, fiches)

    sup_der = d.sup.xs(d.der, level="annee")
    region = {
        "flux": [round(float(d.flux[a].sum()), PRECISION_HA) for a in d.annees_flux],
        "stock": arrondi(d.stock.loc[d.der].sum(), 0), "superficie": arrondi(sup_der.sum(), 0),
        "part": arrondi(d.stock.loc[d.der].sum() / sup_der.sum() * 100),
        "reperes": calculs.reperes(d.st, d.pop, list(d.communes.index), d.annees),
    }
    meta = {
        "annees_stock": d.annees, "annees_flux": d.annees_flux, "annees_iweps": d.annees_iweps,
        "derniere_annee_flux": d.annees_flux[-1], "stats": stats, "libelles": textes.LIBELLES, "libelles_en": textes.LIBELLES_EN,
        "artif": ARTIF, "non_artif": NON_ARTIF, "vue": vue, "frontieres_bassins": frontieres, "region": region,
        "trajectoire_debut": TRAJ_START, "trajectoire_fin": TRAJ_END, "ecart_proche_pct": round(ECART_PROCHE * 100),
        "verifications": _verifications(d),
        "exemple": _exemple_methode(d, fiches),
        "etalement": export.resume_etalement(),
    }

    export.ecrit_site({"meta": meta, "communes": lignes, "bassins": bassins, "wallonie": wallonie}, fiches)
    export.ecrit_telechargements(d.st, d.flux, d.flux_n, d.types, d.reclass, d.communes, bassins + [wallonie], d.pop)
    return {"meta": meta, "fiches": fiches, "bassins": bassins, "wallonie": wallonie, "st": d.st, "iw": d.iw,
            "flux": d.flux, "flux_n": d.flux_n, "types": d.types, "reclass": d.reclass}
