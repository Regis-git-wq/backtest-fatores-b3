"""Coleta e preparação de dados: preços (Yahoo Finance), CDI (Banco Central) e fatores NEFIN.

Tudo fica em cache na pasta data/ para não baixar de novo a cada execução.
"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd
import requests

DATA_DIR = "data"


def _cache(path: str) -> pd.DataFrame | None:
    if os.path.exists(path):
        return pd.read_csv(path, index_col=0, parse_dates=True)
    return None


def download_prices(tickers: list[str], start: str, end: str, benchmark: str) -> dict[str, pd.DataFrame]:
    """Baixa preços diários. Retorna dict com:
    - 'adj_close': fechamento ajustado por proventos e desdobramentos (base dos retornos)
    - 'close': fechamento bruto (para filtro de preço)
    - 'volume': quantidade negociada
    - 'benchmark': série do Ibovespa
    Tickers que falharem são listados e descartados.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    paths = {k: f"{DATA_DIR}/{k}.csv" for k in ["adj_close", "close", "volume", "benchmark"]}
    if all(os.path.exists(p) for p in paths.values()):
        return {k: _cache(p) for k, p in paths.items()}

    import yfinance as yf

    symbols = [f"{t}.SA" for t in tickers]
    raw = yf.download(symbols, start=start, end=end, auto_adjust=False,
                      progress=True, group_by="column", threads=True)
    out = {
        "adj_close": raw["Adj Close"],
        "close": raw["Close"],
        "volume": raw["Volume"],
    }
    for k in out:
        out[k].columns = [c.replace(".SA", "") for c in out[k].columns]

    failed = [t for t in tickers if t not in out["adj_close"] or out["adj_close"][t].dropna().empty]
    if failed:
        print(f"[aviso] sem dados para: {', '.join(failed)} (removidos)")
        for k in out:
            out[k] = out[k].drop(columns=[c for c in failed if c in out[k]])

    bench = yf.download(benchmark, start=start, end=end, auto_adjust=False, progress=False)
    bench_close = bench["Close"]
    if isinstance(bench_close, pd.DataFrame):
        bench_close = bench_close.iloc[:, 0]
    out["benchmark"] = bench_close.to_frame("IBOV")

    for k, df in out.items():
        df.to_csv(paths[k])
    return out


def download_cdi(start: str, end: str) -> pd.Series:
    """CDI diário (série SGS 12 do BCB, em % ao dia). A API limita consultas a 10 anos,
    então a busca é feita em blocos. Retorna a taxa diária em decimal."""
    path = f"{DATA_DIR}/cdi.csv"
    cached = _cache(path)
    if cached is not None:
        return cached.iloc[:, 0]

    start_d, end_d = pd.Timestamp(start), pd.Timestamp(end)
    frames = []
    cur = start_d
    while cur <= end_d:
        stop = min(cur + pd.DateOffset(years=9), end_d)
        url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
               f"&dataInicial={cur:%d/%m/%Y}&dataFinal={stop:%d/%m/%Y}")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        frames.append(pd.DataFrame(r.json()))
        cur = stop + pd.Timedelta(days=1)

    df = pd.concat(frames)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    cdi = df.set_index("data")["valor"].astype(float).div(100).rename("CDI")
    cdi = cdi[~cdi.index.duplicated()]
    os.makedirs(DATA_DIR, exist_ok=True)
    cdi.to_frame().to_csv(path)
    return cdi


def load_nefin(path: str) -> pd.DataFrame | None:
    """Lê fatores mensais do NEFIN-USP, se o arquivo existir.
    Formato esperado (CSV): coluna 'date' + Rm_minus_Rf, SMB, HML, WML, IML em decimal.
    """
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    df.index = df.index.to_period("M").to_timestamp("M")
    return df


def to_monthly_returns(daily_prices: pd.DataFrame) -> pd.DataFrame:
    """Retorno mensal a partir do último preço de cada mês."""
    month_end = daily_prices.resample("ME").last()
    return month_end.pct_change(fill_method=None)


def cdi_monthly(cdi_daily: pd.Series) -> pd.Series:
    """Compõe o CDI diário em taxa mensal."""
    return (1 + cdi_daily).resample("ME").prod() - 1


def flag_suspicious_returns(adj_close: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """Lista retornos diários acima de ±threshold (possíveis erros de ajuste do Yahoo)."""
    r = adj_close.pct_change(fill_method=None)
    s = r.stack()
    s = s[s.abs() > threshold]
    return s.rename("retorno_diario").reset_index().rename(columns={"level_0": "data", "level_1": "ticker"})
