"""Photos aériennes des communes pilotes, pour la carte de l'étalement : un fond à 2 m et des vues à 0,5 m des chantiers.

Source : SPW, orthophotos annuelles 2018 à 2026 (CC BY 4.0), lues par le service cartographique du SPW, une requête
à la fois et gardées en cache dans data/raw/spw_ortho/. Les conditions des services du SPW interdisent un usage
« disproportionné » : on ne télécharge que ce qui sert, une seule fois.

- Fond : toute la commune à 2 m par pixel, pour 2018, 2023 et 2026, en tuiles de 2048 pixels (4 km).
- Chantiers : autour de chaque groupe de taches (taches à moins de 40 m les unes des autres, avec 40 m de marge),
  une fenêtre à 0,5 m par pixel pour chaque année de 2018 à 2026. Les fenêtres d'une année sont rangées dans des
  planches de 2048 pixels, à la même place chaque année.
- Certaines années, le vol ne couvre qu'une partie de la Wallonie (2022, 2024, 2025). On complète alors la vue d'été par
  celle de printemps de la même année, jamais par une autre année. Une vue encore trouée à plus de 2 % est notée
  manquante pour cette année : la carte montre alors le fond.

Sortie : portail/data/photos/<code>/index.json et les images JPEG.
Usage : .venv/Scripts/python.exe -X utf8 src/photos_etalement.py
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
from PIL import Image

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / "data" / "raw" / "spw_ortho"
ETAL = RACINE / "data" / "processed" / "etalement"
PORTAIL = RACINE / "portail" / "data"
SERVICE = "https://geoservices.wallonie.be/arcgis/rest/services/IMAGERIE/{}/MapServer/export"
ANNEES = {2018: ["ORTHO_2018"], 2019: ["ORTHO_2019"], 2020: ["ORTHO_2020"], 2021: ["ORTHO_2021"],
          2022: ["ORTHO_2022_ETE", "ORTHO_2022_PRINTEMPS"], 2023: ["ORTHO_2023_ETE"], 2024: ["ORTHO_2024"],
          2025: ["ORTHO_2025_ETE", "ORTHO_2025_PRINTEMPS"], 2026: ["ORTHO_2026_PRINTEMPS"]}
FOND_ANNEES, FOND_RES, FOND_PX = [2018, 2023, 2026], 2, 2048
TROU_MAX = 0.02
VUE_RES, MARGE, VUE_MAX_M = 0.5, 40, 512
PLANCHE = 2048
QUALITE = 62


def requete(service: str, x0: float, y0: float, l_m: float, h_m: float, px: tuple[int, int], fmt: str, cache: Path) -> bytes:
    """Une requête au service d'orthophotos (Lambert 72), gardée en cache. Une à la fois."""
    if cache.exists():
        return cache.read_bytes()
    cache.parent.mkdir(parents=True, exist_ok=True)
    p = {"bbox": f"{x0},{y0},{x0 + l_m},{y0 + h_m}", "bboxSR": 31370, "imageSR": 31370, "size": f"{px[0]},{px[1]}",
         "format": fmt, "f": "image", **({"transparent": "true"} if fmt == "png32" else {})}
    for essai in range(5):
        try:
            with urllib.request.urlopen(SERVICE.format(service) + "?" + urllib.parse.urlencode(p), timeout=300) as r:
                data = r.read()
            Image.open(io.BytesIO(data)).verify()
            break
        except Exception as e:  # noqa: BLE001
            if essai == 4:
                raise
            print("  nouvel essai", service, e); time.sleep(10 * (essai + 1))
    cache.write_bytes(data)
    time.sleep(0.2)
    return data


COUV_RES = 16   # m par pixel de la carte de couverture de chaque vol


def couverture(code: int, service: str, ox: float, oy: float, L: float, H: float) -> np.ndarray:
    """Où le vol couvre la commune : une seule vignette transparente par vol et par commune, à 16 m par pixel."""
    px = (int(np.ceil(L / COUV_RES)), int(np.ceil(H / COUV_RES)))
    data = requete(service, ox, oy - px[1] * COUV_RES, px[0] * COUV_RES, px[1] * COUV_RES, px, "png32",
                   CACHE / str(code) / "couverture" / f"{service}.png")
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))[..., 3] >= 128


