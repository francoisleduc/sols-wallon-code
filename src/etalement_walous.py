"""Étalement observé sur photos aériennes (WalOUS 2018 -> 2023), croisé avec le plan de secteur, les centralités et les parcelles.

Sources (toutes ouvertes) :
- SPW, « Occupation du sol en Wallonie - WALOUS changement entre les années 2018 et 2023 » (CC BY 4.0),
  https://geodata.wallonie.be/id/03300ff8-5e1d-430d-876a-ffd1b9103e78 ;
- SPW, « Occupation du sol en Wallonie - WALOUS 2018 » (CC BY 4.0) ;
- SPW, plan de secteur et centralités du SDT (CC BY 4.0) ;
- SPF Finances, plan parcellaire cadastral au 1er janvier 2025 (licence open data du SPF).

Données : le raster officiel (1 m, EPSG:3812, 1,1 Go zippé), à placer dans data/raw/spw_walous/cha_2018_2023/.
Chaque valeur vaut code 2018 x 100 + code 2023 ; seuls les pixels qui ont changé sont renseignés.
Contrôle croisé : si les images du service cartographique du SPW sont en cache (data/raw/spw_pilote/walous/),
on vérifie qu'elles redonnent la même classe 2023, pixel par pixel.

Un pixel est « nouvellement artificialisé » s'il a changé entre 2018 et 2023, que sa classe 2023 est artificielle
(revêtement, construction, voie ferrée) et que sa classe 2018 ne l'était pas. L'inverse donne les pixels
« désartificialisés ».

Usage : .venv/Scripts/python.exe -X utf8 src/etalement_walous.py
"""
from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.windows
from PIL import Image
from rasterio.transform import from_origin
from shapely.geometry import shape

import pilote_parcelles as pp

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / "data" / "raw" / "spw_pilote" / "walous"
SORTIE = RACINE / "data" / "processed" / "etalement"
SERVICES = "https://geoservices.wallonie.be/arcgis/rest/services/SOL_SOUS_SOL"
CHANGEMENT, OCS2018 = "WAL_OCS_IA_CHA_18_23", "WALOUS_OCCUPATION_SOL"
# Changements 2018-2019 et 2018-2020 : classe de 2019 ou 2020 là où le sol a changé (même producteur, autre version du modèle)
CHA19, CHA20 = "WAL_OCS_IA__CHA_18_19", "WAL_OCS_IA__CHA_18_20"
PERIODES = ["2018-2019", "2019-2020", "2020-2023"]
TUILE = 4096           # pixels, la taille maximale acceptée par le service
SURFACE_MIN = 30       # m², surface minimale d'un bâtiment neuf (après retrait des liserés)
ABORDS_M = 10          # m, distance aux nouveaux bâtiments dans laquelle un revêtement neuf est retenu
PARCELLE_MIN = 10      # m² de bâtiment neuf pour qu'une parcelle compte comme « bâtie »
CRS_WALOUS = "EPSG:3812"

# Classes et couleurs exactes du rendu de chaque service (lues dans leur légende)
CLASSES = ["vide", "revetement", "construction", "rail", "sol_nu", "eau", "herbe_rotation", "herbe_permanente",
           "resineux_haut", "feuillus_haut", "resineux_bas", "feuillus_bas", "serre"]
ARTIFICIEL = {1, 2, 3}
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


def tuile(service: str, code: int, x0: int, y0: int, l: int, h: int) -> np.ndarray:
    """Classes d'une tuile (y croissant vers le bas), depuis le cache ou le service."""
    f = CACHE / f"{service}_{code}_{x0}_{y0}.png"
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
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
                print("  nouvel essai", e); time.sleep(5)
        f.write_bytes(data)
    a = np.array(Image.open(f).convert("RGBA"))
    cle = (a[..., 0].astype(np.int32) << 16) | (a[..., 1].astype(np.int32) << 8) | a[..., 2]
    classes = np.full(cle.shape, -1, np.int8)
    classes[a[..., 3] == 0] = 0
    for (r, g, b), c in COULEURS[service].items():
        classes[(cle == (r << 16 | g << 8 | b)) & (a[..., 3] > 0)] = c
    return classes


