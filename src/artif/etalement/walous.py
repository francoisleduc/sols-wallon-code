"""Lecture de WalOUS, l'occupation du sol de Wallonie classée par apprentissage automatique (SPW, CC BY 4.0).

Fichiers téléchargés d'un bloc (adresses dans MISE_A_JOUR.md, section 4) :
- changements 2018 -> 2023, raster à 1 m en EPSG:3812 : chaque valeur vaut code 2018 x 100 + code 2023, et seuls
  les pixels qui ont changé sont renseignés (https://geodata.wallonie.be/id/03300ff8-5e1d-430d-876a-ffd1b9103e78) ;
- cartes complètes de 2019 et de 2020, mêmes codes, pour dater les changements.

Les services cartographiques du SPW donnent les mêmes classes en images PNG. Ils ne servent plus qu'à deux choses :
un contrôle croisé, quand leurs images sont déjà en cache, et l'ancienne datation (variable DATATION=service).
"""
from __future__ import annotations

import io
import os
import time
import urllib.parse
import urllib.request

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.windows
from PIL import Image

from ..config import RAW

CRS = "EPSG:3812"       # Lambert 2008, la grille de WalOUS
RASTER_CHANGEMENTS = RAW / "spw_walous" / "cha_2018_2023" / "WAL_OCS_IA_CHA_SIEVED__2018_2023.tif"
CARTES = {2019: RAW / "spw_walous" / "ocs_2019" / "WAL_OCS_IA__2019.tif",
          2020: RAW / "spw_walous" / "ocs_2020" / "WAL_OCS_IA__2020.tif"}

# Classes, dans l'ordre des indices utilisés partout dans le paquet
CLASSES = ["vide", "revetement", "construction", "rail", "sol_nu", "eau", "herbe_rotation", "herbe_permanente",
           "resineux_haut", "feuillus_haut", "resineux_bas", "feuillus_bas", "serre"]
REVETEMENT, CONSTRUCTION, RAIL = 1, 2, 3
ARTIFICIEL = {REVETEMENT, CONSTRUCTION, RAIL}
CODES = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 80: 10, 90: 11}   # code WalOUS -> indice de CLASSES


def _fenetre(r, xmin: int, ymax: int, l: int, h: int) -> np.ndarray:
    """Les pixels d'une boîte (coin haut-gauche, largeur, hauteur en mètres), 0 hors du raster."""
    fen = rasterio.windows.from_bounds(xmin, ymax - h, xmin + l, ymax, r.transform).round_offsets().round_lengths()
    return r.read(1, window=fen, boundless=True, fill_value=0)


