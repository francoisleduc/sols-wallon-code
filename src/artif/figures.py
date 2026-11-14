"""Figures du rapport (PNG 200 dpi, report/figures/)."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch, Polygon

from . import suivi
from .config import BASELINE, PROCESSED, RAW, REPORT_FIGURES, TRAJ_END, TRAJ_START
from .analyse import WALLONIE

# Palette de référence validée (3 premiers créneaux catégoriels) et encre
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
NEUTRAL = "#f0efec"
# Divergente bleu <-> rouge, point milieu gris (ratio observé / trajectoire autour de 1)
DIV_BLUE = ["#184f95", "#3987e5", "#9ec5f4"]
DIV_RED = ["#f4b3b2", "#e34948", "#a12b2b"]
RATIO_BINS = [(-np.inf, 0.5, DIV_BLUE[0], "< 0,5"), (0.5, 0.75, DIV_BLUE[1], "0,5 – 0,75"),
              (0.75, 0.9, DIV_BLUE[2], "0,75 – 0,9"), (0.9, 1.1, NEUTRAL, "0,9 – 1,1"),
              (1.1, 1.5, DIV_RED[0], "1,1 – 1,5"), (1.5, 2.0, DIV_RED[1], "1,5 – 2"),
              (2.0, np.inf, DIV_RED[2], "> 2")]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "axes.titlesize": 10, "axes.titlecolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "ytick.labelcolor": INK2, "xtick.labelcolor": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "savefig.facecolor": "white",
})


def _save(fig, name: str) -> None:
    REPORT_FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(REPORT_FIGURES / name, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fr(x: float, nd: int = 0) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def bassins_series(cons_b: pd.DataFrame, sdt: pd.DataFrame) -> None:
    bassins = [b for b in cons_b.index if b != WALLONIE]
    fig, axes = plt.subplots(2, 4, figsize=(11, 5.6), sharex=True)
    years = list(range(TRAJ_START, TRAJ_END + 1))
    for ax, b in zip(axes.flat, bassins + [WALLONIE]):
        s = cons_b.loc[b, 2000:]
        ref = sdt.loc[b, "artif_nette_moy_10ans_ha_an"]
        ax.plot(s.index, s.values, color=S1, lw=1.6, label="Observé (cadastre, déf. principale)")
        ax.hlines(ref, BASELINE[0], BASELINE[1], color=S2, lw=2, label="Moyenne de référence SDT")
        ax.plot(years, [ref * suivi.trajectory_factor(y) for y in years], color=S2, lw=1.4, ls="--",
                label="Trajectoire SDT")
        ax.set_title(b if b != WALLONIE else "Wallonie (hors CG)")
        ax.set_ylim(bottom=min(0, s.min() * 1.1))
        ax.set_xlim(2000, 2050)
    axes[0, 0].set_ylabel("ha/an")
    axes[1, 0].set_ylabel("ha/an")
    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _save(fig, "bassins_series.png")


def wallonie_long(raw_cons: dict[str, pd.Series], sdt: pd.DataFrame) -> None:
    """Consommation nette régionale 1983-2024 selon les trois définitions."""
    fig, ax = plt.subplots(figsize=(8, 3.6))
    colors = {"bati": S3, "principale": S1, "large": S2}
    labels = {"bati": "Bâti seul", "principale": "Définition principale", "large": "Définition large"}
    for k, s in raw_cons.items():
        ax.plot(s.index, s.values / 100, color=colors[k], lw=2 if k == "principale" else 1.2, label=labels[k])
    ref = sdt.loc[WALLONIE, "artif_nette_moy_10ans_ha_an"] / 100
    years = list(range(TRAJ_START, TRAJ_END + 1))
    ax.plot(years, [ref * suivi.trajectory_factor(y) for y in years], color=INK2, ls="--", lw=1.2,
            label="Trajectoire SDT (Wallonie)")
    ax.set_ylabel("km²/an")
    ax.set_xlim(1983, 2050)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", ncol=2)
    _save(fig, "wallonie_long.png")


def validation_scatter(cons_b: pd.DataFrame) -> None:
    hist = pd.read_csv(PROCESSED / "sdt_series_historiques_numerisees.csv")
    obs = cons_b.drop(WALLONIE).stack().rename("cadastre").rename_axis(["bassin", "annee"]).reset_index()
    d = hist.merge(obs, on=["bassin", "annee"]).dropna()
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.scatter(d["artif_nette_ha_sdt"], d["cadastre"], s=16, color=S1, alpha=0.75, edgecolor="white", lw=0.5)
    lim = (min(d[["artif_nette_ha_sdt", "cadastre"]].min().min(), 0) - 10, 420)
    ax.plot(lim, lim, color=MUTED, lw=1)
    r = np.corrcoef(d["artif_nette_ha_sdt"], d["cadastre"])[0, 1]
    ax.text(0.04, 0.95, f"r = {fr(r, 2)} (n = {len(d)} bassin-années)", transform=ax.transAxes, va="top", color=INK2)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Série historique du SDT, lue sur les graphiques (ha/an)")
    ax.set_ylabel("Reconstitution cadastrale (ha/an)")
    _save(fig, "validation_scatter.png")


def composition(comp: pd.DataFrame) -> None:
    """Variation nette par rubrique : d'où vient (et où va) la superficie artificialisée."""
    c = comp[(comp[["ref_2010_2019_ha_an", "obs_2021_n_ha_an"]].abs() >= 8).any(axis=1)].copy()
    marque = np.where(c["dans_principale"], " ●", np.where(c["dans_large"], " ○", ""))
    c["etiquette"] = [f"{l} [{r}]{m}" for l, r, m in zip(c["libelle"], c.index, marque)]
    c = c.sort_values("ref_2010_2019_ha_an")
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    y = np.arange(len(c))
    ax.barh(y + 0.2, c["ref_2010_2019_ha_an"], height=0.38, color=S1, label="Moyenne 2010-2019")
    ax.barh(y - 0.2, c["obs_2021_n_ha_an"], height=0.38, color=S2, label="Moyenne 2021-2024")
    ax.set_yticks(y, c["etiquette"])
    ax.axvline(0, color=AXIS, lw=0.8)
    ax.set_xlabel("Variation nette annuelle de superficie (ha/an)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    _save(fig, "composition_rubriques.png")


def sensitivity(sens: pd.DataFrame) -> None:
    col = f"ratio_{WALLONIE}"
    s = sens.iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    y = np.arange(len(s))
    colors = [S2 if g == "Référence" else S1 for g in s["groupe"]]
    ax.scatter(s[col], y, color=colors, s=36, zorder=3)
    ax.axvline(1, color=INK2, lw=1)
    ax.axvline(s[col].iloc[-1], color=S2, lw=0.8, ls=":")
    ax.set_yticks(y, s["variante"])
    for yi, v in zip(y, s[col]):
        ax.text(v + 0.005, yi + 0.25, fr(v, 2), fontsize=7, color=INK2)
    ax.xaxis.set_major_formatter(lambda v, _: fr(v, 3))
    ax.set_xlabel("Ratio cumul observé 2021-2024 / cumul autorisé par la trajectoire (Wallonie)")
    ax.grid(axis="y", visible=False)
    _save(fig, "sensibilite_wallonie.png")


def ratio_distribution(ev: pd.DataFrame) -> None:
    d = ev.dropna(subset=["ratio_obs_traj"])
    bassins = sorted(d["bassin_sdt"].unique())
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    data = [d.loc[d["bassin_sdt"] == b, "ratio_obs_traj"].clip(upper=4) for b in bassins]
    ax.boxplot(data, vert=False, widths=0.5, patch_artist=True, showfliers=True,
               boxprops=dict(facecolor="#cde2fb", edgecolor=S1), medianprops=dict(color=INK),
               whiskerprops=dict(color=S1), capprops=dict(color=S1),
               flierprops=dict(marker="o", markersize=3, markerfacecolor=S1, markeredgecolor="white"))
    ax.set_yticks(range(1, len(bassins) + 1), [f"{b} (n={len(x)})" for b, x in zip(bassins, data)])
    ax.axvline(1, color=S2, lw=1.2)
    ax.set_xlabel("Ratio cumul observé / cumul autorisé, par commune (valeurs > 4 ramenées à 4)")
    ax.grid(axis="y", visible=False)
    _save(fig, "communes_ratios_boxplot.png")


def _polygons(geom: dict) -> list[np.ndarray]:
    """Anneaux extérieurs (les enclaves éventuelles sont ignorées à cette échelle)."""
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [np.array(p[0]) for p in polys]


def _map(ax, values: dict, color_of, hatch_codes: set = frozenset()) -> None:
    gj = json.loads((RAW / "spw" / "dirext_communes.geojson").read_text(encoding="utf-8"))
    k = np.cos(np.radians(50.3))
    for f in gj["features"]:
        code = f["properties"]["ADMUKEY"]
        for ring in _polygons(f["geometry"]):
            xy = np.column_stack([ring[:, 0] * k, ring[:, 1]])
            ax.add_patch(Polygon(xy, closed=True, facecolor=color_of(values.get(code)), edgecolor="white",
                                 lw=0.3, hatch="////" if code in hatch_codes else None))
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")


def ratio_map(ev: pd.DataFrame, communes: pd.DataFrame) -> None:
    vals = ev["ratio_obs_traj"].to_dict()
    flagged = set(ev.index[ev["sauts_a_verifier_suivi"].fillna("") != ""])
    gc = set(communes.index[communes["couvert_par_sdt"] == "non"])

    def color(v):
        if v is None or pd.isna(v):
            return "#d9d8d2"
        for lo, hi, c, _ in RATIO_BINS:
            if lo <= v < hi:
                return c
        return RATIO_BINS[-1][2]

    fig, ax = plt.subplots(figsize=(9, 6.2))
    plt.rcParams["hatch.color"] = INK2
    plt.rcParams["hatch.linewidth"] = 0.5
    _map(ax, {c: v for c, v in vals.items() if c not in gc}, color, flagged)
    handles = [Patch(facecolor=c, edgecolor=AXIS, label=l) for _, _, c, l in RATIO_BINS]
    handles += [Patch(facecolor="#d9d8d2", label="Hors SDT (Communauté germanophone) / non interprétable"),
                Patch(facecolor="white", edgecolor=INK2, hatch="////", label="Saut cadastral à vérifier depuis 2021")]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, title="Observé / trajectoire (cumul 2021-2024)",
              title_fontsize=8)
    _save(fig, "carte_ratio_communes.png")


