"""Écriture de l'étalement pour le site : portail/data/etalement/<code>.json, lu par la fiche communale (app.js).

Les tracés sont en mètres depuis le coin haut-gauche de la carte (y vers le bas), arrondis au mètre et simplifiés :
la carte se superpose ainsi aux photos aériennes, calées sur la même grille Lambert 72.
"""
import json

import geopandas as gpd
import numpy as np

from ..config import ROOT
from .analyse import Etalement
from .walous import CLASSES

DOSSIER = ROOT / "portail" / "data" / "etalement"
MARGE_M = 60  # mètres autour de la commune
# Tolérance de simplification des tracés, en mètres
TOL_TACHE, TOL_PARCELLE, TOL_CONTOUR, TOL_ZONE = 0.6, 0.5, 2, 3


def chemin_svg(geom, ox: float, oy: float, tol: float) -> str:
    """Tracé SVG d'un polygone ou multipolygone, en mètres depuis (ox, oy), sans points répétés après arrondi."""
    g = geom.simplify(tol, preserve_topology=True) if tol else geom
    morceaux = []
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        for anneau in [p.exterior, *p.interiors]:
            pts, prec = [], None
            for x, y in anneau.coords[:-1]:
                q = (round(x - ox), round(oy - y))
                if q != prec:
                    pts.append(q)
                    prec = q
            if len(pts) >= 3:
                morceaux.append("M" + "L".join(f"{a} {b}" for a, b in pts) + "Z")
    return "".join(morceaux)


def contenu(e: Etalement) -> dict:
    """Le JSON d'une commune."""
    xmin, ymin, xmax, ymax = e.limite.total_bounds
    ox, oy = np.floor(xmin) - MARGE_M, np.ceil(ymax) + MARGE_M
    largeur, hauteur = int(np.ceil(xmax - ox + MARGE_M)), int(np.ceil(oy - ymin + MARGE_M))

    taches = []
    for (g, m2, cl), a in zip(zip(e.taches.geometry, e.taches["m2"], e.taches["classe"]), e.attributs.itertuples()):
        d = chemin_svg(g, ox, oy, TOL_TACHE)
        if not d:
            continue
        taches.append({"d": d, "m2": round(float(m2)), "c": CLASSES[cl], "a": CLASSES[a.avant],
                       "z": a.zone, "ce": bool(a.centralite), "p": a.parcelle if isinstance(a.parcelle, str) else None,
                       "an": int(a.periode)})

    # Parcelles où un bâtiment est apparu : contour, surface, emprise du bâtiment neuf
    baties = e.parcelles[e.parcelles["CaPaKey"].isin(e.par_parcelle.index)].dissolve("CaPaKey")
    parcelles = {k: {"d": chemin_svg(g, ox, oy, TOL_PARCELLE), "m2": round(float(e.surf_parc[k])), "bati": round(float(e.par_parcelle[k]))}
                 for k, g in zip(baties.index, baties.geometry)}

    zl = gpd.overlay(e.zones[["famille", "geometry"]], e.limite[["geometry"]], how="intersection", keep_geom_type=True).dissolve("famille")
    centr = gpd.overlay(e.centralites[["geometry"]], e.limite[["geometry"]], how="intersection").union_all()
    return {
        "code": e.code, "nom": e.nom, "largeur": largeur, "hauteur": hauteur,
        "lambert_x0": float(ox), "lambert_y0": float(oy),
        "contour": chemin_svg(e.limite.geometry.iloc[0], ox, oy, TOL_CONTOUR),
        "zones": {f: chemin_svg(g, ox, oy, TOL_ZONE) for f, g in zip(zl.index, zl.geometry)},
        "centralites": chemin_svg(centr, ox, oy, TOL_ZONE),
        "taches": taches, "parcelles": parcelles,
        "resume": e.resume,
    }


def ecrit(e: Etalement) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    sortie = contenu(e)
    f = DOSSIER / f"{e.code}.json"
    f.write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  export : {len(sortie['taches'])} taches, {len(sortie['parcelles'])} parcelles, {f.stat().st_size / 1e6:.2f} Mo")


def ecrit_wallonie(totaux: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / "wallonie.json").write_text(json.dumps(totaux), encoding="utf-8")
