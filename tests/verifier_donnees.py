"""Audit des données du portail : recalcule tout depuis les fichiers bruts et compare à portail/data/.

Ce fichier n'importe volontairement rien de src/artif/portail.py : une erreur de calcul dans le portail ne doit
pas pouvoir se confirmer elle-même. Les règles sont réécrites d'après le texte de la page Méthode.

Usage : python tests/verifier_donnees.py        (depuis n'importe quel dossier)
Code de sortie 1 si un écart est trouvé. build_portail.py le lance à chaque génération.

Ce que ce test ne prouve pas : que les règles sont les bonnes, que les fichiers bruts sont conformes à ce que
publient leurs producteurs, que les références du SDT sont bien lues sur ses graphiques.
"""
import csv
import glob
import gzip
import json
import os
import re
import statistics as st
import sys
import unicodedata
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
os.chdir(RACINE)

ARTIF = ["resid", "comm", "equip", "loisirs", "agri_bat", "indus", "carrieres", "transport", "autres_art"]
NON = ["arable", "herbe", "foret", "seminat", "humide", "eau", "inconnu"]
CATS = ARTIF + NON
ORDRE_IWEPS = ["artif"] + CATS
PASSE = list(range(2011, 2020))
T005 = {"2015-2019": 11.2, "2020-2024": 12.3, "2025": 10.5}  # fiche T005 de l'IWEPS, septembre 2026, Wallonie entière
ECHANTILLON_ATOL = Path("data/raw/atol/echantillon_33_communes.json")  # usage local : à ne pas redistribuer

ecarts = defaultdict(list)
controles = defaultdict(int)


def ctrl(famille, ok, message):
    controles[famille] += 1
    if not ok:
        ecarts[famille].append(message)


def proche(famille, valeur, attendu, tolerance, message):
    ok = valeur is not None and attendu is not None and abs(valeur - attendu) <= tolerance
    ctrl(famille, ok, f"{message} : portail {valeur}, recalcul {attendu}")


def norme(texte):
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z]", "", t)


def arr(valeur, decimales=1):
    """L'arrondi attendu à l'écran : une demie s'éloigne de zéro, à partir de la vraie valeur."""
    propre = Decimal(repr(round(float(valeur), 8)))
    return propre.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def fr(valeur, decimales=1):
    return f"{arr(valeur, decimales) + 0:.{decimales}f}".replace(".", ",").replace("-", "−")


def en(valeur, decimales=1):
    return f"{arr(valeur, decimales) + 0:,.{decimales}f}".replace("-", "−")


def ha_fr(valeur):
    return fr(valeur, 1 if abs(valeur) < 100 else 0)


# --- Fichiers bruts ---------------------------------------------------------
ref = {int(r["code_ins"]): r for r in csv.DictReader(open("references/communes_bassins_sdt.csv", encoding="utf-8-sig"))}
for r in ref.values():
    r["b"] = r["bassin_sdt"] if r["couvert_par_sdt"] == "oui" else None
nom_vers_code = {norme(r["commune"]): c for c, r in ref.items()}
nom_vers_code["BERTOGNE"] = 82039
table = {int(r["nature"]): r for r in csv.DictReader(open("references/test_spf_iweps/table_natures_categories.csv", encoding="utf-8-sig"))}

idx = json.load(open("portail/data/index.json", encoding="utf-8"))
ANS = idx["meta"]["annees_stock"]
FL = ANS[:-1]
DER = ANS[-1]
RECENT = [a for a in FL if a >= 2021]  # années comptées depuis le départ de la trajectoire du SDT ; la dernière est provisoire