def image(annee: int, x0: float, y0: float, l_m: float, h_m: float, res: float, cache: Path, couv) -> tuple[Image.Image, float]:
    """Vue d'une année. Un vol qui couvre toute la vue (d'après sa carte de couverture) est lu en JPEG ; une vue à cheval
    sur deux vols est lue en PNG transparent et complétée par l'autre vol de la même année. Rend l'image et la part trouée."""
    px = (round(l_m / res), round(h_m / res))
    part = {s: couv(s, x0, y0, l_m, h_m) for s in ANNEES[annee]}
    for s in ANNEES[annee]:
        if part[s] == 1:
            return Image.open(io.BytesIO(requete(s, x0, y0, l_m, h_m, px, "jpg", cache.with_name(f"{cache.name}_{s}.jpg")))).convert("RGB"), 0.0
    fond = Image.new("RGBA", px, (40, 44, 48, 0))
    for s in reversed([s for s in ANNEES[annee] if part[s] > 0]):   # le premier vol de la liste passe au-dessus
        im = Image.open(io.BytesIO(requete(s, x0, y0, l_m, h_m, px, "png32", cache.with_name(f"{cache.name}_{s}.png")))).convert("RGBA")
        fond = Image.alpha_composite(fond, im)
    trou = float((np.asarray(fond)[..., 3] < 128).mean())
    rgb = Image.new("RGB", px, (40, 44, 48))
    rgb.paste(fond, mask=fond.getchannel("A"))
    return rgb, trou


def fenetres(code: int) -> list[tuple[float, float, float, float]]:
    """Fenêtres (x0, y0, largeur, hauteur en m, Lambert 72) autour des groupes de taches, d'au plus 512 m de côté."""
    t = gpd.read_file(ETAL / f"taches_{code}.geojson")
    u = t.buffer(MARGE).union_all()
    sortie = []
    for g in sorted(getattr(u, "geoms", [u]), key=lambda g: (-g.bounds[3], g.bounds[0])):
        x0, y0, x1, y1 = (np.floor(g.bounds[0]), np.floor(g.bounds[1]), np.ceil(g.bounds[2]), np.ceil(g.bounds[3]))
        nx, ny = int(np.ceil((x1 - x0) / VUE_MAX_M)), int(np.ceil((y1 - y0) / VUE_MAX_M))
        lw, lh = np.ceil((x1 - x0) / nx), np.ceil((y1 - y0) / ny)
        for j in range(ny):
            for i in range(nx):
                sortie.append((float(x0 + i * lw), float(y0 + j * lh), float(lw), float(lh)))
    return sortie


