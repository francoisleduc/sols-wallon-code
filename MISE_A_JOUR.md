# Mettre à jour Sols wallons

Ce guide sert à qui reprend le projet, humain ou agent, pour ajouter une nouvelle année de données ou une nouvelle source. Il suppose le dossier complet du projet (la chaîne `src/`, les tests `tests/`, les références `references/`), pas seulement le site publié. Les règles du projet sont résumées plus bas, sous « Avant de commencer ». Si un fichier `CLAUDE.md` est présent (notes de travail locales, non publiées), le lire aussi.

État décrit : 14 novembre 2026. Les stocks vont du 1er janvier 2011 au 1er janvier 2026, les flux de 2011 à 2025, le bilan des bassins couvre 2021-2024.

## 1. Ce qui change, et à quel rythme

| Quoi | Rythme | Effort | Section |
|---|---|---|---|
| Stocks et flux des 261 communes, bilan des bassins | Chaque année, quand le SPF Finances publie la situation au 1er janvier | Une commande, puis relecture | [2](#2-mise-à-jour-annuelle-des-chiffres) |
| Photos aériennes du curseur | Chaque année, quand le SPW publie une nouvelle orthophoto | Une ligne de code et quelques textes | [3](#3-nouvelle-orthophoto-du-spw) |
| Étalement vu du ciel | Seulement quand le SPW publie une nouvelle carte WalOUS (2018, 2019, 2020 et 2023 existent) | Gros : téléchargements et calcul | [4](#4-étalement-vu-du-ciel) |
| Trajectoires des bassins | Seulement si le SDT est révisé | Moyen | [5](#5-si-le-sdt-change) |
| Liste des communes | Seulement en cas de fusion de communes | Moyen | [6](#6-si-des-communes-fusionnent) |

Les plans parcellaires et les photos ne se retéléchargent **pas** chaque année. Les photos sont lues en direct sur le service du SPW. Les plans parcellaires ne servent qu'à l'étalement vu du ciel.

## Avant de commencer

- **Environnement.** Windows, Python dans `.venv/` (installer avec `requirements.txt`), Node.js avec `npm install --prefix tests`, Chrome pour les tests.
  - Lancer Python avec `-X utf8`.
  - Lancer l'audit de l'affichage avec `NAVIGATEUR=chrome` : Edge ne démarre plus en mode headless avec playwright-core 1.48.
- **Réseau.** Sur un réseau qui intercepte TLS (proxy d'entreprise, antivirus) :
  - régler Git avec `http.sslBackend=schannel` ;
  - lancer npm avec `NODE_OPTIONS=--use-system-ca`.
- **Ne jamais publier** :
  - `data/raw/atol/` (ATOL-C de la CPDT, « All rights reserved ») ;
  - `dirext_communes.geojson` ;
  - ni aucune donnée brute dans le dépôt du site.
- **Demander l'accord du propriétaire avant chaque mise en ligne** (`git push`). C'est une règle du projet.
- **Ne pas surcharger les services du SPW.** Une requête à la fois. Pour un usage en masse, préférer les téléchargements d'un bloc, et écrire d'abord à helpdesk.carto@spw.wallonie.be.

## 2. Mise à jour annuelle des chiffres

C'est la mise à jour principale. Exemple : ajouter la situation au 1er janvier 2027.

### 2.1 Vérifier que les sources sont publiées

| Source | Adresse | Ce qu'elle apporte |
|---|---|---|
| SPF Finances, occupation du sol, fichier communal | `https://opendata.fin.belgium.be/download/datasets/86999d70-51ca-11eb-9238-3448ed25ad7c_{ANNÉE}0101_csv_NA_01000.zip` | Les surfaces par nature cadastrale : la base de tous les stocks et flux |
| IWEPS, API ouverte | `https://opendata.iweps.be/api/data/csv/215700_{0..16}/com+period=all` | La série officielle, pour le contrôle et la tuile « Chiffre de l'IWEPS » |
| Statbel, occupation du sol (registre cadastral) | voir `STATBEL_SQLITE_URL` dans `src/artif/config.py` | Les superficies communales |

- Le fichier du SPF est la seule source indispensable. Tant qu'il répond 404 pour la nouvelle année, il n'y a rien à faire : la date de publication n'est pas fixe, réessayer plus tard. Au 10 janvier, le millésime de l'année n'est sans doute pas encore en ligne.
- Si Statbel n'a pas encore publié, la chaîne reprend la dernière superficie connue (sans erreur).

### 2.2 Relancer la chaîne

```bash
.venv/Scripts/python.exe -X utf8 src/run_all.py --refresh
```

```bash
.venv/Scripts/python.exe -X utf8 src/build_portail.py --refresh
```

- `run_all.py --refresh` retélécharge toutes les sources du rapport :
  - Statbel, pour les superficies de `data/processed/` dont le portail a besoin ;
  - les PDF du SDT et de la CPDT ;
  - la liste des communes par bassin (deux requêtes à l'API du SPW).

  Il réécrit `references/communes_bassins_sdt.csv` et `references/trajectoires_sdt_2024_bassins.csv`. Le dossier du projet n'est pas sous git : copier ces deux fichiers avant de lancer, puis vérifier qu'ils n'ont pas bougé. S'ils ont bougé, comprendre pourquoi avant de continuer : nouvelle version du SDT, ou changement de communes.
- `build_portail.py --refresh` :
  - cherche l'année suivante au SPF et la met en cache dans `data/raw/spf_occupation_sol/` ;
  - retélécharge l'IWEPS ;
  - régénère `portail/data/` ;
  - lance l'audit des données (`tests/verifier_donnees.py`).
- Chaque téléchargement est noté dans `data/raw/PROVENANCE.json` (adresse, date, taille, SHA-256).

### 2.3 Ce qui se met à jour seul

- **Le flux de la nouvelle année.** Les flux suivent la règle « flux N = stock(N+1) − stock(N) ». Le stock au 1er janvier 2027 crée donc le flux 2026.
- **Le passage de provisoire à définitif.**
  - Le dernier flux est toujours provisoire, montré hachuré et non compté. Avec 2027 : 2026 devient provisoire, 2025 devient définitif.
  - Le bilan des bassins passe alors de 2021-2024 à 2021-2025, et les situations « au-dessus », « sous » ou « proche » sont recalculées.
- **Le rythme récent des communes.** Il couvre de 2021 à la dernière année de flux.
- **Les textes et les tests.** Les phrases des fiches, les graphiques, les fichiers à télécharger, l'anglais des phrases (`_phrases_en`) et les années testées par les deux audits suivent tous les données.

### 2.4 Les arrêts possibles, et quoi faire

| Message | Cause | Que faire |
|---|---|---|
| Nature inconnue | Le SPF a créé une nouvelle nature cadastrale | La classer dans `references/test_spf_iweps/table_natures_categories.csv`, selon la méthode de `references/test_spf_iweps/README.md`. Si elle est citée dans une phrase, ajouter sa traduction dans `NATURES_EN` (`portail.py`) |
| `communes inconnues` | Fusion ou nom de commune modifié | Voir [la section 6](#6-si-des-communes-fusionnent) |
| `reclassement de référence perdu` | Les cas de référence de `build_portail.py` (Grâce-Hollogne 2025 et 2018, Seraing 2015) ne sont plus détectés | Comprendre pourquoi avant de toucher aux seuils (en tête de `portail.py`) : la page Méthode s'appuie sur ces cas |
| `écart moyen avec l'IWEPS trop élevé` | L'estimation s'éloigne de l'IWEPS de plus de 0,05 point | Chercher une nature mal classée ou un changement de format chez le SPF |
| Écart dans l'audit des données | Un chiffre publié ne correspond plus au recalcul indépendant | Lire le message. Ne pas publier tant qu'il reste un écart |

### 2.5 Ce qu'il faut relire à la main

- **Les chiffres écrits à la main dans la page Méthode** (`portail/assets/app.js`, section Méthode) : le test de reproduction du 7 novembre 2026 et la comparaison avec la fiche T005 de l'IWEPS.
  - Ils décrivent un test daté et restent vrais tels quels.
  - Si l'IWEPS publie une nouvelle fiche T005, on peut mettre à jour `T005` dans `tests/verifier_donnees.py` et la phrase de la Méthode ensemble. Le test vérifie qu'ils concordent.
- **Le ton.** Si un bassin change de situation, les textes s'adaptent seuls. Garder la règle : la trajectoire est un repère, pas une autorisation. Pas de verdict par commune, pas de classement.
- **L'exemple de la Méthode** (Grâce-Hollogne, choisi pour son reclassement de 2025) se recalcule seul : vérifier qu'il reste parlant.

### 2.6 Vérifier et publier

```bash
NAVIGATEUR=chrome node tests/verifier_affichage.mjs
```

1. Les deux audits doivent finir à 0 écart. L'audit des données tourne déjà dans `build_portail.py`. Celui de l'affichage prend environ 5 minutes et contrôle les 261 fiches en français et en anglais.
2. Regarder le site en local : accueil, un bassin, une fiche, la Méthode.
   - Lancer un serveur avec `npx --yes http-server@14.1.1 portail -p 8765 -a localhost -c-1`.
   - Ou prendre des captures avec `node tests/capture_etalement.mjs`.
3. Committer dans le dépôt du site, avec la ligne `Co-Authored-By` si un agent a travaillé :
   ```bash
   git -C portail add -A
   ```
   ```bash
   git -C portail commit -m "Données au 1er janvier 2027"
   ```
4. **Demander l'accord**, puis `git -C portail push`. GitHub Pages met le site à jour en une à deux minutes : https://francoisleduc.github.io/sols-wallon/

## 3. Nouvelle orthophoto du SPW

Le curseur de l'étalement va de 2018 à la dernière orthophoto déclarée dans `VOLS` (`portail/assets/app.js`). Les photos sont lues en direct sur `geoservices.wallonie.be` (CC BY 4.0). Elles ne sont jamais copiées dans le dépôt.

1. **Repérer le nouveau vol** dans la liste des services : `https://geoservices.wallonie.be/arcgis/rest/services/IMAGERIE?f=json`. Chercher par exemple `ORTHO_2027`, ou `ORTHO_2027_PRINTEMPS` ou `_ETE`. Ignorer les versions `_IR`, qui sont en infrarouge.
2. **Vérifier s'il couvre toute la Wallonie.** Les vols 2022, 2024 et 2025 été ne couvrent qu'une partie de la région, et une zone non volée sort blanche.
   - Tester quelques communes dispersées, par exemple Gembloux, Herve, Marche-en-Famenne, Mouscron et Arlon.
   - Faire quelques images seulement, une requête à la fois : pas de balayage complet.
3. **Ajouter l'année à `VOLS`.**
   - Si le vol est complet : `2027: { couches: [["ORTHO_2027", "jpg"]] }`.
   - Si le vol est partiel :
     - mettre d'abord le vol en `png32`, transparent hors de la zone volée ;
     - puis le vol de secours en `jpg` ;
     - et `repli: <année>` si ce secours est d'une autre année : la mention de la carte la cite.
4. **Mettre à jour les textes qui citent « 2018 à 2026 »** :
   - dans `app.js` : la note des sources de l'étalement, la liste « Les dates et les photos » et la liste des sources de la Méthode ;
   - leurs clés dans `portail/assets/en.js` ;
   - `portail/README.md` et `portail/FONCTIONNALITES.md`.
   - Chercher « 2026 » dans ces fichiers.
5. **Lancer l'audit de l'affichage.** Le bloc `photos-direct` lit la dernière année sur le curseur. Si le nouveau vol est partiel, ce contrôle échoue exprès : vérifier le rendu à l'œil, puis adapter le contrôle.

La version artifact Claude ne peut pas lire les images d'autres sites : elle utilise les photos téléchargées par `src/photos_etalement.py` (Gembloux seulement). Il faut y ajouter l'année dans `ANNEES` et relancer, sans dépasser une commune.

## 4. Étalement vu du ciel

Cette section ne dépend pas du calendrier annuel. Elle sert dans deux cas :

- le SPW publie une nouvelle carte WalOUS des changements, par exemple 2023-2026 ;
- on étend le pilote (3 communes) aux 261 communes.

### 4.1 Les données nécessaires

| Donnée | Producteur | Taille | Où la mettre |
|---|---|---|---|
| WalOUS, changements 2018-2023, raster 1 m | SPW, CC BY 4.0, [fiche](https://geodata.wallonie.be/id/03300ff8-5e1d-430d-876a-ffd1b9103e78) | 1,1 Go | `data/raw/spw_walous/cha_2018_2023/` (déjà là) |
| Plan parcellaire au 1er janvier 2025, par commune | SPF Finances, flux ATOM `https://opendata.fin.belgium.be/download/ATOM/64594d51-71dc-11eb-916d-3448ed25ad7c-fr.xml` (fichiers `PP-FiscSit_20250101_shp_31370_<INS>_<Nom>.zip`) | 2,1 Go pour les 261 communes | `data/raw/spf_plan_parcellaire/` |
| Plan de secteur | SPW, CC BY 4.0, aujourd'hui lu par requêtes au service `AMENAGEMENT_TERRITOIRE/PDS` | requêtes par commune | `data/raw/spw_pilote/` |
| Centralités du SDT | SPW, CC BY 4.0, aujourd'hui lues par requêtes au service `AMENAGEMENT_TERRITOIRE/CENTRALITES` | requêtes par commune | `data/raw/spw_pilote/` |
| Datation 2019 et 2020 | SPW, aujourd'hui lue par images aux services `SOL_SOUS_SOL/WAL_OCS_IA__CHA_18_19` et `__CHA_18_20` | environ 50 images par commune | `data/raw/spw_pilote/walous/` |

Le SPF ne publie le plan parcellaire que commune par commune : il n'existe pas de fichier régional. Ses fichiers sont de simples téléchargements, sans charge pour le SPW.

### 4.2 Version actuelle : par requêtes (lent)

1. Ajouter les communes à `COMMUNES` dans `src/pilote_parcelles.py`.
2. Télécharger leurs plans parcellaires 2025.
3. Lancer `.venv/Scripts/python.exe -X utf8 -u src/etalement_walous.py`.

Comptez environ 13 minutes par commune, surtout passées à attendre le SPW. Pour 261 communes, cela fait 2 à 3 jours de requêtes en continu : trop pour les conditions d'usage du SPW sans le prévenir.

### 4.3 Version conseillée : par téléchargements d'un bloc (à développer)

Le SPW publie aussi ces données en fichiers complets. Les avoir en local évite toutes les requêtes par commune.

| Donnée | Fichier | Taille |
|---|---|---|
| WalOUS 2019, raster | `https://geoservices.wallonie.be/geotraitement/spwdatadownload/results/86462606-4a21-49c8-ab9e-564ccba681b7/WAL_OCS_IA__2019_GEOTIFF_3812.zip` | 724 Mo |
| WalOUS 2020, raster | `https://geoservices.wallonie.be/geotraitement/spwdatadownload/results/47b348f1-6e7a-4baa-963c-0232a43c0cff/WAL_OCS_IA__2020_GEOTIFF_3812.zip` | 728 Mo |
| Plan de secteur, GML INSPIRE | `https://geoservices.wallonie.be/geotraitement/spwdatadownload/get/37502a64-868e-4e3d-bf66-31ff65a24a5a/LU_PlannedLandUse_PDS.gml.zip` | environ 70 Mo |
| SDT, dont les centralités, géopackage | flux ATOM de la fiche `bd8edf22-ca57-431d-a76f-34d4572d2953` | 6 Mo |

À faire avant de s'en servir :

1. Adapter `etalement_walous.py` et `pilote_parcelles.py` pour lire ces fichiers au lieu des services.
2. Vérifier sur les 3 pilotes que la datation et les zones restent les mêmes. WalOUS 2019 et 2020 sont des cartes complètes, alors que les services de datation ne montrent que les changements : de petites différences sont possibles. Les mesurer et les décrire dans la Méthode.
3. Tester que le contenu des fichiers (classes, couches) correspond bien au code.

### 4.4 Après le calcul

- Chaque commune produit `portail/data/etalement/<INS>.json`, d'environ 0,4 à 0,6 Mo. Pour 261 communes, cela fait environ 130 Mo dans le dépôt du site, ce qui reste sous la limite de 1 Go de GitHub Pages.
- Relancer `build_portail.py`, puis les deux audits. Les contrôles de l'étalement portent sur chaque commune présente.
- Les textes qui disent « trois communes pilotes » (Méthode, `portail/README.md`, `FONCTIONNALITES.md`) sont à revoir.

### 4.5 Avec une nouvelle carte WalOUS (par exemple 2023-2026)

C'est un nouveau calcul, pas une simple mise à jour :

- autre raster de changements ;
- plans parcellaires de l'année de fin ;
- datation à revoir selon les cartes intermédiaires publiées ;
- textes datés « 2018-2023 » dans `app.js`, `en.js`, les tests et les README.

## 5. Si le SDT change

- Les trajectoires par bassin sont dans `references/trajectoires_sdt_2024_bassins.csv`. Elles ont été lues sur les graphiques du SDT 2024 par `src/artif/sdt.py` (méthode : `references/trajectoires_sdt_2024_bassins.md`).
- Si la Région publie des chiffres officiels par bassin, ou un SDT révisé, il faut :
  1. remplacer ces références ;
  2. relancer les deux commandes de la section 2 ;
  3. relire la Méthode, qui décrit la lecture des graphiques et l'écart avec la note de la CPDT pour Liège 1.
- Le cap de 2050 est dans `TRAJ_END` (`src/artif/config.py`).

## 6. Si des communes fusionnent

La dernière fusion wallonne est Bertogne dans Bastogne, au 1er janvier 2025. Elle est gérée par `FUSIONS` dans `portail.py`. Pour une nouvelle fusion :

1. **Rattacher l'ancienne commune.** L'ajouter à `FUSIONS` (nom de l'ancienne commune, code INS de la nouvelle). Faire de même dans `nom_vers_code` de `tests/verifier_donnees.py`.
2. **Mettre à jour les références.**
   - `references/communes_bassins_sdt.csv`, construit par `src/artif/communes.py` depuis l'API du SPW.
   - Le fond de carte `references/geo/communes_wallonie.topojson`, refait depuis les secteurs statistiques de Statbel avec la commande de `references/geo/README.md`.
3. **Changer le nombre de communes** (261), écrit dans `build_portail.py`, `tests/verifier_donnees.py` et le titre de la carte dans `app.js`.

## 7. Le rapport LaTeX

`report/` est un livrable plus ancien. Il s'appuie sur Statbel, pas sur le SPF : ses chiffres diffèrent de ceux du portail. `run_all.py` régénère ses figures et ses chiffres. La compilation se fait avec `latexmk -pdf -cd report/rapport.tex`. Il n'est pas obligatoire de le tenir à jour en même temps que le site.

## 8. Liste courte pour un agent

1. Lire ce fichier, et `CLAUDE.md` s'il est présent.
2. Tester l'adresse SPF de l'année en cours. Si elle répond 404, s'arrêter et le dire : rien à faire.
3. `run_all.py --refresh`, puis `build_portail.py --refresh`. En cas d'arrêt, suivre [le tableau 2.4](#24-les-arrêts-possibles-et-quoi-faire).
4. Résumer ce qui a changé :
   - nouvelle année de stock ;
   - bilan des bassins, avant et après ;
   - reclassements nouvellement signalés ;
   - écart moyen avec l'IWEPS.
5. Vérifier si une nouvelle orthophoto existe ([section 3](#3-nouvelle-orthophoto-du-spw)), et si oui, l'ajouter.
6. Lancer `NAVIGATEUR=chrome node tests/verifier_affichage.mjs` : 0 écart exigé.
7. Prendre des captures (accueil, un bassin, une fiche) et les envoyer au propriétaire.
8. Committer dans `portail/`. **Ne pousser qu'avec l'accord explicite du propriétaire.**
9. Mettre à jour l'en-tête « État décrit » de ce fichier et, s'il existe, la section « Où en est le projet » de `CLAUDE.md`.
