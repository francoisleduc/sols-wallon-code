# Méthode du suivi communal (Wallonie)

Implémentée dans le paquet `src/artif/rapport/` (voir `src/construire_rapport.py`). Le rapport `report/rapport.pdf` détaille la méthode, la validation et la sensibilité.

## Données

- Statbel, « Occupation du sol selon le Registre cadastral », 1983-2025 (open data SQLite) : <https://statbel.fgov.be/fr/open-data/occupation-du-sol-selon-le-registre-cadastral>
  - Valeurs : superficie en hectares par commune, par année (situation au 1er janvier) et par catégorie cadastrale. Il y a 25 catégories, plus les parcelles non normalisées et la superficie non cadastrée.
  - Statbel a **recodé toutes les années aux 261 communes actuelles** (Bastogne-Bertogne déjà fusionnées sous le code 82039). Aucun retraitement n'est donc nécessaire.
  - Les années 1992 et 2006 manquent. La variation sur l'intervalle concerné est répartie également entre les années.
- L'IWEPS (Walstat) ne publie que la part artificialisée de la dernière année par commune (10,9 % pour la Wallonie au 01/01/2023), et non une série. Son lien de téléchargement était cassé lors de la consultation du 27/10/2026.

## Définition de « artificialisé »

**Indicateur principal :** toutes les parcelles bâties (codes `2*`), les terrains récréatifs (`1J`) et les chemins cadastrés et places (`1L`).

Statbel ne publie que 25 catégories, alors que l'IWEPS/CPDT reclasse les 216 natures cadastrales. On ne peut donc qu'approcher sa définition. Plusieurs variantes ont été testées contre les références officielles. Le stock est calculé sur toute la Wallonie ; les flux et les corrélations, hors Communauté germanophone :

| Variante | Stock 2015 | Flux moyen 2010-2019 | Corrélation avec les séries du SDT par bassin | Écart moyen |
|---|---|---|---|---|
| Bâti seul | 8,3 % | 11,2 km²/an | 0,72 | 27 ha/an |
| **Bâti + `1J` + `1L` (retenu)** | 8,7 % | 11,7 km²/an | **0,74** | **27 ha/an** |
| Large (+ jardins `1DI` + « autres » `1MNOP`) | 11,1 % | 14,8 km²/an | 0,65 | 50 ha/an |

Références : SDT, 11,5 km²/an sur 2010-2020 ; IWEPS, 11,2 km²/an sur 2015-2019 ; stock IWEPS d'environ 10,8-10,9 %.

- La variante large reproduit le **stock** de l'IWEPS, mais surestime le **flux** d'environ 4 km²/an.
  - La cause est la catégorie `1MNOP`, qui mélange des terrains réellement artificialisés (terrains industriels, chantiers, parkings...) et des reclassements administratifs.
  - Le suivi porte sur des flux, c'est donc l'indicateur principal qui est retenu.
  - Le stock « large » est conservé dans `artif_communes_stock_annuel.csv` (`stock_artif_large_ha`).
- Convention : la consommation de l'année N = stock au 01/01/N+1 − stock au 01/01/N.
  - C'est la convention qui colle aux graphiques du SDT (« année de consommation »). Le décalage d'un an fait chuter la corrélation à environ 0,1.

## Trajectoire et évaluation

- **Référence :** la consommation nette moyenne 2010-2019, comme dans le SDT (« 10 dernières années, avant la pandémie »).
- **Trajectoire :** `plafond(N) = référence × (2050 − N) / 29`, décroissance linéaire de 2021 à 2050.
  - Le SDT fixe cette règle par bassin. Il ne fixe **pas** de trajectoire par commune : chaque commune doit adopter la sienne dans un schéma de développement communal. Ici, la règle du SDT est appliquée à chaque commune.
- **Évaluation :** on compare la consommation **cumulée** observée depuis 2021 (2021-2024 avec le stock au 01/01/2025) au cumul autorisé par la trajectoire. Le cumul est plus robuste que l'année seule.
  - `ratio_obs_traj` = observé / autorisé. Une valeur supérieure à 1 signifie « au-dessus de la trajectoire ».
- Les bassins sont évalués deux fois :
  - avec la référence recalculée ;
  - avec la référence officielle lue sur les graphiques du SDT (colonnes `_sdt`).

## Limites connues

- **Reclassements cadastraux.** Certaines variations ne sont pas de l'artificialisation réelle. Exemples :
  - Arlon 2024 : 108 ha de bois reclassés en terrains récréatifs ;
  - Blegny 2020 : 94 ha de domaine non cadastré intégrés au cadastre comme bâti ;
  - Enghien 2022-2023 : reclassements en chaîne.
  - Ces cas sont **signalés, pas corrigés** : `sauts_a_verifier_suivi` et `sauts_a_verifier_reference` donnent les années où l'écart à la médiane communale dépasse max(15 ha, 6 × la déviation absolue médiane).
- **Références communales fragiles.** Une référence communale petite ou bruitée rend le ratio instable. Exemple : Tubize, avec une référence de 0,97 ha/an, a un ratio supérieur à 9.
  - Il faut lire le ratio avec `ecart_cumul_ha` (l'écart en hectares).
  - Une référence nulle ou négative donne le statut « référence non interprétable ».
- **Domaine non cadastré** (routes, environ 5 % du territoire) : il n'est pas compté, comme à l'IWEPS. Le niveau d'artificialisation est donc un minimum.
- **Cadastre et réalité.** La catégorie cadastrale décrit l'usage déclaré de la parcelle, pas son revêtement réel. Une parcelle bâtie compte entièrement, jardin compris.
