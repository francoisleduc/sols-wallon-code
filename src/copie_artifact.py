"""Copie de portail/index.html sans son squelette HTML, pour la publier comme artifact Claude.

L'artifact ajoute lui-même <!doctype>, <html>, <head>, <body> et les balises meta charset et viewport : on les retire.
Usage : .venv/Scripts/python.exe -X utf8 -I src/copie_artifact.py <fichier de sortie>
Le fichier de sortie se publie avec les fichiers de portail/ (assets/, data/) servis à côté de lui.
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
t = (RACINE / "portail" / "index.html").read_text(encoding="utf-8")
t = re.sub(r"<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", t)
t = re.sub(r'<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", t)
t = re.sub(r"</head>\s*<body>\s*", "", t)
t = re.sub(r"</body>\s*</html>\s*", "", t)
reste = re.findall(r"</?(?:head|body|html)\b[^>]*>", t)
if reste:
    sys.exit(f"Balises de squelette restantes : {reste}")
sortie = Path(sys.argv[1])
sortie.parent.mkdir(parents=True, exist_ok=True)
sortie.write_text(t, encoding="utf-8", newline="\n")
print(f"{sortie} : {len(t)} caractères")
