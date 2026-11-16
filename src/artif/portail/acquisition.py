"""Lecture des sources du portail : natures cadastrales du SPF Finances, parts de l'IWEPS, références.

Les fichiers téléchargés sont gardés dans data/raw/ et notés dans data/raw/PROVENANCE.json.
"""
import csv
import gzip
import io
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from ..config import PROCESSED, RAW
from ..sources import USER_AGENT, fetch, record
from .parametres import (CODES_INS_2019, COMMUNES, FUSIONS, IWEPS_ANCIENNES, IWEPS_ORDRE, IWEPS_URL, POPULATION_URL,
                         SPF_PREMIERE_ANNEE, SPF_URL, TABLE_NATURES, TRAJECTOIRES)


def norme(texte: str) -> str:
    """Nom de commune sans accents, espaces ni ponctuation, pour rapprocher les graphies du SPF et du SPW."""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z]", "", t)


def est_wallonne(code_ins: int) -> bool:
    """Brabant wallon (25xxx), Hainaut (5xxxx), Liège (6xxxx), Luxembourg et Namur (8xxxx, 9xxxx)."""
    return 25000 <= code_ins < 30000 or 50000 <= code_ins < 70000 or code_ins >= 80000


# --- Références ----------------------------------------------------------------
def communes() -> pd.DataFrame:
    """Les 261 communes, indexées par code INS ; « bassin » est vide hors du champ du SDT."""
    c = pd.read_csv(COMMUNES).set_index("code_ins").rename(columns={"bassin_sdt": "bassin"})
    c["bassin"] = c["bassin"].where(c["couvert_par_sdt"] == "oui")
    return c


def trajectoires(bassins) -> pd.DataFrame:
    """Références du SDT par bassin (le fichier contient aussi une ligne régionale, écartée ici)."""
    ref = pd.read_csv(TRAJECTOIRES).set_index("bassin")
    return ref[ref.index.isin(bassins)]


def table_natures() -> pd.DataFrame:
    """Table nature -> catégorie, indexée par le code de la nature (colonnes « categorie », « libelle », « source »)."""
    return pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").set_index("nature")


# --- SPF Finances --------------------------------------------------------------
def _spf_vers_cache(an: int, dest: Path, zips: Path | None) -> bool:
    """Extrait le fichier communal wallon d'une archive SPF. Retourne False si l'année n'existe pas."""
    local = zips / f"{an}.zip" if zips else None
    url = SPF_URL.format(an=an)
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "spf.zip"
        if local and local.exists():
            chemin = local
        else:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=600) as r, open(chemin, "wb") as f:
                    while bloc := r.read(1 << 20):
                        f.write(bloc)
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    return False
                raise
        with zipfile.ZipFile(chemin) as z:
            nom = next(n for n in z.namelist() if "municipality" in n.lower() and n.lower().endswith(".csv"))
            with z.open(nom) as h:
                lecteur = csv.DictReader(io.TextIOWrapper(h, encoding="utf-8-sig"), delimiter=";")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(dest, "wt", encoding="utf-8", newline="") as sortie:
                    ecr = csv.writer(sortie)
                    ecr.writerow(["nis", "nom", "nature", "m2"])
                    for l in lecteur:
                        # les lignes de sous-totaux n'ont pas de code numérique
                        if est_wallonne(int(l["NISCode"])) and l["ParcelNature"].isdigit():
                            ecr.writerow([int(l["NISCode"]), l["NameFre"], l["ParcelNature"], l["TotalParcelsArea"]])
    record(dest, url, "lignes wallonnes du fichier communal, natures numériques seulement")
    return True


def annees_spf(refresh: bool = False, zips: Path | None = None) -> list[int]:
    """Met le cache à jour et cherche l'année suivante : c'est ainsi qu'un nouveau millésime entre."""
    annees, an = [], SPF_PREMIERE_ANNEE
    while True:
        dest = RAW / "spf_occupation_sol" / f"communes_{an}.csv.gz"
        if dest.exists() and not (refresh and an == max(annees, default=an)):
            annees.append(an)
        elif _spf_vers_cache(an, dest, zips):
            annees.append(an)
        else:
            return annees
        an += 1


