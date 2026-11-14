"""Fragments LaTeX du rapport : macros chiffrées et tableaux, régénérés à chaque exécution.

Aucun chiffre du rapport n'est saisi à la main : le texte appelle les macros de
report/generated/chiffres.tex et inclut les tableaux de report/generated/*.tex.
"""
import json
import platform
from datetime import date

import numpy as np
import pandas as pd

from . import suivi
from .analyse import WALLONIE
from .config import (BASELINE, DEFINITION_PRINCIPALE, DEFINITIONS, PROCESSED, RAW, REPORT_GENERATED, SAUT_K_MAD,
                     SAUT_SEUIL_MIN_HA, TRAJ_END, TRAJ_START)

ABBR = {"Brabant wallon": "BW", "Hainaut 1": "H1", "Hainaut 2": "H2", "Liège 1": "L1", "Liège 2": "L2",
        "Luxembourg": "Lux", "Namur": "Nam", WALLONIE: "Wal."}
STATUT_COURT = {"au-dessus de la trajectoire": "au-dessus", "dans la trajectoire": "dans",
                "référence non interprétable": "n.i."}
# Rythmes d'artificialisation nette publiés par l'IWEPS (Charlier et Reginster, Regards statistiques
# n° 12, 2024, résumé p. 5), Wallonie francophone, km²/an. Bornes interprétées en années de consommation.
IWEPS_RS12 = {(2010, 2014): 12.2, (2015, 2019): 10.8, (2020, 2022): 11.6}
# Même indicateur, millésime suivant (données au 01/01/2024) : note préparatoire CPDT 2025, fig. 16, période 2020-2023.
IWEPS_SERIES = [((a, b), v, "RS12 (2024)") for (a, b), v in IWEPS_RS12.items()] + [((2020, 2023), 11.6, "CPDT (2025)")]
CPDT_PERIODE = (2021, 2023)


def num(x: float, nd: int = 0, signe: bool = False) -> str:
    """Nombre au format français pour LaTeX (espace fine des milliers, virgule décimale)."""
    if x is None or pd.isna(x):
        return "--"
    s = f"{x:+,.{nd}f}" if signe else f"{x:,.{nd}f}"
    s = s.replace(",", "\\,").replace(".", "{,}")
    return s.replace("-", "\\textminus{}", 1) if s.startswith("-") else s


def esc(s: str) -> str:
    for a, b in [("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"), ("_", "\\_"), ("#", "\\#")]:
        s = s.replace(a, b)
    return s


def _write(name: str, text: str) -> None:
    REPORT_GENERATED.mkdir(parents=True, exist_ok=True)
    (REPORT_GENERATED / name).write_text(text, encoding="utf-8")


def _tabular(cols: str, header: str, rows: list[str], foot: list[str] = ()) -> str:
    body = "\n".join(r + r" \\" for r in rows)
    tail = ("\\midrule\n" + "\n".join(r + r" \\" for r in foot) + "\n") if foot else ""
    return f"\\begin{{tabular}}{{{cols}}}\n\\toprule\n{header} \\\\\n\\midrule\n{body}\n{tail}\\bottomrule\n\\end{{tabular}}\n"


def reclassements(raw: pd.DataFrame) -> dict:
    """Variations par rubrique des cas de reclassement cités dans le texte (ha)."""
    def delta(code, rubriques, year):
        d = raw[(raw["code_ins"] == code) & raw["rubrique"].isin(rubriques)]
        g = d.groupby("annee")["ha"].sum()
        return g.get(year + 1, 0.0) - g.get(year, 0.0)
    bati = sorted(r for r in raw["rubrique"].unique() if r.startswith("2"))
    return {"ArlonJ": num(delta("81001", ["1J"], 2024)), "ArlonG": num(-delta("81001", ["1G"], 2024)),
            "BlegnyNC": num(-delta("62119", ["5TOT"], 2020)), "BlegnyRST": num(delta("62119", ["2RST"], 2020)),
            "BlegnyBati": num(delta("62119", bati, 2020))}