def stock_map(stock: pd.DataFrame, surface: pd.DataFrame) -> None:
    last = stock.columns.max()
    share = (stock[last] / surface[last] * 100).to_dict()
    ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    bins = [5, 7.5, 10, 15, 25, 40, np.inf]
    labels = ["< 5 %", "5 – 7,5 %", "7,5 – 10 %", "10 – 15 %", "15 – 25 %", "25 – 40 %", "> 40 %"]
    color = lambda v: "#d9d8d2" if v is None or pd.isna(v) else ramp[next(i for i, b in enumerate(bins) if v < b)]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    _map(ax, share, color)
    ax.legend(handles=[Patch(facecolor=c, label=l) for c, l in zip(ramp, labels)], loc="lower left", fontsize=7.5,
              title=f"Part artificialisée au 01/01/{last}", title_fontsize=8)
    _save(fig, "carte_part_artificialisee.png")


def run(res: dict, cons_by_def: dict[str, pd.Series]) -> None:
    bassins_series(res["cons_bassins"], res["sdt"])
    wallonie_long(cons_by_def, res["sdt"])
    validation_scatter(res["cons_bassins"])
    composition(res["composition"])
    sensitivity(res["sensibilite"])
    ratio_distribution(res["eval_communes"])
    ratio_map(res["eval_communes"], res["communes"])
    stock_map(res["stock"], res["surface"])
