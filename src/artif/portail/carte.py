"""Carte des communes : tracés SVG, voisinages et frontières entre bassins, depuis la topologie des limites communales."""
import json

import pandas as pd

from .parametres import GEOMETRIE


def voisins_et_chemins(communes: pd.DataFrame) -> tuple[dict, dict, str, dict]:
    """Chemins SVG en Lambert 72, voisins par arcs partagés et frontières entre bassins.

    Retourne (chemin SVG par commune, voisins triés par commune, tracé des frontières entre bassins, cadre de la vue).
    """
    topo = json.loads(GEOMETRIE.read_text(encoding="utf-8"))
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:  # TopoJSON : coordonnées quantifiées et écrites en différences
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
            a = arcs[i] if i >= 0 else arcs[~i][::-1]  # un indice négatif parcourt l'arc à l'envers
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
        if len(codes) == 2:  # un arc partagé par deux communes : elles sont voisines
            a, b = sorted(codes)
            voisins[a].add(b)
            voisins[b].add(a)
            if bassin.get(a) != bassin.get(b):
                frontieres.append("M" + "L".join(svg(p) for p in arcs[i]))
    return chemins, {c: sorted(v) for c, v in voisins.items()}, "".join(frontieres), vue