def ranger(tailles: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """Rangement en étagères dans des planches carrées : (planche, x, y) pour chaque image, dans l'ordre donné."""
    ordre = sorted(range(len(tailles)), key=lambda i: -tailles[i][1])
    place = [None] * len(tailles)
    planche, x, y, haut = 0, 0, 0, 0
    for i in ordre:
        w, h = tailles[i]
        if x + w > PLANCHE:
            x, y, haut = 0, y + haut, 0
        if y + h > PLANCHE:
            planche, x, y, haut = planche + 1, 0, 0, 0
        place[i] = (planche, x, y)
        x, haut = x + w, max(haut, h)
    return place


def commune(code: int) -> dict:
    e = json.loads((PORTAIL / "etalement" / f"{code}.json").read_text(encoding="utf-8"))
    ox, oy, L, H = e["lambert_x0"], e["lambert_y0"], e["largeur"], e["hauteur"]
    dossier = PORTAIL / "photos" / str(code)
    dossier.mkdir(parents=True, exist_ok=True)
    index = {"annees": list(ANNEES), "fond": {"annees": FOND_ANNEES, "res": FOND_RES, "tuiles": []}, "vues": [], "planches": 0,
             "source": "SPW, orthophotos 2018 à 2026 (CC BY 4.0)", "manquantes": {}}

    masques = {}

    def couv(service, x0, y0, l_m, h_m):
        """Part des cellules de 16 m touchées par la fenêtre que le vol couvre (1 = toute la fenêtre)."""
        if service not in masques:
            masques[service] = couverture(code, service, ox, oy, L, H)
        m = masques[service]
        i0, i1 = int((x0 - ox) // COUV_RES), int(np.ceil((x0 + l_m - ox) / COUV_RES))
        j0, j1 = int((oy - y0 - h_m) // COUV_RES), int(np.ceil((oy - y0) / COUV_RES))
        bloc = m[max(j0, 0):max(j1, 0), max(i0, 0):max(i1, 0)]
        dehors = bloc.size < max(j1 - j0, 0) * max(i1 - i0, 0)
        return 0.5 if dehors and bloc.size else float(bloc.mean()) if bloc.size else 0.5

    # Fond à 2 m : tuiles de 4 km, calées sur le coin haut-gauche de la carte
    pas = FOND_PX * FOND_RES
    for j in range(int(np.ceil(H / pas))):
        for i in range(int(np.ceil(L / pas))):
            lx, ly = i * pas, j * pas
            l_m, h_m = min(pas, L - lx), min(pas, H - ly)
            index["fond"]["tuiles"].append({"x": lx, "y": ly, "l": l_m, "h": h_m})
            for a in FOND_ANNEES:
                f = dossier / f"fond_{a}_{len(index['fond']['tuiles']) - 1}.jpg"
                if not f.exists():
                    im, trou = image(a, ox + lx, oy - ly - h_m, l_m, h_m, FOND_RES, CACHE / str(code) / "fond" / f"{a}_{lx}_{ly}", couv)
                    if trou > TROU_MAX:
                        print(f"  fond {a} tuile {len(index['fond']['tuiles']) - 1} : {trou:.0%} sans photo")
                    im.save(f, "JPEG", quality=QUALITE, optimize=True, progressive=True)

    # Vues à 0,5 m des chantiers, rangées dans des planches identiques d'une année à l'autre
    fen = fenetres(code)
    tailles = [(round(l / VUE_RES), round(h / VUE_RES)) for _, _, l, h in fen]
    place = ranger(tailles)
    index["planches"] = max(p[0] for p in place) + 1
    for (x0, y0, l, h), (w, hh), (pl, px, py) in zip(fen, tailles, place):
        index["vues"].append({"x": round(x0 - ox, 1), "y": round(oy - (y0 + h), 1), "l": l, "h": h, "p": pl, "px": px, "py": py, "pw": w, "ph": hh})
    for a in ANNEES:
        planches = [Image.new("RGB", (PLANCHE, PLANCHE), (40, 44, 48)) for _ in range(index["planches"])]
        for n, ((x0, y0, l, h), (w, hh), (pl, px, py)) in enumerate(zip(fen, tailles, place)):
            im, trou = image(a, x0, y0, l, h, VUE_RES, CACHE / str(code) / "vues" / str(a) / f"{x0:.0f}_{y0:.0f}_{l:.0f}_{h:.0f}", couv)
            if trou > TROU_MAX:
                index["manquantes"].setdefault(str(a), []).append(n)
            planches[pl].paste(im.resize((w, hh)) if im.size != (w, hh) else im, (px, py))
        for k, im in enumerate(planches):
            # on recadre la dernière planche à sa partie utile
            hmax = max((py + hh for (pl, px, py), (w, hh) in zip(place, tailles) if pl == k), default=PLANCHE)
            im.crop((0, 0, PLANCHE, hmax)).save(dossier / f"vues_{a}_{k}.jpg", "JPEG", quality=QUALITE, optimize=True, progressive=True)
        print(f"  {code} {a} : {len(fen)} vues, {len(index['manquantes'].get(str(a), []))} sans photo", flush=True)
    index["hauteurs_planches"] = [max(py + hh for (pl, px, py), (w, hh) in zip(place, tailles) if pl == k) for k in range(index["planches"])]
    (dossier / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    poids = sum(f.stat().st_size for f in dossier.glob("*.jpg")) / 1e6
    print(f"{e['nom']} : {len(index['fond']['tuiles'])} tuiles de fond, {len(fen)} vues en {index['planches']} planches, {poids:.1f} Mo")
    return index


if __name__ == "__main__":
    import sys
    codes = [int(c) for c in sys.argv[1:]] or [92142, 63035, 83034]
    for c in codes:
        commune(c)
