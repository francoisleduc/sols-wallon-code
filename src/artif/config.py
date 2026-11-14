"""Chemins, sources et paramètres de méthode partagés par tout le pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REFERENCES = ROOT / "references"
REPORT = ROOT / "report"
REPORT_FIGURES = REPORT / "figures"
REPORT_GENERATED = REPORT / "generated"

# --- Sources ---------------------------------------------------------------
STATBEL_SQLITE_URL = ("https://statbel.fgov.be/sites/default/files/files/opendata/"
                      "Bodembezetting%20volgens%20het%20Kadasterregister/TF_EAE_LAND_OCCUPTN_sqlite.zip")
SPW_DIREXT_LAYER = ("https://geoservices.wallonie.be/arcgis/rest/services/"
                    "AMENAGEMENT_TERRITOIRE/DIREXT/MapServer/0")
SDT_PDF_URL = ("https://territoire.wallonie.be/storage/territoire/documents/content/"
               "publication/sdt-web-pages.pdf")
CPDT_NOTE_PREP_URL = ("https://cpdt.wallonie.be/wp-content/uploads/2022/12/"
                      "CPDT_RF_Dec_2025_Annexe_CR_InfoTer.1_Note_preparatoire.pdf")

# --- Paramètres de méthode -------------------------------------------------
BASELINE = (2010, 2019)          # 10 ans avant la pandémie (SDT, SA1.P1, note 1)
TRAJ_START, TRAJ_END = 2021, 2050

# Définitions de la surface artificialisée à partir des 27 rubriques Statbel.
# Clé = nom court, valeur = (libellé, ensemble de rubriques non bâties ajoutées au bâti "2*").
DEFINITIONS = {
    "bati": ("Parcelles bâties seules", set()),
    "principale": ("Bâti + terrains récréatifs + chemins cadastrés", {"1J", "1L"}),
    "large": ("Principale + jardins et parcs + autres non bâties", {"1J", "1L", "1DI", "1MNOP"}),
}
DEFINITION_PRINCIPALE = "principale"

# Détection des sauts cadastraux : écart à la médiane communale > max(seuil_min, k * MAD)
SAUT_SEUIL_MIN_HA = 15.0
SAUT_K_MAD = 6.0
