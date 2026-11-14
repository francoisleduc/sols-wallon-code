# Test : retrouver les chiffres de l'IWEPS à partir des natures du SPF Finances

Test mené le 7 novembre 2026. Il ne modifie ni la chaîne de calcul ni le rapport.

## Question

Peut-on reproduire l'indicateur d'artificialisation de l'IWEPS à partir des natures cadastrales ouvertes du SPF Finances, et prolonger ainsi la série après le 01/01/2023 ?

## Données

- SPF Finances, « Occupation du sol », fichiers communaux du 01/01/2011 au 01/01/2026, 251 natures numériques (les lignes de sous-totaux sont écartées). Licence CC BY 4.0.
- IWEPS, API ouverte, indicateurs 215700_0 à 215700_16, parts arrondies à 0,1 point, 2011-2023. Licence CC0.
- Fiche IWEPS T005 de septembre 2026, rythmes régionaux.
- ATOL-C : flux de 33 communes, 2011-2021, utilisés seulement comme contrôle. Ils ne sont pas redistribués, car l'outil porte la mention « All rights reserved ».

## Méthode

1. Une régression non négative estime, pour chaque catégorie de l'IWEPS, le poids de chaque nature (3 393 couples commune-année).
2. Chaque nature est affectée à la catégorie de plus fort poids.
3. Les 118 natures dont le signal est faible ou nul, soit 0,6 % de la surface cadastrée, sont classées d'après leur libellé officiel.

Le résultat est [table_natures_categories.csv](table_natures_categories.csv). **Cette table est déduite des données : ce n'est pas la table officielle de l'IWEPS.**

## Résultats

| Contrôle | Natures SPF | Rubriques Statbel |
|---|---|---|
| Écart de stock avec l'IWEPS, 2011-2023 (moyenne, en points) | 0,026 | non calculé |
| Flux annuels ATOL-C, 33 communes, 2011-2021 : écart médian | 0,08 ha | 0,31 ha |
| Même contrôle : part des écarts de plus de 1 ha | 3 % | 22 % |
| Même contrôle : corrélation temporelle médiane | 0,998 | 0,957 |
| Wallonie 2015-2019 (T005 : 11,2 km²/an) | 11,21 | 11,38 |
| Wallonie 2020-2024 (T005 : 12,3 km²/an) | 12,47 | 13,08 |
| Wallonie 2025 (T005 : 10,5 km²/an) | 10,10 | non disponible |

L'écart de stock correspond au bruit attendu d'un arrondi à 0,1 point (0,025 point en moyenne).

**Test strict.** Table apprise sans les 33 communes d'ATOL-C et sans les années après 2018, puis contrôlée sur ces communes en 2019-2021 : écart médian de 0,08 ha, 4 % d'écarts de plus de 1 ha, corrélation de 0,988. Seules 5 natures changent de catégorie, et une seule change de statut artificialisé ou non.

## Limites

- Les années 2024 et 2025 ne sont contrôlées que par la fiche régionale T005, et les écarts y sont plus grands (+0,17 et −0,40 km²/an). La cause n'est pas établie.
- Quelques années communales restent éloignées d'ATOL-C : Seraing en 2015 et en 2019, Anderlues en 2012.
- Le fichier du 01/01/2010 n'existe pas chez le SPF.
- La dernière année d'une matrice cadastrale est décrite comme incomplète par l'IWEPS : 2025 doit rester provisoire.
- La table reste à confirmer auprès de l'IWEPS.

## Reproduire

Les scripts de `scripts/` sont bruts et attendent les archives du SPF, les fichiers de l'API IWEPS et l'échantillon ATOL-C dans un dossier de travail. Ordre : `build.py`, `fit.py`, `final.py`, `eval.py`, `strict.py`. Les archives pèsent environ 1 Go et ne sont pas conservées ici.
