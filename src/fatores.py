"""Construção dos sinais (fatores) e do filtro de elegibilidade.

Convenção: todo sinal com data t usa apenas informação disponível até o fim do mês t.
O sinal é sempre orientado para que valor MAIOR = ação mais atrativa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def momentum(monthly_returns: pd.DataFrame, lookback: int = 12, skip: int = 1) -> pd.DataFrame:
    """Momentum 12-1: retorno acumulado de t-12 a t-1, pulando o último mês
    (o último mês tende a apresentar reversão de curto prazo)."""
    n = lookback - skip
    # soma de log-retornos = produto dos retornos brutos; exige os n meses completos
    log_ret = np.log1p(monthly_returns)
    cum = np.expm1(log_ret.rolling(n, min_periods=n).sum())
    return cum.shift(skip)


def low_volatility(adj_close: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """Volatilidade diária anualizada do último ano, com sinal invertido
    (menos volátil = maior sinal)."""
    daily_ret = adj_close.pct_change(fill_method=None)
    vol = daily_ret.rolling(window, min_periods=int(window * 0.8)).std() * (252 ** 0.5)
    return -vol.resample("ME").last()


def zscore_cross_section(signal: pd.DataFrame) -> pd.DataFrame:
    """Padroniza o sinal entre as ações em cada data."""
    return signal.sub(signal.mean(axis=1), axis=0).div(signal.std(axis=1), axis=0)


def combined(*signals: pd.DataFrame) -> pd.DataFrame:
    """Média dos z-scores (fator composto). Exige que a ação tenha todos os sinais."""
    zs = [zscore_cross_section(s) for s in signals]
    total = sum(zs)
    return total / len(zs)


def eligibility(adj_close: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame,
                min_history: int, min_volume_brl: float, min_price: float) -> pd.DataFrame:
    """Máscara mensal (True = ação pode entrar na carteira formada no fim do mês)."""
    history = adj_close.notna().cumsum()
    fin_volume = (close * volume).rolling(63, min_periods=40).median()
    ok = (history >= min_history) & (fin_volume >= min_volume_brl) & (close >= min_price)
    return ok.resample("ME").last().fillna(False).astype(bool)