def comparaison_cpdt(res: dict, cpdt: pd.DataFrame) -> pd.DataFrame:
    """Bassin par bassin : série CPDT/IWEPS 2021-2023 et trajectoire CPDT, face à l'étude."""
    a, b = CPDT_PERIODE
    ev_b, cons_b = res["eval_bassins"], res["cons_bassins"]
    years = suivi.observed_years(res["cons"])
    f3 = np.mean([suivi.trajectory_factor(y) for y in range(a, b + 1)])
    fyrs = sum(suivi.trajectory_factor(y) for y in years)
    rows = {}
    for bassin, c in cpdt.iterrows():
        obs3 = cons_b.loc[bassin, a:b].mean()
        ref_sdt, ref_cpdt = ev_b.loc[bassin, "moyenne_ref_ha_an"], c["cpdt_reference_implicite_ha_an"]
        rows[bassin] = {
            "cpdt_obs": c[f"cpdt_{a}-{b}"], "etude_obs": obs3, "ecart": obs3 - c[f"cpdt_{a}-{b}"],
            "ref_sdt": ref_sdt, "ref_cpdt": ref_cpdt, "cpdt_traj": c["cpdt_traj_2021_2023"],
            "ratio_cpdt": c[f"cpdt_{a}-{b}"] / c["cpdt_traj_2021_2023"],
            "ratio_etude_3ans": obs3 / (ref_sdt * f3),
            "ratio_etude": ev_b.loc[bassin, "ratio_obs_traj"],
            "ratio_etude_ref_cpdt": ev_b.loc[bassin, "conso_cumul_obs_ha"] / (ref_cpdt * fyrs),
        }
    df = pd.DataFrame(rows).T
    tot = df[["cpdt_obs", "etude_obs", "ecart", "ref_sdt", "ref_cpdt", "cpdt_traj"]].sum()
    df.loc[WALLONIE] = {**tot.to_dict(), "ratio_cpdt": tot["cpdt_obs"] / tot["cpdt_traj"],
                        "ratio_etude_3ans": tot["etude_obs"] / (tot["ref_sdt"] * f3),
                        "ratio_etude": ev_b.loc[WALLONIE, "ratio_obs_traj"],
                        "ratio_etude_ref_cpdt": ev_b.loc[WALLONIE, "conso_cumul_obs_ha"] / (tot["ref_cpdt"] * fyrs)}
    return df


