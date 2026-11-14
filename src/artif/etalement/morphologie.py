"""Opérations sur des masques raster (tableaux booléens, un pixel = 1 m²), en numpy seul."""
import geopandas as gpd
import numpy as np
import rasterio.features
from shapely.geometry import shape

VOISINS_8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))


def _decale(m: np.ndarray, op) -> np.ndarray:
    """Érosion (op = np.logical_and) ou dilatation (op = np.logical_or) par un carré de 3 x 3 pixels.

    Les bords du tableau ne sont pas complétés : un pixel du bord n'est comparé qu'à ses voisins existants.
    """
    o = m.copy()
    for dy, dx in VOISINS_8:
        cible = o[max(dy, 0):o.shape[0] + min(dy, 0), max(dx, 0):o.shape[1] + min(dx, 0)]
        source = m[max(-dy, 0):m.shape[0] + min(-dy, 0), max(-dx, 0):m.shape[1] + min(-dx, 0)]
        op(cible, source, out=cible)
    return o


def ouverture(m: np.ndarray) -> np.ndarray:
    """Retire les liserés de moins de 3 m de large (bords de classes), garde le reste de la tache intact."""
    return _decale(_decale(m, np.logical_and), np.logical_or) & m


def dilater(m: np.ndarray, metres: int) -> np.ndarray:
    """Élargit le masque de `metres` pixels dans toutes les directions (diagonales comprises)."""
    for _ in range(metres):
        m = _decale(m, np.logical_or)
    return m


def surfaces(m: np.ndarray) -> np.ndarray:
    """Pour chaque pixel du masque, la surface (m²) de sa tache connexe (8 voisins) ; 0 hors du masque."""
    formes = rasterio.features.shapes(m.astype(np.uint8), mask=m, connectivity=8)
    lab = rasterio.features.rasterize(((g, i + 1) for i, (g, _) in enumerate(formes)), out_shape=m.shape, fill=0, dtype="int32")
    n = np.bincount(lab.ravel()).astype(np.int32)
    n[0] = 0
    return n[lab]


def vectoriser(masque: np.ndarray, valeurs: np.ndarray, transform, crs: str) -> gpd.GeoDataFrame:
    """Polygones des taches du masque, une par valeur connexe, avec la valeur dans la colonne « classe »."""
    geoms, vals = [], []
    for g, v in rasterio.features.shapes(valeurs.astype(np.int16), mask=masque, transform=transform, connectivity=8):
        geoms.append(shape(g))
        vals.append(int(v))
    return gpd.GeoDataFrame({"classe": vals}, geometry=geoms, crs=crs)
