"""Données du portail : stocks et flux par commune et par bassin, à partir des natures du SPF Finances.

Sources :
- SPF Finances, « Occupation du sol », fichiers communaux (CC BY 4.0) ;
- IWEPS, API ouverte, indicateurs 215700_0 à 215700_16 (CC0) ;
- Statbel, superficies communales et limites des secteurs statistiques (CC BY 4.0) ;
- SDT 2024, références par bassin lues sur les graphiques.

La table nature -> catégorie est déduite des données (voir references/test_spf_iweps/README.md).
Une nature absente de la table arrête la chaîne : il faut la classer avant de publier une nouvelle année.
"""
import csv
import gzip
import io
import json
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request
import zipfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

from .config import PROCESSED, RAW, REFERENCES, ROOT, SAUT_K_MAD, SAUT_SEUIL_MIN_HA, TRAJ_END, TRAJ_START
from .sources import USER_AGENT, fetch, record

SITE = ROOT / "portail"
SITE_DATA = SITE / "data"
TABLE_NATURES = REFERENCES / "test_spf_iweps" / "table_natures_categories.csv"
GEOMETRIE = REFERENCES / "geo" / "communes_wallonie.topojson"

SPF_URL = ("https://opendata.fin.belgium.be/download/datasets/"
           "86999d70-51ca-11eb-9238-3448ed25ad7c_{an}0101_csv_NA_01000.zip")
IWEPS_URL = "https://opendata.iweps.be/api/data/csv/215700_{i}/com+period=all"
SPF_PREMIERE_ANNEE = 2011
FUSIONS = {"BERTOGNE": 82039}          # commune fusionnée, absente de la liste actuelle
NATURE_TERRAIN = 70                    # « Terrain » : classée non artificialisée, la page Méthode explique pourquoi
EXEMPLE_COMMUNE = 62118                # Grâce-Hollogne : l'exemple de la page Méthode, choisi pour son reclassement de 2025

REFERENCE_COMMUNE = (2011, 2019)       # rythme passé d'une commune : le SPF commence en 2011
ECART_RYTHME_RELATIF = 0.15            # sous ce seuil, ou sous 0,5 ha/an, deux rythmes sont « comparables »
ECART_RYTHME_ABSOLU_HA = 0.5
ECART_PART_POINTS = 1.0                # sous ce seuil, une commune est « proche » de la médiane

RECLASS_SORTIE_MIN_HA = 10.0           # une nature artificialisée qui perd au moins cette surface en un an
RECLASS_COUVERTURE = 0.9               # une nature non artificialisée doit gagner au moins cette part de la perte
RECLASS_RETOUR = 0.5                   # la correction doit réduire au moins de moitié l'écart à la médiane communale
SOLDE_NEGATIF_HA = -10.0               # un solde plus négatif ne peut pas venir de constructions
RECLASS_SEUILS_TESTES = (5.0, 10.0)    # seuils comparés sur la page Méthode
ECART_PROCHE = 0.05                    # à moins de 5 % de la trajectoire, un bassin est dit « proche » de sa trajectoire

PRECISION_PARTS = 6                    # décimales gardées dans les données : l'arrondi se fait une seule fois, à l'affichage
PRECISION_HA = 4                       # le cadastre est en m², soit quatre décimales en hectares

ARTIF = ["resid", "comm", "equip", "loisirs", "agri_bat", "indus", "carrieres", "transport", "autres_art"]
NON_ARTIF = ["arable", "herbe", "foret", "seminat", "humide", "eau", "inconnu"]
CATEGORIES = ARTIF + NON_ARTIF
IWEPS_ORDRE = ["artif"] + CATEGORIES   # ordre des indicateurs 215700_0 à 215700_16
LIBELLES = {
    "artif": "Terrains artificialisés",
    "resid": "Résidentiel",
    "comm": "Commerces, bureaux et services",
    "equip": "Services publics et équipements",
    "loisirs": "Loisirs et espaces verts urbains",
    "agri_bat": "Bâtiments agricoles",
    "indus": "Industrie et artisanat",
    "carrieres": "Carrières, décharges et espaces abandonnés",
    "transport": "Infrastructures de transport",
    "autres_art": "Autres espaces artificialisés",
    "arable": "Terres arables et cultures permanentes",
    "herbe": "Surfaces enherbées et friches agricoles",
    "foret": "Forêts",
    "seminat": "Milieux semi-naturels",
    "humide": "Zones humides",
    "eau": "Surfaces en eau",
    "inconnu": "Nature inconnue, dont non cadastré",
}
PHRASE_CATEGORIE = {
    "resid": "le résidentiel",
    "comm": "les commerces, bureaux et services",
    "equip": "les services publics et équipements",
    "loisirs": "les loisirs et espaces verts urbains",
    "agri_bat": "les bâtiments agricoles",
    "indus": "l'industrie et l'artisanat",
    "carrieres": "les carrières, décharges et espaces abandonnés",
    "transport": "les infrastructures de transport",
    "autres_art": "les autres espaces artificialisés",
}


# Version anglaise. Aucun libellé anglais officiel n'existe pour le cadastre belge : ces traductions sont les nôtres.
LIBELLES_EN = {
    "artif": "Artificialised land",
    "resid": "Residential",
    "comm": "Shops, offices and services",
    "equip": "Public services and facilities",
    "loisirs": "Leisure and urban green space",
    "agri_bat": "Farm buildings",
    "indus": "Industry and crafts",
    "carrieres": "Quarries, landfills and derelict land",
    "transport": "Transport infrastructure",
    "autres_art": "Other artificialised land",
    "arable": "Arable land and permanent crops",
    "herbe": "Grassland and agricultural fallow",
    "foret": "Forests",
    "seminat": "Semi-natural areas",
    "humide": "Wetlands",
    "eau": "Water bodies",
    "inconnu": "Unknown class, including uncadastred land",
}
PHRASE_CATEGORIE_EN = {
    "resid": "residential land",
    "comm": "shops, offices and services",
    "equip": "public services and facilities",
    "loisirs": "leisure and urban green space",
    "agri_bat": "farm buildings",
    "indus": "industry and crafts",
    "carrieres": "quarries, landfills and derelict land",
    "transport": "transport infrastructure",
    "autres_art": "other artificialised land",
}
# Seules les natures citées sur le portail sont traduites. _nature_en signale tout oubli à la génération.
NATURES_EN = {
    "Aéroport": "Airport",
    "Bois": "Woodland",
    "Bâtiment industriel": "Industrial building",
    "Bâtiment militaire": "Military building",
    "Carrière": "Quarry",
    "Champ d’aviation": "Airfield",
    "Charbonnage": "Coal mine",
    "Chemin cadastré": "Cadastred path",
    "Cimenterie": "Cement works",
    "Entrepôt": "Warehouse",
    "Installation sportive": "Sports facility",
    "Maison": "House",
    "Matériel et outillage bâti": "Built plant and equipment",
    "Parking": "Car park",
    "Pré": "Meadow",
    "Pâture": "Pasture",
    "Salle d’exposition": "Exhibition hall",
    "Superficie et parties communes": "Surface and common parts",
    "Terrain": "Land plot",
    "Terrain d’épandage exploite": "Spreading field, in use",
    "Terrain d’épandage vain ou vague": "Spreading field, waste or vacant",
    "Terrain industriel": "Industrial land",
    "Terrain militaire": "Military land",
    "Terrain vain ou vague": "Waste or vacant land",
    "Terrain à bâtir": "Building plot",
    "Terre agricole": "Farmland",
    "Terril exploite": "Slag heap, in use",
    "Terril vain ou vague": "Slag heap, waste or vacant",
    "Verger haute tige": "High-stem orchard",
}


