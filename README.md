# Artificialisation des sols en Belgique : suivi communal

Ce projet vérifie si l'artificialisation des communes suit les trajectoires de réduction fixées par les Régions.

Il couvre pour l'instant la **Wallonie** : le Schéma de développement du territoire (SDT 2024) fixe, par bassin d'optimisation spatiale, une trajectoire linéaire vers 0 km²/an en 2050.

Il a deux livrables :

- le rapport [report/rapport.pdf](report/rapport.pdf), qui décrit la démarche, les choix, la validation, la sensibilité des résultats et leurs limites ;
- le portail [portail/](portail/), un site interactif qui présente les données par commune et par bassin aux citoyens et aux journalistes.

Le rapport et le portail n'utilisent pas la même source de flux : le rapport s'appuie sur Statbel, le portail sur le SPF Finances. Leurs chiffres diffèrent donc.

## Lancer

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe src/run_all.py --refresh
latexmk -pdf -cd report/rapport.tex
```

- `run_all.py` télécharge les sources (API SPW, PDF du SDT, open data Statbel), refait tous les calculs, les figures et les fragments LaTeX.
- Sans `--refresh`, la chaîne réutilise le cache `data/raw/` (moins d'une minute).
- Chaque téléchargement est journalisé dans `data/raw/PROVENANCE.json` (URL, date, taille, SHA-256).
- Aucun chiffre du rapport n'est saisi à la main : le texte appelle les macros de `report/generated/chiffres.tex`.
- La compilation LaTeX demande une distribution TeX (testée avec TinyTeX / TeX Live 2023).

## Portail

Pour le voir en local :

```bash
npx --yes http-server@14.1.1 portail -p 8765 -a localhost -c-1
```

Puis ouvrir http://localhost:8765. Le site doit être servi par un serveur web : il ne fonctionne pas ouvert directement comme fichier. Évitez `python -m http.server` : sous Windows, il a bloqué ou coupé environ une requête sur quinze lors des tests.

Si npm répond `UNABLE_TO_VERIFY_LEAF_SIGNATURE` au premier lancement, demandez-lui d'utiliser les certificats du système, puis relancez la commande (PowerShell) :

```powershell
$env:NODE_OPTIONS = "--use-system-ca"
```

Pour régénérer les données :

```bash
.venv/Scripts/python.exe -X utf8 src/build_portail.py --refresh
```

- La commande retélécharge l'IWEPS et cherche un nouveau millésime au SPF Finances. Sans `--refresh`, elle réutilise le cache `data/raw/`.
- **Ajouter une année :** relancer avec `--refresh`. Si une nature cadastrale inconnue apparaît, la chaîne s'arrête : il faut la classer dans `references/test_spf_iweps/table_natures_categories.csv`.
- La commande écrit `portail/data/` et s'arrête en erreur si un contrôle échoue (261 communes, phrases complètes, somme des catégories, écart avec l'IWEPS d'au plus 0,05 point) ou si l'audit `tests/verifier_donnees.py` trouve un écart.
- **Arrondis :** les données gardent la précision et chaque chiffre n'est arrondi qu'une fois, à l'affichage (`arrondi` dans `portail.py`, avec la même règle que le navigateur).
- **Reclassements :** `portail.py` signale les années où une nature artificialisée perd au moins 10 ha pendant qu'une nature non artificialisée gagne au moins 90 % de cette perte. Les seuils sont en tête du fichier, la justification sur la page Méthode, la liste dans `portail/data/telechargements/reclassements_probables.csv`.
- **Anglais :** les textes du site sont dans `portail/assets/en.js`, avec pour clé le texte français exact de `app.js`. Une clé absente laisse le français à l'écran. Les phrases des fiches, les catégories et les natures citées sont dans `portail.py` (`_phrases_en`, `LIBELLES_EN`, `NATURES_EN`) : si une nature citée n'a pas de traduction, la génération s'arrête. Cette traduction n'a pas été relue par un spécialiste, et les fichiers à télécharger restent en français.
- `portail/` est un site statique sans dépendance : il suffit de copier ce dossier sur un hébergement.
- Avant de le publier : choisir le nom (« Sols wallons » est provisoire) et compléter l'auteur et le contact dans la page Méthode.

## Étalement vu du ciel (communes pilotes)

La fiche de Gembloux, Herve et Marche-en-Famenne montre où l'on a bâti entre 2018 et 2023, d'après WalOUS (SPW). Pour chaque tache, elle donne la zone du plan de secteur, la parcelle et la période. Un curseur fait défiler les années, de 2018 à 2026, sur les orthophotos du SPW.

```bash
.venv/Scripts/python.exe -X utf8 -u src/etalement_walous.py
```

- La commande demande le raster WalOUS des changements 2018-2023 dans `data/raw/spw_walous/` (1,1 Go) et interroge les services du SPW pour la datation et le plan de secteur.
- Les pilotes sont listés dans `COMMUNES`, dans `src/pilote_parcelles.py`.
- Sur un site hébergé, la carte lit les orthophotos en direct. Dans un artifact Claude, qui bloque les images d'autres sites, elle utilise les photos téléchargées par `src/photos_etalement.py`, ou à défaut le plan de secteur.

## Publication

- `portail/` est un dépôt git à part, qui ne contient que le site, publié sur GitHub Pages.
- La version artifact se prépare avec `src/copie_artifact.py`.
- La marche à suivre pour une mise à jour est dans [MISE_A_JOUR.md](MISE_A_JOUR.md).

## Tests

Le premier test tourne à chaque régénération du portail. Il recalcule tous les chiffres publiés depuis les fichiers bruts, sans importer le code du portail, puis contrôle les phrases, les règles d'interprétation, les fichiers à télécharger et les chiffres écrits à la main dans la page Méthode :

```bash
.venv/Scripts/python.exe -X utf8 tests/verifier_donnees.py -v
```

Le second compare ce que le navigateur affiche aux données (tuiles, tableaux, graphiques, carte, cohérence entre les pages), sur les 261 fiches, en français et en anglais. Il demande Node.js et Microsoft Edge, et se lance à la main avant une publication :

```bash
npm install --prefix tests
```

```bash
node tests/verifier_affichage.mjs
```

- Ces tests montrent que les règles sont appliquées comme la page Méthode les décrit. Ils ne montrent pas que ces règles sont les bonnes, ni que les fichiers bruts sont conformes à ce que publient leurs producteurs, ni que les références du SDT sont bien lues sur ses graphiques.
- Les chiffres ATOL-C de la Méthode ne sont contrôlés que si `data/raw/atol/echantillon_33_communes.json` est présent. Ce fichier sert au contrôle local et ne doit pas être redistribué, car l'outil porte la mention « All rights reserved ».
- Le « 100 % » d'avant le renforcement de la détection, dans la Méthode, est une valeur historique : aucun test ne le recalcule.

La méthode d'estimation et son test sont décrits dans [references/test_spf_iweps/README.md](references/test_spf_iweps/README.md). Le fond de carte est décrit dans [references/geo/README.md](references/geo/README.md).

## Contenu

- `src/artif/` : la chaîne de traitement
  - `config.py` : sources, paramètres et choix de méthode (définitions, période de référence, seuils) ;
  - `sources.py` : téléchargement avec cache et provenance ;
  - `communes.py` : correspondance commune → bassin via l'API ArcGIS du SPW ;
  - `sdt.py` : numérisation des graphiques de trajectoires du SDT ;
  - `cpdt.py` : lecture des graphiques vectoriels par bassin de la note préparatoire CPDT (décembre 2025), pour la comparaison externe ;
  - `cadastre.py` : stocks et consommation nette annuelle par commune ;
  - `suivi.py` : trajectoires, évaluation, détection des sauts cadastraux ;
  - `analyse.py` : validation, variabilité, composition, sensibilité ;
  - `figures.py`, `rapport.py` : figures et fragments LaTeX du rapport ;
  - `portail.py` : données du portail, lancé par `src/build_portail.py`.
- `src/etalement_walous.py`, `src/pilote_parcelles.py`, `src/photos_etalement.py` : l'étalement vu du ciel des communes pilotes.
- `references/`
  - `trajectoires_sdt_2024_bassins.csv` / `.md` : trajectoires des 7 bassins, lues sur les graphiques du SDT ;
  - `communes_bassins_sdt.csv` : correspondance commune → bassin ;
  - `methode_suivi.md` : résumé de la méthode ;
  - `test_spf_iweps/` : test de reproduction de l'IWEPS et table nature → catégorie ;
  - `geo/` : fond de carte des communes.
- `data/processed/` (généré)
  - `artif_communes_stock_annuel.csv`, `artif_communes_conso_annuelle.csv` : séries communales 1983-2025 ;
  - `suivi_communes.csv`, `suivi_bassins.csv` : confrontation aux trajectoires (2021-2024) ;
  - `validation_definitions.csv`, `sensibilite.csv`, `variabilite_interannuelle.csv`, `composition_rubriques.csv`.
- `portail/` : le site (`index.html`, `assets/`) et ses données générées (`data/`).
- `tests/` : les deux audits du portail (`verifier_donnees.py`, `verifier_affichage.mjs`) et les captures de l'étalement (`capture_etalement.mjs`).
- `report/` : `rapport.tex`, `references.bib`, `figures/`, `generated/` et le PDF compilé.
