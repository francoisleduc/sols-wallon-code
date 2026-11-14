"""Arrondi et écriture des nombres : la règle doit rester celle du navigateur (portail/assets/app.js)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from artif.portail.nombres import arrondi, ha, ha_en, nombre, nombre_en, points, points_en, signe, signe_en  # noqa: E402


class Arrondi(unittest.TestCase):
    def test_demie_s_eloigne_de_zero(self):
        self.assertEqual(arrondi(0.25), 0.3)
        self.assertEqual(arrondi(-0.25), -0.3)
        self.assertEqual(arrondi(2.5, 0), 3.0)

    def test_bruit_des_flottants_retire(self):
        # 1.005 vaut 1.00499999... en binaire : l'arrondi « naïf » donnerait 1.0
        self.assertEqual(arrondi(1.005, 2), 1.01)
        self.assertEqual(arrondi(0.1 + 0.2, 1), 0.3)

    def test_pas_de_zero_negatif(self):
        self.assertEqual(str(arrondi(-0.04)), "0.0")


class Francais(unittest.TestCase):
    def test_virgule_et_moins_typographique(self):
        self.assertEqual(nombre(1234.56), "1234,6")
        self.assertEqual(nombre(-1.25), "−1,3")
        self.assertEqual(nombre(-0.04), "0,0")

    def test_hectares_selon_la_grandeur(self):
        self.assertEqual(ha(12.34), "12,3")
        self.assertEqual(ha(123.4), "123")

    def test_pluriel_de_point_a_partir_de_2(self):
        self.assertEqual(points(1.94), "1,9 point")
        self.assertEqual(points(1.96), "2,0 points")

    def test_signe(self):
        self.assertEqual(signe(3), "+3,0")
        self.assertEqual(signe(-3, 0), "−3")
        self.assertEqual(signe(0), "+0,0")


class Anglais(unittest.TestCase):
    def test_separateur_de_milliers(self):
        self.assertEqual(nombre_en(1234.56), "1,234.6")
        self.assertEqual(ha_en(1234.5), "1,235")

    def test_singulier_seulement_pour_1(self):
        self.assertEqual(points_en(1.0), "1.0 point")
        self.assertEqual(points_en(0.5), "0.5 points")

    def test_signe(self):
        self.assertEqual(signe_en(-12.0), "−12.0")


if __name__ == "__main__":
    unittest.main()
