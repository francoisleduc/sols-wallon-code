"""Paramètres du portail : chemins, sources, catégories et seuils de la méthode.

Chaque seuil est cité sur la page Méthode du site. Le changer, c'est changer ce que le site affirme :
mettre aussi à jour le texte de la Méthode et l'audit (tests/audit/verifier_donnees.py), qui les réécrit à part.
"""
from ..config import REFERENCES, ROOT

# --- Chemins -----------------------------------------------------------------
SITE_DATA = ROOT / "portail" / "data"
TABLE_NATURES = REFERENCES / "test_spf_iweps" / "table_natures_categories.csv"
GEOMETRIE = REFERENCES / "geo" / "communes_wallonie.topojson"
COMMUNES = REFERENCES / "communes_bassins_sdt.csv"
TRAJECTOIRES = REFERENCES / "trajectoires_sdt_2024_bassins.csv"

# --- Sources -----------------------------------------------------------------
SPF_URL = ("https://opendata.fin.belgium.be/download/datasets/"
           "86999d70-51ca-11eb-9238-3448ed25ad7c_{an}0101_csv_NA_01000.zip")
IWEPS_URL = "https://opendata.iweps.be/api/data/csv/215700_{i}/com+period=all"
POPULATION_URL = ("https://statbel.fgov.be/sites/default/files/files/opendata/bevolking%20naar%20woonplaats%2C"
                  "%20nationaliteit%20burgelijke%20staat%20%2C%20leeftijd%20en%20geslacht/TF_SOC_POP_STRUCT_{an}.zip")
SPF_PREMIERE_ANNEE = 2011
FUSIONS = {"BERTOGNE": 82039}          # commune fusionnée, absente de la liste actuelle
IWEPS_ANCIENNES = (82003, 82005)       # Bastogne et Bertogne avant fusion : 82039 les remplace
# Codes INS changés le 1er janvier 2019 (réforme des arrondissements du Hainaut) : ancien -> actuel
CODES_INS_2019 = {52043: 55086, 52063: 55085, 54007: 57096, 54010: 57097, 55010: 51067, 55022: 58001, 55023: 51069,
                  55039: 51068, 56011: 58002, 56085: 58003, 56087: 58004}
NATURE_TERRAIN = 70                   # « Terrain » : classée non artificialisée, la page Méthode explique pourquoi
EXEMPLE_COMMUNE = 62118                # Grâce-Hollogne : l'exemple de la page Méthode, choisi pour son reclassement de 2025

# --- Catégories (celles de l'IWEPS) -------------------------------------------
ARTIF = ["resid", "comm", "equip", "loisirs", "agri_bat", "indus", "carrieres", "transport", "autres_art"]
NON_ARTIF = ["arable", "herbe", "foret", "seminat", "humide", "eau", "inconnu"]
CATEGORIES = ARTIF + NON_ARTIF
IWEPS_ORDRE = ["artif"] + CATEGORIES   # ordre des indicateurs 215700_0 à 215700_16

# --- Rythmes et comparaisons ---------------------------------------------------
REFERENCE_COMMUNE = (2011, 2019)       # rythme passé d'une commune : le SPF commence en 2011
ECART_RYTHME_RELATIF = 0.15            # sous ce seuil, ou sous 0,5 ha/an, deux rythmes sont « comparables »
ECART_RYTHME_ABSOLU_HA = 0.5
ECART_PART_POINTS = 1.0                # sous ce seuil, une commune est « proche » de la médiane
ECART_PROCHE = 0.05                    # à moins de 5 % de la trajectoire, un bassin est dit « proche » de sa trajectoire

# --- Détection des reclassements cadastraux -----------------------------------
RECLASS_SORTIE_MIN_HA = 10.0           # une nature artificialisée qui perd au moins cette surface en un an
RECLASS_COUVERTURE = 0.9               # une nature non artificialisée doit gagner au moins cette part de la perte
RECLASS_RETOUR = 0.5                   # la correction doit réduire au moins de moitié l'écart à la médiane communale
SOLDE_NEGATIF_HA = -10.0               # un solde plus négatif ne peut pas venir de constructions
RECLASS_SEUILS_TESTES = (5.0, 10.0)    # seuils comparés sur la page Méthode

# --- Précision des données publiées --------------------------------------------
PRECISION_PARTS = 6                    # décimales gardées dans les données : l'arrondi se fait une seule fois, à l'affichage
PRECISION_HA = 4                       # le cadastre est en m², soit quatre décimales en hectares
