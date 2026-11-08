"""Métricas de desempenho e regressões de alfa."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def max_drawdown(returns: pd.Series) -> float:
    wealth = (1 + returns).cumprod()
    return (wealth / wealth.cummax() - 1).min()


def summary(returns: pd.DataFrame, rf: pd.Series, long_short_cols: tuple = ("Long-Short",)) -> pd.DataFrame:
    """Tabela de métricas anualizadas. Para carteiras long-short (autofinanciadas),
    o Sharpe usa o retorno bruto, sem subtrair o CDI."""
    rows = {}
    for col in returns:
        r = returns[col].dropna()
        rf_ = rf.reindex(r.index).fillna(0)
        excess = r if col in long_short_cols else r - rf_
        n = len(r)
        ann_ret = (1 + r).prod() ** (12 / n) - 1
        ann_vol = r.std() * np.sqrt(12)
        sd = excess.std()
        sharpe = excess.mean() / sd * np.sqrt(12) if sd > 1e-12 else np.nan
        t_stat = excess.mean() / (sd / np.sqrt(n)) if sd > 1e-12 else np.nan
        rows[col] = {
            "Retorno a.a.": ann_ret,
            "Volatilidade a.a.": ann_vol,
            "Sharpe": sharpe,
            "t (média excesso)": t_stat,
            "Max drawdown": max_drawdown(r),
            "% meses positivos": (r > 0).mean(),
            "Meses": n,
        }
    return pd.DataFrame(rows).T


def alpha_regression(portfolio: pd.Series, factors: pd.DataFrame, rf: pd.Series | None,
                     lags: int = 6) -> pd.DataFrame:
    """Regressão do excesso de retorno da carteira nos fatores, com erros Newey-West.
    Retorna coeficientes, estatísticas t e o alfa anualizado."""
    y = portfolio if rf is None else portfolio - rf.reindex(portfolio.index)
    df = pd.concat([y.rename("y"), factors], axis=1).dropna()
    X = sm.add_constant(df.drop(columns="y"))
    model = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    out = pd.DataFrame({"coef": model.params, "t": model.tvalues, "p-valor": model.pvalues})
    out.loc["alfa a.a.", "coef"] = (1 + model.params["const"]) ** 12 - 1
    out.loc["R²", "coef"] = model.rsquared
    out.loc["N", "coef"] = model.nobs
    return out
