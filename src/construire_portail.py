"""Génère les données du site dans portail/data/, les contrôle, puis lance l'audit indépendant.

Usage : .venv/Scripts/python.exe -X utf8 src/construire_portail.py [--refresh] [--zips DOSSIER]
  --refresh  retélécharge l'IWEPS et cherche un nouveau millésime au SPF Finances.
  --zips     dossier d'archives SPF déjà téléchargées, nommées AAAA.zip.

Prérequis : la chaîne du rapport (src/construire_rapport.py) a tourné une fois, pour les superficies Statbel.
Pour ajouter une année : relancer avec --refresh (voir MISE_A_JOUR.md). Si une nature inconnue apparaît, la chaîne
s'arrête et la nature doit être classée dans references/test_spf_iweps/table_natures_categories.csv.
"""
import argparse
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from artif.portail import construction, controles  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--zips", type=Path)
    args = p.parse_args()
    res = construction.construit(args.refresh, args.zips)
    erreurs = controles.controle(res)
    meta = res["meta"]
    v = meta["verifications"]
    print(f"Signalements : {v['reclassements']} reclassements, {v['negatifs']} soldes négatifs, {v['sauts']} sauts, sur {v['couples']} couples.")
    print(f"Stocks {meta['annees_stock'][0]}-{meta['annees_stock'][-1]}, flux jusqu'en {meta['derniere_annee_flux']}.")
    for b in res["bassins"] + [res["wallonie"]]:
        print(f"  {b['nom']:<42} {b['statut']:<11} {b['ratios']}")
    if erreurs:
        print("\n".join(erreurs[:40]))
        raise SystemExit(f"{len(erreurs)} erreur(s) de contrôle")
    print("Contrôles réussis.")
    # Recalcul indépendant de tous les chiffres publiés, depuis les fichiers bruts.
    audit = subprocess.run([sys.executable, "-X", "utf8", str(RACINE / "tests" / "audit" / "verifier_donnees.py")])
    if audit.returncode:
        raise SystemExit("L'audit des données a trouvé des écarts : ne pas publier cette version.")


if __name__ == "__main__":
    main()
