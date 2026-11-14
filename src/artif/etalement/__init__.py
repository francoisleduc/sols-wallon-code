"""L'étalement vu du ciel : les bâtiments neufs de 2018 à 2023 d'après WalOUS, sur le plan de secteur et les parcelles.

- walous       lecture des rasters WalOUS (changements 2018-2023, cartes 2019 et 2020) et des services du SPW ;
- morphologie  opérations sur les masques raster (ouverture, dilatation, taches) ;
- amenagement  plan de secteur et centralités du SDT, pour toute la Wallonie ;
- parcelles    plan parcellaire du SPF Finances, par commune ;
- analyse      détection, datation et rattachement des taches d'une commune ;
- export       écriture de portail/data/etalement/.
"""
