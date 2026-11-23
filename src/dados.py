"""Coleta e preparação de dados: preços (Yahoo Finance), CDI (Banco Central) e fatores NEFIN.

Tudo fica em cache na pasta data/ para não baixar de novo a cada execução.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import requests

DATA_DIR = "data"


def _cache(path: str) -> pd.DataFrame | None:
    if os.path.exists(path):
        return pd.read_csv(path, index_col=0, parse_dates=True)
    return None


def _cache_valid(name: str, key: dict) -> bool:
    """O cache só vale se foi gerado com os mesmos parâmetros (tickers, datas).
    Assim, mudar o config.py força um novo download."""
    path = f"{DATA_DIR}/{name}_meta.json"
    if not os.path.exists(path):
        return False
    with open(path) as f:
        return json.load(f) == key


def _save_meta(name: str, key: dict):
    with open(f"{DATA_DIR}/{name}_meta.json", "w") as f:
        json.dump(key, f)


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
    key = {"tickers": sorted(tickers), "start": start, "end": end, "benchmark": benchmark}
    if _cache_valid("precos", key) and all(os.path.exists(p) for p in paths.values()):
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
    _save_meta("precos", key)
    return out


def download_splits(tickers: list[str]) -> dict[str, pd.Series]:
    """Desdobramentos, grupamentos e bonificações do Yahoo (razão > 1 = desdobramento).
    Necessários para desfazer o ajuste do preço de fechamento ao calcular o valor de mercado."""
    path = f"{DATA_DIR}/splits.csv"
    key = {"tickers": sorted(tickers)}
    if _cache_valid("splits", key) and os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["data"])
    else:
        import yfinance as yf
        rows = []
        for t in tickers:
            try:
                sp = yf.Ticker(f"{t}.SA").splits
            except Exception as e:  # um ticker com erro não derruba o resto
                print(f"[aviso] splits de {t}: {e}")
                continue
            for d, r in sp.items():
                rows.append({"ticker": t, "data": pd.Timestamp(d).tz_localize(None).normalize(), "razao": float(r)})
        df = pd.DataFrame(rows, columns=["ticker", "data", "razao"])
        os.makedirs(DATA_DIR, exist_ok=True)
        df.to_csv(path, index=False)
        _save_meta("splits", key)
    return {t: g.set_index("data")["razao"] for t, g in df.groupby("ticker")}


def download_cdi(start: str, end: str) -> pd.Series:
    """CDI diário (série SGS 12 do BCB, em % ao dia). A API limita consultas a 10 anos,
    então a busca é feita em blocos. Retorna a taxa diária em decimal."""
    path = f"{DATA_DIR}/cdi.csv"
    key = {"start": start, "end": end}
    if _cache_valid("cdi", key):
        return _cache(path).iloc[:, 0]

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
    _save_meta("cdi", key)
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


def clean_prices(adj_close: pd.DataFrame, threshold: float = 0.5, revert_window: int = 5,
                 revert_tol: float = 0.25, keep: list[tuple[str, str]] | None = None,
                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trata retornos diários acima de ±threshold no preço ajustado.

    Cada caso é classificado em:
    - "pico revertido": o preço volta para perto do nível anterior (±revert_tol) em até
      revert_window pregões. É erro pontual de dado; os preços do pico viram NaN.
    - "salto permanente": o novo nível se mantém. Em ações líquidas, isso quase sempre é
      desdobramento/grupamento mal ajustado ou cisão (o acionista recebe as novas ações,
      então não é perda). O retorno do dia é zerado, reescalando o histórico anterior.
    Casos em `keep` (ticker, "AAAA-MM-DD") são mantidos como estão: use para eventos reais.

    Retorna (preços limpos, relatório com uma linha por caso).
    """
    keep = {(t, pd.Timestamp(d)) for t, d in (keep or [])}
    out = adj_close.copy()
    log = []
    for col in out.columns:
        s = out[col].dropna().copy()
        handled = set()
        for _ in range(50):  # cada correção pode revelar ou eliminar outros casos
            r = s.pct_change()
            cases = [t for t in r.index[r.abs() > threshold] if t not in handled]
            if not cases:
                break
            t = cases[0]
            handled.add(t)
            i = s.index.get_loc(t)
            p_before, p_jump = s.iloc[i - 1], s.iloc[i]
            entry = {"data": t, "ticker": col, "retorno_original": p_jump / p_before - 1}
            if (col, t) in keep:
                log.append({**entry, "tipo": "mantido (exceção manual)", "acao": "nenhuma"})
                continue
            back = None
            for k in range(1, revert_window + 1):
                if i + k < len(s) and abs(np.log(s.iloc[i + k] / p_before)) <= np.log(1 + revert_tol):
                    back = k
                    break
            if back is not None:
                s.iloc[i:i + back] = np.nan
                s = s.dropna()
                log.append({**entry, "tipo": "pico revertido",
                            "acao": f"{back} pregão(ões) removido(s)"})
            else:
                s.iloc[:i] = s.iloc[:i] * (p_jump / p_before)
                log.append({**entry, "tipo": "salto permanente",
                            "acao": "retorno do dia zerado (histórico reescalado)"})
        out[col] = s.reindex(out.index)
        # mantém NaN onde o original já era NaN e onde o pico foi removido
    report = pd.DataFrame(log, columns=["data", "ticker", "retorno_original", "tipo", "acao"])
    return out, report.sort_values(["data", "ticker"]).reset_index(drop=True)