def macros(res: dict, cons_by_def: dict, cmp: pd.DataFrame) -> str:
    ev_b, ev_c, var, val = res["eval_bassins"], res["eval_communes"], res["variabilite"], res["validation"]
    sens, comp, sdt = res["sensibilite"], res["composition"], res["sdt"]
    w = ev_b.loc[WALLONIE]
    years = suivi.observed_years(res["cons"])
    statuts = ev_c["statut"].value_counts()
    r = ev_c["ratio_obs_traj"].dropna()
    swap = ev_c["statut"] != ev_c["statut_sauts_neutralises"]
    up = (ev_c["statut"] == "dans la trajectoire") & swap
    lux, nam = ev_b.loc["Luxembourg"], ev_b.loc["Namur"]
    sens_w = sens[f"ratio_{WALLONIE}"]
    covered = res["communes"]["couvert_par_sdt"] == "oui"
    stk, surf = res["stock"], res["surface"]
    last = stk.columns.max()
    stk_c, surf_c = stk.loc[covered[covered].index], surf.loc[covered[covered].index]
    zero = sdt["annee_zero_lue"].drop(WALLONIE)
    unc = sdt["incertitude_lecture_ha_an"].drop(WALLONIE)
    princ = cons_by_def[DEFINITION_PRINCIPALE]
    ecart_iweps = princ.loc[2020:2022].mean() / 100 - IWEPS_RS12[(2020, 2022)]
    ecart_iweps_ancien = max((princ.loc[a:b].mean() / 100 - v for (a, b), v in IWEPS_RS12.items() if b < 2020), key=abs)
    cw, cb = cmp.loc[WALLONIE], cmp.drop(WALLONIE)
    quart = ev_c.groupby(pd.qcut(ev_c["part_artificialisee_derniere_annee_pct"], 4), observed=True)["statut"].apply(
        lambda x: (x == "au-dessus de la trajectoire").mean())
    m = {
        "AnneeDebutObs": years[0], "AnneeFinObs": years[-1], "NbAnneesObs": len(years), "AnneeStock": last,
        "RefDebut": BASELINE[0], "RefFin": BASELINE[1], "TrajDebut": TRAJ_START, "TrajFin": TRAJ_END,
        "NbCommunes": len(res["communes"]), "NbCommunesSDT": int(covered.sum()),
        "NbCommunesCG": int((~covered).sum()),
        "WalRef": num(w["moyenne_ref_ha_an"]), "WalRefKm": num(w["moyenne_ref_ha_an"] / 100, 1),
        "WalRefRecalc": num(w["moyenne_ref_ha_an_recalculee"]),
        "WalObsMoy": num(w["conso_moy_obs_ha_an"]), "WalObsMoyKm": num(w["conso_moy_obs_ha_an"] / 100, 1),
        "WalCumObs": num(w["conso_cumul_obs_ha"]), "WalCumTraj": num(w["conso_cumul_traj_ha"]),
        "WalEcart": num(w["ecart_cumul_ha"]), "WalRatio": num(w["ratio_obs_traj"], 2),
        "WalRatioRecalc": num(w["ratio_obs_traj_recalculee"], 2),
        "WalPlafondFin": num(w["plafond_derniere_annee_ha_an"]),
        "WalObsFin": num(res["cons_bassins"].loc[WALLONIE, years[-1]]),
        "WalBudget": num(sdt.loc[WALLONIE, "budget_cumule_2021_2050_ha"]),
        "WalBudgetKm": num(sdt.loc[WALLONIE, "budget_cumule_2021_2050_ha"] / 100, 0),
        "WalBudgetConsommePct": num(w["conso_cumul_obs_ha"] / sdt.loc[WALLONIE, "budget_cumule_2021_2050_ha"] * 100, 0),
        "WalTrajQuinze": num(sdt.loc[WALLONIE, "traj_2025_ha_an"]),
        "WalTrajTrente": num(sdt.loc[WALLONIE, "traj_2030_ha_an"]),
        "WalVarPct": num(var.loc[WALLONIE, "variation_pct"], 1, True), "WalZ": num(var.loc[WALLONIE, "z"], 1),
        "WalEcartType": num(var.loc[WALLONIE, "ecart_type_ref"]),
        "LuxVarPct": num(var.loc["Luxembourg", "variation_pct"], 0, True), "LuxZ": num(var.loc["Luxembourg", "z"], 1),
        "NamVarPct": num(var.loc["Namur", "variation_pct"], 0, True), "NamZ": num(var.loc["Namur", "z"], 1),
        "BWVarPct": num(var.loc["Brabant wallon", "variation_pct"], 0, True), "BWZ": num(var.loc["Brabant wallon", "z"], 1),
        "HDVarPct": num(var.loc["Hainaut 2", "variation_pct"], 0, True), "HDZ": num(var.loc["Hainaut 2", "z"], 1),
        "LuxRatio": num(lux["ratio_obs_traj"], 2), "NamRatio": num(nam["ratio_obs_traj"], 2),
        "LuxEcart": num(lux["ecart_cumul_ha"]), "NamEcart": num(nam["ecart_cumul_ha"]),
        "LuxNamPartEcart": num((lux["ecart_cumul_ha"] + nam["ecart_cumul_ha"]) / w["ecart_cumul_ha"] * 100, 0),
        "LuxObsMoy": num(lux["conso_moy_obs_ha_an"]), "LuxRef": num(lux["moyenne_ref_ha_an"]),
        "NamObsMoy": num(nam["conso_moy_obs_ha_an"]), "NamRef": num(nam["moyenne_ref_ha_an"]),
        "LuxRatioNeutre": num(sens.loc[sens["groupe"] == "Anomalies", "ratio_Luxembourg"].iloc[0], 2),
        "WalRatioNeutre": num(sens.loc[sens["groupe"] == "Anomalies", f"ratio_{WALLONIE}"].iloc[0], 2),
        "NbBassinsAuDessus": int((ev_b.drop(WALLONIE)["ratio_obs_traj"] > 1).sum()),
        "NbAuDessus": int(statuts.get("au-dessus de la trajectoire", 0)),
        "NbDans": int(statuts.get("dans la trajectoire", 0)),
        "NbNonInterp": int(statuts.get("référence non interprétable", 0)),
        "PartAuDessusPct": num(statuts.get("au-dessus de la trajectoire", 0) / len(ev_c) * 100, 0),
        "RatioMed": num(r.median(), 2), "RatioQa": num(r.quantile(0.25), 2), "RatioQc": num(r.quantile(0.75), 2),
        "RatioMax": num(r.max(), 1), "CommuneRatioMax": esc(ev_c.loc[r.idxmax(), "commune"]),
        "RefCommuneRatioMax": num(ev_c.loc[r.idxmax(), "moyenne_ref_ha_an"], 1),
        "NbSautsSuivi": int((ev_c["sauts_a_verifier_suivi"] != "").sum()),
        "NbSautsRef": int((ev_c["sauts_a_verifier_reference"] != "").sum()),
        "NbBasculeHaut": int(up.sum()), "NbBasculeBas": int((swap & ~up).sum()),
        "NbAuDessusNeutre": int((ev_c["statut_sauts_neutralises"] == "au-dessus de la trajectoire").sum()),
        "SensMin": num(sens_w.min(), 2), "SensMax": num(sens_w.max(), 2),
        "SensMinVar": esc(sens.loc[sens_w.idxmin(), "variante"]), "SensMaxVar": esc(sens.loc[sens_w.idxmax(), "variante"]),
        "SensNbVariantes": len(sens),
        "SensComMin": int(sens["communes_au_dessus"].min()), "SensComMax": int(sens["communes_au_dessus"].max()),
        "PartArtifWal": num(stk_c[last].sum() / surf_c[last].sum() * 100, 1),
        "PartArtifWalLarge": num(val.loc["large", "stock_2023_pct"], 1),
        "StockArtifKm": num(stk_c[last].sum() / 100, 0),
        "SautSeuil": num(SAUT_SEUIL_MIN_HA), "SautK": num(SAUT_K_MAD),
        "ZeroMin": f"{zero.min():.1f}".replace(".", "{,}"), "ZeroMax": f"{zero.max():.1f}".replace(".", "{,}"), "IncertLecture": num(unc.max(), 1),
        "NonCadRef": num(comp.loc["5TOT", "ref_2010_2019_ha_an"]), "NonCadObs": num(comp.loc["5TOT", "obs_2021_n_ha_an"]),
        "MaisonsRef": num(comp.loc["2C", "ref_2010_2019_ha_an"]), "MaisonsObs": num(comp.loc["2C", "obs_2021_n_ha_an"]),
        "ApptRef": num(comp.loc["2A1A2", "ref_2010_2019_ha_an"]), "ApptObs": num(comp.loc["2A1A2", "obs_2021_n_ha_an"]),
        "AnnexesRef": num(comp.loc["2DEF", "ref_2010_2019_ha_an"]), "AnnexesObs": num(comp.loc["2DEF", "obs_2021_n_ha_an"]),
        "AutresNBRef": num(comp.loc["1MNOP", "ref_2010_2019_ha_an"]), "AutresNBObs": num(comp.loc["1MNOP", "obs_2021_n_ha_an"]),
        "BoisRef": num(comp.loc["1G", "ref_2010_2019_ha_an"]), "BoisObs": num(comp.loc["1G", "obs_2021_n_ha_an"]),
        "PrincNonantePic": num(princ.loc[1985:1999].max() / 100, 1),
        "PrincDixDix": num(princ.loc[2010:2019].mean() / 100, 1),
        "PythonVersion": platform.python_version(), "DateGeneration": date.today().strftime("%d/%m/%Y"),
        "WalDepassPct": num((w["ratio_obs_traj"] - 1) * 100, 0),
        "WalDepassFinPct": num((res["cons_bassins"].loc[WALLONIE, years[-1]] / w["plafond_derniere_annee_ha_an"] - 1) * 100, 0),
        "WalBaisseAn": num(w["moyenne_ref_ha_an"] / (TRAJ_END - TRAJ_START)),
        "WalEcartProj": num(round((w["conso_moy_obs_ha_an"] - w["moyenne_ref_ha_an"] * np.mean(
            [suivi.trajectory_factor(y) for y in range(TRAJ_START, 2031)])) * (2031 - TRAJ_START), -2)),
        "PartTempsPct": num(len(years) / (TRAJ_END - TRAJ_START + 1) * 100, 0),
        "LUnRatio": num(ev_b.loc["Liège 1", "ratio_obs_traj"], 2), "LUnRef": num(ev_b.loc["Liège 1", "moyenne_ref_ha_an"]),
        "HUnRatio": num(ev_b.loc["Hainaut 1", "ratio_obs_traj"], 2),
        "HUnRatioRecalc": num(ev_b.loc["Hainaut 1", "ratio_obs_traj_recalculee"], 2),
        "HUnRef": num(ev_b.loc["Hainaut 1", "moyenne_ref_ha_an"]),
        "HUnRefRecalc": num(ev_b.loc["Hainaut 1", "moyenne_ref_ha_an_recalculee"]),
        "SensCalageMin": num(sens_w[sens["groupe"] == "Calage de la trajectoire"].min(), 2),
        "SensCalageMax": num(sens_w[sens["groupe"] == "Calage de la trajectoire"].max(), 2),
        "SensDefLarge": num(sens_w[sens["variante"].str.contains("jardins")].iloc[0], 2),
        "SensDefBati": num(sens_w[sens["variante"].str.contains("bâties seules")].iloc[0], 2),
        "SensLectureDelta": num((sens_w[sens["groupe"] == "Lecture des graphiques"] - sens_w.iloc[0]).abs().max(), 2),
        "NbStatutsModifies": int(swap.sum()),
        "NbVarHDDessous": int((sens["ratio_Hainaut 2"] <= 1).sum()),
        "NbVarLUnDessus": int((sens["ratio_Liège 1"] > 1).sum()),
        "EcartFluxLarge": num(val.loc["large", "flux_2010_2019_km2"] - val.loc[DEFINITION_PRINCIPALE, "flux_2010_2019_km2"], 0),
        "PartAuDessusQuartBas": num(quart.iloc[0] * 100, 0), "PartAuDessusQuartHaut": num(quart.iloc[-1] * 100, 0),
        "CorrPartRatio": num(ev_c[["part_artificialisee_derniere_annee_pct", "ratio_obs_traj"]].corr("spearman").iloc[0, 1], 2),
        "IwepsEcartRecent": num(ecart_iweps, 1, True), "IwepsEcartAncien": num(ecart_iweps_ancien, 1, True),
        "IwepsEcartQuatre": num(princ.loc[2020:2023].mean() / 100 - 11.6, 1, True),
        "PrincDeuxMilleVingt": num(princ.loc[2020]), "PrincVingtEtUnVingtTrois": num(princ.loc[2021:2023].mean()),
        # Comparaison par bassin à la note préparatoire CPDT (données IWEPS au 01/01/2024), 2021-2023
        "CpdtEcartWal": num(cw["ecart"], 0, True), "CpdtEcartPct": num(cw["ecart"] / cw["cpdt_obs"] * 100, 1, True),
        "CpdtEcartMin": num(cb["ecart"].min(), 0, True), "CpdtEcartMax": num(cb["ecart"].max(), 0, True),
        "CpdtObsWal": num(cw["cpdt_obs"]), "CpdtRatioWal": num(cw["ratio_cpdt"], 2),
        "EtudeRatioTroisWal": num(cw["ratio_etude_3ans"], 2),
        "CpdtDepassPct": num((cw["ratio_cpdt"] - 1) * 100, 0),
        "EtudeDepassTroisPct": num((cw["ratio_etude_3ans"] - 1) * 100, 0),
        "CpdtRatioLux": num(cmp.loc["Luxembourg", "ratio_cpdt"], 2), "CpdtRatioNam": num(cmp.loc["Namur", "ratio_cpdt"], 2),
        "CpdtRatioLUn": num(cmp.loc["Liège 1", "ratio_cpdt"], 2), "CpdtRatioHUn": num(cmp.loc["Hainaut 1", "ratio_cpdt"], 2),
        "LUnRefCpdt": num(cmp.loc["Liège 1", "ref_cpdt"]), "LUnRatioRefCpdt": num(cmp.loc["Liège 1", "ratio_etude_ref_cpdt"], 2),
        "LUnRatioTrois": num(cmp.loc["Liège 1", "ratio_etude_3ans"], 2),
        "LUnObsFin": num(res["cons_bassins"].loc["Liège 1", years[-1]]),
        "CpdtRefEcartAutres": num((cb["ref_cpdt"] - cb["ref_sdt"]).drop("Liège 1").abs().max(), 0),
        "WalRatioRefCpdt": num(cw["ratio_etude_ref_cpdt"], 2),
        # Variante d'étalonnage : retrancher chaque année observée l'écart moyen 2021-2023 à la série CPDT/IWEPS
        "WalRatioCal": num((w["conso_cumul_obs_ha"] - cw["ecart"] * len(years)) / w["conso_cumul_traj_ha"], 2),
        **reclassements(res["raw"]),
    }
    for k in DEFINITIONS:
        tag = {"bati": "Bati", "principale": "Princ", "large": "Large"}[k]
        v = val.loc[k]
        m[f"Val{tag}StockQuinze"] = num(v["stock_2015_pct"], 1)
        m[f"Val{tag}StockVingtTrois"] = num(v["stock_2023_pct"], 1)
        m[f"Val{tag}Flux"] = num(v["flux_2010_2019_km2"], 1)
        m[f"Val{tag}FluxQuinze"] = num(v["flux_2015_2019_km2"], 1)
        m[f"Val{tag}Corr"] = num(v["corr_mediane_lag0"], 2)
        m[f"Val{tag}CorrLag"] = num(v["corr_mediane_lag1"], 2)
        m[f"Val{tag}MAE"] = num(v["ecart_abs_moy_lag0_ha"], 0)
        m[f"Val{tag}EcartRef"] = num(v["ecart_moy_ref_bassins_ha"], 0)
    return "% Généré par src/artif/rapport.py -- ne pas éditer\n" + "\n".join(
        f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in m.items()) + "\n"


