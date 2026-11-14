"""Étalement : masques raster, familles du plan de secteur, tracés SVG."""
import sys
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from artif.etalement.amenagement import famille  # noqa: E402
from artif.etalement.analyse import surface_par_famille  # noqa: E402
from artif.etalement.walous import CONSTRUCTION, REVETEMENT  # noqa: E402
from artif.etalement.export import chemin_svg  # noqa: E402
from artif.etalement.morphologie import dilater, ouverture, surfaces  # noqa: E402


class Morphologie(unittest.TestCase):
    def test_ouverture_retire_les_liseres_et_garde_les_batiments(self):
        m = np.zeros((20, 20), bool)
        m[2:8, 2:8] = True        # bâtiment de 6 x 6 m
        m[12, 2:18] = True        # liseré d'un mètre de large
        m[15:17, 2:18] = True     # liseré de deux mètres
        o = ouverture(m)
        self.assertTrue(o[2:8, 2:8].all())
        self.assertFalse(o[10:].any())

    def test_dilater_d_un_metre_donne_un_carre_de_3(self):
        m = np.zeros((7, 7), bool)
        m[3, 3] = True
        self.assertEqual(int(dilater(m, 1).sum()), 9)
        self.assertEqual(int(dilater(m, 2).sum()), 25)

    def test_surface_de_chaque_tache_en_8_voisins(self):
        m = np.zeros((6, 6), bool)
        m[0, 0] = m[1, 1] = True   # reliées par la diagonale
        m[4:6, 4:6] = True
        s = surfaces(m)
        self.assertEqual(s[0, 0], 2)
        self.assertEqual(s[5, 5], 4)
        self.assertEqual(s[3, 0], 0)


class PlanDeSecteur(unittest.TestCase):
    def test_familles(self):
        attendu = {"HAB": "habitat", "ACT": "activite", "P01": "equipement", "L01": "equipement", "X01": "extraction",
                   "R01": "agricole", "R02": "forestiere", "R04": "naturelle", "D01": "reserve", "ZEC": "reserve",
                   "E01": "autre", None: "autre"}
        for code, f in attendu.items():
            with self.subTest(code):
                self.assertEqual(famille(code), f)


class SurfaceParZone(unittest.TestCase):
    """Le plan de secteur a des zones qui se recouvrent et des trous : chaque tache doit compter pour sa surface."""

    @staticmethod
    def carre(x0, y0, x1, y1):
        return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    def test_recouvrement_et_trou(self):
        taches = gpd.GeoDataFrame({"classe": [CONSTRUCTION, REVETEMENT]},
                                  geometry=[self.carre(0, 0, 100, 100), self.carre(200, 0, 300, 100)], crs="EPSG:31370")
        zones = gpd.GeoDataFrame({"famille": ["habitat", "agricole", "habitat"]},
                                 geometry=[self.carre(0, 0, 60, 100), self.carre(40, 0, 100, 100),   # 20 m recouverts
                                           self.carre(200, 0, 250, 100)], crs="EPSG:31370")          # moitié hors plan
        ha = surface_par_famille(taches, zones)
        self.assertAlmostEqual(ha.to_numpy().sum(), 2.0)                    # deux taches d'un hectare
        self.assertAlmostEqual(ha.loc["habitat", CONSTRUCTION], 0.5)        # 0,6 ha ramené à 0,5
        self.assertAlmostEqual(ha.loc["agricole", CONSTRUCTION], 0.5)
        self.assertAlmostEqual(ha.loc["hors plan", REVETEMENT], 0.5)

    def test_pas_de_hors_plan_pour_un_reste_d_arrondi(self):
        taches = gpd.GeoDataFrame({"classe": [CONSTRUCTION]}, geometry=[self.carre(0, 0, 10, 10)], crs="EPSG:31370")
        zones = gpd.GeoDataFrame({"famille": ["habitat"]}, geometry=[self.carre(0, 0, 10, 9.99)], crs="EPSG:31370")
        self.assertEqual(list(surface_par_famille(taches, zones).index), ["habitat"])


class Traces(unittest.TestCase):
    def test_carre_en_metres_depuis_le_coin_haut_gauche(self):
        carre = Polygon([(100, 200), (110, 200), (110, 210), (100, 210)])
        self.assertEqual(chemin_svg(carre, 100, 210, 0), "M0 10L10 10L10 0L0 0Z")

    def test_polygone_trop_petit_ignore(self):
        minuscule = Polygon([(0, 0), (0.2, 0), (0.2, 0.2)])
        self.assertEqual(chemin_svg(minuscule, 0, 0, 0), "")


if __name__ == "__main__":
    unittest.main()
