"""Arrondi et écriture des nombres, en français et en anglais.

Un chiffre n'est arrondi qu'une fois, à l'affichage, avec la même règle que le navigateur (portail/assets/app.js) :
une phrase et la tuile qui la jouxte donnent ainsi le même chiffre.
"""
from decimal import ROUND_HALF_UP, Decimal


def arrondi(valeur: float, decimales: int = 1) -> float:
    """Arrondit une demie en s'éloignant de zéro, comme le navigateur."""
    propre = Decimal(repr(round(float(valeur), 8)))  # retire le bruit des calculs en virgule flottante
    return float(propre.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)) + 0.0


# --- Français ------------------------------------------------------------------
def nombre(valeur: float, decimales: int = 1) -> str:
    """« 1234,5 » : virgule décimale et signe moins typographique."""
    return f"{arrondi(valeur, decimales):.{decimales}f}".replace(".", ",").replace("-", "−")


def ha(valeur: float) -> str:
    """Des hectares, arrondis selon leur ordre de grandeur."""
    return nombre(valeur, 1 if abs(valeur) < 100 else 0)


def points(valeur: float) -> str:
    """« 0,7 point », « 2,5 points » : le pluriel français commence à 2."""
    return f"{nombre(valeur)} point" + ("s" if abs(arrondi(valeur)) >= 2 else "")


def signe(valeur: float, decimales: int = 1) -> str:
    """« +1,2 » ou « −1,2 »."""
    return ("+" if valeur >= 0 else "") + nombre(valeur, decimales)


# --- Anglais -------------------------------------------------------------------
def nombre_en(valeur: float, decimales: int = 1) -> str:
    """« 1,234.5 » : séparateur de milliers et signe moins typographique."""
    return f"{arrondi(valeur, decimales):,.{decimales}f}".replace("-", "−")


def ha_en(valeur: float) -> str:
    return nombre_en(valeur, 1 if abs(valeur) < 100 else 0)


def points_en(valeur: float) -> str:
    """« 1.0 point », « 0.7 points » : en anglais, seul 1 est au singulier."""
    return f"{nombre_en(valeur)} point" + ("" if abs(arrondi(valeur)) == 1 else "s")


def signe_en(valeur: float, decimales: int = 1) -> str:
    return ("+" if valeur >= 0 else "") + nombre_en(valeur, decimales)