def table_sdt(sdt: pd.DataFrame) -> str:
    rows = []
    for b, s in sdt.drop(WALLONIE).iterrows():
        rows.append(f"{b} & {num(s['artif_nette_moy_10ans_ha_an'])} & {num(s['incertitude_lecture_ha_an'], 1)} & "
                    f"{num(s['traj_2025_ha_an'])} & {num(s['traj_2030_ha_an'])} & {num(s['traj_2040_ha_an'])} & "
                    f"{num(s['budget_cumule_2021_2050_ha'])} & {num(s['annee_zero_lue'], 1)} & "
                    f"{num(s['part_logements_centralite_2010_2020_pct'])}")
    w = sdt.loc[WALLONIE]
    foot = [f"\\textbf{{Wallonie (hors CG)}} & \\textbf{{{num(w['artif_nette_moy_10ans_ha_an'])}}} & & "
            f"{num(w['traj_2025_ha_an'])} & {num(w['traj_2030_ha_an'])} & {num(w['traj_2040_ha_an'])} & "
            f"{num(w['budget_cumule_2021_2050_ha'])} & & "]
    head = ("Bassin & \\makecell{Moyenne\\\\décennale} & \\makecell{Incert.\\\\lecture} & 2025 & 2030 & 2040 & "
            "\\makecell{Budget\\\\2021-2050 (ha)} & \\makecell{Zéro lu\\\\(année)} & \\makecell{Logements en\\\\centralité (\\%)}")
    return _tabular("lrrrrrrrr", head, rows, foot)


