"""Données du site (portail/data/) : stocks et flux d'artificialisation par commune et par bassin, d'après le SPF Finances.

Modules, dans l'ordre de la chaîne :
- parametres   chemins, sources, catégories et seuils de la méthode ;
- acquisition  lecture du SPF Finances, de l'IWEPS et des références ;
- calculs      stocks, flux, reclassements, signalements, bilan des bassins ;
- nombres      arrondi unique et écriture des nombres (français, anglais) ;
- textes       libellés et phrases d'interprétation des fiches ;
- carte        tracés des communes, voisinages, frontières des bassins ;
- export       écriture des JSON du site et des CSV à télécharger ;
- construction assemblage de tout cela (point d'entrée : construit()) ;
- controles    contrôles rapides avant l'audit complet.
"""
