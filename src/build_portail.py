"""Génère les données du portail dans portail/data/ et contrôle le résultat.

Usage : python src/build_portail.py [--refresh] [--zips DOSSIER]
  --refresh  retélécharge l'IWEPS et cherche un nouveau millésime au SPF Finances.
  --zips     dossier d'archives SPF déjà téléchargées, nommées AAAA.zip.

Pour ajouter une année : relancer avec --refresh. Si une nature inconnue apparaît, la chaîne s'arrête
et la nature doit être classée dans references/test_spf_iweps/table_natures_categories.csv.
"""
import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from artif import portail  # noqa: E402


def controle(res: dict) -> list[str]:
    """Contrôles qui doivent passer avant toute publication."""
    erreurs = []
    meta, fiches = res["meta"], res["fiches"]
    if len(fiches) != 261:
        erreurs.append(f"{len(fiches)} communes au lieu de 261")
    for code, c in fiches.items():
        for p in c["phrases"]:
            t = p["texte"]
            if re.search(r"\b(?:nan|None|inf)\b|\.\.", t):
                erreurs.append(f"{code} phrase suspecte : {t}")
        if not any(p["regle"] == "rythme" for p in c["phrases"]):
            erreurs.append(f"{code} sans phrase de rythme")
        if not 0 <= c["part"] <= 100 or math.isnan(c["part"]):
            erreurs.append(f"{code} part hors limites : {c['part']}")
        somme = sum(c["ha_estimes"][k] for k in meta["artif"] + meta["non_artif"])
        if abs(somme - c["superficie"]) > max(0.01 * c["superficie"], 5):
            erreurs.append(f"{code} catégories {somme:.1f} ha pour {c['superficie']} ha de superficie")
        if not c["voisins"] and c["nom"] != "Comines-Warneton":  # enclave entre la Flandre et la France
            erreurs.append(f"{code} sans voisin")
    # Cas de référence de la détection des reclassements : ils doivent rester trouvés.
    for code, an in [(62118, 2025), (62118, 2018), (62096, 2015)]:
        if (code, an) not in res["reclass"]:
            erreurs.append(f"reclassement de référence perdu : {code} en {an}")
    # L'estimation doit rester au niveau de l'arrondi de l'IWEPS sur les années communes.
    idx = res["st"].index.intersection(res["iw"].index)
    sup = res["st"].loc[idx, meta["artif"] + meta["non_artif"]].sum(axis=1)
    ecart = (res["st"].loc[idx, "artif"] / sup * 100 - res["iw"].loc[idx, "artif"]).abs().mean()
    print(f"Écart moyen avec l'IWEPS sur {len(idx)} couples commune-année : {ecart:.3f} point")
    if ecart > 0.05:
        erreurs.append(f"écart moyen avec l'IWEPS trop élevé : {ecart:.3f} point")
    return erreurs


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--zips", type=Path)
    args = p.parse_args()
    res = portail.construit(args.refresh, args.zips)
    erreurs = controle(res)
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
    audit = subprocess.run([sys.executable, "-X", "utf8", str(RACINE / "tests" / "verifier_donnees.py")])
    if audit.returncode:
        raise SystemExit("L'audit des données a trouvé des écarts : ne pas publier cette version.")


if __name__ == "__main__":
    main()
