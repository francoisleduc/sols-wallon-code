# Fond de carte des communes wallonnes

`communes_wallonie.topojson` contient les contours simplifiés des 261 communes wallonnes. Le portail s'en sert pour dessiner la carte et trouver les communes voisines.

**Source :** secteurs statistiques 2025 de Statbel, licence CC BY 4.0, GeoJSON en Lambert belge 72 (EPSG:31370). Le script met le fichier en cache sous `data/raw/statbel_secteurs/sectors_31370_20250101.geojson.zip`.

**Commande** (mapshaper 0.6.100, à partir du GeoJSON décompressé) :

```bash
npx mapshaper@0.6.100 -i secteurs.geojson -filter "cd_rgn_refnis=='03000'||cd_rgn_refnis==3000" -dissolve cd_munty_refnis copy-fields=tx_munty_descr_fr -simplify 3% keep-shapes planar -clean -o communes_wallonie.topojson format=topojson quantization=20000
```

La carte montre donc les limites de 2025, simplifiées à 3 % : elle sert à situer les communes et ne convient pas à une mesure de surface. Les surfaces du portail viennent du cadastre et de Statbel.
