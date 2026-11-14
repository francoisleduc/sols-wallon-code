"""Correspondance commune -> bassin d'optimisation spatiale, via l'API ArcGIS REST du SPW.

Le SDT (p. 215) définit les bassins comme « les territoires gérés par les directions
extérieures » du SPW Territoire ; la couche DIREXT donne la direction extérieure de chaque commune.
"""
import urllib.parse

import pandas as pd

from .config import RAW, REFERENCES, SPW_DIREXT_LAYER
from .sources import fetch_json

PROVINCES = {"25": "Brabant wallon", "5": "Hainaut", "6": "Liège", "8": "Luxembourg", "9": "Namur"}


def _province(code_ins: str) -> str:
    return PROVINCES.get(code_ins[:2]) or PROVINCES[code_ins[0]]


def _bassin(dirext: str) -> str:
    if dirext == "Communauté Germanophone":
        return ""
    for prefix in ("Direction extérieure du ", "Direction extérieure de "):
        if dirext.startswith(prefix):
            return dirext[len(prefix):]
    raise ValueError(f"Direction extérieure inattendue : {dirext}")


def query(params: dict) -> str:
    return f"{SPW_DIREXT_LAYER}/query?{urllib.parse.urlencode(params)}"


def build(refresh: bool = False) -> pd.DataFrame:
    attrs = fetch_json(query({"where": "1=1", "outFields": "ADMUKEY,ADMUNAFR,REFERENTIEL,DIREXT,DATETRANS",
                              "returnGeometry": "false", "f": "json"}),
                       RAW / "spw" / "dirext_attributs.json", refresh, "Ressorts des fonctionnaires délégués")
    # Géométries simplifiées (WGS84, tolérance ~50 m) pour la cartographie du rapport
    fetch_json(query({"where": "1=1", "outFields": "ADMUKEY", "returnGeometry": "true", "outSR": "4326",
                      "maxAllowableOffset": "0.0005", "geometryPrecision": "5", "f": "geojson"}),
               RAW / "spw" / "dirext_communes.geojson", refresh, "Géométries communales simplifiées")
    rows = []
    for feat in attrs["features"]:
        a = feat["attributes"]
        bassin = _bassin(a["DIREXT"])
        rows.append({"code_ins": a["ADMUKEY"], "commune": a["ADMUNAFR"], "province": _province(a["ADMUKEY"]),
                     "bassin_sdt": bassin, "direction_exterieure": a["DIREXT"],
                     "couvert_par_sdt": "oui" if bassin else "non", "referentiel": a["REFERENTIEL"]})
    df = pd.DataFrame(rows).sort_values("code_ins")
    if len(df) != 261 or df["code_ins"].duplicated().any():
        raise ValueError(f"Couche DIREXT inattendue : {len(df)} communes")
    df.drop(columns="referentiel").to_csv(REFERENCES / "communes_bassins_sdt.csv", index=False)
    return df