def table_bassins(ev_b: pd.DataFrame, cons_b: pd.DataFrame, years: list[int]) -> str:
    rows, foot = [], []
    for b, s in ev_b.iterrows():
        cells = [f"{num(s['moyenne_ref_ha_an'])}", f"{num(s['moyenne_ref_ha_an_recalculee'])}"]
        cells += [num(cons_b.loc[b, y]) for y in years]
        cells += [num(s["conso_cumul_obs_ha"]), num(s["conso_cumul_traj_ha"]), num(s["ecart_cumul_ha"], signe=True),
                  f"\\textbf{{{num(s['ratio_obs_traj'], 2)}}}", num(s["ratio_obs_traj_recalculee"], 2)]
        line = (("\\textbf{Wallonie (hors CG)}" if b == WALLONIE else b) + " & " + " & ".join(cells))
        (foot if b == WALLONIE else rows).append(line)
    head = ("Bassin & \\makecell{Réf.\\\\SDT} & \\makecell{Réf.\\\\recalc.} & " + " & ".join(map(str, years)) +
            " & \\makecell{Cumul\\\\observé} & \\makecell{Cumul\\\\autorisé} & Écart & \\makecell{Ratio\\\\(SDT)} & "
            "\\makecell{Ratio\\\\(recalc.)}")
    return _tabular("l" + "r" * (len(years) + 7), head, rows, foot)


