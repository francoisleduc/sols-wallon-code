"""Calculs de l'étude : séries communales, validation, évaluation, sensibilité, diagnostics.

Chaque fonction renvoie des DataFrames ; `run()` les écrit dans data/processed/ et les rassemble
dans un dictionnaire consommé par les modules `figures` et `latex`.
"""
import numpy as np
import pandas as pd

from . import cadastre, suivi
from ..config import (BASELINE, DEFINITION_PRINCIPALE, DEFINITIONS, PROCESSED, REFERENCES, TRAJ_END,
                     TRAJ_START)

WALLONIE = "Wallonie (hors Communauté germanophone)"


def _communes() -> pd.DataFrame:
    return pd.read_csv(REFERENCES / "communes_bassins_sdt.csv", dtype=str).set_index("code_ins")


def _sdt() -> pd.DataFrame:
    return pd.read_csv(REFERENCES / "trajectoires_sdt_2024_bassins.csv").set_index("bassin")


def by_bassin(cons: pd.DataFrame, communes: pd.DataFrame) -> pd.DataFrame:
    sdt_communes = communes[communes["couvert_par_sdt"] == "oui"]
    return cons.loc[cons.index.intersection(sdt_communes.index)].groupby(sdt_communes["bassin_sdt"]).sum()


def with_total(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.loc[WALLONIE] = df.sum()
    return out


def validation(raw: pd.DataFrame, communes: pd.DataFrame, sdt: pd.DataFrame) -> pd.DataFrame:
    """Confronte chaque définition aux références officielles (SDT, IWEPS)."""
    hist = pd.read_csv(PROCESSED / "sdt_series_historiques_numerisees.csv").pivot(
        index="bassin", columns="annee", values="artif_nette_ha_sdt")
    wal = communes.index
    superficie = raw[raw["code_ins"].isin(wal)].groupby("annee")["ha"].sum()
    rows = []
    for key, (label, _) in DEFINITIONS.items():
        stk = cadastre.stock(raw[raw["code_ins"].isin(wal)], key)
        cons_b = by_bassin(cadastre.consumption(stk), communes)
        ref_b = suivi.baseline(cons_b)
        row = {"definition": key, "libelle": label,
               "stock_2015_pct": stk[2015].sum() / superficie[2015] * 100,
               "stock_2023_pct": stk[2023].sum() / superficie[2023] * 100,
               "flux_2010_2019_km2": ref_b.sum() / 100,
               "flux_2015_2019_km2": cons_b.loc[:, 2015:2019].mean(axis=1).sum() / 100,
               "ecart_moy_ref_bassins_ha": (ref_b - sdt["artif_nette_moy_10ans_ha_an"].reindex(ref_b.index)).abs().mean()}
        for lag in (0, 1):
            shifted = cons_b.copy()
            shifted.columns = shifted.columns + lag
            rs, maes = [], []
            for b in hist.index:
                h = hist.loc[b].dropna()
                x = shifted.loc[b].reindex(h.index)
                ok = x.notna()
                rs.append(np.corrcoef(h[ok], x[ok])[0, 1])
                maes.append((x[ok] - h[ok]).abs().mean())
            row[f"corr_mediane_lag{lag}"] = float(np.median(rs))
            row[f"ecart_abs_moy_lag{lag}_ha"] = float(np.mean(maes))
        rows.append(row)
    return pd.DataFrame(rows).set_index("definition")


def variability(cons_b: pd.DataFrame) -> pd.DataFrame:
    """Variabilité interannuelle 2010-2019 et écart standardisé de la moyenne 2021-N."""
    t = with_total(cons_b)
    ref = t.loc[:, BASELINE[0]:BASELINE[1]]
    obs = t[suivi.observed_years(t)]
    out = pd.DataFrame({"moyenne_ref": ref.mean(axis=1), "ecart_type_ref": ref.std(axis=1, ddof=1),
                        "moyenne_obs": obs.mean(axis=1), "n_obs": obs.shape[1]})
    # Écart-type de la différence de deux moyennes (années supposées indépendantes)
    se = np.sqrt(out["ecart_type_ref"] ** 2 / ref.shape[1] + out["ecart_type_ref"] ** 2 / obs.shape[1])
    out["variation_pct"] = (out["moyenne_obs"] / out["moyenne_ref"] - 1) * 100
    out["z"] = (out["moyenne_obs"] - out["moyenne_ref"]) / se
    return out


def composition(raw: pd.DataFrame, communes: pd.DataFrame) -> pd.DataFrame:
    """Variation nette annuelle moyenne par rubrique cadastrale (Wallonie couverte par le SDT)."""
    sdt_codes = communes.index[communes["couvert_par_sdt"] == "oui"]
    reg = raw[raw["code_ins"].isin(sdt_codes)].pivot_table(index="rubrique", columns="annee", values="ha",
                                                           aggfunc="sum").fillna(0.0)
    cons = cadastre.consumption(reg)
    lab = cadastre.rubriques().set_index("rubrique")
    out = pd.DataFrame({"ref_2010_2019_ha_an": cons.loc[:, BASELINE[0]:BASELINE[1]].mean(axis=1),
                        "obs_2021_n_ha_an": cons[suivi.observed_years(cons)].mean(axis=1)})
    out = out.join(lab)
    out["dans_principale"] = [cadastre.in_definition(r, DEFINITION_PRINCIPALE) for r in out.index]
    out["dans_large"] = [cadastre.in_definition(r, "large") for r in out.index]
    return out


def sensitivity(raw: pd.DataFrame, communes: pd.DataFrame, sdt: pd.DataFrame) -> pd.DataFrame:
    """Ratio observé/trajectoire (Wallonie et bassins) et statuts communaux selon les choix de méthode."""
    sdt_codes = communes.index[communes["couvert_par_sdt"] == "oui"]
    base = raw[raw["code_ins"].isin(sdt_codes)]
    sdt_ref = sdt["artif_nette_moy_10ans_ha_an"].drop(WALLONIE)
    unc = sdt["incertitude_lecture_ha_an"].drop(WALLONIE)
    rows = []

    def add(name, group, cons, ref_b=None, ref_com_period=BASELINE, start=TRAJ_START, end=TRAJ_END):
        cons_b = by_bassin(cons, communes)
        rb = suivi.baseline(cons_b, ref_com_period) if ref_b is None else ref_b
        ev_b = suivi.evaluate(with_total(cons_b), with_total(rb.to_frame()).iloc[:, 0], start, end)
        ev_c = suivi.evaluate(cons, suivi.baseline(cons, ref_com_period), start, end)
        row = {"variante": name, "groupe": group, **{f"ratio_{b}": ev_b.loc[b, "ratio_obs_traj"] for b in ev_b.index},
               "communes_au_dessus": int((ev_c["statut"] == "au-dessus de la trajectoire").sum()),
               "communes_dans": int((ev_c["statut"] == "dans la trajectoire").sum()),
               "communes_non_interpretables": int((ev_c["statut"] == "référence non interprétable").sum())}
        rows.append(row)

    cons_main = cadastre.consumption(cadastre.stock(base, DEFINITION_PRINCIPALE))
    add("Référence de l'étude (référence SDT numérisée)", "Référence", cons_main, ref_b=sdt_ref)
    add("Référence bassin recalculée 2010-2019", "Référence de bassin", cons_main)
    add("Référence SDT numérisée - incertitude de lecture", "Lecture des graphiques", cons_main, ref_b=sdt_ref - unc)
    add("Référence SDT numérisée + incertitude de lecture", "Lecture des graphiques", cons_main, ref_b=sdt_ref + unc)
    for key in DEFINITIONS:
        if key != DEFINITION_PRINCIPALE:
            c = cadastre.consumption(cadastre.stock(base, key))
            add(f"Définition « {DEFINITIONS[key][0]} »", "Définition", c)
    for period in [(2009, 2018), (2011, 2020), (2012, 2021), (2015, 2019)]:
        add(f"Période de référence {period[0]}-{period[1]}", "Période de référence", cons_main, ref_com_period=period)
    for start, end in [(2020, 2050), (2020, 2049), (2022, 2050)]:
        add(f"Trajectoire {start}-{end}", "Calage de la trajectoire", cons_main, ref_b=sdt_ref, start=start, end=end)
    add("Sauts cadastraux neutralisés", "Anomalies", suivi.neutralize_jumps(cons_main), ref_b=sdt_ref)
    return pd.DataFrame(rows)


def run() -> dict:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    communes, sdt = _communes(), _sdt()
    raw = cadastre.load()
    raw = raw[raw["code_ins"].isin(communes.index)]
    sdt_com = communes[communes["couvert_par_sdt"] == "oui"]

    stk = cadastre.stock(raw, DEFINITION_PRINCIPALE)
    stk_large = cadastre.stock(raw, "large")
    surf = raw.pivot_table(index="code_ins", columns="annee", values="ha", aggfunc="sum")
    cons = cadastre.consumption(stk)

    serie = pd.concat({"stock_artif_ha": stk.stack(), "stock_artif_large_ha": stk_large.stack(),
                       "superficie_ha": surf.stack()}, axis=1)
    serie = serie.rename_axis(["code_ins", "annee_stock_1er_janvier"]).reset_index()
    serie.join(communes[["commune", "bassin_sdt"]], on="code_ins").round(2).to_csv(
        PROCESSED / "artif_communes_stock_annuel.csv", index=False)
    conso_long = cons.stack().rename("conso_nette_ha").rename_axis(["code_ins", "annee"]).reset_index()
    conso_long.join(communes[["commune", "bassin_sdt"]], on="code_ins").round(2).to_csv(
        PROCESSED / "artif_communes_conso_annuelle.csv", index=False)

    # Communes couvertes par le SDT
    cons_sdt = cons.loc[sdt_com.index]
    ev_c = suivi.evaluate(cons_sdt, suivi.baseline(cons_sdt))
    ev_c["sauts_a_verifier_reference"] = suivi.flag_jumps(cons_sdt, list(range(BASELINE[0], BASELINE[1] + 1)))
    ev_c["sauts_a_verifier_suivi"] = suivi.flag_jumps(cons_sdt, suivi.observed_years(cons_sdt))
    robust = suivi.neutralize_jumps(cons_sdt)
    ev_r = suivi.evaluate(robust, suivi.baseline(robust))
    ev_c["ratio_obs_traj_sauts_neutralises"] = ev_r["ratio_obs_traj"]
    ev_c["statut_sauts_neutralises"] = ev_r["statut"]
    ev_c["part_artificialisee_derniere_annee_pct"] = stk.loc[sdt_com.index, stk.columns.max()] / \
        surf.loc[sdt_com.index, surf.columns.max()] * 100
    ev_c = sdt_com[["commune", "province", "bassin_sdt"]].join(ev_c)
    ev_c.round(3).reset_index().to_csv(PROCESSED / "suivi_communes.csv", index=False)

    # Bassins : référence officielle (SDT numérisé) et référence recalculée
    cons_b = by_bassin(cons, communes)
    cons_bt = with_total(cons_b)
    ref_sdt = sdt["artif_nette_moy_10ans_ha_an"]
    ev_b = suivi.evaluate(cons_bt, ref_sdt.reindex(cons_bt.index))
    ev_b_recalc = suivi.evaluate(cons_bt, suivi.baseline(cons_bt))
    ev_b = ev_b.join(ev_b_recalc[["moyenne_ref_ha_an", "conso_cumul_traj_ha", "ratio_obs_traj", "statut"]]
                     .add_suffix("_recalculee"))
    ev_b.round(3).rename_axis("bassin").reset_index().to_csv(PROCESSED / "suivi_bassins.csv", index=False)
    cons_bt.round(1).to_csv(PROCESSED / "conso_bassins_annuelle.csv")

    val = validation(raw, communes, sdt)
    var = variability(cons_b)
    comp = composition(raw, communes)
    sens = sensitivity(raw, communes, sdt)
    for name, df in {"validation_definitions": val, "variabilite_interannuelle": var,
                     "composition_rubriques": comp}.items():
        df.round(4).to_csv(PROCESSED / f"{name}.csv")
    sens.round(4).to_csv(PROCESSED / "sensibilite.csv", index=False)

    return {"communes": communes, "sdt": sdt, "raw": raw, "stock": stk, "surface": surf, "cons": cons,
            "cons_bassins": cons_bt, "eval_communes": ev_c, "eval_bassins": ev_b, "validation": val,
            "variabilite": var, "composition": comp, "sensibilite": sens}