def mosaique(service: str, code: int, xmin: int, ymax: int, l: int, h: int) -> np.ndarray:
    out = np.zeros((h, l), np.int8)
    for j in range(0, h, TUILE):
        for i in range(0, l, TUILE):
            tl, th = min(TUILE, l - i), min(TUILE, h - j)
            out[j:j + th, i:i + tl] = tuile(service, code, xmin + i, ymax - j - th, tl, th)
    return out


RASTER = RACINE / "data" / "raw" / "spw_walous" / "cha_2018_2023" / "WAL_OCS_IA_CHA_SIEVED__2018_2023.tif"
# Codes WalOUS (table du raster) -> indices de CLASSES
CODES = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 80: 10, 90: 11}


def classes_raster(xmin: int, ymax: int, l: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Classes 2018 et 2023 de chaque pixel, lues dans le raster officiel (valeur = code 2018 x 100 + code 2023)."""
    vat = gpd.read_file(RASTER.with_name(RASTER.name + ".vat.dbf"))
    with rasterio.open(RASTER) as r:
        fen = rasterio.windows.from_bounds(xmin, ymax - h, xmin + l, ymax, r.transform).round_offsets().round_lengths()
        v = r.read(1, window=fen, boundless=True, fill_value=0)
    t18, t23 = np.zeros(65536, np.int8), np.zeros(65536, np.int8)
    for val, a, b in zip(vat["Value"], vat["Code18"], vat["Code23"]):
        t18[int(val)], t23[int(val)] = CODES[int(a)], CODES[int(b)]
    return t18[v], t23[v]


def controle_service(code, xmin, ymax, l, h, c23) -> dict | None:
    """Contrôle croisé : les images du service cartographique, si elles sont en cache, redonnent-elles la classe 2023 ?"""
    if not any(CACHE.glob(f"{CHANGEMENT}_{code}_*.png")):
        return None
    s23 = mosaique(CHANGEMENT, code, xmin, ymax, l, h)
    change = c23 > 0
    return {"pixels_changes": int(change.sum()), "classe23_identique_pct": round(float((s23[change] == c23[change]).mean()) * 100, 3),
            "change_service_hors_raster": int(((s23 > 0) & ~change).sum())}


def _decale(m: np.ndarray, op) -> np.ndarray:
    """Érosion (op = &) ou dilatation (op = |) par un carré de 3 x 3 pixels."""
    o = m.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        cible = o[max(dy, 0):o.shape[0] + min(dy, 0), max(dx, 0):o.shape[1] + min(dx, 0)]
        source = m[max(-dy, 0):m.shape[0] + min(-dy, 0), max(-dx, 0):m.shape[1] + min(-dx, 0)]
        op(cible, source, out=cible)
    return o


def ouverture(m: np.ndarray) -> np.ndarray:
    """Retire les liserés de moins de 3 m de large (bords de classes), garde le reste de la tache intact."""
    return _decale(_decale(m, np.logical_and), np.logical_or) & m


def dilater(m: np.ndarray, metres: int) -> np.ndarray:
    for _ in range(metres):
        m = _decale(m, np.logical_or)
    return m


def surfaces(m: np.ndarray) -> np.ndarray:
    """Pour chaque pixel du masque, la surface (m²) de sa tache connexe (8 voisins)."""
    formes = rasterio.features.shapes(m.astype(np.uint8), mask=m, connectivity=8)
    lab = rasterio.features.rasterize(((g, i + 1) for i, (g, _) in enumerate(formes)), out_shape=m.shape, fill=0, dtype="int32")
    n = np.bincount(lab.ravel()).astype(np.int32)
    n[0] = 0
    return n[lab]


def vectoriser(masque: np.ndarray, valeurs: np.ndarray, transform) -> gpd.GeoDataFrame:
    geoms, vals = [], []
    for g, v in rasterio.features.shapes(valeurs.astype(np.int16), mask=masque, transform=transform, connectivity=8):
        geoms.append(shape(g)); vals.append(int(v))
    return gpd.GeoDataFrame({"classe": vals}, geometry=geoms, crs=CRS_WALOUS)


def analyse(code: int, nom: str) -> dict:
    limite = pp.couche(code, pp.PARCELLES, "Apn_CaDi").dissolve()
    lim3812 = limite.to_crs(CRS_WALOUS)
    xmin, ymin, xmax, ymax = lim3812.total_bounds
    xmin, ymin, xmax, ymax = int(np.floor(xmin)) - 5, int(np.floor(ymin)) - 5, int(np.ceil(xmax)) + 5, int(np.ceil(ymax)) + 5
    l, h = xmax - xmin, ymax - ymin
    print(f"{nom} : {l} x {h} pixels")
    c18, c23 = classes_raster(xmin, ymax, l, h)
    transform = from_origin(xmin, ymax, 1, 1)
    controle = controle_service(code, xmin, ymax, l, h, c23)
    dedans = rasterio.features.geometry_mask(lim3812.geometry, (h, l), transform, invert=True)

    change = dedans & (c23 > 0)
    inconnus = int((dedans & ((c23 < 0) | (c18 < 0))).sum())
    meme = int((change & (c18 == c23)).sum())           # changé selon le produit mais même classe en 2018 : contrôle
    a18, a23 = np.isin(c18, list(ARTIFICIEL)), np.isin(c23, list(ARTIFICIEL))
    brut_neuf, brut_retour = change & a23 & ~a18, change & a18 & ~a23
    # Règle retenue (voir le module) : bâtiments neufs nets, et revêtements neufs à leurs abords
    bat = ouverture(change & (c23 == 2) & ~a18)
    bat &= surfaces(bat) >= SURFACE_MIN
    abords = change & np.isin(c23, [1, 3]) & ~a18 & dilater(bat, ABORDS_M)
    neuf = bat | abords
    # Contrôle du bruit : la même règle appliquée au mouvement inverse (ce qui « disparaît »)
    bat_inv = ouverture(change & (c18 == 2) & ~a23)
    bat_inv &= surfaces(bat_inv) >= SURFACE_MIN
    abords_inv = change & np.isin(c18, [1, 3]) & ~a23 & dilater(bat, ABORDS_M)
    avant = pd.Series(c18[neuf]).map(dict(enumerate(CLASSES))).value_counts()

    taches = vectoriser(neuf, np.where(bat, 2, 1), transform).to_crs(pp.CRS)
    taches["m2"] = taches.area
    zones = pp.requete_arcgis(pp.PDS, limite.total_bounds, pp.SPW / f"pds_{code}.geojson")
    zones["famille"] = zones["AFFECT"].map(pp.famille)
    centr = pp.requete_arcgis(pp.CENTR, limite.total_bounds, pp.SPW / f"centralites_{code}.geojson")
    parc = pp.couche(code, pp.PARCELLES, "Bpn_CaPa")

    z = gpd.overlay(taches[["classe", "geometry"]], zones[["famille", "geometry"]], how="intersection", keep_geom_type=True)
    z["m2"] = z.area
    par_famille = z.groupby(["famille", "classe"])["m2"].sum().unstack(fill_value=0) / 1e4
    zl = gpd.overlay(zones[["famille", "geometry"]], limite[["geometry"]], how="intersection", keep_geom_type=True)
    territoire = zl.assign(ha=zl.area / 1e4).groupby("famille")["ha"].sum()
    cz = gpd.overlay(taches[["classe", "geometry"]], centr[["geometry"]].dissolve(), how="intersection", keep_geom_type=True)
    tp = gpd.overlay(taches[taches["classe"] == 2][["geometry"]], parc[["CaPaKey", "geometry"]], how="intersection", keep_geom_type=True)
    tp["m2"] = tp.area
    par_parcelle = tp.groupby("CaPaKey")["m2"].sum()
    par_parcelle = par_parcelle[par_parcelle >= PARCELLE_MIN]
    surf_parc = parc.set_index("CaPaKey").geometry.area.groupby(level=0).sum()

    flux = None
    try:
        idx = json.loads((RACINE / "portail" / "data" / "index.json").read_text(encoding="utf-8"))
        prem = idx["meta"]["derniere_annee_flux"] - len(json.loads((RACINE / "portail" / "data" / "communes" / f"{str(code)[:2]}.json").read_text(encoding="utf-8"))[str(code)]["flux"]) + 1
        fl = json.loads((RACINE / "portail" / "data" / "communes" / f"{str(code)[:2]}.json").read_text(encoding="utf-8"))[str(code)]["flux"]
        flux = {"annees": [2018, 2022], "ha": round(sum(fl[a - prem] for a in range(2018, 2023)), 1)}
    except (KeyError, FileNotFoundError) as e:
        print("  flux cadastral introuvable", e)

    ha = lambda m: round(float(m) / 1e4, 2)
    col = lambda k: par_famille[k] if k in par_famille else pd.Series(dtype=float)
    resume = {
        "code": code, "nom": nom, "superficie_ha": round(float(limite.area.iloc[0]) / 1e4, 1),
        "controles": {"pixels_inconnus": inconnus, "pixels_meme_classe": meme, "service": controle},
        "brut": {"neuf_ha": ha(brut_neuf.sum()), "retour_ha": ha(brut_retour.sum())},
        "batiments_ha": ha(bat.sum()), "abords_ha": ha(abords.sum()), "neuf_ha": ha(neuf.sum()),
        "bruit": {"batiments_inverses_ha": ha(bat_inv.sum()), "abords_inverses_ha": ha(abords_inv.sum())},
        "avant": {k: ha(v) for k, v in avant.items()},
        "par_famille": {k: {"batiments_ha": round(float(col(2).get(k, 0)), 2), "abords_ha": round(float(col(1).get(k, 0)), 2)}
                        for k in par_famille.index},
        "territoire_par_famille_ha": {k: round(float(v), 1) for k, v in territoire.items()},
        "centralite": {"batiments_ha": ha(cz[cz["classe"] == 2].area.sum()), "neuf_ha": ha(cz.area.sum()),
                       "part_territoire_pct": round(float(gpd.overlay(centr[["geometry"]], limite[["geometry"]], how="intersection").area.sum() / limite.area.iloc[0] * 100), 1)},
        "parcelles": {"nombre": int(len(par_parcelle)), "surface_ha": ha(surf_parc.reindex(par_parcelle.index).sum()),
                      "batiments_ha": ha(par_parcelle.sum())},
        "flux_cadastre": flux,
    }
    SORTIE.mkdir(parents=True, exist_ok=True)
    taches.to_file(SORTIE / f"taches_{code}.geojson", driver="GeoJSON")
    par_parcelle.rename("m2_neufs").to_csv(SORTIE / f"parcelles_{code}.csv")
    c19, c20 = mosaique(CHA19, code, xmin, ymax, l, h), mosaique(CHA20, code, xmin, ymax, l, h)
    exporter(code, nom, resume, limite, zones, centr, parc, taches, neuf, c18, transform, par_parcelle, surf_parc, c19, c20)
    return resume


# ---------- Export vers le portail ----------
PORTAIL_ETALEMENT = RACINE / "portail" / "data" / "etalement"
MARGE = 60  # mètres autour de la commune


def _chemin(geom, ox: float, oy: float, tol: float) -> str:
    """Tracé SVG en mètres depuis le coin haut-gauche (y vers le bas), arrondi au mètre."""
    g = geom.simplify(tol, preserve_topology=True) if tol else geom
    morceaux = []
    polys = getattr(g, "geoms", [g])
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        for anneau in [p.exterior, *p.interiors]:
            pts, prec = [], None
            for x, y in anneau.coords[:-1]:
                q = (round(x - ox), round(oy - y))
                if q != prec:
                    pts.append(q); prec = q
            if len(pts) >= 3:
                morceaux.append("M" + "L".join(f"{a} {b}" for a, b in pts) + "Z")
    return "".join(morceaux)


def exporter(code, nom, resume, limite, zones, centr, parc, taches, neuf, c18, transform, par_parcelle, surf_parc, c19, c20) -> None:
    xmin, ymin, xmax, ymax = limite.total_bounds
    ox, oy = np.floor(xmin) - MARGE, np.ceil(ymax) + MARGE
    largeur, hauteur = int(np.ceil(xmax - ox + MARGE)), int(np.ceil(oy - ymin + MARGE))
    contour = limite.geometry.iloc[0]

    # Classe 2018 dominante de chaque tache : on repasse les taches en raster (grille WalOUS) et on compte
    t3812 = taches.to_crs(CRS_WALOUS)
    ids = rasterio.features.rasterize(((g, i + 1) for i, g in enumerate(t3812.geometry)), out_shape=c18.shape, transform=transform, fill=0, dtype="int32")
    sel = neuf & (ids > 0)
    comptes = pd.DataFrame({"id": ids[sel] - 1, "c18": c18[sel]}).value_counts().reset_index(name="n")
    avant = comptes.sort_values("n", ascending=False).drop_duplicates("id").set_index("id")["c18"]

    # Datation : une tache est « déjà là » en 2019 (ou 2020) si la moitié de ses pixels y est déjà bâtie (ou revêtue, pour les abords)
    classe_px = np.asarray(taches["classe"])[ids[sel] - 1]
    deja = lambda c: np.where(classe_px == 2, c[sel] == 2, np.isin(c[sel], [1, 2, 3]))
    d19, d20 = deja(c19), deja(c20)
    n_px = np.bincount(ids[sel] - 1, minlength=len(taches))
    f19 = np.bincount(ids[sel] - 1, weights=d19, minlength=len(taches)) / np.maximum(n_px, 1)
    f20 = np.bincount(ids[sel] - 1, weights=d20, minlength=len(taches)) / np.maximum(n_px, 1)
    periode = np.where(f19 >= 0.5, 0, np.where(f20 >= 0.5, 1, 2))
    m2 = taches["m2"].to_numpy()
    resume["periodes"] = {PERIODES[k]: {"batiments_ha": round(float(m2[(periode == k) & (taches["classe"].to_numpy() == 2)].sum()) / 1e4, 2),
                                        "abords_ha": round(float(m2[(periode == k) & (taches["classe"].to_numpy() == 1)].sum()) / 1e4, 2)}
                          for k in range(3)}
    # Contrôle : une tache vue en 2019 doit l'être encore en 2020 (sinon, le classement de 2019 ou de 2020 se trompe)
    vu19 = f19 >= 0.5
    resume["controles"]["datation_incoherente_pct"] = round(float(m2[vu19 & (f20 < 0.5)].sum() / max(m2[vu19].sum(), 1)) * 100, 1)

    # Zone du plan de secteur et centralité de chaque tache (par la plus grande part de sa surface)
    tz = gpd.overlay(taches[["geometry"]].assign(id=range(len(taches))), zones[["famille", "geometry"]], how="intersection", keep_geom_type=True)
    tz["a"] = tz.area
    zone_de = tz.sort_values("a", ascending=False).drop_duplicates("id").set_index("id")
    tc = gpd.overlay(taches[["geometry"]].assign(id=range(len(taches))), centr[["geometry"]].dissolve(), how="intersection", keep_geom_type=True)
    aires = pd.Series(taches.area.values, index=range(len(taches)))
    en_centr = (tc.assign(a=tc.area).groupby("id")["a"].sum() / aires).reindex(range(len(taches))).fillna(0)
    tp = gpd.overlay(taches[["geometry"]].assign(id=range(len(taches))), parc[["CaPaKey", "geometry"]], how="intersection", keep_geom_type=True)
    tp["a"] = tp.area
    parc_de = tp.sort_values("a", ascending=False).drop_duplicates("id").set_index("id")["CaPaKey"]
    parc_de = parc_de[parc_de.isin(par_parcelle.index)]

    lignes = []
    for i, (g, m2, cl) in enumerate(zip(taches.geometry, taches["m2"], taches["classe"])):
        d = _chemin(g, ox, oy, 0.6)
        if not d:
            continue
        lignes.append({"d": d, "m2": round(float(m2)), "c": CLASSES[cl], "a": CLASSES[int(avant.get(i, 0))],
                       "z": zone_de["famille"].get(i, "hors plan"), "ce": bool(en_centr[i] >= 0.5),
                       "p": parc_de.get(i), "an": int(periode[i])})

    # Parcelles où un bâtiment est apparu : contour, surface, emprise du bâtiment neuf
    baties = parc[parc["CaPaKey"].isin(par_parcelle.index)].dissolve("CaPaKey")
    parcelles = {k: {"d": _chemin(g, ox, oy, 0.5), "m2": round(float(surf_parc[k])), "bati": round(float(par_parcelle[k]))}
                 for k, g in zip(baties.index, baties.geometry)}

    zl = gpd.overlay(zones[["famille", "geometry"]], limite[["geometry"]], how="intersection", keep_geom_type=True).dissolve("famille")
    sortie = {
        "code": code, "nom": nom, "largeur": largeur, "hauteur": hauteur,
        "lambert_x0": float(ox), "lambert_y0": float(oy),
        "contour": _chemin(contour, ox, oy, 2),
        "zones": {f: _chemin(g, ox, oy, 3) for f, g in zip(zl.index, zl.geometry)},
        "centralites": _chemin(gpd.overlay(centr[["geometry"]], limite[["geometry"]], how="intersection").union_all(), ox, oy, 3),
        "taches": lignes, "parcelles": parcelles,
        "resume": resume,
    }
    PORTAIL_ETALEMENT.mkdir(parents=True, exist_ok=True)
    (PORTAIL_ETALEMENT / f"{code}.json").write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  export : {len(lignes)} taches, {len(parcelles)} parcelles, {(PORTAIL_ETALEMENT / f'{code}.json').stat().st_size / 1e6:.2f} Mo")


def wallonie() -> dict:
    """Changements bruts sur toute la Wallonie, depuis la table du raster : pour montrer l'ampleur du bruit de classement."""
    v = gpd.read_file(RASTER.with_name(RASTER.name + ".vat.dbf"))
    v = v[v["Value"] > 0]
    a18, a23 = v["Code18"].isin([1, 2, 3]), v["Code23"].isin([1, 2, 3])
    ha = lambda m: round(float(v.loc[m, "Count"].sum()) / 1e4)
    sortie = {"neuf_ha": ha(~a18 & a23), "retour_ha": ha(a18 & ~a23),
              "constructions_neuves_ha": ha(~a18 & (v["Code23"] == 2)), "constructions_disparues_ha": ha((v["Code18"] == 2) & ~a23)}
    PORTAIL_ETALEMENT.mkdir(parents=True, exist_ok=True)
    (PORTAIL_ETALEMENT / "wallonie.json").write_text(json.dumps(sortie), encoding="utf-8")
    return sortie


if __name__ == "__main__":
    print("Wallonie, changements bruts :", wallonie())
    resumes = [analyse(c, n) for c, n in pp.COMMUNES.items()]
    (SORTIE / "resume.json").write_text(json.dumps(resumes, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in resumes:
        print(json.dumps(r, ensure_ascii=False, indent=1))