def _nature_en(libelle: str) -> str:
    if libelle not in NATURES_EN:
        raise ValueError(f"Nature sans traduction anglaise : {libelle}. Ajoutez-la à NATURES_EN.")
    return NATURES_EN[libelle]


def _norme(texte: str) -> str:
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z]", "", t)


def arrondi(valeur: float, decimales: int = 1) -> float:
    """Arrondit une demie en s'éloignant de zéro, comme le navigateur : phrases et tuiles donnent ainsi le même chiffre."""
    propre = Decimal(repr(round(float(valeur), 8)))  # retire le bruit des calculs en virgule flottante
    return float(propre.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)) + 0.0


def _nombre(valeur: float, decimales: int = 1) -> str:
    """Écrit un nombre à la française, avec le signe moins typographique."""
    return f"{arrondi(valeur, decimales):.{decimales}f}".replace(".", ",").replace("-", "−")


def _ha(valeur: float) -> str:
    """Arrondit des hectares selon leur ordre de grandeur."""
    return _nombre(valeur, 1 if abs(valeur) < 100 else 0)


def _points(valeur: float) -> str:
    """« 0,7 point », « 2,5 points » : le pluriel français commence à 2."""
    return f"{_nombre(valeur)} point" + ("s" if abs(arrondi(valeur)) >= 2 else "")


def _s(valeur: float, decimales: int = 1) -> str:
    return ("+" if valeur >= 0 else "") + _nombre(valeur, decimales)


# --- Acquisition ------------------------------------------------------------
def _spf_vers_cache(an: int, dest: Path, zips: Path | None) -> bool:
    """Extrait le fichier communal wallon d'une archive SPF. Retourne False si l'année n'existe pas."""
    local = zips / f"{an}.zip" if zips else None
    url = SPF_URL.format(an=an)
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "spf.zip"
        if local and local.exists():
            chemin = local
        else:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=600) as r, open(chemin, "wb") as f:
                    while bloc := r.read(1 << 20):
                        f.write(bloc)
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    return False
                raise
        with zipfile.ZipFile(chemin) as z:
            nom = next(n for n in z.namelist() if "municipality" in n.lower() and n.lower().endswith(".csv"))
            with z.open(nom) as h:
                lignes = io.TextIOWrapper(h, encoding="utf-8-sig")
                lecteur = csv.DictReader(lignes, delimiter=";")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(dest, "wt", encoding="utf-8", newline="") as sortie:
                    ecr = csv.writer(sortie)
                    ecr.writerow(["nis", "nom", "nature", "m2"])
                    for l in lecteur:
                        nis = int(l["NISCode"])
                        wallon = 25000 <= nis < 30000 or 50000 <= nis < 70000 or nis >= 80000
                        if wallon and l["ParcelNature"].isdigit():
                            ecr.writerow([nis, l["NameFre"], l["ParcelNature"], l["TotalParcelsArea"]])
    record(dest, url, "lignes wallonnes du fichier communal, natures numériques seulement")
    return True


def annees_spf(refresh: bool = False, zips: Path | None = None) -> list[int]:
    """Met le cache à jour et cherche l'année suivante : c'est ainsi qu'un nouveau millésime entre."""
    annees, an = [], SPF_PREMIERE_ANNEE
    while True:
        dest = RAW / "spf_occupation_sol" / f"communes_{an}.csv.gz"
        if dest.exists() and not (refresh and an == max(annees, default=an)):
            annees.append(an)
        elif _spf_vers_cache(an, dest, zips):
            annees.append(an)
        else:
            return annees
        an += 1


def charge_spf(annees: list[int], communes: pd.DataFrame) -> pd.DataFrame:
    """Surfaces en hectares, indexées par (commune actuelle, année), une colonne par nature."""
    correspondance = {_norme(n): c for c, n in communes["commune"].items()} | FUSIONS
    morceaux = []
    for an in annees:
        d = pd.read_csv(RAW / "spf_occupation_sol" / f"communes_{an}.csv.gz")
        d["code_ins"] = d["nom"].map(lambda n: correspondance.get(_norme(n)))
        if d["code_ins"].isna().any():
            raise ValueError(f"{an} : communes inconnues {sorted(d.loc[d.code_ins.isna(), 'nom'].unique())}")
        d["annee"] = an
        morceaux.append(d)
    d = pd.concat(morceaux)
    d["code_ins"] = d["code_ins"].astype(int)
    return d.pivot_table(index=["code_ins", "annee"], columns="nature", values="m2", aggfunc="sum", fill_value=0) / 1e4


def charge_iweps(refresh: bool = False) -> pd.DataFrame:
    """Parts en %, indexées par (commune, année), une colonne par indicateur."""
    morceaux = []
    for i, cle in enumerate(IWEPS_ORDRE):
        f = fetch(IWEPS_URL.format(i=i), RAW / "iweps_api" / f"215700_{i}.csv", refresh, f"indicateur {cle}, CC0")
        d = pd.read_csv(f, skiprows=1, header=None, names=["code_ins", "type", "entite", "periode", "valeur"])
        d["annee"] = d["periode"].str[-4:].astype(int)
        d["cat"] = cle
        morceaux.append(d[["code_ins", "annee", "cat", "valeur"]])
    d = pd.concat(morceaux)
    d = d[~d["code_ins"].isin([82003, 82005])]  # Bastogne et Bertogne avant fusion : 82039 les remplace
    return d.pivot_table(index=["code_ins", "annee"], columns="cat", values="valeur")


