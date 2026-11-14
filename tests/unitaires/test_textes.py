"""Phrases des fiches : français et anglais alignés, mêmes nombres, aucune valeur manquante."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from artif.portail import textes  # noqa: E402

STATS = {"annee_stock": 2026, "annee_iweps": 2023, "premiere_annee": 2011, "recent": [2021, 2025], "passe": [2011, 2019],
         "mediane_wallonie": 9.5}


def fiche(**changements) -> dict:
    c = {"nom": "Test", "bassin": "Namur", "part": 12.34, "part_iweps": 12.1, "mediane_bassin": 10.0,
         "hausse_points": 1.2, "moteur": ["resid", 0.9], "rythme_recent": 12.0, "rythme_passe": 8.0,
         "rythme_recent_sans_saut": 11.9, "rythme_passe_sans_saut": 8.1, "reclassements": [], "sauts": [],
         "part_bassin_pct": 4.56}
    c.update(changements)
    return c


def nombres_fr(t):
    return sorted(x.replace(",", ".") for x in re.findall(r"\d+(?:,\d+)?", t))


def nombres_en(t):
    return sorted(re.findall(r"\d+(?:\.\d+)?", t.replace(",", "")))


class Phrases(unittest.TestCase):
    CAS = {
        "cas courant": fiche(),
        "hors bassin": fiche(bassin=None, mediane_bassin=None, part_bassin_pct=None),
        "solde négatif": fiche(rythme_recent=-3.0, rythme_recent_sans_saut=-2.0, hausse_points=-0.4),
        "variations": fiche(sauts=[(2019, 42.0)], rythme_recent_sans_saut=4.0,
                            reclassements=[{"annee": 2025, "flux": -30.0, "corrige": 2.0,
                                            "sorties": [{"nature": "Maison", "ha": -32.0}],
                                            "contrepartie": {"nature": "Terrain", "ha": 32.0}}]),
    }

    def test_chaque_phrase_a_sa_traduction_avec_les_memes_nombres(self):
        for nom, c in self.CAS.items():
            with self.subTest(nom):
                for p in textes.phrases(c, STATS):
                    self.assertEqual(nombres_fr(p["texte"]), nombres_en(p["texte_en"]), p["regle"])
                    self.assertNotRegex(p["texte"] + p["texte_en"], r"\b(?:nan|None|inf)\b")

    def test_constat_incertain_si_la_correction_change_le_sens(self):
        c = fiche(rythme_recent=12.0, rythme_passe=8.0, rythme_recent_sans_saut=8.0, rythme_passe_sans_saut=8.0)
        rythme = next(p for p in textes.phrases(c, STATS) if p["regle"] == "rythme")
        self.assertEqual(rythme["signal"], "incertain")
        self.assertIn("difficile à juger", rythme["texte"])

    def test_hors_bassin_pas_de_trajectoire(self):
        bassin = [p for p in textes.phrases(self.CAS["hors bassin"], STATS) if p["regle"] == "bassin"]
        self.assertIn("Communauté germanophone", bassin[0]["texte"])

    def test_nature_sans_traduction_refusee(self):
        with self.assertRaises(ValueError):
            textes.nature_en("Nature inventée")


if __name__ == "__main__":
    unittest.main()
