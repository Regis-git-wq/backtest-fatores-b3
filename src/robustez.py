"""Análises de robustez: os resultados se sustentam quando mudamos o período,
o regime de juros, os custos e as escolhas de construção das carteiras?

Duas medidas são usadas em todas as tabelas (médias mensais × 12):
- Prêmio long-short: melhor grupo − pior grupo
- Excesso sobre o universo: melhor grupo − carteira igualmente ponderada do universo
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import carteiras


def _stats(x: pd.Series) -> tuple[float, float, int]:
    """Média anualizada, estatística t e número de meses."""
    x = x.dropna()
    n = len(x)
    if n < 6 or x.std() < 1e-12:
        return np.nan, np.nan, n
    return x.mean() * 12, x.mean() / (x.std() / np.sqrt(n)), n


def _row(rets: pd.DataFrame, top: str, market: str) -> dict:
    ls, t_ls, n = _stats(rets["Long-Short"])
    act, t_act, _ = _stats(rets[top] - rets[market])
    return {"Prêmio long-short a.a.": ls, "t (long-short)": t_ls,
            "Excesso sobre o universo a.a.": act, "t (excesso)": t_act, "Meses": n}


def por_subperiodo(rets_by_strategy: dict[str, pd.DataFrame], periods: list[tuple[str, str]],
                   top: str, market: str) -> pd.DataFrame:
    rows = []
    for name, rets in rets_by_strategy.items():
        for start, end in periods:
            sub = rets.loc[start:end]
            rows.append({"Estratégia": name, "Período": f"{start}–{end}", **_row(sub, top, market)})
    return pd.DataFrame(rows)


def regime_selic(cdi_daily: pd.Series, window_months: int = 3, threshold: float = 0.0025) -> pd.Series:
    """Classifica cada mês em 'Alta', 'Queda' ou 'Estável' pela variação da taxa do CDI
    (anualizada, base 252) em relação a `window_months` meses antes.
    É uma classificação descritiva (usa a taxa do próprio mês), não um sinal de investimento."""
    annual = ((1 + cdi_daily) ** 252 - 1).resample("ME").last()
    delta = annual - annual.shift(window_months)
    regime = pd.Series("Estável", index=annual.index)
    regime[delta > threshold] = "Alta"
    regime[delta < -threshold] = "Queda"
    return regime.where(delta.notna())


def por_regime(rets_by_strategy: dict[str, pd.DataFrame], regime: pd.Series,
               top: str, market: str) -> pd.DataFrame:
    rows = []
    for name, rets in rets_by_strategy.items():
        reg = regime.reindex(rets.index)
        for r in ["Alta", "Estável", "Queda"]:
            sub = rets[reg == r]
            rows.append({"Estratégia": name, "Ciclo da Selic": r, **_row(sub, top, market)})
    return pd.DataFrame(rows)


def por_especificacao(signals: dict[str, pd.DataFrame], eligible: pd.DataFrame,
                      monthly: pd.DataFrame, specs: list[dict]) -> pd.DataFrame:
    """Refaz o backtest para cada especificação (custo, número de grupos, ações excluídas,
    ou outra base de dados: chaves opcionais "monthly" e "signals")."""
    rows = []
    for spec in specs:
        base_monthly = spec.get("monthly", monthly)
        base_signals = spec.get("signals", signals)
        drop = [c for c in spec.get("excluir", []) if c in base_monthly.columns]
        elig = eligible.drop(columns=drop)
        mret = base_monthly.drop(columns=drop)
        n, cost = spec["grupos"], spec["custo_bps"]
        market, _ = carteiras.portfolio_returns(carteiras.weights_from_mask(elig), mret, cost)
        for name, sig in base_signals.items():
            bt = carteiras.sort_backtest(sig.drop(columns=drop), elig, mret, n, cost)["returns"]
            bt["mkt"] = market.reindex(bt.index)
            bt = bt.dropna()
            rows.append({"Especificação": spec["nome"], "Estratégia": name, **_row(bt, f"G{n}", "mkt")})
    return pd.DataFrame(rows)
