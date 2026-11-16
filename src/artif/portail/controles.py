"""Contrôles rapides de cohérence, lancés à chaque génération avant l'audit complet (tests/audit/verifier_donnees.py).

Ils attrapent les erreurs grossières (commune manquante, phrase cassée, référence perdue) avant de recalculer tout.
"""
import math
import re

from .parametres import ARTIF, NON_ARTIF

NB_COMMUNES = 261
# Cas de référence de la détection des reclassements, décrits sur la page Méthode : ils doivent rester trouvés.
RECLASSEMENTS_DE_REFERENCE = [(62118, 2025), (62118, 2018), (62096, 2015)]
ECART_IWEPS_MAX = 0.05     # point de pourcentage : l'IWEPS publie ses parts arrondies à 0,1 point
COMMUNES_SANS_VOISIN = {"Comines-Warneton"}   # enclave entre la Flandre et la France


def controle(res: dict) -> list[str]:
    """Liste des erreurs trouvées dans le résultat de construction.construit() ; vide si tout va bien."""
    erreurs = []
    fiches = res["fiches"]
    if len(fiches) != NB_COMMUNES:
        erreurs.append(f"{len(fiches)} communes au lieu de {NB_COMMUNES}")
    for code, c in fiches.items():
        for p in c["phrases"]:
            if re.search(r"\b(?:nan|None|inf)\b|\.\.", p["texte"]):
                erreurs.append(f"{code} phrase suspecte : {p['texte']}")
        if not any(p["regle"] == "rythme" for p in c["phrases"]):
            erreurs.append(f"{code} sans phrase de rythme")
        if not 0 <= c["part"] <= 100 or math.isnan(c["part"]):
            erreurs.append(f"{code} part hors limites : {c['part']}")
        somme = sum(c["ha_estimes"][k] for k in ARTIF + NON_ARTIF)
        if abs(somme - c["superficie"]) > max(0.01 * c["superficie"], 5):
            erreurs.append(f"{code} catégories {somme:.1f} ha pour {c['superficie']} ha de superficie")
        if not c["voisins"] and c["nom"] not in COMMUNES_SANS_VOISIN:
            erreurs.append(f"{code} sans voisin")
    for code, an in RECLASSEMENTS_DE_REFERENCE:
        if (code, an) not in res["reclass"]:
            erreurs.append(f"reclassement de référence perdu : {code} en {an}")
    # L'estimation doit rester au niveau de l'arrondi de l'IWEPS sur les années communes.
    idx = res["st"].index.intersection(res["iw"].index)
    sup = res["st"].loc[idx, ARTIF + NON_ARTIF].sum(axis=1)
    ecart = (res["st"].loc[idx, "artif"] / sup * 100 - res["iw"].loc[idx, "artif"]).abs().mean()
    print(f"Écart moyen avec l'IWEPS sur {len(idx)} couples commune-année : {ecart:.3f} point")
    if ecart > ECART_IWEPS_MAX:
        erreurs.append(f"écart moyen avec l'IWEPS trop élevé : {ecart:.3f} point")
    return erreurs