def classes_2018_2023(xmin: int, ymax: int, l: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Classes 2018 et 2023 de chaque pixel (0 là où rien n'a changé), lues dans le raster des changements."""
    vat = gpd.read_file(RASTER_CHANGEMENTS.with_name(RASTER_CHANGEMENTS.name + ".vat.dbf"))
    with rasterio.open(RASTER_CHANGEMENTS) as r:
        v = _fenetre(r, xmin, ymax, l, h)
    t18, t23 = np.zeros(65536, np.int8), np.zeros(65536, np.int8)
    for val, a, b in zip(vat["Value"], vat["Code18"], vat["Code23"]):
        t18[int(val)], t23[int(val)] = CODES[int(a)], CODES[int(b)]
    return t18[v], t23[v]


def classes_annee(annee: int, xmin: int, ymax: int, l: int, h: int) -> np.ndarray:
    """Classe de chaque pixel en 2019 ou 2020, lue dans la carte complète (0 hors de la Wallonie)."""
    table = np.zeros(256, np.int8)
    for v, c in CODES.items():
        table[v] = c
    with rasterio.open(CARTES[annee]) as r:
        return table[_fenetre(r, xmin, ymax, l, h)]


def changements_wallonie() -> dict:
    """Changements bruts sur toute la Wallonie, depuis la table du raster : l'ampleur du bruit de classement."""
    v = gpd.read_file(RASTER_CHANGEMENTS.with_name(RASTER_CHANGEMENTS.name + ".vat.dbf"))
    v = v[v["Value"] > 0]
    a18, a23 = v["Code18"].isin(ARTIFICIEL), v["Code23"].isin(ARTIFICIEL)

    def ha(masque):
        return round(float(v.loc[masque, "Count"].sum()) / 1e4)   # un pixel = 1 m²

    return {"neuf_ha": ha(~a18 & a23), "retour_ha": ha(a18 & ~a23),
            "constructions_neuves_ha": ha(~a18 & (v["Code23"] == CONSTRUCTION)),
            "constructions_disparues_ha": ha((v["Code18"] == CONSTRUCTION) & ~a23)}


# --- Services cartographiques (contrôle croisé et ancienne datation) ----------------
SERVICES = "https://geoservices.wallonie.be/arcgis/rest/services/SOL_SOUS_SOL"
CACHE_SERVICES = RAW / "spw_pilote" / "walous"
CHANGEMENT, OCS2018 = "WAL_OCS_IA_CHA_18_23", "WALOUS_OCCUPATION_SOL"
CHA19, CHA20 = "WAL_OCS_IA__CHA_18_19", "WAL_OCS_IA__CHA_18_20"   # changements 2018-2019 et 2018-2020
TUILE = 4096           # pixels, la taille maximale acceptée par le service
# Couleurs exactes du rendu de chaque service (lues dans leur légende) -> indice de CLASSES
COULEURS = {
    CHANGEMENT: {(138, 138, 138): 1, (202, 15, 15): 2, (78, 78, 78): 3, (208, 208, 208): 4, (36, 97, 247): 5,
                 (255, 255, 155): 6, (233, 255, 190): 7, (0, 50, 0): 8, (40, 200, 40): 9, (0, 120, 0): 10, (183, 232, 176): 11},
    OCS2018: {(138, 138, 138): 1, (220, 15, 15): 2, (78, 78, 78): 3, (208, 208, 208): 4, (36, 97, 247): 5,
              (255, 255, 115): 6, (233, 255, 190): 7, (0, 50, 0): 8, (40, 200, 40): 9, (0, 120, 0): 10, (183, 232, 176): 11,
              (255, 85, 0): 12},
    CHA19: {(138, 138, 138): 1, (202, 15, 15): 2, (78, 78, 78): 3, (208, 208, 208): 4, (36, 97, 247): 5,
            (255, 255, 115): 6, (233, 255, 190): 7, (0, 50, 0): 8, (40, 50, 40): 9, (0, 120, 0): 10, (183, 232, 176): 11},
    CHA20: {(138, 138, 138): 1, (202, 15, 15): 2, (78, 78, 78): 3, (208, 208, 208): 4, (36, 97, 247): 5,
            (255, 255, 115): 6, (233, 255, 190): 7, (0, 50, 0): 8, (40, 200, 40): 9, (0, 120, 0): 10, (183, 232, 176): 11},
}


def _tuile(service: str, code: int, x0: int, y0: int, l: int, h: int) -> np.ndarray:
    """Classes d'une tuile (y croissant vers le bas), depuis le cache ou le service ; -1 pour une couleur inconnue."""
    f = CACHE_SERVICES / f"{service}_{code}_{x0}_{y0}.png"
    if not f.exists():
        CACHE_SERVICES.mkdir(parents=True, exist_ok=True)
        p = {"bbox": f"{x0},{y0},{x0 + l},{y0 + h}", "bboxSR": 3812, "imageSR": 3812, "size": f"{l},{h}",
             "format": "png32", "transparent": "true", "f": "image"}
        for essai in range(4):
            try:
                with urllib.request.urlopen(f"{SERVICES}/{service}/MapServer/export?" + urllib.parse.urlencode(p), timeout=300) as r:
                    data = r.read()
                Image.open(io.BytesIO(data)).verify()
                break
            except Exception as e:  # noqa: BLE001
                if essai == 3:
                    raise
                print("  nouvel essai", e)
                time.sleep(5)
        f.write_bytes(data)
    a = np.array(Image.open(f).convert("RGBA"))
    cle = (a[..., 0].astype(np.int32) << 16) | (a[..., 1].astype(np.int32) << 8) | a[..., 2]
    classes = np.full(cle.shape, -1, np.int8)
    classes[a[..., 3] == 0] = 0
    for (r, g, b), c in COULEURS[service].items():
        classes[(cle == (r << 16 | g << 8 | b)) & (a[..., 3] > 0)] = c
    return classes


def mosaique(service: str, code: int, xmin: int, ymax: int, l: int, h: int) -> np.ndarray:
    """Classes d'une boîte entière, assemblée en tuiles."""
    out = np.zeros((h, l), np.int8)
    for j in range(0, h, TUILE):
        for i in range(0, l, TUILE):
            tl, th = min(TUILE, l - i), min(TUILE, h - j)
            out[j:j + th, i:i + tl] = _tuile(service, code, xmin + i, ymax - j - th, tl, th)
    return out


def classes_2019_2020(code: int, xmin: int, ymax: int, l: int, h: int) -> tuple[np.ndarray, np.ndarray, str]:
    """Classes de 2019 et de 2020 pour dater les changements, avec la source utilisée."""
    if os.environ.get("DATATION") != "service" and all(p.exists() for p in CARTES.values()):
        return classes_annee(2019, xmin, ymax, l, h), classes_annee(2020, xmin, ymax, l, h), "cartes WalOUS 2019 et 2020"
    return mosaique(CHA19, code, xmin, ymax, l, h), mosaique(CHA20, code, xmin, ymax, l, h), "services de changements 2018-2019 et 2018-2020"


def controle_service(code: int, xmin: int, ymax: int, l: int, h: int, c23: np.ndarray) -> dict | None:
    """Les images du service, si elles sont en cache, redonnent-elles la classe 2023 du raster ? (None sinon)"""
    if not any(CACHE_SERVICES.glob(f"{CHANGEMENT}_{code}_*.png")):
        return None
    s23 = mosaique(CHANGEMENT, code, xmin, ymax, l, h)
    change = c23 > 0
    return {"pixels_changes": int(change.sum()), "classe23_identique_pct": round(float((s23[change] == c23[change]).mean()) * 100, 3),
            "change_service_hors_raster": int(((s23 > 0) & ~change).sum())}