nat = defaultdict(lambda: defaultdict(float))
inconnues = set()
for an in ANS:
    with gzip.open(f"data/raw/spf_occupation_sol/communes_{an}.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = nom_vers_code.get(norme(r["nom"]))
            if c is None:
                inconnues.add((an, r["nom"]))
                continue
            nat[(c, an)][int(r["nature"])] += float(r["m2"]) / 1e4
ctrl("sources", not inconnues, f"communes inconnues : {sorted(inconnues)[:5]}")
sup = {}
for r in csv.DictReader(open("data/processed/artif_communes_stock_annuel.csv", encoding="utf-8-sig")):
    sup[(int(r["code_ins"]), int(r["annee_stock_1er_janvier"]))] = float(r["superficie_ha"])
for c in ref:
    for an in ANS:
        if (c, an) not in sup:
            sup[(c, an)] = sup[(c, an - 1)]

stock = {}
for c in ref:
    for an in ANS:
        d = {k: 0.0 for k in CATS}
        total = 0.0
        for n, v in nat[(c, an)].items():
            d[table[n]["categorie"]] += v
            total += v
        d["inconnu"] += max(sup[(c, an)] - total, 0)
        d["artif"] = sum(d[k] for k in ARTIF)
        stock[(c, an)] = d
flux = {c: {y: stock[(c, y + 1)]["artif"] - stock[(c, y)]["artif"] for y in FL} for c in ref}

iw = defaultdict(dict)
for i, cle in enumerate(ORDRE_IWEPS):
    with open(f"data/raw/iweps_api/215700_{i}.csv", encoding="utf-8-sig") as f:
        lignes = csv.reader(f)
        next(lignes)
        for l in lignes:
            if not l or l[0] in ("82003", "82005"):
                continue
            try:
                iw[(int(l[0]), int(l[3][-4:]))][cle] = float(l[4])
            except ValueError:
                pass


# --- Détection, d'après le texte de la page Méthode -------------------------
def est_artif(n):
    return table[n]["categorie"] in ARTIF


def variations(c, y):
    a, b = nat[(c, y)], nat[(c, y + 1)]
    return {n: b.get(n, 0.0) - a.get(n, 0.0) for n in set(a) | set(b)}


def retenues(delta, seuil):
    gains = {n: v for n, v in delta.items() if not est_artif(n)}
    pertes = sorted((v, n) for n, v in delta.items() if est_artif(n) and v <= -seuil)
    if not pertes or not gains:
        return gains, [], 0.0
    plafond = max(gains.values()) / 0.9
    somme, sorties = 0.0, []
    for v, n in pertes:
        if somme - v <= plafond:
            somme -= v
            sorties.append((n, v))
    return gains, sorties, somme


reclass = {}
for c in ref:
    med = st.median(flux[c].values())
    for y in FL:
        delta = variations(c, y)
        gains, sorties, somme = retenues(delta, 10)
        if not sorties:
            continue
        candidats = [(v, n) for n, v in gains.items() if v >= 0.9 * somme]
        brut = flux[c][y]
        if abs(brut + somme - med) > 0.5 * abs(brut - med):
            continue
        reclass[(c, y)] = {"brut": brut, "corrige": brut + somme, "sorties": sorties, "contrepartie": min(candidats)[1], "gain": min(candidats)[0]}

types, corr = {}, {}
for c in ref:
    co, t = {}, {}
    for y in FL:
        if (c, y) in reclass:
            t[y], co[y] = "reclassement", reclass[(c, y)]["corrige"]
        else:
            co[y] = flux[c][y]
            t[y] = "negatif" if co[y] <= -10 else ""
    sains = [co[y] for y in FL if not t[y]]
    med = st.median(sains)
    mad = st.median(abs(x - med) for x in sains)
    seuil = max(6 * mad, 15)
    for y in FL:
        if not t[y] and abs(co[y] - med) > seuil:
            t[y] = "saut"
    types[c] = t
    corr[c] = {y: (med if t[y] in ("negatif", "saut") else co[y]) for y in FL}


def moy(d, ans):
    return sum(d[y] for y in ans) / len(ans)


def sens(a, b):
    d = a - b
    if abs(d) < 0.5 or abs(d) < 0.15 * abs(b):
        return "comparable"
    return "plus rapide" if d > 0 else "plus lent"


parts = {c: stock[(c, DER)]["artif"] / sup[(c, DER)] * 100 for c in ref}
par_bassin = defaultdict(list)
for c, r in ref.items():
    if r["b"]:
        par_bassin[r["b"]].append(c)
med_b = {b: st.median(parts[c] for c in m) for b, m in par_bassin.items()}
med_w = st.median(parts.values())

# --- Fiches -----------------------------------------------------------------
fiches = {}
for f in glob.glob("portail/data/communes/*.json"):
    for k, v in json.load(open(f, encoding="utf-8")).items():
        fiches[int(k)] = v
ctrl("communes", set(fiches) == set(ref) and len(fiches) == 261, f"{len(fiches)} fiches")
index_c = {c["code"]: c for c in idx["communes"]}
ctrl("communes", set(index_c) == set(ref), "index incomplet")
proche("bassins", idx["meta"]["stats"]["mediane_wallonie"], med_w, 1e-6, "médiane wallonne")

TOL_PART, TOL_HA = 1e-5, 1.1e-4
for c, f in fiches.items():
    r = ref[c]
    n = f["nom"]
    s_der, s_0 = stock[(c, DER)], stock[(c, ANS[0])]
    ctrl("identite", f["nom"] == r["commune"] and f["province"] == r["province"] and f["bassin"] == r["b"], f"{c} identité {n}")

    # Stocks et parts
    proche("stocks", f["superficie"], sup[(c, DER)], .051, f"{n} superficie")
    proche("stocks", f["part"], parts[c], TOL_PART, f"{n} part")
    hausse = {k: s_der[k] / sup[(c, DER)] * 100 - s_0[k] / sup[(c, ANS[0])] * 100 for k in CATS + ["artif"]}
    for k in CATS + ["artif"]:
        proche("stocks", f["ha_estimes"][k], s_der[k], TOL_HA, f"{n} ha {k}")
        for i, an in enumerate(ANS):
            proche("stocks", f["parts_estimees"][k][i], stock[(c, an)][k] / sup[(c, an)] * 100, TOL_PART, f"{n} part {k} {an}")
    for k in CATS:
        proche("stocks", f["hausses"][k], hausse[k], TOL_PART, f"{n} hausse {k}")
    proche("stocks", f["hausse_points"], hausse["artif"], TOL_PART, f"{n} hausse")
    moteur = max(ARTIF, key=lambda k: hausse[k])
    ctrl("stocks", f["moteur"][0] == moteur, f"{n} moteur {f['moteur']} au lieu de {moteur}")

    # IWEPS
    i_der = iw.get((c, idx["meta"]["stats"]["annee_iweps"]), {}).get("artif")
    if f["part_iweps"] is not None or i_der is not None:
        proche("iweps", f["part_iweps"], i_der, .051, f"{n} part IWEPS")
    if f["parts_iweps"]:
        for k in ORDRE_IWEPS:
            for i, an in enumerate(idx["meta"]["annees_iweps"]):
                proche("iweps", f["parts_iweps"][k][i], iw.get((c, an), {}).get(k), .0051, f"{n} IWEPS {k} {an}")

    # Flux et rythmes
    for i, y in enumerate(FL):
        proche("flux", f["flux"][i], flux[c][y], TOL_HA, f"{n} flux {y}")
    rr, rp = moy(flux[c], RECENT), moy(flux[c], PASSE)
    rn, pn = moy(corr[c], RECENT), moy(corr[c], PASSE)
    for cle, attendu in [("rythme_recent", rr), ("rythme_passe", rp), ("rythme_recent_sans_saut", rn), ("rythme_passe_sans_saut", pn)]:
        proche("rythmes", f[cle], attendu, TOL_PART, f"{n} {cle}")

    # Médianes et voisins
    if r["b"]:
        proche("stocks", f["mediane_bassin"], med_b[r["b"]], TOL_PART, f"{n} médiane du bassin")
    for v in f["voisins"]:
        ctrl("voisins", Decimal(repr(v["part"])) == arr(parts[v["code"]]), f"{n} voisin {v['nom']} : {v['part']}, vrai {parts[v['code']]:.4f}")
        ctrl("voisins", c in {x["code"] for x in fiches[v["code"]]["voisins"]}, f"voisinage non réciproque {n}/{v['nom']}")

    # Signalements
    attendu = {y for y in FL if types[c][y] in ("negatif", "saut")}
    ctrl("detection", {a for a, _ in f["sauts"]} == attendu, f"{n} sauts {[a for a, _ in f['sauts']]}, attendu {sorted(attendu)}")
    for a, v in f["sauts"]:
        proche("detection", v, flux[c][a], TOL_HA, f"{n} valeur du saut {a}")
    attendu = {y for y in FL if types[c][y] == "reclassement"}
    ctrl("detection", {x["annee"] for x in f["reclassements"]} == attendu, f"{n} reclassements {[x['annee'] for x in f['reclassements']]}, attendu {sorted(attendu)}")
    for x in f["reclassements"]:
        q = reclass.get((c, x["annee"]))
        if not q:
            continue
        proche("reclassements", x["flux"], q["brut"], TOL_HA, f"{n} {x['annee']} brut")
        proche("reclassements", x["corrige"], q["corrige"], TOL_HA, f"{n} {x['annee']} corrigé")
        proche("reclassements", x["contrepartie"]["ha"], q["gain"], TOL_HA, f"{n} {x['annee']} gain")
        ctrl("reclassements", x["contrepartie"]["nature"] == table[q["contrepartie"]]["libelle"], f"{n} {x['annee']} contrepartie")
        ctrl("reclassements", {s["nature"] for s in x["sorties"]} == {table[m]["libelle"] for m, _ in q["sorties"]}, f"{n} {x['annee']} natures sorties")
        somme = -sum(s["ha"] for s in x["sorties"])
        ctrl("reclassements", all(s["ha"] <= -10 + 1e-3 for s in x["sorties"]), f"{n} {x['annee']} perte sous 10 ha")
        ctrl("reclassements", x["contrepartie"]["ha"] >= .9 * somme - 1e-3, f"{n} {x['annee']} gain sous 90 %")

    # Part dans le bassin
    attendu_pct = None
    if r["b"]:
        total = sum(sum(flux[m][y] for y in RECENT) for m in par_bassin[r["b"]])
        attendu_pct = sum(flux[c][y] for y in RECENT) / total * 100 if total > 0 else None
        proche("bassins", f["part_bassin_pct"], attendu_pct, TOL_PART, f"{n} part dans le bassin")

    # Index : un seul arrondi, à partir de la vraie valeur
    ic = index_c[c]
    ctrl("index", Decimal(repr(ic["part"])) == arr(parts[c]), f"{n} index part {ic['part']}, vrai {parts[c]:.4f}")
    ctrl("index", Decimal(repr(ic["rythme"])) == arr(rr), f"{n} index rythme {ic['rythme']}, vrai {rr:.4f}")
    ctrl("index", Decimal(repr(ic["ecart"])) == arr(rr - rp), f"{n} index écart {ic['ecart']}, vrai {rr - rp:.4f}")
    ctrl("index", ic["saut"] == bool(f["sauts"] or f["reclassements"]), f"{n} index variation")
    s1, s2 = sens(rr, rp), sens(rn, pn)
    signal = s1 if s1 == s2 else "incertain"
    ctrl("interpretation", ic["signal"] == signal, f"{n} constat {ic['signal']}, attendu {signal} ({rr:.2f}/{rp:.2f}, {rn:.2f}/{pn:.2f})")

    # --- Phrases : les règles et les chiffres cités, relus sur les valeurs recalculées
    ph = defaultdict(list)
    for p in f["phrases"]:
        ph[p["regle"]].append(p)
    def doit(regle, morceau, phrase, famille="chiffres-phrases"):  # noqa: E301
        ctrl(famille, morceau in phrase, f"{n} [{regle}] « {morceau} » absent de : {phrase}")

    t = ph["part"][0]["texte"]
    te = ph["part"][0]["texte_en"]
    ctrl("chiffres-phrases", t.startswith(fr(parts[c]) + " %"), f"{n} part {parts[c]:.4f} : {t}")
    ctrl("chiffres-phrases", te.startswith(en(parts[c]) + "%"), f"{n} part {parts[c]:.4f} : {te}")
    if i_der is not None:
        doit("part", fr(i_der) + " %", t)

    med = med_b[r["b"]] if r["b"] else med_w
    e = parts[c] - med
    t = ph["comparaison"][0]["texte"]
    doit("comparaison", "proche" if abs(e) < 1 else "plus que" if e > 0 else "moins que", t, "interpretation")
    doit("comparaison", "de son bassin" if r["b"] else "wallonne", t, "interpretation")
    doit("comparaison", fr(med) + " %", t)

    t = ph["composition"][0]["texte"]
    h = hausse["artif"]
    if abs(h) < .1:
        doit("composition", "presque pas", t, "interpretation")
    elif h < 0:
        doit("composition", "reculé", t, "interpretation")
        doit("composition", fr(-h), t)
    else:
        doit("composition", "gagné", t, "interpretation")
        doit("composition", fr(h), t)
        v = hausse[moteur]
        doit("composition", fr(v), t)
        if arr(v) > arr(h):
            doit("composition", "d'autres catégories ont reculé", t, "interpretation")
            ctrl("interpretation", any(hausse[k] < 0 for k in ARTIF), f"{n} aucune catégorie n'a reculé : {t}")
        elif v >= .5 * h:
            doit("composition", "dont", t, "interpretation")
        else:
            doit("composition", "Aucune catégorie", t, "interpretation")

    t = ph["rythme"][0]["texte"]
    ctrl("interpretation", ph["rythme"][0]["signal"] == signal, f"{n} constat de la phrase")
    doit("rythme", {"incertain": "difficile à juger", "comparable": "comparable", "plus rapide": "plus vite", "plus lent": "moins vite"}[signal], t, "interpretation")
    doit("rythme", f"de {ha_fr(rr)} ha/an", t)
    doit("rythme", f"contre {ha_fr(rp)} ha/an", t)
    corrige_cite = abs(rn - rr) >= .5 or abs(pn - rp) >= .5 or signal == "incertain"
    ctrl("interpretation", ("Sans les variations" in t or "sans les variations" in t) == corrige_cite, f"{n} rappel des variations ({rn:.2f}/{pn:.2f}) : {t}")
    if corrige_cite:
        doit("rythme", f"à {ha_fr(rn)} contre {ha_fr(pn)} ha/an", t)

    if "solde" in ph:
        ctrl("interpretation", rr < 0, f"{n} solde dit négatif alors que {rr:.2f}")
        t = ph["solde"][0]["texte"]
        ctrl("interpretation", ("à cause des variations" in t) == (rn >= 0), f"{n} cause du solde ({rn:.2f}) : {t}")
        if rn >= 0:
            ctrl("interpretation", any(types[c][y] for y in RECENT), f"{n} solde attribué aux variations, sans variation récente : {t}")
    else:
        ctrl("interpretation", rr >= 0, f"{n} solde négatif ({rr:.2f}) sans phrase")

    ctrl("interpretation", ("saut" in ph) == bool(f["sauts"]), f"{n} phrase de saut")
    ctrl("interpretation", len(ph["reclassement"]) == len(f["reclassements"]), f"{n} phrases de reclassement")
    for x, p in zip(f["reclassements"], ph["reclassement"]):
        t = p["texte"]
        q = reclass.get((c, x["annee"]))
        if not q:
            continue
        doit("reclassement", str(x["annee"]), t)
        doit("reclassement", f"gagne {ha_fr(q['gain'])} ha", t)
        doit("reclassement", f"de {'+' if q['brut'] >= 0 else ''}{fr(q['brut'])} à {'+' if q['corrige'] >= 0 else ''}{fr(q['corrige'])} ha", t)
        for m, v in q["sorties"]:
            doit("reclassement", f"« {table[m]['libelle']} » perd {ha_fr(abs(v))} ha", t)
    if f["sauts"]:
        for a, v in f["sauts"]:
            doit("saut", f"{a} ({'+' if v >= 0 else ''}{fr(v, 0)} ha)", ph["saut"][0]["texte"])

    if r["b"]:
        if attendu_pct is not None and arr(attendu_pct) > 0:
            t = ph["bassin"][0]["texte"]
            doit("bassin", fr(attendu_pct, 0 if arr(attendu_pct) >= 10 else 1) + " %", t)
            doit("bassin", r["b"], t)
        else:
            ctrl("interpretation", "bassin" not in ph, f"{n} part du bassin nulle ou négative, mais phrase présente")
    else:
        doit("bassin", "ne s'applique pas", ph["bassin"][0]["texte"], "interpretation")

    # Français et anglais : mêmes nombres, aucun zéro négatif
    for p in f["phrases"]:
        a = sorted(x.replace(",", ".") for x in re.findall(r"\d+(?:,\d+)?", p["texte"]))
        b = sorted(re.findall(r"\d+(?:\.\d+)?", p["texte_en"].replace(",", "")))
        ctrl("francais-anglais", a == b, f"{n} [{p['regle']}] {a} / {b}")
        ctrl("francais-anglais", not re.search(r"−0(?:[,.]0)?\b(?![,.]\d)", p["texte"] + " " + p["texte_en"]), f"{n} zéro négatif : {p['texte']}")

v = idx["meta"]["verifications"]
ctrl("detection", len(reclass) == v["reclassements"]["annees"], f"{len(reclass)} reclassements recalculés, {v['reclassements']['annees']} publiés")
compte = lambda k: sum(1 for c in ref for y in FL if types[c][y] == k)  # noqa: E731
ctrl("detection", compte("negatif") == v["negatifs"]["annees"], "compte des soldes négatifs")
ctrl("detection", compte("saut") == v["sauts"]["annees"], "compte des sauts")


# --- Test du seuil cité par la Méthode --------------------------------------
def test_seuil(seuil):
    oui = total = 0
    for c in ref:
        med = st.median(flux[c].values())
        for y in FL:
            _, sorties, somme = retenues(variations(c, y), seuil)
            if sorties:
                total += 1
                oui += abs(flux[c][y] + somme - med) < abs(flux[c][y] - med)
    return oui, total


for t in v["test_seuil"]:
    oui, total = test_seuil(t["ha"])
    ctrl("methode", (t["oui"], t["total"]) == (oui, total), f"test du seuil à {t['ha']} ha : portail {t['oui']}/{t['total']}, recalcul {oui}/{total}")

# --- Bassins et trajectoires ------------------------------------------------
traj = {r["bassin"]: r for r in csv.DictReader(open("references/trajectoires_sdt_2024_bassins.csv", encoding="utf-8-sig"))}
part_t = lambda a: max((2050 - a) / 29, 0)  # noqa: E731


def verifie_bassin(b, membres, R, marge_ha):
    n = b["nom"]
    tot = {y: sum(flux[c][y] for c in membres) for y in FL}
    tot_n = {y: sum(corr[c][y] for c in membres) for y in FL}
    avant = [a for a in RECENT if a < RECENT[-1]]
    aut = lambda ref_, ans: sum(ref_ * part_t(a) for a in ans)  # noqa: E731
    R_propre = sum(tot[y] for y in PASSE) / len(PASSE)
    ratios = {"confirme": sum(tot[a] for a in avant) / aut(R, avant), "avec_provisoire": sum(tot[a] for a in RECENT) / aut(R, RECENT),
              "sans_saut": sum(tot_n[a] for a in RECENT) / aut(R, RECENT), "reference_recalculee": sum(tot[a] for a in RECENT) / aut(R_propre, RECENT)}
    for k, x in ratios.items():
        proche("bassins", b["ratios"][k], x, TOL_PART, f"{n} ratio {k}")
    for i, y in enumerate(FL):
        proche("bassins", b["flux"][i], tot[y], TOL_HA, f"{n} flux {y}")
        proche("bassins", b["flux_sans_saut"][i], tot_n[y], TOL_HA, f"{n} flux corrigé {y}")
    proche("bassins", b["cumul_observe"], sum(tot[a] for a in RECENT), TOL_HA, f"{n} observé")
    proche("bassins", b["cumul_autorise"], aut(R, RECENT), TOL_HA, f"{n} autorisé")
    proche("bassins", b["cumul_observe_confirme"], sum(tot[a] for a in avant), TOL_HA, f"{n} observé consolidé")
    proche("bassins", b["cumul_autorise_confirme"], aut(R, avant), TOL_HA, f"{n} autorisé consolidé")
    proche("bassins", b["reference_recalculee"], R_propre, TOL_HA, f"{n} référence recalculée")
    proche("bassins", b["plafond_derniere_annee"], R * part_t(RECENT[-1]), TOL_HA, f"{n} plafond")
    proche("bassins", b["incertitude"], marge_ha, 1e-6, f"{n} marge")
    marquante = max(membres, key=lambda c: abs(flux[c][RECENT[-1]]))
    ctrl("bassins", b["marquante"]["code"] == marquante, f"{n} commune marquante {b['marquante']['code']}, attendu {marquante}")
    proche("bassins", b["marquante"]["valeur"], flux[marquante][RECENT[-1]], TOL_HA, f"{n} valeur marquante")
    m = marge_ha / R
    x = list(ratios.values())
    # Une seule lecture : le cumul des années définitives (sans la dernière, provisoire), « proche » à moins de 5 %
    proche_pct = 5
    proche("bassins", b["ratio"], ratios["confirme"], TOL_PART, f"{n} ratio retenu")
    r = ratios["confirme"]
    attendu = "au-dessus" if r > 1 + proche_pct / 100 else "en-dessous" if r < 1 - proche_pct / 100 else "proche"
    ctrl("interpretation", b["statut"] == attendu, f"{n} statut {b['statut']}, attendu {attendu} ({r})")
    ctrl("interpretation", idx["meta"].get("ecart_proche_pct") == proche_pct, f"seuil « proche » {idx['meta'].get('ecart_proche_pct')}, attendu {proche_pct}")
    ctrl("interpretation", "fiabilite" not in b, f"{n} garde un champ « fiabilite » périmé")
    return ratios, m


for b in idx["bassins"]:
    t = traj[b["nom"]]
    R = float(t["artif_nette_moy_10ans_ha_an"])
    verifie_bassin(b, par_bassin[b["nom"]], R, float(t["incertitude_lecture_ha_an"]))
    ctrl("communes", {x["code"] for x in b["communes"]} == set(par_bassin[b["nom"]]), f"{b['nom']} membres")
    for an, cle in [(2025, "traj_2025_ha_an"), (2030, "traj_2030_ha_an"), (2040, "traj_2040_ha_an")]:
        proche("trajectoires", R * part_t(an), float(t[cle]), 1.0, f"{b['nom']} trajectoire {an}")
    for x in b["communes"]:
        c = x["code"]
        ctrl("bassins", Decimal(repr(x["cumul"])) == arr(sum(flux[c][y] for y in RECENT)), f"{b['nom']} cumul {x['nom']}")
        ctrl("bassins", Decimal(repr(x["part"])) == arr(parts[c]) and Decimal(repr(x["rythme"])) == arr(moy(flux[c], RECENT)), f"{b['nom']} ligne {x['nom']}")
tous = [c for m in par_bassin.values() for c in m]
Rw = sum(float(traj[b]["artif_nette_moy_10ans_ha_an"]) for b in par_bassin)
Mw = sum(float(traj[b]["incertitude_lecture_ha_an"]) for b in par_bassin)
ratios_w, marge_w = verifie_bassin(idx["wallonie"], tous, Rw, Mw)
reg = idx["meta"]["region"]
for i, y in enumerate(FL):
    proche("bassins", reg["flux"][i], sum(flux[c][y] for c in ref), TOL_HA, f"région flux {y}")
proche("bassins", reg["part"], sum(stock[(c, DER)]["artif"] for c in ref) / sum(sup[(c, DER)] for c in ref) * 100, .051, "région part")

# --- Exemple de la Méthode --------------------------------------------------
e = idx["meta"]["exemple"]
c = e["code"]
libelle_vers_nature = {r["libelle"]: n for n, r in table.items()}
proche("exemple", e["stock"], stock[(c, DER)]["artif"], .051, "stock")
proche("exemple", e["stock_avant"], stock[(c, DER - 1)]["artif"], .051, "stock précédent")
proche("exemple", e["flux"], flux[c][DER - 1], TOL_HA, "flux")
proche("exemple", e["flux_corrige"], corr[c][DER - 1], TOL_HA, "flux corrigé")
proche("exemple", e["part"], parts[c], TOL_PART, "part")
proche("exemple", e["nb_natures"], len([n for n, x in nat[(c, DER)].items() if x > 0]), 0, "nombre de natures")
proche("exemple", e["mediane"], st.median(flux[c].values()), TOL_HA, "médiane")
gain_terrain = sum(nat[(k, DER)].get(70, 0) - nat[(k, ANS[0])].get(70, 0) for k in ref)
proche("exemple", e["terrain_gain_wallonie"], gain_terrain, 1, "gain de Terrain")
for x in e["premieres"]:
    proche("exemple", x["ha"], nat[(c, DER)].get(libelle_vers_nature[x["nature"]], 0), .051, f"nature {x['nature']}")
for x in e["mouvements"]:
    proche("exemple", x["apres"], nat[(c, DER)].get(libelle_vers_nature[x["nature"]], 0), TOL_HA, f"mouvement {x['nature']}")
    proche("exemple", x["avant"], nat[(c, DER - 1)].get(libelle_vers_nature[x["nature"]], 0), TOL_HA, f"mouvement précédent {x['nature']}")

# --- Fichiers à télécharger -------------------------------------------------
d = "portail/data/telechargements/"
for r in csv.DictReader(open(d + "flux_par_commune.csv", encoding="utf-8-sig")):
    k, y = int(r["code_ins"]), int(r["annee"])
    proche("telechargements", float(r["flux_net_ha"]), flux[k][y], .0051, f"flux {k} {y}")
    proche("telechargements", float(r["flux_corrige_ha"]), corr[k][y], .0051, f"flux corrigé {k} {y}")
    ctrl("telechargements", (r["signalement"] or "") == types[k][y], f"signalement {k} {y}")
for r in csv.DictReader(open(d + "stocks_par_commune.csv", encoding="utf-8-sig")):
    proche("telechargements", float(r["hectares"]), stock[(int(r["code_ins"]), int(r["annee_1er_janvier"]))][r["categorie"]], .0051, f"stock {r['code_ins']} {r['categorie']}")

# --- Chiffres écrits à la main dans la page Méthode -------------------------
app = open("portail/assets/app.js", encoding="utf-8").read()
def cite(texte, explication):  # noqa: E302
    ctrl("methode", texte in app, f"« {texte} » absent de la page Méthode ({explication})")


petites = [n for n, r in table.items() if r["source"] != "donnees"]
surface = sum(float(r["ha_2023"]) for r in table.values())
cite(f"Les {len(petites)} petites natures", "nombre de natures classées d'après le libellé")
cite(f"({fr(sum(float(table[n]['ha_2023']) for n in petites) / surface * 100)} % de la surface cadastrée)", "part de ces natures")
mesures = [abs(stock[(k, a)]["artif"] / sup[(k, a)] * 100 - iw[(k, a)]["artif"]) for k in ref for a in range(2011, 2024) if "artif" in iw.get((k, a), {})]
cite(f"est de {fr(sum(mesures) / len(mesures), 3)} point", "écart moyen à l'IWEPS")
cite(f"environ {fr(st.median(sup[(k, DER)] for k in ref) * 0.001, 0)} ha pour une commune médiane", "valeur de 0,1 point")
km2 = lambda a0, a1: sum(sum(flux[k][y] for k in ref) for y in range(a0, a1 + 1)) / (a1 - a0 + 1) / 100  # noqa: E731
cite(f"on obtient {fr(km2(2015, 2019), 2)} km²/an en 2015-2019 pour {fr(T005['2015-2019'])} publiés", "Wallonie 2015-2019")
cite(f"{fr(km2(2020, 2024), 2)} pour {fr(T005['2020-2024'])} en 2020-2024", "Wallonie 2020-2024")
cite(f"et {fr(km2(2025, 2025), 2)} pour {fr(T005['2025'])} en 2025", "Wallonie 2025")
marges = {float(r["incertitude_lecture_ha_an"]) for r in traj.values() if r["incertitude_lecture_ha_an"]}
ctrl("methode", marges == {2.2}, f"marge de lecture par bassin : {marges}, la page Méthode dit 2,2 ha/an")
cite("Passer de 35,1 à 35,5 % du territoire, c'est gagner 0,4 point", "exemple de ce qu'est un point")

atol_lu = ECHANTILLON_ATOL.exists()
if atol_lu:
    brut = json.load(open(ECHANTILLON_ATOL, encoding="utf-8"))
    atol = defaultdict(dict)
    for k, valeurs in brut.items():   # {code INS : {année : flux}}
        for an, x in valeurs.items():
            if x is not None:
                atol[int(k)][int(an)] = float(x)
    ctrl("methode", len(atol) == 33, f"{len(atol)} communes dans l'échantillon ATOL-C, la page Méthode dit 33")
    diffs = [abs(flux[k][y] - x) for k, s in atol.items() for y, x in s.items() if 2011 <= y <= 2021 and k in ref and y in FL]
    cite(f"l'écart annuel médian est de {fr(st.median(diffs), 2)} ha, et {fr(sum(x > 1 for x in diffs) / len(diffs) * 100, 0)} % des écarts dépassent 1 ha", "comparaison à ATOL-C")
    couverts = sorted((ref[k]["commune"], y) for (k, y) in reclass if k in atol and y in atol[k])
    ctrl("methode", couverts == [("Anderlues", 2012), ("Gouvy", 2016), ("Seraing", 2015)], f"reclassements couverts par ATOL-C : {couverts}")
    code = {ref[k]["commune"]: k for k in ref}
    ctrl("methode", atol[code["Anderlues"]][2012] < 0 and atol[code["Gouvy"]][2016] < 0, "ATOL-C n'affiche plus un solde négatif à Anderlues 2012 et Gouvy 2016")
    ctrl("methode", abs(atol[code["Seraing"]][2015] - reclass[(code["Seraing"], 2015)]["corrige"]) < 1, "ATOL-C n'est plus proche de notre valeur corrigée à Seraing 2015")

# --- Étalement vu du ciel (communes pilotes) --------------------------------
# Cohérence interne de chaque fichier, recalcul du flux cadastral et des totaux wallons depuis la table du raster.
VAT_WALOUS = Path("data/raw/spw_walous/cha_2018_2023/WAL_OCS_IA_CHA_SIEVED__2018_2023.tif.vat.dbf")
etal_meta = idx["meta"].get("etalement") or {"communes": [], "wallonie": None}
etal_fichiers = {int(Path(f).stem): json.load(open(f, encoding="utf-8")) for f in glob.glob("portail/data/etalement/[0-9]*.json")}
ctrl("etalement", sorted(etal_fichiers) == sorted(x["code"] for x in etal_meta["communes"]), "liste des communes pilotes")
for x in etal_meta["communes"]:
    e = etal_fichiers.get(x["code"])
    if not e:
        continue
    r, n = e["resume"], x["nom"]
    ctrl("etalement", r["nom"] == ref[x["code"]]["commune"] == n, f"{n} identité")
    for k in ("neuf_ha", "batiments_ha"):
        proche("etalement", x[k], r[k], 1e-9, f"{n} {k} dans l'index")
    proche("etalement", r["batiments_ha"] + r["abords_ha"], r["neuf_ha"], 0.011, f"{n} bâtiments + abords")
    pf = r["par_famille"]
    proche("etalement", sum(v["batiments_ha"] for v in pf.values()), r["batiments_ha"], 0.05, f"{n} bâtiments par zone")
    proche("etalement", sum(v["abords_ha"] for v in pf.values()), r["abords_ha"], 0.05, f"{n} abords par zone")
    proche("etalement", sum(r["territoire_par_famille_ha"].values()), r["superficie_ha"], r["superficie_ha"] * 0.01, f"{n} zones couvrant la commune")
    proche("etalement", r["superficie_ha"], fiches[x["code"]]["superficie"], fiches[x["code"]]["superficie"] * 0.01, f"{n} superficie cadastrale")
    m2 = defaultdict(float)
    for t in e["taches"]:
        m2[t["c"]] += t["m2"]
    proche("etalement", m2["construction"] / 1e4, r["batiments_ha"], r["batiments_ha"] * 0.01, f"{n} surface des taches bâties")
    proche("etalement", m2["revetement"] / 1e4, r["abords_ha"], r["abords_ha"] * 0.01, f"{n} surface des taches d'abords")
    proche("etalement", sum(p["bati"] for p in e["parcelles"].values()) / 1e4, r["parcelles"]["batiments_ha"], 0.01, f"{n} bâti par parcelle")
    ctrl("etalement", all(t["p"] in e["parcelles"] for t in e["taches"] if t["p"]), f"{n} parcelle inconnue")
    ctrl("etalement", r["centralite"]["neuf_ha"] <= r["neuf_ha"] and r["centralite"]["batiments_ha"] <= r["batiments_ha"], f"{n} centralité")
    ctrl("etalement", r["controles"]["pixels_meme_classe"] == 0 and r["controles"]["pixels_inconnus"] == 0, f"{n} pixels incohérents")
    ctrl("etalement", r["controles"]["service"] is None or r["controles"]["service"]["classe23_identique_pct"] == 100.0, f"{n} écart avec le service du SPW")
    a0, a1 = r["flux_cadastre"]["annees"]
    proche("etalement", r["flux_cadastre"]["ha"], sum(flux[x["code"]][y] for y in range(a0, a1 + 1)), 0.051, f"{n} flux cadastral {a0}-{a1}")
    ctrl("etalement", (a0, a1) == (2018, 2022), f"{n} période cadastrale {a0}-{a1}")
    # Datation : chaque tache a une période, et les périodes refont les totaux
    pe = r.get("periodes")
    ctrl("etalement", pe is not None and list(pe) == ["2018-2019", "2019-2020", "2020-2023"], f"{n} périodes de datation")
    if pe:
        ctrl("etalement", all(t.get("an") in (0, 1, 2) for t in e["taches"]), f"{n} période de chaque tache")
        for j, cle in enumerate(pe):
            for c, champ in (("construction", "batiments_ha"), ("revetement", "abords_ha")):
                proche("etalement", sum(t["m2"] for t in e["taches"] if t["an"] == j and t["c"] == c) / 1e4, pe[cle][champ], 0.011 + pe[cle][champ] * 0.01, f"{n} {champ} {cle}")
        proche("etalement", sum(v["batiments_ha"] for v in pe.values()), r["batiments_ha"], 0.03, f"{n} bâtiments par période")
        proche("etalement", sum(v["abords_ha"] for v in pe.values()), r["abords_ha"], 0.03, f"{n} abords par période")
        ctrl("etalement", 0 <= r["controles"]["datation_incoherente_pct"] <= 15, f"{n} datation incohérente {r['controles']['datation_incoherente_pct']} %")
    # Photos aériennes : chaque image annoncée existe, les tuiles de fond couvrent la carte, les vues restent dedans
    fp = Path(f"portail/data/photos/{x['code']}/index.json")
    if not fp.exists():
        print(f"  Non contrôlé : pas de photos aériennes pour {n} (la carte reste sur le plan de secteur).")
    else:
        ph = json.load(open(fp, encoding="utf-8"))
        dos = fp.parent
        ctrl("etalement", ph["annees"] == list(range(2018, 2027)), f"{n} années des photos")
        ctrl("etalement", set(ph["fond"]["annees"]) <= set(ph["annees"]), f"{n} années du fond")
        manque = [f for a in ph["fond"]["annees"] for i in range(len(ph["fond"]["tuiles"])) if not (dos / f"fond_{a}_{i}.jpg").exists()]
        manque += [f"vues_{a}_{k}" for a in ph["annees"] for k in range(ph["planches"]) if not (dos / f"vues_{a}_{k}.jpg").exists()]
        ctrl("etalement", not manque, f"{n} images manquantes : {manque[:3]}")
        proche("etalement", sum(t["l"] * t["h"] for t in ph["fond"]["tuiles"]), e["largeur"] * e["hauteur"], 1, f"{n} fond couvrant la carte")
        ctrl("etalement", all(-1 <= v["x"] and v["x"] + v["l"] <= e["largeur"] + 1 and -1 <= v["y"] and v["y"] + v["h"] <= e["hauteur"] + 1 for v in ph["vues"]), f"{n} vues dans la carte")
        ctrl("etalement", all(v["px"] + v["pw"] <= 2048 and v["py"] + v["ph"] <= ph["hauteurs_planches"][v["p"]] for v in ph["vues"]), f"{n} vues dans leurs planches")
        # les vues ne se chevauchent pas dans une planche
        cases = defaultdict(list)
        for v in ph["vues"]:
            cases[v["p"]].append((v["px"], v["py"], v["px"] + v["pw"], v["py"] + v["ph"]))
        chevauche = sum(1 for b in cases.values() for i, a in enumerate(b) for c in b[i + 1:] if a[0] < c[2] and c[0] < a[2] and a[1] < c[3] and c[1] < a[3])
        ctrl("etalement", chevauche == 0, f"{n} vues superposées dans une planche : {chevauche}")
        # chaque tache est dans une vue (au centre de sa boîte)
        def boite(d):
            nb = [float(z) for z in re.findall(r"-?\d+(?:\.\d+)?", d)]
            xs, ys = nb[0::2], nb[1::2]
            return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        hors = sum(1 for t in e["taches"] if not any(v["x"] <= boite(t["d"])[0] <= v["x"] + v["l"] and v["y"] <= boite(t["d"])[1] <= v["y"] + v["h"] for v in ph["vues"]))
        ctrl("etalement", hors == 0, f"{n} taches hors des vues à 0,5 m : {hors}")
        ctrl("etalement", all(int(a) in ph["annees"] and all(0 <= i < len(ph["vues"]) for i in l) for a, l in ph.get("manquantes", {}).items()), f"{n} vues manquantes valides")
if VAT_WALOUS.exists() and etal_meta["wallonie"]:
    import pyogrio  # noqa: E402
    v = pyogrio.read_dataframe(VAT_WALOUS, read_geometry=False)
    v = v[v["Value"] > 0]
    art18, art23 = v["Code18"].isin([1, 2, 3]), v["Code23"].isin([1, 2, 3])
    w = etal_meta["wallonie"]
    for cle, masque in (("neuf_ha", ~art18 & art23), ("retour_ha", art18 & ~art23),
                        ("constructions_neuves_ha", ~art18 & (v["Code23"] == 2)), ("constructions_disparues_ha", (v["Code18"] == 2) & ~art23)):
        proche("etalement", w[cle], v.loc[masque, "Count"].sum() / 1e4, 0.51, f"Wallonie {cle}")
elif etal_meta["communes"]:
    print(f"  Non contrôlé : les totaux wallons de WalOUS ({VAT_WALOUS} absent).")

# --- Bilan ------------------------------------------------------------------
total = sum(controles.values())
nb_ecarts = sum(len(x) for x in ecarts.values())
print(f"Audit des données : {total} contrôles sur {len(fiches)} communes, {nb_ecarts} écart(s).")
if not atol_lu:
    print(f"  Non contrôlé : les chiffres ATOL-C de la Méthode ({ECHANTILLON_ATOL} absent).")
if "-v" in sys.argv:
    for famille in sorted(controles):
        print(f"  {famille:<20} {controles[famille]:>7} contrôles, {len(ecarts.get(famille, []))} écart(s)")
for famille, liste in sorted(ecarts.items()):
    print(f"\n--- {famille} : {len(liste)} écart(s)")
    for x in liste[:15]:
        print("   ", x[:320])
sys.exit(1 if nb_ecarts else 0)
