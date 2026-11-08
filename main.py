"""Backtest de estratégias fatoriais na B3.

Uso:
    python main.py              # dados reais (Yahoo Finance + Banco Central)
    python main.py --sintetico  # dados simulados, para testar o código sem internet
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

import config as cfg
from src import dados, fatores, carteiras, metricas, graficos

RESULTS = "results"
MARKET = "Universo EW"  # carteira igualmente ponderada de todas as ações elegíveis


def save_csv(df: pd.DataFrame, path: str, index: bool = True, index_label: str | None = None):
    """Salva CSV no padrão do Excel em português: colunas separadas por ';',
    vírgula decimal, 4 casas e codificação que preserva os acentos (UTF-8 com BOM)."""
    df.round(4).to_csv(path, sep=";", decimal=",", encoding="utf-8-sig",
                       index=index, index_label=index_label, date_format="%Y-%m-%d")


def load_data(synthetic: bool):
    if synthetic:
        from tests.dados_sinteticos import gerar
        return gerar()
    px = dados.download_prices(cfg.TICKERS, cfg.START_DATE, cfg.END_DATE, cfg.BENCHMARK)
    cdi = dados.download_cdi(cfg.START_DATE, cfg.END_DATE)
    return px, cdi


def main(synthetic: bool = False):
    os.makedirs(RESULTS, exist_ok=True)
    px, cdi_daily = load_data(synthetic)

    adj, close, vol = px["adj_close"], px["close"], px["volume"]
    monthly = dados.to_monthly_returns(adj)
    ibov = dados.to_monthly_returns(px["benchmark"])["IBOV"]
    rf = dados.cdi_monthly(cdi_daily)

    if not synthetic:
        save_csv(dados.flag_suspicious_returns(adj), f"{RESULTS}/retornos_suspeitos.csv", index=False)

    elig = fatores.eligibility(adj, close, vol, cfg.MIN_HISTORY_DAYS,
                               cfg.MIN_MEDIAN_VOLUME_BRL, cfg.MIN_PRICE_BRL)

    # Benchmark principal: todas as ações elegíveis com pesos iguais, com dividendos e custos.
    # É a comparação justa com as carteiras (mesmo universo, mesmos ajustes). O Ibovespa
    # do Yahoo é índice de preço (sem dividendos) e fica só como referência.
    market, _ = carteiras.portfolio_returns(carteiras.weights_from_mask(elig), monthly,
                                            cfg.TRANSACTION_COST_BPS)

    sig_mom = fatores.momentum(monthly, cfg.MOM_LOOKBACK, cfg.MOM_SKIP)
    sig_vol = fatores.low_volatility(adj, cfg.VOL_WINDOW_DAYS).reindex_like(sig_mom)
    signals = {
        "Momentum": sig_mom,
        "Baixa_Vol": sig_vol,
        "Combinado": fatores.combined(sig_mom, sig_vol),
    }

    nefin = dados.load_nefin(cfg.NEFIN_FILE)
    mkt_excess = (market - rf).rename("Mercado").to_frame()
    all_summaries, all_alphas, all_rets = [], [], {}
    top = f"G{cfg.N_GROUPS}"

    for name, sig in signals.items():
        bt = carteiras.sort_backtest(sig, elig, monthly, cfg.N_GROUPS, cfg.TRANSACTION_COST_BPS)
        rets = bt["returns"]
        rets[MARKET] = market.reindex(rets.index)
        rets["Ibovespa (sem dividendos)"] = ibov.reindex(rets.index)
        rets["CDI"] = rf.reindex(rets.index)
        rets = rets.dropna()

        summ = metricas.summary(rets, rf)
        summ["Giro mensal médio"] = bt["turnover"].mean().reindex(summ.index)
        summ.insert(0, "Estratégia", name)
        all_summaries.append(summ)
        save_csv(rets, f"{RESULTS}/retornos_{name}.csv", index_label="Mês")
        all_rets[name] = rets

        # Alfa do melhor grupo (em excesso ao CDI) e da long-short (autofinanciada)
        for port in [top, "Long-Short"]:
            use_rf = rf if port == top else None
            models = [("CAPM", mkt_excess)]
            if nefin is not None:
                models.append(("NEFIN 5F", nefin[["Rm_minus_Rf", "SMB", "HML", "WML", "IML"]]))
            for model_name, factors in models:
                a = metricas.alpha_regression(rets[port], factors, use_rf, cfg.NEWEY_WEST_LAGS)
                a.insert(0, "modelo", model_name)
                a.insert(0, "carteira", port)
                a.insert(0, "estrategia", name)
                all_alphas.append(a)

        graficos.cumulative(rets, name, top, MARKET, f"{RESULTS}/acumulado_{name}.png")
        graficos.drawdown(rets, name, top, MARKET, f"{RESULTS}/drawdown_{name}.png")

    summary = pd.concat(all_summaries)
    summary["Meses"] = summary["Meses"].astype(int)
    alphas = pd.concat(all_alphas)
    save_csv(summary, f"{RESULTS}/metricas.csv", index_label="Carteira")
    save_csv(alphas, f"{RESULTS}/regressoes_alfa.csv", index_label="Termo")
    graficos.hero(all_rets, top, MARKET, f"{RESULTS}/destaque.png")
    graficos.alpha_plot(alphas, top, f"{RESULTS}/alfas.png")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", lambda x: f"{x:,.3f}")
    print("\n=== Métricas (líquidas de custos) ===")
    print(summary)
    print("\n=== Alfas (erros Newey-West) ===")
    print(alphas.loc[["const", "alfa a.a."]])
    print(f"\nAções no universo: {adj.shape[1]}. "
          f"Período: {rets.index.min():%m/%Y} a {rets.index.max():%m/%Y}. Resultados em ./{RESULTS}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sintetico", action="store_true", help="usa dados simulados")
    main(p.parse_args().sintetico)
