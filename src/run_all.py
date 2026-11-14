"""Chaîne complète : acquisition des sources -> calculs -> figures -> fragments LaTeX du rapport.

Usage : python src/run_all.py [--refresh]
  --refresh  retélécharge toutes les sources (sinon, le cache data/raw/ est réutilisé).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from artif import analyse, cadastre, communes, cpdt, figures, rapport, sdt  # noqa: E402
from artif.config import DEFINITIONS  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    print("1/5 Correspondance communes -> bassins (API SPW)")
    communes.build(args.refresh)
    print("2/5 Trajectoires du SDT (numérisation des graphiques)")
    sdt.build(args.refresh)
    cpdt_bassins = cpdt.build(args.refresh)   # séries par bassin de la note préparatoire CPDT (comparaison)
    if args.refresh:
        cadastre.load(refresh=True)
    print("3/5 Calculs (cadastre Statbel)")
    res = analyse.run()

    covered = res["communes"].index[res["communes"]["couvert_par_sdt"] == "oui"]
    raw_sdt = res["raw"][res["raw"]["code_ins"].isin(covered)]
    cons_by_def = {k: cadastre.consumption(cadastre.stock(raw_sdt, k)).sum() for k in DEFINITIONS}
    print("4/5 Figures")
    figures.run(res, cons_by_def)
    print("5/5 Chiffres et tableaux LaTeX")
    rapport.run(res, cons_by_def, cpdt_bassins)
    print("Terminé. Compiler : latexmk -pdf -cd report/rapport.tex")


if __name__ == "__main__":
    main()
