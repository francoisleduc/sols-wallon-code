"""Reconstitution chiffrée des trajectoires du SDT 2024 à partir de ses graphiques.

Le SDT ne publie pas de valeurs : les trajectoires (SA1.P1, p. 40-42) et la part de logements
en centralité (SA2.P2, p. 53-54) n'existent que sous forme d'images matricielles. On les
numérise ici par analyse des couleurs de pixels, calée sur le quadrillage des axes.
"""
import numpy as np
import pandas as pd
import pymupdf

from ..config import PROCESSED, RAW, REFERENCES, REPORT_FIGURES, SDT_PDF_URL, TRAJ_END, TRAJ_START
from ..sources import fetch

# Ordre des graphiques dans le document (vérifié visuellement, voir report/figures/sdt_numerisation.png)
ARTIF_PAGES = {40: ["Hainaut 1", "Hainaut 2"], 41: ["Brabant wallon", "Namur", "Luxembourg"],
               42: ["Liège 1", "Liège 2"]}
ETAL_PAGES = {53: ["Hainaut 1", "Hainaut 2", "Brabant wallon", "Namur"], 54: ["Luxembourg", "Liège 1", "Liège 2"]}

# Axe des abscisses des graphiques d'artificialisation : centres des étiquettes 2002 et 2050 (px)
X2002, X2050 = 59.6, 631.2
Y_MAX_HA = 400.0                 # graduation supérieure de l'axe vertical (axes homogénéisés)


def _images(doc: pymupdf.Document, page: int) -> list[np.ndarray]:
    out = []
    for img in doc[page - 1].get_images(full=True):
        pix = pymupdf.Pixmap(doc, img[0])
        if pix.n - pix.alpha >= 4:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        out.append(a.astype(int))
    return out


def _gridlines(a: np.ndarray, x_range: slice) -> list[float]:
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    grey = (abs(r - g) < 8) & (abs(g - b) < 8) & (r > 200) & (r < 248)
    rows = [y for y in range(a.shape[0]) if grey[y, x_range].mean() > 0.6]
    groups: list[list[int]] = []
    for y in rows:
        if groups and y - groups[-1][-1] <= 1:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [float(np.mean(gp)) for gp in groups]


def _year_x(year: float) -> float:
    return X2002 + (year - 2002) * (X2050 - X2002) / 48


def digitize_artif(a: np.ndarray) -> dict:
    grid = _gridlines(a, slice(300, 600))
    y0, ytop = grid[-1], grid[0]
    to_ha = lambda y: (y0 - y) * Y_MAX_HA / (y0 - ytop)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # Moyenne décennale : trait bleu continu, mesuré avant le début de la trajectoire
    blue = (b > 180) & (r < 150) & (g > 140) & (g < 210) & (b - r > 60)
    centres = [np.where(blue[:, x])[0].mean() for x in range(150, 270) if blue[:, x].any()]
    moyenne = to_ha(float(np.median(centres)))
    # Trajectoire : tirets verts, ajustement linéaire
    green = (g > 150) & (r < 160) & (g - r > 35) & (g >= b - 10)
    green[:, :285] = False
    gy, gx = np.where(green)
    k, c = np.polyfit(gx, gy, 1)
    x_zero = (y0 - c) / k
    annee_zero = 2002 + (x_zero - X2002) * 48 / (X2050 - X2002)
    # Série historique : trait gris, une lecture par année (hors lignes du quadrillage)
    grey = (abs(r - g) < 12) & (abs(g - b) < 12) & (r < 225) & (r > 120)
    for gl in grid:
        grey[int(gl) - 1:int(gl) + 2, :] = False
    hist = {}
    for year in range(2002, 2022):
        x = int(round(_year_x(year)))
        rows = np.where(grey[:, x - 1:x + 2].any(axis=1))[0]
        rows = rows[(rows > ytop - 8) & (rows < y0 + 2)]
        hist[year] = to_ha(float(np.median(rows))) if len(rows) else np.nan
    return {"moyenne": moyenne, "annee_zero_lue": annee_zero, "historique": hist,
            "px_par_ha": (y0 - ytop) / Y_MAX_HA}