# --- Calculs ----------------------------------------------------------------
def stocks_categories(spf: pd.DataFrame, superficies: pd.DataFrame) -> pd.DataFrame:
    table = pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").set_index("nature")["categorie"]
    inconnues = sorted(set(spf.columns) - set(table.index))
    if inconnues:
        raise ValueError(f"Natures absentes de {TABLE_NATURES.name} : {inconnues}. Classez-les avant de continuer.")
    res = spf.T.groupby(table.reindex(spf.columns)).sum().T.reindex(columns=CATEGORIES, fill_value=0.0)
    non_cadastre = (superficies.reindex(res.index) - spf.sum(axis=1)).clip(lower=0)
    res["inconnu"] += non_cadastre
    res["artif"] = res[ARTIF].sum(axis=1)
    return res


def superficies(annees: list[int]) -> pd.Series:
    """Superficie de chaque commune chaque année, prolongée avec la dernière valeur connue."""
    s = pd.read_csv(PROCESSED / "artif_communes_stock_annuel.csv")
    t = s.pivot_table(index="code_ins", columns="annee_stock_1er_janvier", values="superficie_ha")
    t = t.reindex(columns=sorted(set(t.columns) | set(annees))).ffill(axis=1)[annees]
    return t.stack().rename_axis(["code_ins", "annee"])


def _variations_natures(spf: pd.DataFrame) -> pd.DataFrame:
    """Variation de chaque nature entre l'année N et l'année N+1, rangée sous l'année N."""
    return spf.groupby(level="code_ins").diff().groupby(level="code_ins").shift(-1)


def _sorties_retenues(rang: pd.Series, artif: list, non_artif: list, seuil: float) -> tuple[pd.Series, list, float]:
    """Natures artificialisées qui perdent au moins le seuil, tant qu'une seule nature peut en recevoir l'essentiel."""
    gains = rang[non_artif]
    plafond = gains.max() / RECLASS_COUVERTURE
    pertes = rang[artif][rang[artif] <= -seuil].sort_values()
    retenues, somme = [], 0.0
    for nature, valeur in pertes.items():
        if somme - valeur <= plafond:
            retenues.append((nature, valeur))
            somme -= valeur
    return gains, retenues, somme


def test_seuil_reclassement(spf: pd.DataFrame, flux: pd.DataFrame, seuil: float) -> dict:
    """Parmi les années qui remplissent les deux premières conditions, combien se rapprochent de la médiane sans la perte ?"""
    categories = pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").set_index("nature")
    artif = [n for n in spf.columns if categories.loc[n, "categorie"] in ARTIF]
    non_artif = [n for n in spf.columns if n not in artif]
    delta = _variations_natures(spf)
    mediane = flux.median(axis=1)
    oui = total = 0
    for (code, an), rang in delta[delta[artif].min(axis=1) <= -seuil].iterrows():
        if an not in flux.columns:
            continue
        _, retenues, somme = _sorties_retenues(rang, artif, non_artif, seuil)
        if retenues:
            brut = float(flux.loc[code, an])
            total += 1
            oui += abs(brut + somme - mediane[code]) < abs(brut - mediane[code])
    return {"ha": seuil, "oui": int(oui), "total": total}


def reclassements(spf: pd.DataFrame, flux: pd.DataFrame) -> dict[tuple[int, int], dict]:
    """Repère les années où une sortie de la catégorie artificialisée a une contrepartie exacte au cadastre.

    Signature retenue : une ou plusieurs natures artificialisées perdent chacune au moins 10 ha, une seule nature
    non artificialisée gagne au moins 90 % de cette perte, et retirer cette perte réduit au moins de moitié l'écart
    à la médiane de la commune. Les entrées ne sont pas traitées : elles ne se distinguent pas d'un vrai chantier.
    """
    categories = pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").set_index("nature")
    artif = [n for n in spf.columns if categories.loc[n, "categorie"] in ARTIF]
    non_artif = [n for n in spf.columns if n not in artif]
    delta = _variations_natures(spf)
    mediane = flux.median(axis=1)
    candidats = delta[delta[artif].min(axis=1) <= -RECLASS_SORTIE_MIN_HA]
    trouves = {}
    for (code, an), rang in candidats.iterrows():
        if an not in flux.columns:
            continue
        gains, retenues, somme = _sorties_retenues(rang, artif, non_artif, RECLASS_SORTIE_MIN_HA)
        if not retenues:
            continue
        contrepartie = gains[gains >= RECLASS_COUVERTURE * somme].idxmin()
        brut = float(flux.loc[code, an])
        corrige = brut + somme
        if abs(corrige - mediane[code]) > RECLASS_RETOUR * abs(brut - mediane[code]):
            continue
        trouves[(int(code), int(an))] = {
            "annee": int(an), "flux": round(brut, PRECISION_HA), "corrige": round(corrige, PRECISION_HA),
            "sorties": [{"nature": categories.loc[n, "libelle"], "ha": round(float(v), PRECISION_HA)} for n, v in retenues],
            "contrepartie": {"nature": categories.loc[contrepartie, "libelle"], "ha": round(float(gains[contrepartie]), PRECISION_HA)},
        }
    return trouves


