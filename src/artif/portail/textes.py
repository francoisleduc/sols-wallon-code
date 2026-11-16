"""Libellés et phrases d'interprétation des fiches communales, en français et en anglais.

Les règles sont décrites sur la page Méthode, et l'audit (tests/audit/verifier_donnees.py) les relit sur les
valeurs recalculées. Les deux langues sont écrites côte à côte plutôt que par gabarit : la grammaire diffère
(pluriels, ordre des mots), et une phrase se relit mieux entière. `phrases()` vérifie qu'elles restent alignées.
"""
from .calculs import sens_rythme
from .nombres import arrondi, ha, ha_en, nombre, nombre_en, points, points_en, signe, signe_en
from .parametres import ECART_PART_POINTS, ECART_RYTHME_ABSOLU_HA, REFERENCE_COMMUNE

LIBELLES = {
    "artif": "Terrains artificialisés",
    "resid": "Résidentiel",
    "comm": "Commerces, bureaux et services",
    "equip": "Services publics et équipements",
    "loisirs": "Loisirs et espaces verts urbains",
    "agri_bat": "Bâtiments agricoles",
    "indus": "Industrie et artisanat",
    "carrieres": "Carrières, décharges et espaces abandonnés",
    "transport": "Infrastructures de transport",
    "autres_art": "Autres espaces artificialisés",
    "arable": "Terres arables et cultures permanentes",
    "herbe": "Surfaces enherbées et friches agricoles",
    "foret": "Forêts",
    "seminat": "Milieux semi-naturels",
    "humide": "Zones humides",
    "eau": "Surfaces en eau",
    "inconnu": "Nature inconnue, dont non cadastré",
}
PHRASE_CATEGORIE = {
    "resid": "le résidentiel",
    "comm": "les commerces, bureaux et services",
    "equip": "les services publics et équipements",
    "loisirs": "les loisirs et espaces verts urbains",
    "agri_bat": "les bâtiments agricoles",
    "indus": "l'industrie et l'artisanat",
    "carrieres": "les carrières, décharges et espaces abandonnés",
    "transport": "les infrastructures de transport",
    "autres_art": "les autres espaces artificialisés",
}

# Version anglaise. Aucun libellé anglais officiel n'existe pour le cadastre belge : ces traductions sont les nôtres.
LIBELLES_EN = {
    "artif": "Artificialised land",
    "resid": "Residential",
    "comm": "Shops, offices and services",
    "equip": "Public services and facilities",
    "loisirs": "Leisure and urban green space",
    "agri_bat": "Farm buildings",
    "indus": "Industry and crafts",
    "carrieres": "Quarries, landfills and derelict land",
    "transport": "Transport infrastructure",
    "autres_art": "Other artificialised land",
    "arable": "Arable land and permanent crops",
    "herbe": "Grassland and agricultural fallow",
    "foret": "Forests",
    "seminat": "Semi-natural areas",
    "humide": "Wetlands",
    "eau": "Water bodies",
    "inconnu": "Unknown class, including uncadastred land",
}
PHRASE_CATEGORIE_EN = {
    "resid": "residential land",
    "comm": "shops, offices and services",
    "equip": "public services and facilities",
    "loisirs": "leisure and urban green space",
    "agri_bat": "farm buildings",
    "indus": "industry and crafts",
    "carrieres": "quarries, landfills and derelict land",
    "transport": "transport infrastructure",
    "autres_art": "other artificialised land",
}
# Seules les natures citées sur le portail sont traduites. nature_en() signale tout oubli à la génération.
NATURES_EN = {
    "Aéroport": "Airport",
    "Bois": "Woodland",
    "Bâtiment industriel": "Industrial building",
    "Bâtiment militaire": "Military building",
    "Carrière": "Quarry",
    "Champ d’aviation": "Airfield",
    "Charbonnage": "Coal mine",
    "Chemin cadastré": "Cadastred path",
    "Cimenterie": "Cement works",
    "Entrepôt": "Warehouse",
    "Installation sportive": "Sports facility",
    "Maison": "House",
    "Matériel et outillage bâti": "Built plant and equipment",
    "Parking": "Car park",
    "Pré": "Meadow",
    "Pâture": "Pasture",
    "Salle d’exposition": "Exhibition hall",
    "Superficie et parties communes": "Surface and common parts",
    "Terrain": "Land plot",
    "Terrain d’épandage exploite": "Spreading field, in use",
    "Terrain d’épandage vain ou vague": "Spreading field, waste or vacant",
    "Terrain industriel": "Industrial land",
    "Terrain militaire": "Military land",
    "Terrain vain ou vague": "Waste or vacant land",
    "Terrain à bâtir": "Building plot",
    "Terre agricole": "Farmland",
    "Terril exploite": "Slag heap, in use",
    "Terril vain ou vague": "Slag heap, waste or vacant",
    "Verger haute tige": "High-stem orchard",
}


