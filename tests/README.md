# Tests

Trois familles, de la plus rapide à la plus complète. Toutes se lancent depuis la racine du projet.

| Dossier | Ce qui est vérifié | Durée | Quand |
|---|---|---|---|
| `unitaires/` | Les fonctions de calcul, une à une, sur de petites données inventées : arrondis, convention des flux, détection des reclassements, trajectoire, phrases, masques de l'étalement. | 1 s | Après chaque modification du code. |
| `audit/verifier_donnees.py` | Chaque chiffre publié dans `portail/data/`, recalculé depuis les fichiers bruts sans importer le code du portail (environ 280 000 contrôles). | 1 à 2 min | À chaque génération (`src/construire_portail.py` le lance). |
| `audit/verifier_affichage.mjs` | Ce que le navigateur affiche, comparé aux données, sur les 261 fiches, en français et en anglais (environ 79 000 contrôles). | quelques min | Avant toute publication. |

```bash
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests/unitaires
.venv/Scripts/python.exe -X utf8 tests/audit/verifier_donnees.py -v
node tests/audit/verifier_affichage.mjs
```

Chaque audit rend le code de sortie 1 au premier écart et liste les écarts par famille de contrôles.

## Pourquoi deux sortes de tests

Les tests unitaires disent qu'une fonction fait ce que son auteur voulait. Les audits disent que les chiffres publiés
sont justes. Ils sont donc écrits à part du code qu'ils contrôlent : `verifier_donnees.py` réécrit les règles d'après le
texte de la page Méthode, sans rien importer de `src/`. Une erreur de calcul ne peut pas se confirmer elle-même. Ce
fichier est un script linéaire, découpé en sections dans l'ordre de la page Méthode : c'est voulu, il se relit de haut
en bas comme la méthode.

Ce que les audits ne prouvent pas : que les règles sont les bonnes, que les fichiers bruts sont conformes à ce que
publient leurs producteurs, que les références du SDT sont bien lues sur ses graphiques.

## Navigateur

`verifier_affichage.mjs` pilote Chrome, ou Edge à défaut (variable `NAVIGATEUR=chrome` ou `msedge` pour en imposer un),
avec `playwright-core` installé une fois par `npm install --prefix tests`. Derrière un proxy qui intercepte TLS, npm a
besoin de `NODE_OPTIONS=--use-system-ca`. Les scripts Node résolvent leurs imports depuis leur dossier : un script de
test temporaire doit être placé sous `tests/`.

## Outils

`outils/capture_etalement.mjs` n'est pas un test : il fait des captures de la section « étalement vu du ciel » pour
les relire à l'œil, en local ou sur le site en ligne.

```bash
node tests/outils/capture_etalement.mjs 8765 captures 92142          # site local sur le port 8765, Gembloux
node tests/outils/capture_etalement.mjs https://exemple.org/ captures
```

Variables : `ANNEES=2018,2026` (années montrées), `ATTENTE=ms` (pause avant chaque capture, pour les photos en direct).
