"""Plan de secteur et centralités du SDT (SPW, CC BY 4.0), lus d'un bloc pour toute la Wallonie.

Les couches viennent des services cartographiques du SPW, page par page et une requête à la fois (une vingtaine
de requêtes en tout), puis restent en cache dans data/raw/spw_amenagement/. Le téléchargement INSPIRE du plan de
secteur date de 2022 : le service, lui, est à jour.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import geopandas as gpd
from shapely.geometry import box

from ..config import RAW
from ..sources import USER_AGENT, record
from .parcelles import CRS

PDS = "https://geoservices.wallonie.be/arcgis/rest/services/AMENAGEMENT_TERRITOIRE/PDS/MapServer/22/query"
CENTRALITES = "https://geoservices.wallonie.be/arcgis/rest/services/AMENAGEMENT_TERRITOIRE/CENTRALITES/MapServer/0/query"
CACHE = RAW / "spw_amenagement"
PAGE = 1000          # entités par requête, le maximum du service
PAUSE_S = 2          # entre deux requêtes : les conditions du SPW interdisent un usage « disproportionné »


def famille(affect: str | None) -> str:
    """Regroupe les zones du plan de secteur (champ AFFECT) en familles lisibles."""
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


def couche_wallonie(url: str, nom: str) -> gpd.GeoDataFrame:
    """Toute la couche d'un service, en Lambert 72, gardée en cache dans {nom}_wallonie.geojson."""
    cache = CACHE / f"{nom}_wallonie.geojson"
    if cache.exists():
        return gpd.read_file(cache)
    CACHE.mkdir(parents=True, exist_ok=True)
    morceaux, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "outSR": "31370", "orderByFields": "OBJECTID",
                  "resultOffset": offset, "resultRecordCount": PAGE, "f": "geojson"}
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as r:
            feats = json.load(r).get("features", [])
        morceaux += feats
        print(f"  {nom} : {len(morceaux)} entités", flush=True)
        if len(feats) < PAGE:
            break
        offset += PAGE
        time.sleep(PAUSE_S)
    g = gpd.GeoDataFrame.from_features(morceaux, crs=CRS)
    g.to_file(cache, driver="GeoJSON")
    record(cache, url + "?where=1=1&outFields=*", f"SPW, {nom}, toute la Wallonie, lu par pages de {PAGE} (CC BY 4.0)")
    return g


def dans_boite(g: gpd.GeoDataFrame, bbox) -> gpd.GeoDataFrame:
    """Les entités qui touchent la boîte (xmin, ymin, xmax, ymax), dans leur ordre d'origine."""
    return g.iloc[sorted(g.sindex.query(box(*bbox), predicate="intersects"))].reset_index(drop=True)


def zones(bbox) -> gpd.GeoDataFrame:
    """Zones du plan de secteur qui touchent la boîte, avec leur famille."""
    z = dans_boite(couche_wallonie(PDS, "plan_de_secteur"), bbox)
    z["famille"] = z["AFFECT"].map(famille)
    return z


def centralites(bbox) -> gpd.GeoDataFrame:
    return dans_boite(couche_wallonie(CENTRALITES, "centralites"), bbox)