def nature_en(libelle: str) -> str:
    if libelle not in NATURES_EN:
        raise ValueError(f"Nature sans traduction anglaise : {libelle}. Ajoutez-la à NATURES_EN.")
    return NATURES_EN[libelle]


def phrases(c: dict, stats: dict) -> list[dict]:
    """Les phrases d'une fiche : {"regle", "texte", ["signal"], "texte_en"}, dans l'ordre d'affichage."""
    fr = phrases_fr(c, stats)
    en = phrases_en(c, stats, signal=next(p["signal"] for p in fr if p["regle"] == "rythme"))
    if len(en) != len(fr):
        raise ValueError(f"Phrases françaises et anglaises désalignées pour {c['nom']}.")
    for phrase, texte in zip(fr, en):
        phrase["texte_en"] = texte
    return fr


def _periodes(stats: dict) -> tuple[str, str]:
    return f"{stats['recent'][0]}-{stats['recent'][1]}", f"{REFERENCE_COMMUNE[0]}-{REFERENCE_COMMUNE[1]}"


def _part_bassin_citee(c: dict) -> bool:
    return bool(c["bassin"]) and c["part_bassin_pct"] is not None and arrondi(c["part_bassin_pct"]) > 0


def phrases_fr(c: dict, stats: dict) -> list[dict]:
    out = []
    der = stats["annee_stock"]
    part = c["part"]
    txt = f"{nombre(part)} % du territoire est artificialisé au 1er janvier {der}."
    if c["part_iweps"] is not None:
        txt += f" L'IWEPS indiquait {nombre(c['part_iweps'])} % au 1er janvier {stats['annee_iweps']}."
    out.append({"regle": "part", "texte": txt})

    med, lieu = (c["mediane_bassin"], "de son bassin") if c["bassin"] else (stats["mediane_wallonie"], "wallonne")
    ecart = part - med
    if abs(ecart) < ECART_PART_POINTS:
        txt = f"C'est proche de la médiane {lieu} ({nombre(med)} %)."
    elif ecart > 0:
        txt = f"C'est plus que la médiane {lieu} ({nombre(med)} %)."
    else:
        txt = f"C'est moins que la médiane {lieu} ({nombre(med)} %)."
    out.append({"regle": "comparaison", "texte": txt})

    h = c["hausse_points"]
    a0 = stats["premiere_annee"]
    if abs(h) < 0.1:
        txt = f"Cette part n'a presque pas bougé depuis {a0}."
    elif h < 0:
        txt = f"Cette part a reculé de {points(-h)} depuis {a0}, ce qui traduit souvent des reclassements au cadastre."
    else:
        cat, val = c["moteur"]
        if arrondi(val) > arrondi(h):
            txt = (f"Depuis {a0}, cette part a gagné {points(h)}. "
                   f"Pour {PHRASE_CATEGORIE[cat]}, la hausse atteint {points(val)}, car d'autres catégories ont reculé.")
        elif val >= 0.5 * h:
            txt = f"Depuis {a0}, cette part a gagné {points(h)}, dont {nombre(val)} pour {PHRASE_CATEGORIE[cat]}."
        else:
            txt = (f"Depuis {a0}, cette part a gagné {points(h)}. "
                   f"Aucune catégorie n'en explique seule la majorité : {PHRASE_CATEGORIE[cat]} y pèse le plus ({points(val)}).")
    out.append({"regle": "composition", "texte": txt})

    r, p = c["rythme_recent"], c["rythme_passe"]
    rn, pn = c["rythme_recent_sans_saut"], c["rythme_passe_sans_saut"]
    periodes, passe = _periodes(stats)
    s1, s2 = sens_rythme(r, p), sens_rythme(rn, pn)
    base = f"Le rythme récent est de {ha(r)} ha/an ({periodes}), contre {ha(p)} ha/an en {passe}"
    corrige = abs(rn - r) >= ECART_RYTHME_ABSOLU_HA or abs(pn - p) >= ECART_RYTHME_ABSOLU_HA
    hors = f" Sans les variations signalées, on passe à {ha(rn)} contre {ha(pn)} ha/an." if corrige else ""
    if s1 != s2:
        txt = (f"{base}. Il est difficile à juger : sans les variations signalées, on passe à {ha(rn)} contre "
               f"{ha(pn)} ha/an, et le constat change.")
    elif s1 == "comparable":
        txt = f"{base} : il reste comparable.{hors}"
    elif s1 == "plus rapide":
        txt = f"{base} : la commune artificialise plus vite qu'avant.{hors}"
    else:
        txt = f"{base} : la commune artificialise moins vite qu'avant.{hors}"
    out.append({"regle": "rythme", "texte": txt, "signal": s1 if s1 == s2 else "incertain"})

    if r < 0 and rn >= 0:
        out.append({"regle": "solde", "texte": "Le solde récent est négatif à cause des variations signalées ci-dessous : "
                    "il ne faut pas y voir un retour de terrains à la nature."})
    elif r < 0:
        out.append({"regle": "solde", "texte": "Le solde récent est négatif : il y a eu plus de terrains sortis "
                    "de la catégorie artificialisée que de terrains entrés, souvent à cause de reclassements."})

    for x in c["reclassements"]:
        noms = " et ".join(f"« {s['nature']} » perd {ha(abs(s['ha']))} ha" for s in x["sorties"])
        out.append({"regle": "reclassement", "texte": f"Reclassement probable en {x['annee']} : {noms} "
                    f"pendant que « {x['contrepartie']['nature']} » gagne {ha(x['contrepartie']['ha'])} ha. Sans ce mouvement, "
                    f"le flux de l'année passe de {signe(x['flux'])} à {signe(x['corrige'])} ha."})

    if c["sauts"]:
        liste = ", ".join(f"{a} ({signe(v, 0)} ha)" for a, v in c["sauts"])
        debut = "Variation inhabituelle à vérifier" if len(c["sauts"]) == 1 else "Variations inhabituelles à vérifier"
        out.append({"regle": "saut", "texte": f"{debut} : {liste}. Il peut s'agir d'un reclassement cadastral "
                    "comme d'un vrai chantier : les données ne permettent pas de trancher."})

    if _part_bassin_citee(c):
        pct = c["part_bassin_pct"]
        out.append({"regle": "bassin", "texte": f"La commune représente {nombre(pct, 0 if arrondi(pct) >= 10 else 1)} % "
                    f"de ce que le bassin {c['bassin']} a artificialisé en {periodes}. "
                    "Le SDT fixe la trajectoire au niveau du bassin, pas de la commune."})
    elif not c["bassin"]:
        out.append({"regle": "bassin", "texte": "Le SDT ne s'applique pas sur le territoire de la Communauté "
                    "germanophone : cette commune n'a pas de bassin ni de trajectoire."})
    return out


