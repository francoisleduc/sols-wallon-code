"""Plan parcellaire cadastral du SPF Finances (licence open data du SPF), un fichier par commune.

Les archives PP-FiscSit_<AAAA>0101_shp_31370_<code INS>_<nom>.zip se téléchargent par le flux ATOM du SPF
(voir MISE_A_JOUR.md, section 4) et se rangent dans data/raw/spf_plan_parcellaire/.
"""
import geopandas as gpd

from ..config import RAW

DOSSIER = RAW / "spf_plan_parcellaire"
ANNEE = 2025            # situation au 1er janvier : la plus proche de la fin de la période WalOUS (2018-2023) disponible
CRS = "EPSG:31370"      # Lambert 72


def couche(code: int, nom: str, annee: int = ANNEE) -> gpd.GeoDataFrame:
    """Une couche de l'archive d'une commune : « Bpn_CaPa » (parcelles), « Apn_CaDi » (divisions cadastrales)…"""
    zips = list(DOSSIER.glob(f"PP-FiscSit_{annee}0101_shp_31370_{code}_*.zip"))
    if len(zips) != 1:
        raise FileNotFoundError(f"plan parcellaire manquant : {code} {annee}")
    return gpd.read_file(f"/vsizip/{zips[0].as_posix()}/{nom}.shp", engine="pyogrio").set_crs(CRS, allow_override=True)


def limite_communale(code: int) -> gpd.GeoDataFrame:
    """Contour de la commune : l'union de ses divisions cadastrales."""
    return couche(code, "Apn_CaDi").dissolve()
