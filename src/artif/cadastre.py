"""Occupation du sol cadastrale (Statbel) : stocks et consommation nette annuelle par commune."""
import sqlite3
import zipfile

import pandas as pd

from .config import DEFINITIONS, RAW, STATBEL_SQLITE_URL
from .sources import fetch

DB = RAW / "statbel_occupation_sol" / "bodembezetting.sqlite"


def load(refresh: bool = False) -> pd.DataFrame:
    """Table longue : code INS, rubrique cadastrale, année (situation au 1er janvier), superficie (ha)."""
    archive = fetch(STATBEL_SQLITE_URL, RAW / "statbel_occupation_sol" / "TF_EAE_LAND_OCCUPTN_sqlite.zip",
                    refresh, "Statbel - Occupation du sol selon le registre cadastral, 1983-2025")
    if refresh or not DB.exists():
        with zipfile.ZipFile(archive) as z:
            z.extract("bodembezetting.sqlite", DB.parent)
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    df = pd.read_sql("select CD_REFNIS as code_ins, CD_RUB as rubrique, MS_TOT_SUR as ha, CD_YEAR as annee "
                     "from TF_EAE_LAND_OCCUPTN_MATRIX", con)
    con.close()
    df["annee"] = df["annee"].astype(int)
    return df


def rubriques() -> pd.DataFrame:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    r = pd.read_sql("select CD_RUB_LVL_3 as rubrique, TX_RUB_FR_LVL_2 as groupe, TX_RUB_FR_LVL_3 as libelle "
                    "from TF_EAE_LAND_OCCUPTN_RUB order by 1", con)
    con.close()
    return r


def in_definition(rubrique: str, definition: str) -> bool:
    return rubrique.startswith("2") or rubrique in DEFINITIONS[definition][1]


def stock(df: pd.DataFrame, definition: str) -> pd.DataFrame:
    """Superficie artificialisée (ha) au 1er janvier : communes en lignes, années en colonnes."""
    sel = df[df["rubrique"].map(lambda r: in_definition(r, definition))]
    return sel.pivot_table(index="code_ins", columns="annee", values="ha", aggfunc="sum").fillna(0.0)


def by_rubrique(df: pd.DataFrame) -> pd.DataFrame:
    return df.pivot_table(index=["code_ins", "rubrique"], columns="annee", values="ha", aggfunc="sum").fillna(0.0)


def consumption(stk: pd.DataFrame) -> pd.DataFrame:
    """Consommation nette de l'année N = stock au 01/01/N+1 - stock au 01/01/N.

    Les millésimes manquants (1992, 2006) : la variation de l'intervalle est répartie uniformément.
    """
    years = sorted(stk.columns)
    cons = {}
    for y0, y1 in zip(years[:-1], years[1:]):
        for y in range(y0, y1):
            cons[y] = (stk[y1] - stk[y0]) / (y1 - y0)
    return pd.DataFrame(cons)