def verifications(flux: pd.DataFrame, reclass: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classe chaque année communale et calcule le flux corrigé.

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


def part_trajectoire(an: int) -> float:
    return max((TRAJ_END - an) / (TRAJ_END - TRAJ_START), 0.0)


def _voisins_et_chemins(communes: pd.DataFrame) -> tuple[dict, dict, str, list]:
    """Chemins SVG en Lambert 72, voisins par arcs partagés et frontières entre bassins."""
    topo = json.loads(GEOMETRIE.read_text(encoding="utf-8"))
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x, y, pts = 0, 0, []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    tous = [p for a in arcs for p in a]
    xmin, xmax = min(p[0] for p in tous), max(p[0] for p in tous)
    ymin, ymax = min(p[1] for p in tous), max(p[1] for p in tous)
    echelle = 1000 / (xmax - xmin)
    vue = {"largeur": 1000, "hauteur": round((ymax - ymin) * echelle), "lambert_xmin": xmin, "lambert_ymax": ymax, "metres_par_unite": 1 / echelle}

    def svg(p):
        return f"{(p[0] - xmin) * echelle:.1f} {(ymax - p[1]) * echelle:.1f}"

    def anneau(indices):
        pts = []
        for i in indices:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(a if not pts else a[1:])
        return "M" + "L".join(svg(p) for p in pts) + "Z"

    chemins, par_arc = {}, {}
    for g in next(iter(topo["objects"].values()))["geometries"]:
        code = int(g["properties"]["cd_munty_refnis"])
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        chemins[code] = "".join(anneau(r) for p in polys for r in p)
        for p in polys:
            for r in p:
                for i in r:
                    par_arc.setdefault(i if i >= 0 else ~i, set()).add(code)
    voisins = {c: set() for c in chemins}
    frontieres = []
    bassin = communes["bassin"].to_dict()
    for i, codes in par_arc.items():
        if len(codes) == 2:
            a, b = sorted(codes)
            voisins[a].add(b)
            voisins[b].add(a)
            if bassin.get(a) != bassin.get(b):
                frontieres.append("M" + "L".join(svg(p) for p in arcs[i]))
    return chemins, {c: sorted(v) for c, v in voisins.items()}, "".join(frontieres), vue


def _phrases(c: dict, stats: dict) -> list[dict]:
    """Règles d'interprétation de la fiche communale. Elles sont décrites sur la page Méthode."""
    out = []
    der = stats["annee_stock"]
    part = c["part"]
    txt = f"{_nombre(part)} % du territoire est artificialisé au 1er janvier {der}."
    if c["part_iweps"] is not None:
        txt += f" L'IWEPS indiquait {_nombre(c['part_iweps'])} % au 1er janvier {stats['annee_iweps']}."
    out.append({"regle": "part", "texte": txt})

    med, lieu = (c["mediane_bassin"], "de son bassin") if c["bassin"] else (stats["mediane_wallonie"], "wallonne")
    ecart = part - med
    if abs(ecart) < ECART_PART_POINTS:
        txt = f"C'est proche de la médiane {lieu} ({_nombre(med)} %)."
    elif ecart > 0:
        txt = f"C'est plus que la médiane {lieu} ({_nombre(med)} %)."
    else:
        txt = f"C'est moins que la médiane {lieu} ({_nombre(med)} %)."
    out.append({"regle": "comparaison", "texte": txt})

    h = c["hausse_points"]
    a0, a1 = stats["premiere_annee"], der
    if abs(h) < 0.1:
        out.append({"regle": "composition", "texte": f"Cette part n'a presque pas bougé depuis {a0}."})
    elif h < 0:
        out.append({"regle": "composition", "texte": f"Cette part a reculé de {_points(-h)} depuis {a0}, "
                    "ce qui traduit souvent des reclassements au cadastre."})
    else:
        cat, val = c["moteur"]
        if arrondi(val) > arrondi(h):
            out.append({"regle": "composition", "texte": f"Depuis {a0}, cette part a gagné {_points(h)}. "
                        f"Pour {PHRASE_CATEGORIE[cat]}, la hausse atteint {_points(val)}, car d'autres catégories ont reculé."})
        elif val >= 0.5 * h:
            out.append({"regle": "composition", "texte": f"Depuis {a0}, cette part a gagné {_points(h)}, "
                        f"dont {_nombre(val)} pour {PHRASE_CATEGORIE[cat]}."})
        else:
            out.append({"regle": "composition", "texte": f"Depuis {a0}, cette part a gagné {_points(h)}. "
                        f"Aucune catégorie n'en explique seule la majorité : {PHRASE_CATEGORIE[cat]} y pèse le plus "
                        f"({_points(val)})."})

    r, p = c["rythme_recent"], c["rythme_passe"]
    rn, pn = c["rythme_recent_sans_saut"], c["rythme_passe_sans_saut"]
    periodes = f"{stats['recent'][0]}-{stats['recent'][1]}"
    passe = f"{REFERENCE_COMMUNE[0]}-{REFERENCE_COMMUNE[1]}"

    def sens(a, b):
        d = a - b
        if abs(d) < ECART_RYTHME_ABSOLU_HA or abs(d) < ECART_RYTHME_RELATIF * abs(b):
            return "comparable"
        return "plus rapide" if d > 0 else "plus lent"

    s1, s2 = sens(r, p), sens(rn, pn)
    base = f"Le rythme récent est de {_ha(r)} ha/an ({periodes}), contre {_ha(p)} ha/an en {passe}"
    corrige = abs(rn - r) >= ECART_RYTHME_ABSOLU_HA or abs(pn - p) >= ECART_RYTHME_ABSOLU_HA
    hors = f" Sans les variations signalées, on passe à {_ha(rn)} contre {_ha(pn)} ha/an." if corrige else ""
    if s1 != s2:
        txt = (f"{base}. Il est difficile à juger : sans les variations signalées, on passe à {_ha(rn)} contre "
               f"{_ha(pn)} ha/an, et le constat change.")
    elif s1 == "comparable":
        txt = f"{base} : il reste comparable.{hors}"
    elif s1 == "plus rapide":
        txt = f"{base} : la commune artificialise plus vite qu'avant.{hors}"
    else:
        txt = f"{base} : la commune artificialise moins vite qu'avant.{hors}"
    out.append({"regle": "rythme", "texte": txt, "signal": s1 if s1 == s2 else "incertain"})

    if r < 0 and rn >= 0:
        out.append({"regle": "solde", "texte": "Le solde récent est négatif à cause des variations signalées ci-dessous : "
                    "il ne faut pas y voir un retour de terrains à la nature."})
    elif r < 0:
        out.append({"regle": "solde", "texte": "Le solde récent est négatif : il y a eu plus de terrains sortis "
                    "de la catégorie artificialisée que de terrains entrés, souvent à cause de reclassements."})

    for x in c["reclassements"]:
        noms = " et ".join(f"« {s['nature']} » perd {_ha(abs(s['ha']))} ha" for s in x["sorties"])
        out.append({"regle": "reclassement", "texte": f"Reclassement probable en {x['annee']} : {noms} "
                    f"pendant que « {x['contrepartie']['nature']} » gagne {_ha(x['contrepartie']['ha'])} ha. Sans ce mouvement, "
                    f"le flux de l'année passe de {_s(x['flux'])} à {_s(x['corrige'])} ha."})

    if c["sauts"]:
        liste = ", ".join(f"{a} ({_s(v, 0)} ha)" for a, v in c["sauts"])
        pluriel = "Variation inhabituelle à vérifier" if len(c["sauts"]) == 1 else "Variations inhabituelles à vérifier"
        out.append({"regle": "saut", "texte": f"{pluriel} : {liste}. Il peut s'agir d'un reclassement cadastral "
                    "comme d'un vrai chantier : les données ne permettent pas de trancher."})

    if c["bassin"] and c["part_bassin_pct"] is not None and arrondi(c["part_bassin_pct"]) > 0:
        out.append({"regle": "bassin", "texte": f"La commune représente {_nombre(c['part_bassin_pct'], 0 if arrondi(c['part_bassin_pct']) >= 10 else 1)} % "
                    f"de ce que le bassin {c['bassin']} a artificialisé en {periodes}. "
                    "Le SDT fixe la trajectoire au niveau du bassin, pas de la commune."})
    elif not c["bassin"]:
        out.append({"regle": "bassin", "texte": "Le SDT ne s'applique pas sur le territoire de la Communauté "
                    "germanophone : cette commune n'a pas de bassin ni de trajectoire."})
    return out


def _n_en(valeur: float, decimales: int = 1) -> str:
    """Écrit un nombre à l'anglaise, avec le signe moins typographique."""
    return f"{arrondi(valeur, decimales):,.{decimales}f}".replace("-", "−")


def _ha_en(valeur: float) -> str:
    return _n_en(valeur, 1 if abs(valeur) < 100 else 0)


def _points_en(valeur: float) -> str:
    return f"{_n_en(valeur)} point" + ("" if abs(arrondi(valeur)) == 1 else "s")


def _s_en(valeur: float, decimales: int = 1) -> str:
    return ("+" if valeur >= 0 else "") + _n_en(valeur, decimales)


def _phrases_en(c: dict, stats: dict) -> list[str]:
    """Mêmes règles que _phrases, dans le même ordre : une phrase anglaise pour chaque phrase française."""
    out = []
    der = stats["annee_stock"]
    part = c["part"]
    txt = f"{_n_en(part)}% of the territory is artificialised as of 1 January {der}."
    if c["part_iweps"] is not None:
        txt += f" IWEPS reported {_n_en(c['part_iweps'])}% as of 1 January {stats['annee_iweps']}."
    out.append(txt)

    med, lieu = (c["mediane_bassin"], "its basin's median") if c["bassin"] else (stats["mediane_wallonie"], "the Walloon median")
    ecart = part - med
    if abs(ecart) < ECART_PART_POINTS:
        out.append(f"That is close to {lieu} ({_n_en(med)}%).")
    elif ecart > 0:
        out.append(f"That is above {lieu} ({_n_en(med)}%).")
    else:
        out.append(f"That is below {lieu} ({_n_en(med)}%).")

    h = c["hausse_points"]
    a0 = stats["premiere_annee"]
    if abs(h) < 0.1:
        out.append(f"This share has barely moved since {a0}.")
    elif h < 0:
        out.append(f"This share has fallen by {_points_en(-h)} since {a0}, which often reflects cadastral reclassifications.")
    else:
        cat, val = c["moteur"]
        if arrondi(val) > arrondi(h):
            out.append(f"Since {a0}, this share has gained {_points_en(h)}. For {PHRASE_CATEGORIE_EN[cat]}, the rise reaches "
                       f"{_points_en(val)}, because other categories have fallen.")
        elif val >= 0.5 * h:
            out.append(f"Since {a0}, this share has gained {_points_en(h)}, including {_n_en(val)} for {PHRASE_CATEGORIE_EN[cat]}.")
        else:
            out.append(f"Since {a0}, this share has gained {_points_en(h)}. No single category explains most of it: "
                       f"{PHRASE_CATEGORIE_EN[cat]} weighs the most ({_points_en(val)}).")

    r, p = c["rythme_recent"], c["rythme_passe"]
    rn, pn = c["rythme_recent_sans_saut"], c["rythme_passe_sans_saut"]
    periodes = f"{stats['recent'][0]}-{stats['recent'][1]}"
    passe = f"{REFERENCE_COMMUNE[0]}-{REFERENCE_COMMUNE[1]}"
    signal = next(x["signal"] for x in c["phrases"] if x["regle"] == "rythme")
    base = f"The recent pace is {_ha_en(r)} ha/yr ({periodes}), against {_ha_en(p)} ha/yr in {passe}"
    corrige = abs(rn - r) >= ECART_RYTHME_ABSOLU_HA or abs(pn - p) >= ECART_RYTHME_ABSOLU_HA
    hors = f" Without the flagged changes, it becomes {_ha_en(rn)} against {_ha_en(pn)} ha/yr." if corrige else ""
    if signal == "incertain":
        out.append(f"{base}. It is hard to judge: without the flagged changes, it becomes {_ha_en(rn)} against {_ha_en(pn)} ha/yr, "
                   "and the finding changes.")
    elif signal == "comparable":
        out.append(f"{base}: it remains comparable.{hors}")
    elif signal == "plus rapide":
        out.append(f"{base}: the municipality is artificialising land faster than before.{hors}")
    else:
        out.append(f"{base}: the municipality is artificialising land more slowly than before.{hors}")

    if r < 0 and rn >= 0:
        out.append("The recent balance is negative because of the flagged changes below: it should not be read as land returning to nature.")
    elif r < 0:
        out.append("The recent balance is negative: more land left the artificialised category than entered it, often because of reclassifications.")

    for x in c["reclassements"]:
        noms = " and ".join(f"“{_nature_en(s['nature'])}” loses {_ha_en(abs(s['ha']))} ha" for s in x["sorties"])
        out.append(f"Likely reclassification in {x['annee']}: {noms} while “{_nature_en(x['contrepartie']['nature'])}” gains "
                   f"{_ha_en(x['contrepartie']['ha'])} ha. Without this movement, the year's flow goes from {_s_en(x['flux'])} to {_s_en(x['corrige'])} ha.")

    if c["sauts"]:
        liste = ", ".join(f"{a} ({_s_en(v, 0)} ha)" for a, v in c["sauts"])
        debut = "Unusual change to check" if len(c["sauts"]) == 1 else "Unusual changes to check"
        out.append(f"{debut}: {liste}. This may be a cadastral reclassification or real construction: the data cannot settle it.")

    if c["bassin"] and c["part_bassin_pct"] is not None and arrondi(c["part_bassin_pct"]) > 0:
        out.append(f"The municipality accounts for {_n_en(c['part_bassin_pct'], 0 if arrondi(c['part_bassin_pct']) >= 10 else 1)}% of what the "
                   f"{c['bassin']} basin artificialised in {periodes}. The SDT sets the trajectory at basin level, not municipal level.")
    elif not c["bassin"]:
        out.append("The SDT does not apply in the territory of the German-speaking Community: this municipality has no basin and no trajectory.")
    return out


def _statut(ratio: float) -> str:
    """Situation du bassin d'après la seule lecture retenue, le cumul consolidé (années définitives)."""
    if ratio > 1 + ECART_PROCHE:
        return "au-dessus"
    if ratio < 1 - ECART_PROCHE:
        return "en-dessous"
    return "proche"


def _bassin(nom: str, cle: str, ref: float, incertitude: float, f: pd.DataFrame, fn: pd.DataFrame, annees_flux: list[int]) -> dict:
    total = f.sum(axis=0)
    total_n = fn.sum(axis=0)
    der = annees_flux[-1]
    a_avant = [a for a in annees_flux if TRAJ_START <= a < der]
    a_tout = a_avant + [der]
    cumul = lambda s, an: float(s[an].sum())  # noqa: E731
    autorise = lambda r, an: float(sum(r * part_trajectoire(a) for a in an))  # noqa: E731
    ref_propre = float(total[list(range(REFERENCE_COMMUNE[0], REFERENCE_COMMUNE[1] + 1))].mean())
    ratios = {
        "confirme": cumul(total, a_avant) / autorise(ref, a_avant),
        "avec_provisoire": cumul(total, a_tout) / autorise(ref, a_tout),
        "sans_saut": cumul(total_n, a_tout) / autorise(ref, a_tout),
        "reference_recalculee": cumul(total, a_tout) / autorise(ref_propre, a_tout),
    }
    return {
        "cle": cle, "nom": nom, "reference": ref, "reference_recalculee": round(ref_propre, PRECISION_HA),
        "incertitude": incertitude, "flux": [round(float(total[a]), PRECISION_HA) for a in annees_flux],
        "flux_sans_saut": [round(float(total_n[a]), PRECISION_HA) for a in annees_flux],
        "cumul_observe": round(cumul(total, a_tout), PRECISION_HA), "cumul_autorise": round(autorise(ref, a_tout), PRECISION_HA),
        "cumul_observe_confirme": round(cumul(total, a_avant), PRECISION_HA), "cumul_autorise_confirme": round(autorise(ref, a_avant), PRECISION_HA),
        "ratios": {k: round(v, PRECISION_PARTS) for k, v in ratios.items()},
        "ratio": round(ratios["confirme"], PRECISION_PARTS),
        "statut": _statut(ratios["confirme"]),
        "plafond_derniere_annee": round(ref * part_trajectoire(der), PRECISION_HA),
        "marquante": _marquante(f, der),
    }


def _marquante(f: pd.DataFrame, an: int) -> dict:
    """La commune qui pèse le plus sur le flux de l'année, pour pouvoir expliquer un chiffre surprenant."""
    code = f[an].abs().idxmax()
    return {"code": int(code), "valeur": round(float(f.loc[code, an]), PRECISION_HA), "annee": an}


def _exemple_methode(code: int, spf: pd.DataFrame, st: pd.DataFrame, sup: pd.Series, flux: pd.DataFrame, flux_n: pd.DataFrame,
                     iw: pd.DataFrame, an_iw: int, annees: list[int], fiches: dict) -> dict:
    """Tous les chiffres de l'exemple de la page Méthode, pour qu'aucun ne soit écrit à la main."""
    der, avant = annees[-1], annees[-2]
    table = pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").set_index("nature")
    surfaces = spf.loc[(code, der)].sort_values(ascending=False)
    mouvements = (spf.loc[(code, der)] - spf.loc[(code, avant)])
    mouvements = mouvements.reindex(mouvements.abs().sort_values(ascending=False).index)
    decrire = lambda n: {"nature": table.loc[n, "libelle"], "nature_en": _nature_en(table.loc[n, "libelle"]),  # noqa: E731
                         "categorie": LIBELLES[table.loc[n, "categorie"]], "categorie_en": LIBELLES_EN[table.loc[n, "categorie"]],
                         "artificialise": bool(table.loc[n, "categorie"] in ARTIF)}
    return {
        "code": code, "nom": fiches[code]["nom"], "bassin": fiches[code]["bassin"], "bassin_cle": fiches[code]["bassin_cle"],
        "annee": der, "annee_avant": avant, "nb_natures": int((surfaces > 0).sum()),
        "premieres": [{**decrire(n), "ha": arrondi(v)} for n, v in surfaces.head(6).items()],
        "stock": arrondi(st.loc[(code, der), "artif"]), "stock_avant": arrondi(st.loc[(code, avant), "artif"]),
        "superficie": arrondi(sup.loc[(code, der)]), "part": fiches[code]["part"],
        "part_iweps": round(float(iw.loc[(code, an_iw), "artif"]), 1),
        "flux": round(float(flux.loc[code, avant]), PRECISION_HA), "flux_corrige": round(float(flux_n.loc[code, avant]), PRECISION_HA),
        "mediane": round(float(flux.loc[code].median()), PRECISION_HA),
        "mouvements": [{**decrire(n), "ha": round(float(v), PRECISION_HA), "avant": round(float(spf.loc[(code, avant), n]), PRECISION_HA), "apres": round(float(spf.loc[(code, der), n]), PRECISION_HA)} for n, v in mouvements.head(5).items()],
        "terrain_gain_wallonie": round(float(spf.xs(der, level="annee")[NATURE_TERRAIN].sum() - spf.xs(annees[0], level="annee")[NATURE_TERRAIN].sum())),
        "rythme_recent": fiches[code]["rythme_recent"], "rythme_passe": fiches[code]["rythme_passe"],
        "rythme_recent_corrige": fiches[code]["rythme_recent_sans_saut"], "rythme_passe_corrige": fiches[code]["rythme_passe_sans_saut"],
    }


def _ecrit(chemin: Path, objet) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _cle_bassin(nom: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()).strip("-")


def construit(refresh: bool = False, zips: Path | None = None) -> dict:
    communes = pd.read_csv(REFERENCES / "communes_bassins_sdt.csv").set_index("code_ins").rename(columns={"bassin_sdt": "bassin"})
    communes["bassin"] = communes["bassin"].where(communes["couvert_par_sdt"] == "oui")
    annees = annees_spf(refresh, zips)
    spf = charge_spf(annees, communes)
    iw = charge_iweps(refresh)
    sup = superficies(annees)
    st = stocks_categories(spf, sup)
    if st.index.get_level_values(0).nunique() != len(communes):
        raise ValueError("Le nombre de communes ne correspond pas à la liste de référence.")

    stock = st["artif"].unstack(0).sort_index()
    annees_flux = annees[:-1]
    flux = stock.diff().shift(-1).loc[annees_flux].T          # flux N = stock(N+1) - stock(N)
    flux.columns = annees_flux
    reclass = reclassements(spf, flux)
    types, flux_n = verifications(flux, reclass)
    masque = types.ne("")
    der = annees[-1]
    an_iw = int(iw.index.get_level_values(1).max())
    annees_iw = sorted(iw.index.get_level_values(1).unique())
    recent = [a for a in annees_flux if a >= TRAJ_START]
    passe = list(range(REFERENCE_COMMUNE[0], REFERENCE_COMMUNE[1] + 1))
    chemins, voisins, frontieres, vue = _voisins_et_chemins(communes)
    parts = (stock.loc[der] / sup.xs(der, level="annee") * 100).rename("part")

    stats = {
        "annee_stock": der, "annee_iweps": an_iw, "premiere_annee": annees[0],
        "recent": [recent[0], recent[-1]], "passe": list(REFERENCE_COMMUNE),
        "mediane_wallonie": float(parts.median()),
    }
    medianes = parts.groupby(communes["bassin"]).median()
    ref = pd.read_csv(REFERENCES / "trajectoires_sdt_2024_bassins.csv").set_index("bassin")
    ref = ref[ref.index.isin(communes["bassin"].dropna().unique())]  # le fichier contient aussi une ligne régionale
    flux_bassin_recent = flux[recent].sum(axis=1).groupby(communes["bassin"]).sum()

    index, fiches = [], {}
    for code in sorted(communes.index):
        rang = communes.loc[code]
        nom_bassin = rang["bassin"] if isinstance(rang["bassin"], str) else None
        s = st.xs(code, level="code_ins")
        a = sup.xs(code, level="code_ins")
        hausse = (s.loc[der] / a[der] - s.loc[annees[0]] / a[annees[0]]) * 100
        moteur = hausse[ARTIF].idxmax()
        iw_c = iw.xs(code, level="code_ins") if code in iw.index.get_level_values(0) else None
        f = flux.loc[code]
        sauts_c = [(int(y), round(float(f[y]), PRECISION_HA)) for y in annees_flux if types.loc[code, y] in ("negatif", "saut")]
        reclass_c = [reclass[(int(code), int(y))] for y in annees_flux if types.loc[code, y] == "reclassement"]
        c = {
            "code": int(code), "nom": rang["commune"], "province": rang["province"], "bassin": nom_bassin,
            "bassin_cle": _cle_bassin(nom_bassin) if nom_bassin else None,
            "superficie": arrondi(a[der]), "part": round(float(parts[code]), PRECISION_PARTS),
            "part_iweps": round(float(iw_c.loc[an_iw, "artif"]), 1) if iw_c is not None else None,
            "mediane_bassin": round(float(medianes[nom_bassin]), PRECISION_PARTS) if nom_bassin else None,
            "hausse_points": round(float(hausse["artif"]), PRECISION_PARTS), "moteur": [moteur, round(float(hausse[moteur]), PRECISION_PARTS)],
            "hausses": {k: round(float(hausse[k]), PRECISION_PARTS) for k in CATEGORIES},
            "rythme_recent": round(float(f[recent].mean()), PRECISION_PARTS), "rythme_passe": round(float(f[passe].mean()), PRECISION_PARTS),
            "rythme_recent_sans_saut": round(float(flux_n.loc[code, recent].mean()), PRECISION_PARTS),
            "rythme_passe_sans_saut": round(float(flux_n.loc[code, passe].mean()), PRECISION_PARTS),
            "sauts": sauts_c, "reclassements": reclass_c, "flux": [round(float(f[y]), PRECISION_HA) for y in annees_flux],
            "part_bassin_pct": round(float(f[recent].sum() / flux_bassin_recent[nom_bassin] * 100), PRECISION_PARTS)
            if nom_bassin and flux_bassin_recent[nom_bassin] > 0 else None,
            "voisins": [{"code": v, "nom": communes.loc[v, "commune"], "part": arrondi(parts[v])} for v in voisins.get(code, [])],
            "parts_estimees": {k: [round(float(s.loc[y, k] / a[y] * 100), PRECISION_PARTS) for y in annees] for k in CATEGORIES + ["artif"]},
            "parts_iweps": {k: [round(float(iw_c.loc[y, k]), 2) for y in annees_iw] for k in IWEPS_ORDRE} if iw_c is not None else None,
            "ha_estimes": {k: round(float(s.loc[der, k]), PRECISION_HA) for k in CATEGORIES + ["artif"]},
        }
        c["phrases"] = _phrases(c, stats)
        anglais = _phrases_en(c, stats)
        if len(anglais) != len(c["phrases"]):
            raise ValueError(f"Phrases françaises et anglaises désalignées pour {c['nom']}.")
        for phrase, en in zip(c["phrases"], anglais):
            phrase["texte_en"] = en
        fiches[code] = c
        signal = next(p["signal"] for p in c["phrases"] if p["regle"] == "rythme")
        index.append({
            "code": int(code), "nom": c["nom"], "bassin": nom_bassin, "bassin_cle": c["bassin_cle"], "province": c["province"],
            "part": arrondi(parts[code]), "rythme": arrondi(f[recent].mean()), "ecart": arrondi(f[recent].mean() - f[passe].mean()),
            "signal": signal, "saut": bool(sauts_c or reclass_c), "chemin": chemins[code],
        })

    bassins = []
    for nom in ref.index:
        membres = communes.index[communes["bassin"] == nom]
        b = _bassin(nom, _cle_bassin(nom), float(ref.loc[nom, "artif_nette_moy_10ans_ha_an"]), float(ref.loc[nom, "incertitude_lecture_ha_an"]),
                    flux.loc[membres], flux_n.loc[membres], annees_flux)
        b["communes"] = sorted(
            ({"code": int(k), "nom": fiches[k]["nom"], "rythme": arrondi(flux.loc[k, recent].mean()), "cumul": arrondi(flux.loc[k, recent].sum()),
              "part": arrondi(parts[k]), "saut": bool(fiches[k]["sauts"] or fiches[k]["reclassements"])} for k in membres), key=lambda x: _norme(x["nom"]))
        bassins.append(b)
    bassins.sort(key=lambda b: b["nom"])
    couvertes = communes.index[communes["bassin"].notna()]
    wallonie_sdt = _bassin("Wallonie, hors Communauté germanophone", "wallonie", float(ref["artif_nette_moy_10ans_ha_an"].sum()), float(ref["incertitude_lecture_ha_an"].sum()),
                           flux.loc[couvertes], flux_n.loc[couvertes], annees_flux)
    region = {
        "flux": [round(float(flux[a].sum()), PRECISION_HA) for a in annees_flux],
        "stock": arrondi(stock.loc[der].sum(), 0), "superficie": arrondi(sup.xs(der, level="annee").sum(), 0),
        "part": arrondi(stock.loc[der].sum() / sup.xs(der, level="annee").sum() * 100),
    }
    meta = {
        "annees_stock": annees, "annees_flux": annees_flux, "annees_iweps": annees_iw,
        "derniere_annee_flux": annees_flux[-1], "stats": stats, "libelles": LIBELLES, "libelles_en": LIBELLES_EN, "artif": ARTIF, "non_artif": NON_ARTIF,
        "vue": vue, "frontieres_bassins": frontieres, "region": region, "trajectoire_debut": TRAJ_START, "trajectoire_fin": TRAJ_END, "ecart_proche_pct": round(ECART_PROCHE * 100),
        "verifications": {
            "reclassements": {"annees": len(reclass), "communes": len({k[0] for k in reclass})},
            "negatifs": {"annees": int(types.eq("negatif").sum().sum()), "communes": int(types.eq("negatif").any(axis=1).sum())},
            "sauts": {"annees": int(types.eq("saut").sum().sum()), "communes": int(types.eq("saut").any(axis=1).sum())},
            "couples": int(types.size),
            "seuils": {"sortie_ha": RECLASS_SORTIE_MIN_HA, "couverture_pct": round(RECLASS_COUVERTURE * 100), "retour_pct": round(RECLASS_RETOUR * 100),
                       "negatif_ha": SOLDE_NEGATIF_HA, "saut_ha": SAUT_SEUIL_MIN_HA, "saut_mad": SAUT_K_MAD},
            "test_seuil": [test_seuil_reclassement(spf, flux, s) for s in RECLASS_SEUILS_TESTES],
        },
        "exemple": _exemple_methode(EXEMPLE_COMMUNE, spf, st, sup, flux, flux_n, iw, an_iw, annees, fiches),
        # Communes pilotes dont la carte de l'étalement vu du ciel existe (produite par src/etalement_walous.py)
        "etalement": _etalement(),
    }

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    _ecrit(SITE_DATA / "index.json", {"meta": meta, "communes": index, "bassins": bassins, "wallonie": wallonie_sdt})
    paquets = {}
    for code, c in fiches.items():
        paquets.setdefault(code // 1000, {})[str(code)] = c    # un fichier par arrondissement
    for arrondissement, contenu in paquets.items():
        _ecrit(SITE_DATA / "communes" / f"{arrondissement}.json", contenu)
    _exports(st, flux, flux_n, types, reclass, communes, annees_flux, bassins, wallonie_sdt)
    return {"meta": meta, "fiches": fiches, "bassins": bassins, "wallonie": wallonie_sdt, "st": st, "iw": iw, "flux": flux, "flux_n": flux_n, "types": types, "reclass": reclass}


def _etalement() -> dict:
    """Résumé des communes pilotes dont la carte de l'étalement vu du ciel existe (produite par src/etalement_walous.py)."""
    dossier = SITE_DATA / "etalement"
    communes = []
    for f in sorted(dossier.glob("*.json")):
        if f.stem.isdigit():
            r = json.loads(f.read_text(encoding="utf-8"))["resume"]
            communes.append({"code": r["code"], "nom": r["nom"], "neuf_ha": r["neuf_ha"], "batiments_ha": r["batiments_ha"],
                             "bruit_ha": round(r["bruit"]["batiments_inverses_ha"] + r["bruit"]["abords_inverses_ha"], 2),
                             "brut_neuf_ha": r["brut"]["neuf_ha"], "brut_retour_ha": r["brut"]["retour_ha"],
                             "photos": (SITE_DATA / "photos" / str(r["code"]) / "index.json").exists()})
    w = dossier / "wallonie.json"
    return {"communes": communes, "wallonie": json.loads(w.read_text(encoding="utf-8")) if w.exists() else None}


def _exports(st, flux, flux_n, types, reclass, communes, annees_flux, bassins, wallonie) -> None:
    dossier = SITE_DATA / "telechargements"
    dossier.mkdir(parents=True, exist_ok=True)
    long = st.rename_axis(columns="categorie").stack().rename("hectares").round(2).reset_index()
    long = long.rename(columns={"annee": "annee_1er_janvier"})
    long["commune"] = long["code_ins"].map(communes["commune"])
    long[["code_ins", "commune", "annee_1er_janvier", "categorie", "hectares"]].to_csv(dossier / "stocks_par_commune.csv", index=False, encoding="utf-8-sig")
    f = flux.rename_axis(index="code_ins", columns="annee").stack().rename("flux_net_ha").round(2).reset_index()
    f["commune"] = f["code_ins"].map(communes["commune"])
    f["bassin"] = f["code_ins"].map(communes["bassin"])
    f["signalement"] = [types.loc[c, a] for c, a in zip(f["code_ins"], f["annee"])]
    f["flux_corrige_ha"] = [round(float(flux_n.loc[c, a]), 2) for c, a in zip(f["code_ins"], f["annee"])]
    f["provisoire"] = f["annee"] == annees_flux[-1]
    f[["code_ins", "commune", "bassin", "annee", "flux_net_ha", "signalement", "flux_corrige_ha", "provisoire"]].to_csv(dossier / "flux_par_commune.csv", index=False, encoding="utf-8-sig")
    lignes_r = [{"code_ins": c, "commune": communes.loc[c, "commune"], "annee": a, "flux_net_ha": arrondi(r["flux"]), "flux_corrige_ha": arrondi(r["corrige"]),
                 "natures_en_baisse": " + ".join(f"{s['nature']} ({arrondi(s['ha'])} ha)" for s in r["sorties"]),
                 "contrepartie": f"{r['contrepartie']['nature']} (+{arrondi(r['contrepartie']['ha'])} ha)"} for (c, a), r in sorted(reclass.items())]
    pd.DataFrame(lignes_r).to_csv(dossier / "reclassements_probables.csv", index=False, encoding="utf-8-sig")
    lignes = [{"bassin": b["nom"], "annee": a, "flux_net_ha": arrondi(v), "trajectoire_ha": round(b["reference"] * part_trajectoire(a), 1) if a >= TRAJ_START else None}
              for b in bassins + [wallonie] for a, v in zip(annees_flux, b["flux"])]
    pd.DataFrame(lignes).to_csv(dossier / "flux_par_bassin.csv", index=False, encoding="utf-8-sig")
    pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").to_csv(dossier / "table_natures_categories.csv", index=False, encoding="utf-8-sig")
