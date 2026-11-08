"""Backtest de estratégias fatoriais na B3.

Uso:
    python main.py              # dados reais (Yahoo Finance + Banco Central)
    python main.py --sintetico  # dados simulados, para testar o código sem internet
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config as cfg
from src import dados, fatores, carteiras, metricas, excel

RESULTS = "results"


def load_data(synthetic: bool):
    if synthetic:
        from tests.dados_sinteticos import gerar
        return gerar()
    px = dados.download_prices(cfg.TICKERS, cfg.START_DATE, cfg.END_DATE, cfg.BENCHMARK)
    cdi = dados.download_cdi(cfg.START_DATE, cfg.END_DATE)
    return px, cdi


def plot_cumulative(rets: pd.DataFrame, title: str, path: str):
    labels = {f"G{cfg.N_GROUPS}": f"Melhor grupo (G{cfg.N_GROUPS})", "G1": "Pior grupo (G1)"}
    fig, ax = plt.subplots(figsize=(10, 5))
    (1 + rets).cumprod().rename(columns=labels).plot(ax=ax, logy=True, lw=1.6)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1f}"))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_title(title)
    ax.set_ylabel("R$ 1 investido (escala log)")
    ax.set_xlabel("")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_drawdown(rets: pd.DataFrame, title: str, path: str):
    w = (1 + rets).cumprod()
    dd = w / w.cummax() - 1
    fig, ax = plt.subplots(figsize=(10, 4))
    dd.plot(ax=ax, lw=1.2)
    ax.set_title(title)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(synthetic: bool = False):
    os.makedirs(RESULTS, exist_ok=True)
    px, cdi_daily = load_data(synthetic)

    adj, close, vol = px["adj_close"], px["close"], px["volume"]
    monthly = dados.to_monthly_returns(adj)
    ibov = dados.to_monthly_returns(px["benchmark"])["IBOV"]
    rf = dados.cdi_monthly(cdi_daily)

    if not synthetic:
        dados.flag_suspicious_returns(adj).to_csv(f"{RESULTS}/retornos_suspeitos.csv", index=False)

    elig = fatores.eligibility(adj, close, vol, cfg.MIN_HISTORY_DAYS,
                               cfg.MIN_MEDIAN_VOLUME_BRL, cfg.MIN_PRICE_BRL)
    sig_mom = fatores.momentum(monthly, cfg.MOM_LOOKBACK, cfg.MOM_SKIP)
    sig_vol = fatores.low_volatility(adj, cfg.VOL_WINDOW_DAYS).reindex_like(sig_mom)
    signals = {
        "Momentum": sig_mom,
        "Baixa_Vol": sig_vol,
        "Combinado": fatores.combined(sig_mom, sig_vol),
    }

    nefin = dados.load_nefin(cfg.NEFIN_FILE)
    all_summaries, all_alphas, all_rets = [], [], {}
    top = f"G{cfg.N_GROUPS}"

    for name, sig in signals.items():
        bt = carteiras.sort_backtest(sig, elig, monthly, cfg.N_GROUPS, cfg.TRANSACTION_COST_BPS)
        rets = bt["returns"]
        rets["Ibovespa"] = ibov.reindex(rets.index)
        rets["CDI"] = rf.reindex(rets.index)
        rets = rets.dropna()

        summ = metricas.summary(rets, rf)
        summ["Giro mensal médio"] = bt["turnover"].mean().reindex(summ.index)
        summ.insert(0, "Estratégia", name)
        all_summaries.append(summ)
        rets.to_csv(f"{RESULTS}/retornos_{name}.csv")
        all_rets[name] = rets

        # Alfa da carteira vencedora e da long-short: CAPM (Ibovespa) e, se houver, NEFIN
        mkt = (ibov - rf).rename("Mercado")
        for port in [top, "Long-Short"]:
            use_rf = rf if port == top else None
            a = metricas.alpha_regression(rets[port], mkt.to_frame(), use_rf, cfg.NEWEY_WEST_LAGS)
            a.insert(0, "modelo", "CAPM"); a.insert(0, "carteira", port); a.insert(0, "estrategia", name)
            all_alphas.append(a)
            if nefin is not None:
                a = metricas.alpha_regression(rets[port], nefin[["Rm_minus_Rf", "SMB", "HML", "WML", "IML"]],
                                              use_rf, cfg.NEWEY_WEST_LAGS)
                a.insert(0, "modelo", "NEFIN 5F"); a.insert(0, "carteira", port); a.insert(0, "estrategia", name)
                all_alphas.append(a)

        plot_cumulative(rets[[top, "G1", "Ibovespa", "CDI"]],
                        f"{name}: carteiras extremas vs Ibovespa e CDI",
                        f"{RESULTS}/acumulado_{name}.png")
        plot_drawdown(rets[[top, "Ibovespa"]], f"{name}: drawdown", f"{RESULTS}/drawdown_{name}.png")

    summary = pd.concat(all_summaries)
    alphas = pd.concat(all_alphas)
    summary.to_csv(f"{RESULTS}/metricas.csv")
    alphas.to_csv(f"{RESULTS}/regressoes_alfa.csv")

    params = {
        "Fonte dos dados": "Simulados (teste)" if synthetic else "Yahoo Finance (preços) e Banco Central (CDI)",
        "Período dos dados": f"{cfg.START_DATE} a {cfg.END_DATE}",
        "Ações no universo": ", ".join(adj.columns),
        "Benchmark": "Ibovespa",
        "Histórico mínimo (pregões)": cfg.MIN_HISTORY_DAYS,
        "Volume financeiro mediano mínimo (R$/dia)": cfg.MIN_MEDIAN_VOLUME_BRL,
        "Preço mínimo (R$)": cfg.MIN_PRICE_BRL,
        "Número de grupos": cfg.N_GROUPS,
        "Custo de transação (bps por lado)": cfg.TRANSACTION_COST_BPS,
        "Momentum": f"{cfg.MOM_LOOKBACK}-{cfg.MOM_SKIP}",
        "Janela da volatilidade (pregões)": cfg.VOL_WINDOW_DAYS,
        "Defasagens Newey-West": cfg.NEWEY_WEST_LAGS,
        "Fatores NEFIN": "Sim" if nefin is not None else "Não (só CAPM)",
    }
    excel.export_excel(f"{RESULTS}/resultados_backtest.xlsx", summary, alphas, all_rets, params, cfg.N_GROUPS)

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:,.3f}")
    print("\n=== Métricas (líquidas de custos) ===")
    print(summary)
    print("\n=== Alfas (erros Newey-West) ===")
    print(alphas.loc[["const", "alfa a.a."]] if "const" in alphas.index else alphas)
    print(f"\nPeríodo: {rets.index.min():%m/%Y} a {rets.index.max():%m/%Y}. Resultados em ./{RESULTS}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sintetico", action="store_true", help="usa dados simulados")
    main(p.parse_args().sintetico)
