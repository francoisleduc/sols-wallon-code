"""L'étalement d'une commune vu du ciel : ce qui a été bâti entre 2018 et 2023, et où.

Règle retenue (décrite sur la page Méthode du site) :
- un bâtiment neuf est un pixel classé « construction » en 2023 et non artificiel en 2018, après retrait des liserés
  de moins de 3 m (ouverture morphologique), dans une tache d'au moins 30 m² ;
- s'y ajoutent les revêtements et voies neufs à moins de 10 m d'un bâtiment neuf (« abords »).
Les changements bruts de WalOUS sont surtout du bruit de classement : la même règle appliquée au mouvement inverse
(ce qui « disparaît ») mesure ce bruit.

Chaque tache est ensuite datée (2018-2019, 2019-2020 ou 2020-2023) et rattachée à la zone du plan de secteur, à la
centralité et à la parcelle cadastrale qui en portent la plus grande part.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio.features
from rasterio.transform import from_origin

from ..config import PROCESSED, ROOT
from . import amenagement, parcelles, walous
from .morphologie import dilater, ouverture, surfaces, vectoriser
from .walous import CONSTRUCTION, RAIL, REVETEMENT

SORTIE = PROCESSED / "etalement"
SURFACE_MIN = 30       # m², surface minimale d'un bâtiment neuf (après retrait des liserés)
ABORDS_M = 10          # m, distance aux nouveaux bâtiments dans laquelle un revêtement neuf est retenu
PARCELLE_MIN = 10      # m² de bâtiment neuf pour qu'une parcelle compte comme « bâtie »
MARGE_PX = 5           # pixels lus autour de la commune
PERIODES = ["2018-2019", "2019-2020", "2020-2023"]
DEJA_LA = 0.5          # part d'une tache déjà bâtie (ou revêtue) sur une carte pour la dater de cette carte
ANNEES_CADASTRE = (2018, 2022)   # flux cadastraux du 1/1/2018 au 1/1/2023, la même période que WalOUS


@dataclass
class Etalement:
    """Résultat de l'analyse d'une commune, prêt pour l'export vers le site."""
    code: int
    nom: str
    resume: dict                 # chiffres de la fiche
    limite: gpd.GeoDataFrame     # contour (Lambert 72)
    zones: gpd.GeoDataFrame      # plan de secteur autour de la commune
    centralites: gpd.GeoDataFrame
    parcelles: gpd.GeoDataFrame  # plan parcellaire 2025
    taches: gpd.GeoDataFrame     # une ligne par tache : classe (2 bâtiment, 1 abords), m2, geometry
    attributs: pd.DataFrame      # par tache : classe 2018 dominante, période, zone, centralité, parcelle
    par_parcelle: pd.Series      # m² de bâtiment neuf par parcelle bâtie
    surf_parc: pd.Series         # surface de chaque parcelle (m²)


def _flux_cadastre(code: int) -> dict | None:
    """Flux cadastral de la commune sur la même période, lu dans les données du portail (déjà construites)."""
    try:
        idx = json.loads((ROOT / "portail" / "data" / "index.json").read_text(encoding="utf-8"))
        fiche = json.loads((ROOT / "portail" / "data" / "communes" / f"{code // 1000}.json").read_text(encoding="utf-8"))[str(code)]
    except (KeyError, FileNotFoundError) as e:
        print("  flux cadastral introuvable", e)
        return None
    premiere = idx["meta"]["derniere_annee_flux"] - len(fiche["flux"]) + 1
    a0, a1 = ANNEES_CADASTRE
    return {"annees": [a0, a1], "ha": round(sum(fiche["flux"][a - premiere] for a in range(a0, a1 + 1)), 1)}


