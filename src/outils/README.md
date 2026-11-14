# Outils de la version artifact

Le site public (GitHub Pages) n'en a pas besoin. Une page publiée comme artifact Claude ne peut pas charger d'images
d'autres sites : ces deux scripts préparent une copie autonome.

- `copie_artifact.py <sortie>/index.html` : retire le squelette HTML de `portail/index.html`, que l'artifact ajoute lui-même.
- `photos_artifact.py CODE_INS` : télécharge les photos aériennes d'une commune dans `portail/data/photos/<code>/`
  (exclues du dépôt du site). Plusieurs centaines de requêtes au SPW par commune, une à la fois : à réserver aux
  communes utiles.