def charge_spf(annees: list[int], communes: pd.DataFrame) -> pd.DataFrame:
    """Surfaces en hectares, indexées par (commune actuelle, année), une colonne par nature."""
    correspondance = {norme(n): c for c, n in communes["commune"].items()} | FUSIONS
    morceaux = []
    for an in annees:
        d = pd.read_csv(RAW / "spf_occupation_sol" / f"communes_{an}.csv.gz")
        d["code_ins"] = d["nom"].map(lambda n: correspondance.get(norme(n)))
        if d["code_ins"].isna().any():
            raise ValueError(f"{an} : communes inconnues {sorted(d.loc[d.code_ins.isna(), 'nom'].unique())}")
        d["annee"] = an
        morceaux.append(d)
    d = pd.concat(morceaux)
    d["code_ins"] = d["code_ins"].astype(int)
    return d.pivot_table(index=["code_ins", "annee"], columns="nature", values="m2", aggfunc="sum", fill_value=0) / 1e4


# --- IWEPS et Statbel ----------------------------------------------------------
def charge_iweps(refresh: bool = False) -> pd.DataFrame:
    """Parts en %, indexées par (commune, année), une colonne par indicateur."""
    morceaux = []
    for i, cle in enumerate(IWEPS_ORDRE):
        f = fetch(IWEPS_URL.format(i=i), RAW / "iweps_api" / f"215700_{i}.csv", refresh, f"indicateur {cle}, CC0")
        d = pd.read_csv(f, skiprows=1, header=None, names=["code_ins", "type", "entite", "periode", "valeur"])
        d["annee"] = d["periode"].str[-4:].astype(int)
        d["cat"] = cle
        morceaux.append(d[["code_ins", "annee", "cat", "valeur"]])
    d = pd.concat(morceaux)
    d = d[~d["code_ins"].isin(IWEPS_ANCIENNES)]
    return d.pivot_table(index=["code_ins", "annee"], columns="cat", values="valeur")


def population(annees: list[int], refresh: bool = False) -> pd.Series:
    """Habitants au 1er janvier (Statbel, registre national, CC BY 4.0), indexés par (commune actuelle, année).

    Un fichier par année, détaillé par âge, sexe, nationalité et état civil : on additionne. Bastogne et Bertogne,
    fusionnées en 2025, sont additionnées sous le code de la commune actuelle. Une année pas encore publiée
    reprend la dernière connue.
    """
    morceaux = []
    for an in annees:
        dest = RAW / "statbel_population" / f"TF_SOC_POP_STRUCT_{an}.zip"
        try:
            fetch(POPULATION_URL.format(an=an), dest, refresh, f"Statbel, population au 1er janvier {an}, CC BY 4.0")
        except urllib.error.HTTPError as e:
            if e.code == 404 and morceaux:
                break
            raise
        with zipfile.ZipFile(dest) as z:
            nom = next(n for n in z.namelist() if n.lower().endswith((".txt", ".csv")))
            # Le code s'appelle CD_MUNTY_REFNIS ou CD_REFNIS selon l'année ; certains noms ne sont pas en UTF-8,
            # mais on ne lit que les codes et les effectifs.
            d = pd.read_csv(z.open(nom), sep="|", encoding="utf-8-sig", encoding_errors="replace",
                            usecols=lambda c: c in ("CD_MUNTY_REFNIS", "CD_REFNIS", "MS_POPULATION"))
        commune = next(c for c in d.columns if "REFNIS" in c)
        p = d.groupby(commune)["MS_POPULATION"].sum()
        p = p[p.index.map(est_wallonne)]
        p.index = p.index.map(lambda c: CODES_INS_2019.get(c, c))
        p.index = p.index.where(~p.index.isin(IWEPS_ANCIENNES), FUSIONS["BERTOGNE"])
        morceaux.append(p.groupby(level=0).sum().rename(an))
    t = pd.concat(morceaux, axis=1).reindex(columns=annees).ffill(axis=1)
    if t.isna().any().any():
        raise ValueError(f"population incomplète pour les communes {sorted(t.index[t.isna().any(axis=1)])}")
    return t.stack().astype(int).rename_axis(["code_ins", "annee"])


def superficies(annees: list[int]) -> pd.Series:
    """Superficie de chaque commune chaque année (Statbel), prolongée avec la dernière valeur connue.

    Le fichier vient de la chaîne du rapport (src/construire_rapport.py), qui doit donc avoir tourné une fois.
    """
    s = pd.read_csv(PROCESSED / "artif_communes_stock_annuel.csv")
    t = s.pivot_table(index="code_ins", columns="annee_stock_1er_janvier", values="superficie_ha")
    t = t.reindex(columns=sorted(set(t.columns) | set(annees))).ffill(axis=1)[annees]
    return t.stack().rename_axis(["code_ins", "annee"])