def table_validation(val: pd.DataFrame) -> str:
    rows = []
    for k, v in val.iterrows():
        name = esc(v["libelle"]) + (" \\textbf{(retenue)}" if k == DEFINITION_PRINCIPALE else "")
        rows.append(f"{name} & {num(v['stock_2015_pct'], 1)} & {num(v['stock_2023_pct'], 1)} & "
                    f"{num(v['flux_2010_2019_km2'], 1)} & {num(v['flux_2015_2019_km2'], 1)} & "
                    f"{num(v['ecart_moy_ref_bassins_ha'], 0)} & {num(v['corr_mediane_lag0'], 2)} & "
                    f"{num(v['ecart_abs_moy_lag0_ha'], 0)} & {num(v['corr_mediane_lag1'], 2)}")
    head = ("Définition & \\makecell{Stock\\\\2015 (\\%)} & \\makecell{Stock\\\\2023 (\\%)} & "
            "\\makecell{Flux 2010-19\\\\(km²/an)} & \\makecell{Flux 2015-19\\\\(km²/an)} & "
            "\\makecell{|Réf. bassin\\\\ $-$ SDT| (ha)} & \\makecell{$r$ médian\\\\(même année)} & "
            "\\makecell{Écart abs.\\\\moyen (ha)} & \\makecell{$r$ médian\\\\(décalage 1 an)}")
    rows.append("\\addlinespace \\emph{Références publiées} & & $\\geq$\\,10{,}8$^{a}$ & 11{,}5$^{b}$ & "
                f"{num(IWEPS_RS12[(2015, 2019)], 1)}$^{{c}}$ & & & &")
    return _tabular("p{4.4cm}rrrrrrrr", head, rows)


def table_iweps(cons_by_def: dict) -> str:
    """Rythmes régionaux par période : IWEPS (RS12) et les trois définitions cadastrales."""
    keys = list(DEFINITIONS)
    rows = []
    for (a, b), ref, src in IWEPS_SERIES:
        ours = [cons_by_def[k].loc[a:b].mean() / 100 for k in keys]
        cells = [num(v, 1) for v in ours]
        cells[keys.index(DEFINITION_PRINCIPALE)] = f"\\textbf{{{cells[keys.index(DEFINITION_PRINCIPALE)]}}}"
        rows.append(f"{a}-{b} & {num(ref, 1)} & {src} & " + " & ".join(cells) +
                    f" & {num(ours[keys.index(DEFINITION_PRINCIPALE)] - ref, 1, True)}")
    noms = {"bati": "Bâti seul", "principale": "Principale", "large": "Large"}
    head = ("\\makecell{Années de\\\\consommation} & IWEPS & \\makecell{Publication\\\\(millésime)} & " +
            " & ".join(noms[k] for k in keys) + " & \\makecell{Écart\\\\principale $-$ IWEPS}")
    return _tabular("lrlrrrr", head, rows)


