"""Gera um mercado simulado para testar o pipeline sem internet.

Embute dois efeitos conhecidos, para conferir se o backtest os detecta:
- momentum: ações com retorno alto nos últimos meses continuam subindo um pouco mais;
- baixa volatilidade: ações menos voláteis têm o mesmo retorno esperado das voláteis
  (logo, melhor retorno ajustado ao risco).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def gerar(n_stocks: int = 60, start: str = "2010-01-01", end: str = "2025-12-31", seed: int = 42,
          com_erros: bool = False):
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
    # CDI com ciclos de alta e queda (entre 6% e 14% a.a.), para exercitar a análise por regime
    annual = 0.10 + 0.04 * np.sin(np.arange(n) / 252 * 2 * np.pi / 5)
    cdi = pd.Series((1 + annual) ** (1 / 252) - 1, index=days, name="CDI")
    if com_erros:
        # erros típicos do Yahoo, para exercitar a limpeza: desdobramento não ajustado e pico
        adj.iloc[:2500, 1] *= 4
        adj.iloc[3000:3002, 2] *= 2.5
    return {"adj_close": adj, "close": adj, "volume": volume, "benchmark": bench}, cdi


def gerar_fundamentos(px: dict, seed: int = 0):
    """Fundamentos simulados no mesmo formato dos da CVM, para testar o pipeline.

    Inclui os casos difíceis: um desdobramento 2:1 (ACAO05) e uma unit de 5 ações (ACAO10).
    Cada exercício (31/dez) só fica disponível em 25/mar do ano seguinte.
    """
    rng = np.random.default_rng(seed)
    close = px["close"]
    tickers = list(close.columns)
    tmap = pd.DataFrame({
        "ticker": tickers,
        "cnpj": [f"{i:02d}.000.000/0001-00" for i in range(len(tickers))],
        "empresa": tickers,
        "acoes_por_unit": [5 if t == "ACAO10" else 1 for t in tickers],
        "inicio_negociacao": pd.NaT,
    })
    split_day = pd.Timestamp("2018-06-15")
    shares = pd.DataFrame({"cnpj": tmap["cnpj"], "data": pd.Timestamp("2005-01-01"), "acoes": 1e9})
    c5 = tmap.loc[tmap.ticker == "ACAO05", "cnpj"].iloc[0]
    shares = pd.concat([shares, pd.DataFrame({"cnpj": [c5], "data": [split_day], "acoes": [2e9]})])
    splits = {"ACAO05": pd.Series([2.0], index=[split_day])}

    rows = []
    year_end = close.resample("YE").last()
    for _, r in tmap.iterrows():
        for d, price in year_end[r["ticker"]].dropna().items():
            if d.year >= 2025:
                continue
            per_share = price * (2.0 if (r["ticker"] == "ACAO05" and d < split_day) else 1.0)
            n = 2e9 if (r["ticker"] == "ACAO05" and d >= split_day) else 1e9
            mcap = per_share / r["acoes_por_unit"] * n
            pl = mcap * rng.uniform(0.3, 1.5)
            rows.append({"cnpj": r["cnpj"], "exercicio": d.normalize(),
                         "disponivel_em": pd.Timestamp(f"{d.year + 1}-03-25"),
                         "ativo": pl * rng.uniform(1.5, 4.0), "pl_total": pl, "minoritarios": 0.0,
                         "pl_ctrl": pl, "lucro_total": pl * rng.normal(0.12, 0.08),
                         "fonte": "consolidada"})
    fund = pd.DataFrame(rows)
    fund["lucro_ctrl"] = fund["lucro_total"]
    return tmap, fund, shares, splits
