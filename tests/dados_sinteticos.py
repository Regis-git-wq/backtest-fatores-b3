"""Gera um mercado simulado para testar o pipeline sem internet.

Embute dois efeitos conhecidos, para conferir se o backtest os detecta:
- momentum: ações com retorno alto nos últimos meses continuam subindo um pouco mais;
- baixa volatilidade: ações menos voláteis têm o mesmo retorno esperado das voláteis
  (logo, melhor retorno ajustado ao risco).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def gerar(n_stocks: int = 60, start: str = "2010-01-01", end: str = "2025-12-31", seed: int = 42):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, end)
    n = len(days)
    tickers = [f"ACAO{i:02d}" for i in range(n_stocks)]

    mkt = rng.normal(0.0004, 0.014, n)
    vols = rng.uniform(0.012, 0.035, n_stocks)          # vol idiossincrática diária
    betas = rng.uniform(0.6, 1.4, n_stocks)
    rets = np.zeros((n, n_stocks))
    for t in range(n):
        # momentum: usa retorno acumulado de ~1 ano até ~1 mês atrás
        if t > 252:
            past = rets[t - 252:t - 21].sum(axis=0)
            drift = 0.0006 * (past - past.mean()) / (past.std() + 1e-9)
        else:
            drift = 0
        # o termo -0.5*vol² iguala o retorno esperado simples entre ações voláteis e não voláteis
        rets[t] = betas * mkt[t] + rng.normal(0, vols) - 0.5 * vols**2 + drift * 0.15

    adj = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=days, columns=tickers)
    # algumas ações só começam a negociar depois (IPO)
    for i in rng.choice(n_stocks, 10, replace=False):
        adj.iloc[: rng.integers(300, 2000), i] = np.nan
    volume = pd.DataFrame(rng.uniform(2e5, 3e6, adj.shape), index=days, columns=tickers).where(adj.notna())
    bench = pd.DataFrame({"IBOV": 50000 * np.exp(np.cumsum(mkt))}, index=days)
    cdi = pd.Series(0.10 / 252, index=days, name="CDI")
    return {"adj_close": adj, "close": adj, "volume": volume, "benchmark": bench}, cdi
