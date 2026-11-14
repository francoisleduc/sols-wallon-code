"""Séries par bassin de la note préparatoire CPDT au rapport triennal (décembre 2025).

La note (Centre de ressources InfoTer, annexe 1, fig. 17 à 23, p. 26-29) représente, pour chaque bassin,
l'artificialisation annuelle nette par période de trois ans (données IWEPS au 01/01/2024) et la trajectoire
du SDT telle que tracée par la CPDT. Les graphiques sont vectoriels : les hauteurs de barres et les sommets de
la trajectoire sont lus dans le PDF et convertis en ha/an par calage sur la ligne de base (0) et la ligne de
grille supérieure (300 ha). Aucune valeur n'est saisie à la main.

Remarque : dans le PDF, les légendes des figures 20 et 21 (Liège 1 et Liège 2) sont interverties ; on retient le
titre inscrit dans chaque graphique.
"""
import pandas as pd

from .. import sources
from ..config import CPDT_NOTE_PREP_URL, RAW, REFERENCES

PDF = RAW / "cpdt" / "CPDT_RF_Dec_2025_Annexe_CR_InfoTer.1_Note_preparatoire.pdf"
OUT = REFERENCES / "cpdt_2025_bassins.csv"
PERIODES = ["2009-2011", "2012-2014", "2015-2017", "2018-2020", "2021-2023"]
PAGES = range(25, 29)          # pages 26 à 29 (index 0)
BLEU = (0.122, 0.286, 0.49)    # couleur des barres
GRIS = 0.851                   # couleur des lignes de grille


def _charts(page):
    """Graphiques d'une page : (titre, barres en ha/an, sommets de la trajectoire en ha/an)."""
    dr = page.get_drawings()
    words = page.get_text("words")
    gray = [x for x in dr if x["type"] == "s" and x.get("color") and abs(x["color"][0] - GRIS) < 0.01]
    grids = [x for x in gray if len(x["items"]) == 6]
    bases = [x for x in gray if len(x["items"]) == 1]
    for g in grids:
        y300 = g["rect"].y0
        y0 = min((b["rect"].y0 for b in bases if b["rect"].y0 > g["rect"].y1), key=lambda y: y - g["rect"].y1)
        val = lambda y: (y0 - y) / (y0 - y300) * 300  # noqa: E731
        title = " ".join(w[4] for w in sorted((w for w in words if y300 - 30 < w[1] < y300 - 5), key=lambda w: w[0]))
        bars, traj = [], set()
        for x in dr:
            r = x["rect"]
            if (x["type"] == "f" and x.get("fill") and len(x["items"]) >= 3 and abs(r.y1 - y0) < 1
                    and all(abs(a - b) < 0.01 for a, b in zip(x["fill"], BLEU))):
                bars += [(it[1].x0, val(it[1].y0)) for it in x["items"] if it[0] == "re"]
                bars += [(it[1].rect.x0, val(it[1].rect.y0)) for it in x["items"] if it[0] == "qu"]
            if (x["type"] == "s" and x.get("color") and x["color"][0] > 0.9 and x["color"][1] < 0.1
                    and len(x["items"]) > 1 and y300 - 5 <= r.y1 <= y0 + 1):
                for it in x["items"]:
                    if it[0] == "l":
                        traj |= {(round(it[1].x, 1), val(it[1].y)), (round(it[2].x, 1), val(it[2].y))}
        yield title, [v for _, v in sorted(bars)], [v for _, v in sorted(traj)]


def build(refresh: bool = False) -> pd.DataFrame:
    import pymupdf
    sources.fetch(CPDT_NOTE_PREP_URL, PDF, refresh, note="CPDT, note préparatoire au rapport triennal (déc. 2025)")
    doc = pymupdf.open(PDF)
    rows = []
    for pno in PAGES:
        for title, bars, traj in _charts(doc[pno]):
            if len(bars) != len(PERIODES) or len(traj) < 2:
                raise ValueError(f"Graphique inattendu p. {pno + 1} ({title}) : {len(bars)} barres")
            pente = (traj[0] - traj[-1]) / (len(traj) - 1) / 3   # ha/an par an
            rows.append({"bassin": title, **{f"cpdt_{p}": round(v, 1) for p, v in zip(PERIODES, bars)},
                         "cpdt_traj_2021_2023": round(traj[0], 1), "cpdt_traj_pente_ha_an2": round(pente, 2),
                         "cpdt_reference_implicite_ha_an": round(pente * 29, 1), "page": pno + 1})
    df = pd.DataFrame(rows).set_index("bassin")
    if len(df) != 7:
        raise ValueError(f"7 bassins attendus, {len(df)} lus")
    df.to_csv(OUT, encoding="utf-8")
    return df


def load() -> pd.DataFrame:
    return pd.read_csv(OUT, index_col="bassin", encoding="utf-8") if OUT.exists() else build()
