"""Calcule l'étalement vu du ciel des communes et l'écrit dans portail/data/etalement/.

Usage : .venv/Scripts/python.exe -X utf8 -u src/calculer_etalement.py [CODE_INS ...] [--refaire]
  sans code   les 261 communes ; une commune déjà exportée est sautée ;
  CODE_INS    seulement ces communes (par exemple 92142 pour Gembloux), toujours recalculées ;
  --refaire   recalcule aussi les communes déjà exportées.
Une commune en erreur est notée dans data/processed/etalement/erreurs.json et n'arrête pas les autres.

Prérequis (voir MISE_A_JOUR.md, section 4) : les rasters WalOUS et les plans parcellaires 2025 dans data/raw/, et
les données du portail déjà construites (src/construire_portail.py), pour le flux cadastral de chaque commune.
Relancer ensuite src/construire_portail.py, qui ajoute le résumé de l'étalement à portail/data/index.json.
Durée : environ une minute par commune.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from artif.config import REFERENCES  # noqa: E402
from artif.etalement import export, walous  # noqa: E402
from artif.etalement.analyse import SORTIE, analyse  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("codes", nargs="*", type=int)
    p.add_argument("--refaire", action="store_true")
    args = p.parse_args()
    ref = pd.read_csv(REFERENCES / "communes_bassins_sdt.csv")
    noms = dict(zip(ref["code_ins"].astype(int), ref["commune"]))
    inconnus = set(args.codes) - set(noms)
    if inconnus:
        raise SystemExit(f"Codes INS inconnus : {sorted(inconnus)}")
    communes = {c: noms[c] for c in args.codes} if args.codes else noms
    sauter = not args.codes and not args.refaire

    totaux = walous.changements_wallonie()
    export.ecrit_wallonie(totaux)
    print("Wallonie, changements bruts :", totaux)
    resumes, erreurs, debut = [], {}, time.time()
    for i, (code, nom) in enumerate(communes.items(), 1):
        deja = export.DOSSIER / f"{code}.json"
        if sauter and deja.exists():
            resumes.append(json.loads(deja.read_text(encoding="utf-8"))["resume"])
            continue
        t0 = time.time()
        try:
            e = analyse(code, nom)
            export.ecrit(e)
            resumes.append(e.resume)
        except Exception as err:  # noqa: BLE001 - une commune en erreur ne doit pas arrêter les autres
            erreurs[code] = f"{nom} : {type(err).__name__} {err}"
            print(f"  ERREUR {erreurs[code]}", flush=True)
        print(f"[{i}/{len(communes)}] {nom} : {time.time() - t0:.0f} s, total {(time.time() - debut) / 60:.0f} min", flush=True)
    SORTIE.mkdir(parents=True, exist_ok=True)
    (SORTIE / "resume.json").write_text(json.dumps(resumes, ensure_ascii=False, indent=1), encoding="utf-8")
    (SORTIE / "erreurs.json").write_text(json.dumps(erreurs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Terminé : {len(resumes)} communes, {len(erreurs)} erreur(s).")
    if erreurs:
        sys.exit(1)


if __name__ == "__main__":
    main()
