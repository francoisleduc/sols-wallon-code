"""Confrontation de la consommation observée aux trajectoires de réduction de l'artificialisation nette."""
import pandas as pd

from ..config import BASELINE, SAUT_K_MAD, SAUT_SEUIL_MIN_HA, TRAJ_END, TRAJ_START


def trajectory_factor(year: int, start: int = TRAJ_START, end: int = TRAJ_END) -> float:
    """Fraction de la moyenne de référence autorisée l'année `year` (1 en `start`, 0 en `end`)."""
    return min(max((end - year) / (end - start), 0.0), 1.0)


def observed_years(cons: pd.DataFrame, start: int = TRAJ_START) -> list[int]:
    return [y for y in cons.columns if y >= start]


def baseline(cons: pd.DataFrame, period: tuple[int, int] = BASELINE) -> pd.Series:
    return cons.loc[:, period[0]:period[1]].mean(axis=1)


def flag_jumps(cons: pd.DataFrame, years: list[int]) -> pd.Series:
    """Années à vérifier : |conso - médiane communale 2000-N| > max(seuil, k x MAD).

    Ces sauts correspondent le plus souvent à des reclassements cadastraux (bois -> terrain
    récréatif, intégration de domaine non cadastré...) plutôt qu'à une artificialisation réelle.
    """
    hist = cons.loc[:, 2000:]
    med = hist.median(axis=1)
    mad = hist.sub(med, axis=0).abs().median(axis=1)
    seuil = (SAUT_K_MAD * mad).clip(lower=SAUT_SEUIL_MIN_HA)
    out = cons[years].sub(med, axis=0).abs().gt(seuil, axis=0)
    return out.apply(lambda r: " ".join(str(y) for y in r.index[r]), axis=1)


def neutralize_jumps(cons: pd.DataFrame) -> pd.DataFrame:
    """Variante de robustesse : remplace chaque année signalée par la médiane communale."""
    hist = cons.loc[:, 2000:]
    med = hist.median(axis=1)
    mad = hist.sub(med, axis=0).abs().median(axis=1)
    seuil = (SAUT_K_MAD * mad).clip(lower=SAUT_SEUIL_MIN_HA)
    out = cons.copy()
    cols = [c for c in cons.columns if c >= 2000]
    mask = cons[cols].sub(med, axis=0).abs().gt(seuil, axis=0)
    out[cols] = cons[cols].mask(mask, pd.concat([med] * len(cols), axis=1, keys=cols))
    return out


def evaluate(cons: pd.DataFrame, ref: pd.Series, start: int = TRAJ_START, end: int = TRAJ_END,
             first_obs: int = TRAJ_START) -> pd.DataFrame:
    """Cumul observé depuis `first_obs` vs cumul autorisé par la trajectoire de référence `ref`."""
    years = observed_years(cons, first_obs)
    budget = sum(trajectory_factor(y, start, end) for y in years)
    res = pd.DataFrame({"moyenne_ref_ha_an": ref, "conso_cumul_obs_ha": cons[years].sum(axis=1)})
    res["conso_cumul_traj_ha"] = ref * budget
    res["conso_moy_obs_ha_an"] = res["conso_cumul_obs_ha"] / len(years)
    res["plafond_derniere_annee_ha_an"] = ref * trajectory_factor(years[-1], start, end)
    res["ecart_cumul_ha"] = res["conso_cumul_obs_ha"] - res["conso_cumul_traj_ha"]
    res["ratio_obs_traj"] = res["conso_cumul_obs_ha"] / res["conso_cumul_traj_ha"]
    res["statut"] = "au-dessus de la trajectoire"
    res.loc[res["ratio_obs_traj"] <= 1, "statut"] = "dans la trajectoire"
    res.loc[res["moyenne_ref_ha_an"] <= 0, ["ratio_obs_traj", "statut"]] = [float("nan"), "référence non interprétable"]
    return res
