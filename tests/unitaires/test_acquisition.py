"""Lecture des sources : rapprochement des noms de communes et périmètre wallon."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from artif.portail.acquisition import est_wallonne, norme  # noqa: E402


class Noms(unittest.TestCase):
    def test_accents_tirets_et_casse_ignores(self):
        self.assertEqual(norme("Écaussinnes"), "ECAUSSINNES")
        self.assertEqual(norme("Braine-l'Alleud"), norme("BRAINE L ALLEUD"))
        self.assertEqual(norme("Chapelle-lez-Herlaimont"), "CHAPELLELEZHERLAIMONT")


class Perimetre(unittest.TestCase):
    def test_codes_ins_wallons(self):
        for code, wallonne in {25005: True, 21004: False, 24062: False, 44021: False, 57081: True,
                               63035: True, 73109: False, 84068: True, 92142: True}.items():
            with self.subTest(code):
                self.assertEqual(est_wallonne(code), wallonne)


if __name__ == "__main__":
    unittest.main()