def table_cpdt(cmp: pd.DataFrame) -> str:
    """Comparaison par bassin à la note préparatoire CPDT (2021-2023)."""
    rows, foot = [], []
    for b, s in cmp.iterrows():
        cells = [num(s["cpdt_obs"]), num(s["etude_obs"]), num(s["ecart"], 0, True), num(s["ref_cpdt"]),
                 num(s["ref_sdt"]), f"\\textbf{{{num(s['ratio_cpdt'], 2)}}}", num(s["ratio_etude_3ans"], 2),
                 num(s["ratio_etude"], 2)]
        line = ("\\textbf{Wallonie (hors CG)}" if b == WALLONIE else b) + " & " + " & ".join(cells)
        (foot if b == WALLONIE else rows).append(line)
    head = ("Bassin & \\makecell{CPDT/IWEPS\\\\2021-2023} & \\makecell{Étude\\\\2021-2023} & Écart & "
            "\\makecell{Réf.\\\\CPDT$^{a}$} & \\makecell{Réf.\\\\SDT$^{b}$} & \\makecell{Ratio CPDT\\\\2021-2023} & "
            "\\makecell{Ratio étude\\\\2021-2023$^{c}$} & \\makecell{Ratio étude\\\\2021-2024}")
    return _tabular("lrrrrrrrr", head, rows, foot)


def table_sensibilite(sens: pd.DataFrame) -> str:
    bassins = [c[6:] for c in sens.columns if c.startswith("ratio_")]
    order = [b for b in ABBR if b in bassins]
    rows, group = [], None
    for _, s in sens.iterrows():
        if s["groupe"] != group:
            group = s["groupe"]
            rows.append(f"\\multicolumn{{{len(order) + 2}}}{{l}}{{\\emph{{{esc(group)}}}}}")
        vals = [num(s[f"ratio_{b}"], 2) for b in order]
        vals[-1] = f"\\textbf{{{vals[-1]}}}"
        rows.append(f"\\quad {esc(s['variante'])} & " + " & ".join(vals) + f" & {int(s['communes_au_dessus'])}")
    head = "Variante & " + " & ".join(ABBR[b] for b in order) + " & \\makecell{Communes\\\\au-dessus}"
    return _tabular("p{5.6cm}" + "r" * (len(order) + 1), head, rows)


def table_variabilite(var: pd.DataFrame) -> str:
    rows = []
    for b, v in var.iterrows():
        rows.append(f"{'Wallonie (hors CG)' if b == WALLONIE else b} & {num(v['moyenne_ref'])} & "
                    f"{num(v['ecart_type_ref'])} & {num(v['moyenne_obs'])} & {num(v['variation_pct'], 1, True)} & "
                    f"{num(v['z'], 2)}")
    head = ("Bassin & \\makecell{Moyenne\\\\2010-2019} & \\makecell{Écart-type\\\\interannuel} & "
            "\\makecell{Moyenne\\\\2021-2024} & Variation (\\%) & $z$")
    return _tabular("lrrrrr", head, rows)


def table_composition(comp: pd.DataFrame) -> str:
    rows = []
    for r, c in comp.sort_index().iterrows():
        d = "principale" if c["dans_principale"] else ("large" if c["dans_large"] else "--")
        rows.append(f"{r} & {esc(c['libelle'])} & {d} & {num(c['ref_2010_2019_ha_an'], 1)} & "
                    f"{num(c['obs_2021_n_ha_an'], 1)}")
    head = "Code & Rubrique cadastrale (Statbel) & \\makecell{Incluse dans\\\\la définition} & \\makecell{2010-2019\\\\(ha/an)} & \\makecell{2021-2024\\\\(ha/an)}"
    return _tabular("llcrr", head, rows)


def table_contributeurs(ev_c: pd.DataFrame, n: int = 12) -> str:
    d = ev_c.sort_values("ecart_cumul_ha")
    rows = []
    for label, part in [("Plus forts dépassements", d.iloc[::-1].head(n)), ("Plus fortes marges", d.head(n))]:
        rows.append(f"\\multicolumn{{8}}{{l}}{{\\emph{{{label}}}}}")
        for _, c in part.iterrows():
            rows.append(f"\\quad {esc(c['commune'])} & {c['bassin_sdt']} & {num(c['moyenne_ref_ha_an'], 1)} & "
                        f"{num(c['conso_moy_obs_ha_an'], 1)} & {num(c['ecart_cumul_ha'], 0, True)} & "
                        f"{num(c['ratio_obs_traj'], 2)} & {num(c['ratio_obs_traj_sauts_neutralises'], 2)} & "
                        f"{c['sauts_a_verifier_suivi'] or '--'}")
    head = ("Commune & Bassin & \\makecell{Réf.\\\\(ha/an)} & \\makecell{Obs.\\\\(ha/an)} & \\makecell{Écart\\\\cumulé (ha)} & "
            "Ratio & \\makecell{Ratio\\\\neutralisé} & \\makecell{Saut(s)\\\\à vérifier}")
    return _tabular("llrrrrrl", head, rows)