def phrases_en(c: dict, stats: dict, signal: str) -> list[str]:
    """Mêmes règles que phrases_fr, dans le même ordre. `signal` : le constat de rythme, déjà établi en français."""
    out = []
    der = stats["annee_stock"]
    part = c["part"]
    txt = f"{nombre_en(part)}% of the territory is artificialised as of 1 January {der}."
    if c["part_iweps"] is not None:
        txt += f" IWEPS reported {nombre_en(c['part_iweps'])}% as of 1 January {stats['annee_iweps']}."
    out.append(txt)

    med, lieu = (c["mediane_bassin"], "its basin's median") if c["bassin"] else (stats["mediane_wallonie"], "the Walloon median")
    ecart = part - med
    if abs(ecart) < ECART_PART_POINTS:
        out.append(f"That is close to {lieu} ({nombre_en(med)}%).")
    elif ecart > 0:
        out.append(f"That is above {lieu} ({nombre_en(med)}%).")
    else:
        out.append(f"That is below {lieu} ({nombre_en(med)}%).")

    h = c["hausse_points"]
    a0 = stats["premiere_annee"]
    if abs(h) < 0.1:
        out.append(f"This share has barely moved since {a0}.")
    elif h < 0:
        out.append(f"This share has fallen by {points_en(-h)} since {a0}, which often reflects cadastral reclassifications.")
    else:
        cat, val = c["moteur"]
        if arrondi(val) > arrondi(h):
            out.append(f"Since {a0}, this share has gained {points_en(h)}. For {PHRASE_CATEGORIE_EN[cat]}, the rise reaches "
                       f"{points_en(val)}, because other categories have fallen.")
        elif val >= 0.5 * h:
            out.append(f"Since {a0}, this share has gained {points_en(h)}, including {nombre_en(val)} for {PHRASE_CATEGORIE_EN[cat]}.")
        else:
            out.append(f"Since {a0}, this share has gained {points_en(h)}. No single category explains most of it: "
                       f"{PHRASE_CATEGORIE_EN[cat]} weighs the most ({points_en(val)}).")

    r, p = c["rythme_recent"], c["rythme_passe"]
    rn, pn = c["rythme_recent_sans_saut"], c["rythme_passe_sans_saut"]
    periodes, passe = _periodes(stats)
    base = f"The recent pace is {ha_en(r)} ha/yr ({periodes}), against {ha_en(p)} ha/yr in {passe}"
    corrige = abs(rn - r) >= ECART_RYTHME_ABSOLU_HA or abs(pn - p) >= ECART_RYTHME_ABSOLU_HA
    hors = f" Without the flagged changes, it becomes {ha_en(rn)} against {ha_en(pn)} ha/yr." if corrige else ""
    if signal == "incertain":
        out.append(f"{base}. It is hard to judge: without the flagged changes, it becomes {ha_en(rn)} against {ha_en(pn)} ha/yr, "
                   "and the finding changes.")
    elif signal == "comparable":
        out.append(f"{base}: it remains comparable.{hors}")
    elif signal == "plus rapide":
        out.append(f"{base}: the municipality is artificialising land faster than before.{hors}")
    else:
        out.append(f"{base}: the municipality is artificialising land more slowly than before.{hors}")

    if r < 0 and rn >= 0:
        out.append("The recent balance is negative because of the flagged changes below: it should not be read as land returning to nature.")
    elif r < 0:
        out.append("The recent balance is negative: more land left the artificialised category than entered it, often because of reclassifications.")

    for x in c["reclassements"]:
        noms = " and ".join(f"“{nature_en(s['nature'])}” loses {ha_en(abs(s['ha']))} ha" for s in x["sorties"])
        out.append(f"Likely reclassification in {x['annee']}: {noms} while “{nature_en(x['contrepartie']['nature'])}” gains "
                   f"{ha_en(x['contrepartie']['ha'])} ha. Without this movement, the year's flow goes from {signe_en(x['flux'])} to {signe_en(x['corrige'])} ha.")

    if c["sauts"]:
        liste = ", ".join(f"{a} ({signe_en(v, 0)} ha)" for a, v in c["sauts"])
        debut = "Unusual change to check" if len(c["sauts"]) == 1 else "Unusual changes to check"
        out.append(f"{debut}: {liste}. This may be a cadastral reclassification or real construction: the data cannot settle it.")

    if _part_bassin_citee(c):
        pct = c["part_bassin_pct"]
        out.append(f"The municipality accounts for {nombre_en(pct, 0 if arrondi(pct) >= 10 else 1)}% of what the "
                   f"{c['bassin']} basin artificialised in {periodes}. The SDT sets the trajectory at basin level, not municipal level.")
    elif not c["bassin"]:
        out.append("The SDT does not apply in the territory of the German-speaking Community: this municipality has no basin and no trajectory.")
    return out
