"""Écriture des données du site : JSON lus par portail/assets/app.js et CSV proposés au téléchargement."""
import json
from pathlib import Path

import pandas as pd

from ..config import TRAJ_START
from .calculs import part_trajectoire
from .nombres import arrondi
from .parametres import SITE_DATA, TABLE_NATURES


def ecrit_json(chemin: Path, objet) -> None:
    """JSON compact : le site le charge tel quel."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def ecrit_site(index: dict, fiches: dict) -> None:
    """index.json (carte, bassins, méthode) et les fiches communales, un fichier par arrondissement (deux premiers chiffres du code INS)."""
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    ecrit_json(SITE_DATA / "index.json", index)
    paquets = {}
    for code, c in fiches.items():
        paquets.setdefault(code // 1000, {})[str(code)] = c
    for arrondissement, contenu in paquets.items():
        ecrit_json(SITE_DATA / "communes" / f"{arrondissement}.json", contenu)


def resume_etalement() -> dict:
    """Résumé des communes dont la carte de l'étalement existe (produite par src/calculer_etalement.py)."""
    dossier = SITE_DATA / "etalement"
    communes = []
    for f in sorted(dossier.glob("*.json")):
        if f.stem.isdigit():
            r = json.loads(f.read_text(encoding="utf-8"))["resume"]
            communes.append({"code": r["code"], "nom": r["nom"], "neuf_ha": r["neuf_ha"], "batiments_ha": r["batiments_ha"],
                             "bruit_ha": round(r["bruit"]["batiments_inverses_ha"] + r["bruit"]["abords_inverses_ha"], 2),
                             "brut_neuf_ha": r["brut"]["neuf_ha"], "brut_retour_ha": r["brut"]["retour_ha"],
                             "photos": (SITE_DATA / "photos" / str(r["code"]) / "index.json").exists()})
    w = dossier / "wallonie.json"
    return {"communes": communes, "wallonie": json.loads(w.read_text(encoding="utf-8")) if w.exists() else None}


def ecrit_telechargements(st, flux, flux_n, types, reclass, communes, bassins: list[dict], population) -> None:
    """Les CSV de la page Données, arrondis à 0,01 ha (les JSON du site gardent toute la précision)."""
    dossier = SITE_DATA / "telechargements"
    dossier.mkdir(parents=True, exist_ok=True)
    annees_flux = list(flux.columns)
    csv = {"index": False, "encoding": "utf-8-sig"}

    long = st.rename_axis(columns="categorie").stack().rename("hectares").round(2).reset_index()
    long = long.rename(columns={"annee": "annee_1er_janvier"})
    long["commune"] = long["code_ins"].map(communes["commune"])
    long[["code_ins", "commune", "annee_1er_janvier", "categorie", "hectares"]].to_csv(dossier / "stocks_par_commune.csv", **csv)

    f = flux.rename_axis(index="code_ins", columns="annee").stack().rename("flux_net_ha").round(2).reset_index()
    f["commune"] = f["code_ins"].map(communes["commune"])
    f["bassin"] = f["code_ins"].map(communes["bassin"])
    f["signalement"] = [types.loc[c, a] for c, a in zip(f["code_ins"], f["annee"])]
    f["flux_corrige_ha"] = [round(float(flux_n.loc[c, a]), 2) for c, a in zip(f["code_ins"], f["annee"])]
    f["provisoire"] = f["annee"] == annees_flux[-1]
    f[["code_ins", "commune", "bassin", "annee", "flux_net_ha", "signalement", "flux_corrige_ha", "provisoire"]].to_csv(dossier / "flux_par_commune.csv", **csv)

    lignes = [{"code_ins": c, "commune": communes.loc[c, "commune"], "annee": a, "flux_net_ha": arrondi(r["flux"]), "flux_corrige_ha": arrondi(r["corrige"]),
               "natures_en_baisse": " + ".join(f"{s['nature']} ({arrondi(s['ha'])} ha)" for s in r["sorties"]),
               "contrepartie": f"{r['contrepartie']['nature']} (+{arrondi(r['contrepartie']['ha'])} ha)"} for (c, a), r in sorted(reclass.items())]
    pd.DataFrame(lignes).to_csv(dossier / "reclassements_probables.csv", **csv)

    lignes = [{"bassin": b["nom"], "annee": a, "flux_net_ha": arrondi(v),
               "trajectoire_ha": round(b["reference"] * part_trajectoire(a), 1) if a >= TRAJ_START else None}
              for b in bassins for a, v in zip(annees_flux, b["flux"])]
    pd.DataFrame(lignes).to_csv(dossier / "flux_par_bassin.csv", **csv)
    pd.read_csv(TABLE_NATURES, encoding="utf-8-sig").to_csv(dossier / "table_natures_categories.csv", **csv)

    h = population.rename("habitants").reset_index().rename(columns={"annee": "annee_1er_janvier"})
    h["commune"] = h["code_ins"].map(communes["commune"])
    artif = st["artif"].reindex(pd.MultiIndex.from_arrays([h["code_ins"], h["annee_1er_janvier"]])).to_numpy()
    h["artificialise_ha"] = artif.round(2)
    h["m2_artificialises_par_habitant"] = (artif * 1e4 / h["habitants"]).round(1)
    h[["code_ins", "commune", "annee_1er_janvier", "habitants", "artificialise_ha", "m2_artificialises_par_habitant"]].to_csv(dossier / "habitants_par_commune.csv", **csv)