def table_sauts(ev_c: pd.DataFrame, cons: pd.DataFrame) -> str:
    d = ev_c[ev_c["sauts_a_verifier_suivi"] != ""].sort_values(["bassin_sdt", "commune"])
    rows = []
    for code, c in d.iterrows():
        ys = [int(y) for y in c["sauts_a_verifier_suivi"].split()]
        flux = ", ".join(f"{y} : {num(cons.loc[code, y], 0, True)}" for y in ys)
        med = cons.loc[code, 2000:].median()
        rows.append(f"{esc(c['commune'])} & {c['bassin_sdt']} & {flux} & {num(med, 1)} & "
                    f"{STATUT_COURT[c['statut']]} & {STATUT_COURT[c['statut_sauts_neutralises']]}")
    head = ("Commune & Bassin & Année : flux (ha) & \\makecell{Médiane\\\\2000-2024} & Statut & "
            "\\makecell{Statut\\\\neutralisé}")
    return _tabular("llp{4.2cm}rll", head, rows)


def table_communes(ev_c: pd.DataFrame) -> str:
    """Annexe : toutes les communes couvertes (longtable)."""
    head = ("Commune & INS & \\makecell{Part artif.\\\\(\\%)} & \\makecell{Réf.\\\\(ha/an)} & \\makecell{Obs.\\\\(ha/an)} & "
            "\\makecell{Écart\\\\(ha)} & Ratio & Statut & \\makecell{Sauts\\\\réf.} & \\makecell{Sauts\\\\suivi}")
    out = ["\\begin{longtable}{lrrrrrrlll}", "\\toprule", head + " \\\\", "\\midrule", "\\endfirsthead",
           "\\toprule", head + " \\\\", "\\midrule", "\\endhead", "\\bottomrule", "\\endfoot"]
    for b, grp in ev_c.groupby("bassin_sdt"):
        out.append(f"\\multicolumn{{10}}{{l}}{{\\textbf{{{b}}} ({len(grp)} communes)}} \\\\")
        for code, c in grp.sort_values("commune").iterrows():
            out.append(f"{esc(c['commune'])} & {code} & {num(c['part_artificialisee_derniere_annee_pct'], 1)} & "
                       f"{num(c['moyenne_ref_ha_an'], 1)} & {num(c['conso_moy_obs_ha_an'], 1)} & "
                       f"{num(c['ecart_cumul_ha'], 0, True)} & {num(c['ratio_obs_traj'], 2)} & "
                       f"{STATUT_COURT[c['statut']]} & {c['sauts_a_verifier_reference'].replace(' ', ', ') or '--'} & "
                       f"{c['sauts_a_verifier_suivi'] or '--'} \\\\")
        out.append("\\addlinespace")
    out.append("\\end{longtable}")
    return "\n".join(out) + "\n"


def table_provenance() -> str:
    prov = json.loads((RAW / "PROVENANCE.json").read_text(encoding="utf-8"))
    rows = []
    for path, p in sorted(prov.items()):
        url = p["url"].split("?")[0]
        rows.append(f"\\nolinkurl{{{path}}} & \\url{{{url}}} & {p['telecharge_le'][:10]} & "
                    f"{num(p['octets'] / 1e6, 2)} & \\texttt{{{p['sha256'][:12]}}}")
    head = "Fichier (data/raw/) & Source & Date d'accès & Mo & SHA-256 (début)"
    return _tabular(">{\\raggedright\\arraybackslash}p{3.4cm}>{\\raggedright\\arraybackslash}p{7.2cm}lrl", head, rows)


def run(res: dict, cons_by_def: dict, cpdt: pd.DataFrame) -> None:
    years = suivi.observed_years(res["cons"])
    ev_c = res["eval_communes"].copy()
    for c in ("sauts_a_verifier_reference", "sauts_a_verifier_suivi"):
        ev_c[c] = ev_c[c].fillna("")
    res = {**res, "eval_communes": ev_c}
    cmp = comparaison_cpdt(res, cpdt)
    cmp.to_csv(PROCESSED / "comparaison_cpdt_bassins.csv", encoding="utf-8")
    _write("chiffres.tex", macros(res, cons_by_def, cmp))
    _write("tab_cpdt.tex", table_cpdt(cmp))
    _write("tab_sdt.tex", table_sdt(res["sdt"]))
    _write("tab_bassins.tex", table_bassins(res["eval_bassins"], res["cons_bassins"], years))
    _write("tab_validation.tex", table_validation(res["validation"]))
    _write("tab_iweps.tex", table_iweps(cons_by_def))
    _write("tab_sensibilite.tex", table_sensibilite(res["sensibilite"]))
    _write("tab_variabilite.tex", table_variabilite(res["variabilite"]))
    _write("tab_composition.tex", table_composition(res["composition"]))
    _write("tab_contributeurs.tex", table_contributeurs(ev_c))
    _write("tab_sauts.tex", table_sauts(ev_c, res["cons"]))
    _write("tab_communes.tex", table_communes(ev_c))
    _write("tab_provenance.tex", table_provenance())
