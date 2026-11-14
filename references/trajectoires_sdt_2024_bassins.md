# Trajectoires SDT 2024 par bassin d'optimisation spatiale

Valeurs de `trajectoires_sdt_2024_bassins.csv`.

## Source

- Schéma de développement du territoire (SDT), adopté par AGW le 23/04/2024, en vigueur le 01/08/2024.
  - Document : <https://territoire.wallonie.be/storage/territoire/documents/content/publication/sdt-web-pages.pdf>
  - Pages utilisées : SA1.P1 p. 40-42 (trajectoires d'artificialisation nette), SA2.P2 p. 53-54 (étalement urbain résidentiel), carte des bassins p. 216.
- Le SDT ne publie **aucune valeur chiffrée** pour les trajectoires : elles n'existent que sous forme de graphiques (images).
  Les valeurs du CSV ont été **numérisées depuis ces graphiques**, en lisant les pixels et en se calant sur le quadrillage des axes.
  - Précision estimée : ±3 ha/an pour l'artificialisation, ±2 points pour la part de logements en centralité.

## Méthode du SDT (SA1.P1)

- Point de départ : l'artificialisation nette moyenne sur les 10 dernières années, « calculée avant la pandémie de COVID-19 ».
  - Sur les graphiques, il s'agit d'une ligne horizontale qui couvre environ 2009-2020.
  - Le texte du SDT donne 11,5 km²/an pour la période 2010-2020, hors Communauté germanophone.
- Trajectoire : une décroissance linéaire depuis cette moyenne (vers 2021) jusqu'à 0 ha/an en 2050.
  - Formule utilisée : `traj(année) = moyenne × (2050 − année) / 29`.
  - Lecture des graphiques : départ entre 2020 et 2021. L'incertitude qui en découle est de l'ordre de 3 % sur les valeurs intermédiaires.
- `budget_cumule_2021_2050_ha` : somme des valeurs annuelles de la trajectoire, soit environ 15 × la moyenne. C'est une dérivation, pas un chiffre du SDT.
- Statut : le SDT a une **valeur indicative**. Les trajectoires « servent de références dans le cadre d'un monitoring » (SA1.P1).
  - SA1.M1 prévoit un monitoring annuel par bassin.
  - SA1.P9 prévoit la compensation de toute nouvelle artificialisation, avec l'objectif de 0 km² net au plus tard en 2050.
- Définition (déclaration environnementale, PA20) : sont artificialisées les parcelles et les espaces non cadastrés qui portent une construction ou une installation fixe autorisée par permis, quelle que soit leur fonction.

## Bassins

- Il y a **7 bassins**, qui correspondent aux territoires des directions extérieures du SPW Territoire : Hainaut 1, Hainaut 2, Brabant wallon, Namur, Luxembourg, Liège 1 (agglomération liégeoise) et Liège 2 (reste de la province).
- La Communauté germanophone est **exclue** du SDT, car elle est compétente en aménagement du territoire.
  - L'annexe CPDT de décembre 2025 ajoute un 8e bassin, « Eupen », pour ses propres analyses.

## Communes

- Le SDT ne fixe **pas** de trajectoire par commune.
- Chaque commune doit inscrire sa propre trajectoire dans un schéma de développement communal (SDC) ou pluricommunal (SDP) « optimisation spatiale ».
  - Contenu attendu : une baisse vers 0 km²/an au plus tard en 2050 (SA1.M5) et au moins 3 logements neufs sur 4 en centralité en 2050 (SA2.M7).
  - Délai : 6 ans à partir du 01/08/2024. Sans SDC, les centralités du SDT s'appliquent.

## Annexe CPDT de décembre 2025 (R1, annexe 5, Lepur-ULiège)

- Elle ne porte **que sur le foncier économique** (terrains à usage industriel et artisanal, données cadastrales IWEPS 2012-2024). Elle ne donne pas de trajectoire générale par bassin.
- Chiffres utiles :
  - Wallonie : 16 750 ha de terrains industriels et artisanaux en 2012, 18 113 ha en 2024 ; 2 445 ha artificialisés et 705 ha désartificialisés sur la période.
  - Besoins liés à la réindustrialisation : 1 343 ha d'ici 2035, répartis par bassin.
  - Potentiel de densification des parcs d'activité économique (PAE) : 3 516 ha.
- Elle confirme que **les permis** devraient à terme servir d'indicateur de référence. En attendant que les permis soient dématérialisés, l'utilisation du sol cadastrale de l'IWEPS reste l'indicateur utilisé.
  - Source : <https://cpdt.wallonie.be/wp-content/uploads/2024/04/CPDT_RF_Decembre_2025_Annexe_R1.9_TrajectoireArtificialisation.pdf>

## Correspondance communes → bassins (`communes_bassins_sdt.csv`)

- Source : la couche SPW « Ressorts au sein desquels s'exercent les compétences d'un fonctionnaire délégué ». Elle a été mise à jour le 09/09/2025 et utilise le référentiel CadGIS 2025.
  - Service : <https://geoservices.wallonie.be/arcgis/rest/services/AMENAGEMENT_TERRITOIRE/DIREXT/MapServer/0>
  - Fiche du catalogue : <https://geoportail.wallonie.be/catalogue/53d4270c-011f-45c1-befc-95f5690386ef.html>
- Le SDT (p. 215) définit les bassins comme « les territoires gérés par les directions extérieures ». Le ressort de la direction extérieure donne donc directement le bassin.
- Le champ `bassin_sdt` reprend les noms utilisés dans `trajectoires_sdt_2024_bassins.csv`, ce qui permet la jointure directe.
- Le fichier compte 261 communes :
  - 252 communes couvertes par le SDT ;
  - 9 communes de la Communauté germanophone (`couvert_par_sdt = non`, `bassin_sdt` vide).
- Les bassins suivent les provinces, sauf dans deux cas :
  - le Hainaut est découpé entre Hainaut 1 (ouest, 36 communes) et Hainaut 2 (est, 33 communes) ;
  - la province de Liège est découpée entre Liège 1 (agglomération, 20 communes) et Liège 2 (55 communes), sans compter la Communauté germanophone.
- **Fusion Bastogne-Bertogne** : les deux communes forment la commune de Bastogne, code INS 82039. La fusion est effective le 02/12/2024 selon la note de fusion du Registre national : <https://ibz.rrn.fgov.be/fileadmin/user_upload/fr/rn/circulaires/NOT_Fusion_General.pdf>.
  - Les données Statbel d'occupation du sol sont déjà recodées sous 82039 pour toutes les années.
  - D'autres sources peuvent encore utiliser les anciens codes, Bastogne 82003 et Bertogne 82005 (tous deux dans le bassin Luxembourg). Il faut alors les regrouper sous 82039.