def _plus_grande_part(taches: gpd.GeoDataFrame, couche: gpd.GeoDataFrame, colonne: str) -> pd.Series:
    """Pour chaque tache (par sa position), la valeur de `colonne` dans l'entité de `couche` qui en couvre le plus."""
    t = gpd.overlay(taches[["geometry"]].assign(id=range(len(taches))), couche[[colonne, "geometry"]], how="intersection", keep_geom_type=True)
    t["a"] = t.area
    return t.sort_values("a", ascending=False).drop_duplicates("id").set_index("id")[colonne]


def surface_par_famille(taches: gpd.GeoDataFrame, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Hectares de chaque classe de tache (lignes : famille de zone, colonnes : classe).

    La couche du plan de secteur a, par endroits, des zones qui se recouvrent (Arlon) et des trous le long des
    frontières régionales (La Hulpe, Aubange). Chaque tache compte donc pour sa surface exacte : là où des zones se
    recouvrent, leurs parts sont réduites en proportion ; ce qu'aucune zone ne couvre va « hors plan ».
    """
    t = taches[["classe", "geometry"]].assign(id=range(len(taches)), aire=taches.area)
    z = gpd.overlay(t, zones[["famille", "geometry"]], how="intersection", keep_geom_type=True)
    z["m2"] = z.area
    couvert = z.groupby("id")["m2"].sum().reindex(t["id"], fill_value=0).to_numpy()
    aire = t["aire"].to_numpy()
    z["m2"] *= z["id"].map(dict(enumerate(np.minimum(1, aire / np.maximum(couvert, 1e-9)))))
    hors = t.assign(famille="hors plan", m2=np.maximum(aire - couvert, 0))
    tout = pd.concat([z[["famille", "classe", "m2"]], hors[["famille", "classe", "m2"]]])
    ha = tout.groupby(["famille", "classe"])["m2"].sum().unstack(fill_value=0) / 1e4
    minuscule = (ha.index == "hors plan") & (ha.sum(axis=1) < 0.005)   # restes d'arrondi des contours
    return ha[~minuscule]


def _attributs(taches, neuf, c18, c19, c20, transform, zones, centr, parc, par_parcelle) -> tuple[pd.DataFrame, dict, float]:
    """Classe 2018 dominante, période, zone, centralité et parcelle de chaque tache.

    Retourne aussi les surfaces par période et la part de surface vue bâtie en 2019 qui ne l'est plus en 2020.
    """
    n = len(taches)
    # On repasse les taches en raster sur la grille WalOUS pour compter leurs pixels
    ids = rasterio.features.rasterize(((g, i + 1) for i, g in enumerate(taches.to_crs(walous.CRS).geometry)),
                                      out_shape=c18.shape, transform=transform, fill=0, dtype="int32")
    sel = neuf & (ids > 0)
    id_px = ids[sel] - 1
    comptes = pd.DataFrame({"id": id_px, "c18": c18[sel]}).value_counts().reset_index(name="n")
    avant = comptes.sort_values("n", ascending=False).drop_duplicates("id").set_index("id")["c18"]

    # Datation : une tache est « déjà là » en 2019 (ou 2020) si la moitié de ses pixels y est déjà bâtie
    # (ou revêtue, pour les abords)
    classe_px = np.asarray(taches["classe"])[id_px]

    def deja(c):
        return np.where(classe_px == CONSTRUCTION, c[sel] == CONSTRUCTION, np.isin(c[sel], list(walous.ARTIFICIEL)))

    n_px = np.bincount(id_px, minlength=n)
    f19 = np.bincount(id_px, weights=deja(c19), minlength=n) / np.maximum(n_px, 1)
    f20 = np.bincount(id_px, weights=deja(c20), minlength=n) / np.maximum(n_px, 1)
    periode = np.where(f19 >= DEJA_LA, 0, np.where(f20 >= DEJA_LA, 1, 2))
    m2 = taches["m2"].to_numpy()
    classe = taches["classe"].to_numpy()
    par_periode = {PERIODES[k]: {"batiments_ha": round(float(m2[(periode == k) & (classe == CONSTRUCTION)].sum()) / 1e4, 2),
                                 "abords_ha": round(float(m2[(periode == k) & (classe == REVETEMENT)].sum()) / 1e4, 2)}
                   for k in range(len(PERIODES))}
    # Contrôle : une tache vue en 2019 doit l'être encore en 2020 (sinon, le classement de 2019 ou de 2020 se trompe)
    vu19 = f19 >= DEJA_LA
    incoherente_pct = round(float(m2[vu19 & (f20 < DEJA_LA)].sum() / max(m2[vu19].sum(), 1)) * 100, 1)

    zone = _plus_grande_part(taches, zones, "famille")
    tc = gpd.overlay(taches[["geometry"]].assign(id=range(n)), centr[["geometry"]].dissolve(), how="intersection", keep_geom_type=True)
    en_centr = (tc.assign(a=tc.area).groupby("id")["a"].sum() / pd.Series(taches.area.values, index=range(n))).reindex(range(n)).fillna(0)
    parcelle = _plus_grande_part(taches, parc, "CaPaKey")
    parcelle = parcelle[parcelle.isin(par_parcelle.index)]
    attributs = pd.DataFrame({
        "avant": [int(avant.get(i, 0)) for i in range(n)],
        "periode": periode.astype(int),
        "zone": [zone.get(i, "hors plan") for i in range(n)],
        "centralite": (en_centr >= 0.5).to_numpy(),
        "parcelle": [parcelle.get(i) for i in range(n)],
    })
    return attributs, par_periode, incoherente_pct


def analyse(code: int, nom: str) -> Etalement:
    limite = parcelles.limite_communale(code)
    lim3812 = limite.to_crs(walous.CRS)
    xmin, ymin, xmax, ymax = lim3812.total_bounds
    xmin, ymin = int(np.floor(xmin)) - MARGE_PX, int(np.floor(ymin)) - MARGE_PX
    xmax, ymax = int(np.ceil(xmax)) + MARGE_PX, int(np.ceil(ymax)) + MARGE_PX
    l, h = xmax - xmin, ymax - ymin
    print(f"{nom} : {l} x {h} pixels")
    c18, c23 = walous.classes_2018_2023(xmin, ymax, l, h)
    transform = from_origin(xmin, ymax, 1, 1)
    controle = walous.controle_service(code, xmin, ymax, l, h, c23)
    dedans = rasterio.features.geometry_mask(lim3812.geometry, (h, l), transform, invert=True)

    # --- Détection ---
    change = dedans & (c23 > 0)
    inconnus = int((dedans & ((c23 < 0) | (c18 < 0))).sum())
    meme = int((change & (c18 == c23)).sum())           # changé selon le produit mais même classe en 2018 : contrôle
    a18, a23 = np.isin(c18, list(walous.ARTIFICIEL)), np.isin(c23, list(walous.ARTIFICIEL))
    brut_neuf, brut_retour = change & a23 & ~a18, change & a18 & ~a23
    bat = ouverture(change & (c23 == CONSTRUCTION) & ~a18)
    bat &= surfaces(bat) >= SURFACE_MIN
    abords = change & np.isin(c23, [REVETEMENT, RAIL]) & ~a18 & dilater(bat, ABORDS_M)
    neuf = bat | abords
    # Bruit : la même règle appliquée au mouvement inverse
    bat_inv = ouverture(change & (c18 == CONSTRUCTION) & ~a23)
    bat_inv &= surfaces(bat_inv) >= SURFACE_MIN
    abords_inv = change & np.isin(c18, [REVETEMENT, RAIL]) & ~a23 & dilater(bat, ABORDS_M)
    avant = pd.Series(c18[neuf]).map(dict(enumerate(walous.CLASSES))).value_counts()

    taches = vectoriser(neuf, np.where(bat, CONSTRUCTION, REVETEMENT), transform, walous.CRS).to_crs(parcelles.CRS)
    taches["m2"] = taches.area

    # --- Contexte : plan de secteur, centralités, parcelles ---
    zones = amenagement.zones(limite.total_bounds)
    centr = amenagement.centralites(limite.total_bounds)
    parc = parcelles.couche(code, "Bpn_CaPa")

    par_famille = surface_par_famille(taches, zones)
    zl = gpd.overlay(zones[["famille", "geometry"]], limite[["geometry"]], how="intersection", keep_geom_type=True)
    territoire = zl.assign(ha=zl.area / 1e4).groupby("famille")["ha"].sum()
    cz = gpd.overlay(taches[["classe", "geometry"]], centr[["geometry"]].dissolve(), how="intersection", keep_geom_type=True)
    tp = gpd.overlay(taches[taches["classe"] == CONSTRUCTION][["geometry"]], parc[["CaPaKey", "geometry"]], how="intersection", keep_geom_type=True)
    tp["m2"] = tp.area
    par_parcelle = tp.groupby("CaPaKey")["m2"].sum()
    par_parcelle = par_parcelle[par_parcelle >= PARCELLE_MIN]
    surf_parc = parc.set_index("CaPaKey").geometry.area.groupby(level=0).sum()

    def ha(m):
        return round(float(m) / 1e4, 2)

    def col(k):
        return par_famille[k] if k in par_famille else pd.Series(dtype=float)

    resume = {
        "code": code, "nom": nom, "superficie_ha": round(float(limite.area.iloc[0]) / 1e4, 1),
        "controles": {"pixels_inconnus": inconnus, "pixels_meme_classe": meme, "service": controle},
        "brut": {"neuf_ha": ha(brut_neuf.sum()), "retour_ha": ha(brut_retour.sum())},
        "batiments_ha": ha(bat.sum()), "abords_ha": ha(abords.sum()), "neuf_ha": ha(neuf.sum()),
        "bruit": {"batiments_inverses_ha": ha(bat_inv.sum()), "abords_inverses_ha": ha(abords_inv.sum())},
        "avant": {k: ha(v) for k, v in avant.items()},
        "par_famille": {k: {"batiments_ha": round(float(col(CONSTRUCTION).get(k, 0)), 2), "abords_ha": round(float(col(REVETEMENT).get(k, 0)), 2)}
                        for k in par_famille.index},
        "territoire_par_famille_ha": {k: round(float(v), 1) for k, v in territoire.items()},
        "centralite": {"batiments_ha": ha(cz[cz["classe"] == CONSTRUCTION].area.sum()), "neuf_ha": ha(cz.area.sum()),
                       "part_territoire_pct": round(float(gpd.overlay(centr[["geometry"]], limite[["geometry"]], how="intersection").area.sum() / limite.area.iloc[0] * 100), 1)},
        "parcelles": {"nombre": int(len(par_parcelle)), "surface_ha": ha(surf_parc.reindex(par_parcelle.index).sum()),
                      "batiments_ha": ha(par_parcelle.sum())},
        "flux_cadastre": _flux_cadastre(code),
    }
    SORTIE.mkdir(parents=True, exist_ok=True)
    taches.to_file(SORTIE / f"taches_{code}.geojson", driver="GeoJSON")   # lu par src/outils/photos_artifact.py
    par_parcelle.rename("m2_neufs").to_csv(SORTIE / f"parcelles_{code}.csv")

    # --- Datation et rattachement de chaque tache ---
    c19, c20, resume["controles"]["datation_source"] = walous.classes_2019_2020(code, xmin, ymax, l, h)
    attributs, resume["periodes"], resume["controles"]["datation_incoherente_pct"] = _attributs(
        taches, neuf, c18, c19, c20, transform, zones, centr, parc, par_parcelle)
    return Etalement(code, nom, resume, limite, zones, centr, parc, taches, attributs, par_parcelle, surf_parc)
