"""Pilote : où se construit-on ? Bâtiments mis en service et parcelles nouvelles, croisés avec le plan de secteur.

Sources (toutes ouvertes) :
- SPF Finances, plan parcellaire cadastral, situation au 1er janvier (licence open data du SPF, citer la source) ;
- SPW, plan de secteur en vigueur, version coordonnée vectorielle (CC BY 4.0) ;
- SPW, centralités urbaines et rurales du SDT (CC BY 4.0).

Méthode :
- un bâtiment est « nouveau » s'il figure au 1er janvier 2024 et pas au 1er janvier 2021 : moins de 20 % de son emprise
  recouvre un bâtiment de 2021, et sa situation fiscale est postérieure à 2021 ;
- les bâtiments souterrains (type UN) sont écartés ;
- chaque nouveau bâtiment est rattaché à la zone du plan de secteur qui contient son centre, et à une centralité s'il y en a une ;
- la parcelle de 2025 qui contient le bâtiment donne la surface que le cadastre a pu faire passer en « artificialisé ».

Usage : .venv/Scripts/python.exe -X utf8 src/pilote_parcelles.py
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
BRUT = RACINE / "data" / "raw" / "spf_plan_parcellaire"
SPW = RACINE / "data" / "raw" / "spw_pilote"
SORTIE = RACINE / "data" / "processed" / "pilote_parcelles"
COMMUNES = {92142: "Gembloux", 63035: "Herve", 83034: "Marche-en-Famenne"}
AVANT, APRES, PARCELLES = 2021, 2024, 2025   # bâtiments 2021 -> 2024, parcelles 2021 -> 2025
# Attention : la couche des bâtiments du cadastre (Bpn_CaBu) disparaît des extraits wallons dès 2022, 2023 ou 2024 selon la commune.
RECOUVREMENT_MAX = 0.2
CRS = "EPSG:31370"
PDS = "https://geoservices.wallonie.be/arcgis/rest/services/AMENAGEMENT_TERRITOIRE/PDS/MapServer/22/query"
CENTR = "https://geoservices.wallonie.be/arcgis/rest/services/AMENAGEMENT_TERRITOIRE/CENTRALITES/MapServer/0/query"

# Regroupement des zones du plan de secteur (champ AFFECT) en familles lisibles
def famille(affect: str | None) -> str:
    a = affect or ""
    if a.startswith("H"):
        return "habitat"
    if a.startswith("A"):
        return "activite"
    if a.startswith("P01") or a.startswith("L"):
        return "equipement"   # services publics et équipements communautaires, loisirs
    if a.startswith("X"):
        return "extraction"
    if a == "R01":
        return "agricole"
    if a == "R02":
        return "forestiere"
    if a in ("R03", "R04", "R05"):
        return "naturelle"
    if a in ("D01", "D02", "ZEC", "ZER"):
        return "reserve"   # aménagement communal concerté, zones d'enjeu
    return "autre"         # zones blanches (non affectées), plans d'eau


def couche(code: int, an: int, nom: str) -> gpd.GeoDataFrame:
    zips = list(BRUT.glob(f"PP-FiscSit_{an}0101_shp_31370_{code}_*.zip"))
    if len(zips) != 1:
        raise SystemExit(f"fichier manquant : {code} {an}")
    return gpd.read_file(f"/vsizip/{zips[0].as_posix()}/{nom}.shp", engine="pyogrio").set_crs(CRS, allow_override=True)


def requete_arcgis(url: str, bbox, cache: Path) -> gpd.GeoDataFrame:
    """Toutes les entités qui touchent la boîte, page par page, gardées en cache."""
    if cache.exists():
        return gpd.read_file(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    morceaux, offset = [], 0
    while True:
        params = {"where": "1=1", "geometry": ",".join(f"{v:.0f}" for v in bbox), "geometryType": "esriGeometryEnvelope",
                  "inSR": "31370", "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "outSR": "31370",
                  "resultOffset": offset, "resultRecordCount": 1000, "f": "geojson"}
        with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=120) as r:
            page = json.load(r)
        feats = page.get("features", [])
        morceaux += feats
        if len(feats) < 1000:
            break
        offset += 1000
    g = gpd.GeoDataFrame.from_features(morceaux, crs=CRS)
    g.to_file(cache, driver="GeoJSON")
    return g


def analyse(code: int, nom: str) -> dict:
    b0 = couche(code, AVANT, "Bpn_CaBu")
    b1 = couche(code, APRES, "Bpn_CaBu")
    p0 = couche(code, AVANT, "Bpn_CaPa")
    p1 = couche(code, PARCELLES, "Bpn_CaPa")
    limite = couche(code, PARCELLES, "Apn_CaDi").dissolve()
    b1 = b1[b1["Type"] != "UN"].copy()
    b0 = b0[b0["Type"] != "UN"]
    b1["id"] = range(len(b1))
    b1["emprise_m2"] = b1.geometry.area
    inter = gpd.overlay(b1[["id", "geometry"]], b0[["geometry"]], how="intersection", keep_geom_type=True)
    deja = inter.assign(a=inter.geometry.area).groupby("id")["a"].sum()
    b1["recouvrement"] = b1["id"].map(deja).fillna(0) / b1["emprise_m2"]
    sit_avant = int(b0["FiscSitId"].max())  # dernière situation fiscale connue en 2021
    neufs = b1[(b1["recouvrement"] < RECOUVREMENT_MAX) & (b1["FiscSitId"] > sit_avant)].copy()

    zones = requete_arcgis(PDS, limite.total_bounds, SPW / f"pds_{code}.geojson")
    centr = requete_arcgis(CENTR, limite.total_bounds, SPW / f"centralites_{code}.geojson")
    zones["famille"] = zones["AFFECT"].map(famille)
    pts = neufs.copy()
    pts["geometry"] = neufs.geometry.representative_point()
    pts = gpd.sjoin(pts, zones[["AFFECT", "famille", "geometry"]], how="left", predicate="within").drop(columns="index_right")
    pts = pts[~pts.index.duplicated()]
    pts["famille"] = pts["famille"].fillna("hors plan")
    pts["centralite"] = gpd.sjoin(pts[["geometry"]], centr[["geometry"]], how="left", predicate="within")["index_right"].groupby(level=0).first().notna()
    # Parcelle de 2025 qui porte le bâtiment, et si elle est nouvelle (clé absente en 2021)
    par = gpd.sjoin(pts[["geometry"]], p1[["CaPaKey", "geometry"]], how="left", predicate="within")["CaPaKey"].groupby(level=0).first()
    pts["parcelle"] = par
    nouvelles_cles = set(p1["CaPaKey"]) - set(p0["CaPaKey"])
    pts["parcelle_nouvelle"] = pts["parcelle"].isin(nouvelles_cles)
    surf_parc = p1.set_index("CaPaKey").geometry.area
    parcelles_baties = pts["parcelle"].dropna().unique()

    par_famille = pts.groupby("famille").agg(batiments=("id", "size"), emprise_ha=("emprise_m2", lambda s: s.sum() / 1e4))
    resume = {
        "code": code, "nom": nom, "superficie_ha": round(float(limite.area.iloc[0]) / 1e4, 1),
        "batiments_2021": int(len(b0)), "batiments_2024": int(len(b1)),
        "nouveaux_batiments": int(len(pts)), "emprise_neuve_ha": round(float(pts["emprise_m2"].sum()) / 1e4, 2),
        "parcelles_baties_ha": round(float(surf_parc.reindex(parcelles_baties).sum()) / 1e4, 1),
        "part_parcelle_nouvelle": round(float(pts["parcelle_nouvelle"].mean()) * 100, 1),
        "part_centralite": round(float(pts["centralite"].mean()) * 100, 1),
        "par_famille": {k: {"batiments": int(v.batiments), "emprise_ha": round(float(v.emprise_ha), 2)} for k, v in par_famille.iterrows()},
        "nouvelles_parcelles": len(nouvelles_cles), "parcelles_2021": int(len(p0)), "parcelles_2025": int(len(p1)),
    }
    SORTIE.mkdir(parents=True, exist_ok=True)
    neufs.assign(famille=pts["famille"], centralite=pts["centralite"], parcelle_nouvelle=pts["parcelle_nouvelle"]) \
        [["Type", "FiscSitId", "emprise_m2", "famille", "centralite", "parcelle_nouvelle", "geometry"]] \
        .to_file(SORTIE / f"nouveaux_batiments_{code}.geojson", driver="GeoJSON")
    return resume


if __name__ == "__main__":
    import zipfile
    def complet(code):
        z = list(BRUT.glob(f"PP-FiscSit_{APRES}0101_shp_31370_{code}_*.zip"))
        return bool(z) and any(n.endswith("Bpn_CaBu.shp") for n in zipfile.ZipFile(z[0]).namelist())
    for c, n in COMMUNES.items():
        if not complet(c):
            print(f"{n} : pas de bâtiments du cadastre au 1er janvier {APRES}, commune écartée du pilote")
    resumes = [analyse(c, n) for c, n in COMMUNES.items() if complet(c)]
    (SORTIE / "resume.json").write_text(json.dumps(resumes, ensure_ascii=False, indent=1), encoding="utf-8")
    t = pd.DataFrame([{**{k: v for k, v in r.items() if k != "par_famille"}} for r in resumes]).set_index("nom")
    print(t.T.to_string())
    for r in resumes:
        tot = r["nouveaux_batiments"]
        print(f"\n{r['nom']} : {tot} nouveaux bâtiments 2021-2024")
        for k, v in sorted(r["par_famille"].items(), key=lambda x: -x[1]["batiments"]):
            print(f"  {k:12s} {v['batiments']:5d}  ({v['batiments'] / tot * 100:4.1f} %)  emprise {v['emprise_ha']:.2f} ha")
