"""Formação de carteiras por ordenação (sorting) e cálculo dos retornos.

No fim do mês t: ordena as ações elegíveis pelo sinal e divide em N grupos.
Cada grupo é uma carteira igualmente ponderada, mantida durante o mês t+1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def assign_groups(signal: pd.DataFrame, eligible: pd.DataFrame, n_groups: int) -> pd.DataFrame:
    """Retorna, para cada data/ação, o grupo (1 = pior sinal, n_groups = melhor)."""
    sig = signal.where(eligible.reindex_like(signal).fillna(False).astype(bool))

    def _rank(row: pd.Series) -> pd.Series:
        valid = row.dropna()
        if len(valid) < n_groups * 3:  # poucas ações -> não forma carteira nesse mês
            return pd.Series(np.nan, index=row.index)
        g = pd.qcut(valid.rank(method="first"), n_groups, labels=False) + 1
        return g.reindex(row.index)

    return sig.apply(_rank, axis=1)


def weights_from_mask(mask: pd.DataFrame) -> pd.DataFrame:
    """Pesos iguais para as ações marcadas como True em cada data."""
    members = mask.astype(float)
    return members.div(members.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def weights_from_groups(groups: pd.DataFrame, group: int) -> pd.DataFrame:
    return weights_from_mask(groups == group)


def portfolio_returns(weights: pd.DataFrame, monthly_returns: pd.DataFrame,
                      cost_bps: float = 0.0) -> tuple[pd.Series, pd.Series]:
    """Retorno líquido de custos da carteira com pesos definidos no fim de t e aplicados em t+1.

    O giro (turnover) considera a deriva dos pesos durante o mês: compara os pesos-alvo
    novos com os pesos que a carteira antiga tinha ao final do mês.
    """
    w = weights.shift(1)  # peso decidido em t vale para o retorno de t+1
    r = monthly_returns.reindex_like(w)
    # ação sem retorno no mês (ex.: deixou de negociar) é tratada como retorno zero (ver README)
    gross = (w * r.fillna(0)).sum(axis=1)

    drifted = (w * (1 + r.fillna(0)))
    drifted = drifted.div(drifted.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    turnover = (weights - drifted).abs().sum(axis=1) / 2
    cost = turnover.shift(1).fillna(0) * cost_bps / 1e4 * 2  # compra + venda
    active = w.sum(axis=1) > 0
    net = (gross - cost).where(active)
    return net.dropna(), turnover.where(weights.sum(axis=1) > 0).dropna()


def sort_backtest(signal: pd.DataFrame, eligible: pd.DataFrame, monthly_returns: pd.DataFrame,
                  n_groups: int, cost_bps: float) -> dict:
    groups = assign_groups(signal, eligible, n_groups)
    rets, turns = {}, {}
    for g in range(1, n_groups + 1):
        w = weights_from_groups(groups, g)
        rets[f"G{g}"], turns[f"G{g}"] = portfolio_returns(w, monthly_returns, cost_bps)
    rets = pd.DataFrame(rets)
    rets["Long-Short"] = rets[f"G{n_groups}"] - rets["G1"]
    return {"returns": rets, "turnover": pd.DataFrame(turns), "groups": groups}