def digitize_etalement(a: np.ndarray) -> float:
    """Part de logements en centralité pour la décennie 2010-2020 (dernier point observé).

    Calage vertical sur les aires empilées de la période observée : le haut de l'aire verte
    correspond à 100 %, le bas de l'aire rouge à 0 %.
    """
    ref = a[:, 200]
    teal = np.where(ref[:, 1] - ref[:, 0] > 20)[0]
    red = np.where(ref[:, 0] - ref[:, 1] > 25)[0]
    y100, y0 = teal.min(), red.max()
    col = a[:, 297]
    red_top = np.where(col[:, 0] - col[:, 1] > 25)[0].min()
    return (y0 - red_top) / (y0 - y100) * 100


def build(refresh: bool = False) -> pd.DataFrame:
    pdf = fetch(SDT_PDF_URL, RAW / "sdt" / "sdt-web-pages.pdf", refresh, "SDT 2024, version publiée")
    doc = pymupdf.open(pdf)
    rows, hist_rows, crops = [], [], []
    for page, names in ARTIF_PAGES.items():
        imgs = _images(doc, page)
        if len(imgs) != len(names):
            raise ValueError(f"Page {page} : {len(imgs)} graphiques, {len(names)} attendus")
        for name, a in zip(names, imgs):
            d = digitize_artif(a)
            rows.append({"bassin": name, "moyenne": d["moyenne"], "annee_zero_lue": d["annee_zero_lue"],
                         "incertitude_lecture_ha_an": 1.5 / d["px_par_ha"]})
            hist_rows += [{"bassin": name, "annee": y, "artif_nette_ha_sdt": v} for y, v in d["historique"].items()]
            crops.append((name, a))
    etal = {}
    for page, names in ETAL_PAGES.items():
        for name, a in zip(names, _images(doc, page)):
            etal[name] = digitize_etalement(a)

    df = pd.DataFrame(rows).set_index("bassin")
    out = pd.DataFrame(index=df.index)
    m = df["moyenne"]
    out["artif_nette_moy_10ans_ha_an"] = m.round(0)
    for y in (2025, 2030, 2040):
        out[f"traj_{y}_ha_an"] = (m * (TRAJ_END - y) / (TRAJ_END - TRAJ_START)).round(0)
    out["traj_2050_ha_an"] = 0
    out["budget_cumule_2021_2050_ha"] = (m * sum(TRAJ_END - y for y in range(TRAJ_START, TRAJ_END + 1))
                                         / (TRAJ_END - TRAJ_START)).round(0)
    out["part_logements_centralite_2010_2020_pct"] = pd.Series(etal).round(0)
    out["objectif_part_centralite_2050_pct"] = 75
    out["incertitude_lecture_ha_an"] = df["incertitude_lecture_ha_an"].round(1)
    out["annee_zero_lue"] = df["annee_zero_lue"].round(1)
    total = out.sum(numeric_only=True)
    total[["part_logements_centralite_2010_2020_pct", "objectif_part_centralite_2050_pct", "annee_zero_lue",
           "incertitude_lecture_ha_an"]] = np.nan
    out.loc["Wallonie (hors Communauté germanophone)"] = total
    out.loc["Wallonie (hors Communauté germanophone)", "objectif_part_centralite_2050_pct"] = 75
    out.rename_axis("bassin").reset_index().to_csv(REFERENCES / "trajectoires_sdt_2024_bassins.csv", index=False)
    pd.DataFrame(hist_rows).round(0).to_csv(PROCESSED / "sdt_series_historiques_numerisees.csv", index=False)
    _qa_figure(crops, df)
    return out


def _qa_figure(crops, df) -> None:
    """Planche de contrôle : chaque graphique source avec la valeur numérisée superposée."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    REPORT_FIGURES.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(4, 2, figsize=(11, 12))
    for ax, (name, a) in zip(axes.flat, crops):
        grid = _gridlines(a, slice(300, 600))
        y0, ytop = grid[-1], grid[0]
        ax.imshow(a.astype(np.uint8))
        y = y0 - df.loc[name, "moyenne"] * (y0 - ytop) / Y_MAX_HA
        ax.axhline(y, color="red", lw=0.8, ls=":")
        ax.set_title(f"{name} : moyenne lue {df.loc[name, 'moyenne']:.0f} ha/an", fontsize=9)
        ax.axis("off")
    axes.flat[-1].axis("off")
    fig.tight_layout()
    fig.savefig(REPORT_FIGURES / "sdt_numerisation.png", dpi=110)
    plt.close(fig)
