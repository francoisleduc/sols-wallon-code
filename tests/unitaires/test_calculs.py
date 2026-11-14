"""Calculs du portail sur de petites données inventées : conventions, détection des reclassements, trajectoire."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from artif.portail import calculs  # noqa: E402

MAISON, PATURE = 1, 2   # une nature artificialisée et une qui ne l'est pas
TABLE = pd.DataFrame({"categorie": ["resid", "herbe"], "libelle": ["Maison", "Pâture"]}, index=pd.Index([MAISON, PATURE], name="nature"))
ANNEES = list(range(2011, 2017))


def natures(maison: list[float], pature: list[float], code: int = 1) -> pd.DataFrame:
    """Hectares par nature, indexés par (commune, année), comme acquisition.charge_spf."""
    index = pd.MultiIndex.from_product([[code], ANNEES], names=["code_ins", "annee"])
    return pd.DataFrame({MAISON: maison, PATURE: pature}, index=index)


def flux_de(spf: pd.DataFrame) -> pd.DataFrame:
    return calculs.flux_annuels(spf[MAISON].unstack(0).sort_index())


class Conventions(unittest.TestCase):
    def test_flux_n_vaut_stock_suivant_moins_stock(self):
        stock = pd.DataFrame({7: [100.0, 103.0, 104.0]}, index=[2020, 2021, 2022])
        flux = calculs.flux_annuels(stock)
        self.assertEqual(list(flux.columns), [2020, 2021])     # la dernière année de stock n'a pas de flux
        self.assertEqual(flux.loc[7].tolist(), [3.0, 1.0])

    def test_variation_des_natures_rangee_sous_l_annee_de_depart(self):
        spf = natures([10, 11, 13, 13, 13, 13], [50] * 6)
        delta = calculs.variations_natures(spf)
        self.assertEqual(delta.loc[(1, 2011), MAISON], 1)
        self.assertEqual(delta.loc[(1, 2012), MAISON], 2)
        self.assertTrue(pd.isna(delta.loc[(1, 2016), MAISON]))


class Reclassements(unittest.TestCase):
    # « Maison » grandit de 1 ha par an, mais perd 20 ha en 2014 ; « Pâture » reçoit ou non cette surface.
    MAISON = [100, 101, 102, 103, 84, 85]

    def test_perte_compensee_par_une_seule_nature_detectee(self):
        spf = natures(self.MAISON, [50, 50, 50, 50, 70, 70])
        flux = flux_de(spf)
        trouves = calculs.reclassements(spf, flux, TABLE)
        self.assertEqual(list(trouves), [(1, 2014)])
        r = trouves[(1, 2014)]
        self.assertEqual((r["flux"], r["corrige"]), (-19.0, 0.0))
        self.assertEqual(r["contrepartie"], {"nature": "Pâture", "ha": 20.0})
        types, corrige = calculs.verifications(flux, trouves)
        self.assertEqual(types.loc[1, 2014], "reclassement")
        self.assertEqual(corrige.loc[1, 2014], 0.0)

    def test_perte_sans_contrepartie_signalee_comme_solde_negatif(self):
        spf = natures(self.MAISON, [50, 50, 50, 50, 55, 55])   # la pâture ne gagne que 5 ha sur 19
        flux = flux_de(spf)
        self.assertEqual(calculs.reclassements(spf, flux, TABLE), {})
        types, corrige = calculs.verifications(flux, {})
        self.assertEqual(types.loc[1, 2014], "negatif")
        self.assertEqual(corrige.loc[1, 2014], 1.0)              # remplacé par la médiane de la commune

    def test_saut_au_dela_du_seuil(self):
        flux = pd.DataFrame({a: [1.0] for a in ANNEES}, index=[1])
        flux[2014] = 1.0 + 16                                     # écart de 16 ha : au-delà du seuil minimal de 15 ha
        types, _ = calculs.verifications(flux, {})
        self.assertEqual(types.loc[1].tolist(), ["", "", "", "saut", "", ""])

    def test_ecart_sous_le_seuil_non_signale(self):
        flux = pd.DataFrame({a: [1.0] for a in ANNEES}, index=[1])
        flux[2014] = 1.0 + 14
        types, _ = calculs.verifications(flux, {})
        self.assertTrue(types.eq("").all().all())


class Trajectoire(unittest.TestCase):
    def test_lineaire_de_2021_a_2050(self):
        self.assertEqual(calculs.part_trajectoire(2021), 1.0)
        self.assertAlmostEqual(calculs.part_trajectoire(2022), 28 / 29)
        self.assertEqual(calculs.part_trajectoire(2050), 0.0)
        self.assertEqual(calculs.part_trajectoire(2060), 0.0)

    def test_statut_proche_a_moins_de_5_pourcent(self):
        self.assertEqual(calculs.statut_bassin(1.05), "proche")
        self.assertEqual(calculs.statut_bassin(1.0501), "au-dessus")
        self.assertEqual(calculs.statut_bassin(0.95), "proche")
        self.assertEqual(calculs.statut_bassin(0.9499), "en-dessous")

    def test_bilan_compte_les_annees_definitives(self):
        # Deux communes, 10 ha/an chacune ; référence du bassin 20 ha/an. Flux de 2011 à 2025, 2025 provisoire.
        annees = list(range(2011, 2026))
        flux = pd.DataFrame({a: [10.0, 10.0] for a in annees}, index=[1, 2])
        b = calculs.bilan_bassin("Test", "test", 20.0, 2.2, flux, flux)
        prevu = sum(20 * calculs.part_trajectoire(a) for a in range(2021, 2025))
        self.assertAlmostEqual(b["cumul_observe_confirme"], 80.0)     # 2021 à 2024
        self.assertAlmostEqual(b["cumul_autorise_confirme"], round(prevu, 4))
        self.assertEqual(b["statut"], "au-dessus")                    # 80 ha observés pour environ 75 ha prévus
        self.assertEqual(b["marquante"]["annee"], 2025)


class Rythmes(unittest.TestCase):
    def test_comparable_sous_0_5_ha_ou_15_pourcent(self):
        self.assertEqual(calculs.sens_rythme(10.4, 10.0), "comparable")
        self.assertEqual(calculs.sens_rythme(11.4, 10.0), "comparable")   # 14 %
        self.assertEqual(calculs.sens_rythme(11.6, 10.0), "plus rapide")  # 16 %
        self.assertEqual(calculs.sens_rythme(1.0, 2.0), "plus lent")


if __name__ == "__main__":
    unittest.main()
