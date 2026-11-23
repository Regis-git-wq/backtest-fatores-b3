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
from src import dados, fatores, carteiras, metricas, graficos, robustez, fundamentos

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
        return gerar(com_erros=True)
    px = dados.download_prices(cfg.TICKERS, cfg.START_DATE, cfg.END_DATE, cfg.BENCHMARK)
    cdi = dados.download_cdi(cfg.START_DATE, cfg.END_DATE)
    return px, cdi


def build_signals(adj: pd.DataFrame, monthly: pd.DataFrame,
                  fund: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    sig_mom = fatores.momentum(monthly, cfg.MOM_LOOKBACK, cfg.MOM_SKIP)
    sig_vol = fatores.low_volatility(adj, cfg.VOL_WINDOW_DAYS).reindex_like(sig_mom)
    out = {
        "Momentum": sig_mom,
        "Baixa_Vol": sig_vol,
        "Combinado": fatores.combined(sig_mom, sig_vol),
    }
    if fund is not None:
        val = fund["Valor"].reindex_like(sig_mom)
        qual = fund["Qualidade"].reindex_like(sig_mom)
        out["Valor"] = val
        out["Qualidade"] = qual
        out["Multifator"] = fatores.combined(sig_mom, sig_vol, val, qual)
    return out


def load_fundamentals(synthetic: bool, px: dict) -> dict[str, pd.DataFrame] | None:
    """Sinais de valor e qualidade a partir dos dados da CVM (ou simulados).
    Se a CVM estiver fora do ar, o backtest segue só com os fatores de preço."""
    if not cfg.USE_FUNDAMENTALS:
        return None
    tickers = list(px["close"].columns)
    if synthetic:
        from tests.dados_sinteticos import gerar_fundamentos
        tmap, fund, shares, splits = gerar_fundamentos(px)
    else:
        try:
            tmap = fundamentos.ticker_map(tickers, overrides=cfg.CNPJ_OVERRIDES)
            cnpjs = tmap["cnpj"].unique().tolist()
            fund = fundamentos.statements(cnpjs, cfg.FUND_YEARS)
            shares = fundamentos.share_counts(cnpjs, cfg.FUND_YEARS)
            splits = dados.download_splits(tickers)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[aviso] fundamentos da CVM indisponíveis ({e!r}); seguindo só com os fatores de preço")
            return None
    missing = sorted(set(tickers) - set(tmap["ticker"]))
    print(f"Fundamentos: {len(tmap)} ações ligadas a um CNPJ"
          + (f"; sem CNPJ: {', '.join(missing)}" if missing else ""))

    shares, share_fix = fundamentos.align_share_changes(shares, splits, tmap)
    save_csv(share_fix, f"{RESULTS}/fundamentos_ajustes_acoes.csv", index=False)
    close_m = px["close"].resample("ME").last()
    mcap = fundamentos.market_cap(close_m, splits, tmap, shares)
    mcap, dropped = fundamentos.drop_inconsistent_segments(mcap, close_m)
    save_csv(dropped, f"{RESULTS}/fundamentos_trechos_descartados.csv", index=False)
    pit = fundamentos.point_in_time(fund, tmap, close_m.index, cfg.FUND_MAX_AGE_MONTHS)
    sig = fundamentos.signals(pit, mcap, cfg.FINANCIALS)

    # auditoria: mapeamento, cobertura, valores de mercado suspeitos e foto do último mês
    save_csv(tmap, f"{RESULTS}/fundamentos_mapeamento.csv", index=False)
    cov = fundamentos.coverage({"Valor de mercado": mcap, "B/M": sig["_bm"], "E/P": sig["_ep"],
                                "ROE": sig["_roe"], "Valor": sig["Valor"], "Qualidade": sig["Qualidade"]})
    save_csv(cov, f"{RESULTS}/fundamentos_cobertura.csv", index_label="Ano (dezembro)")
    save_csv(fundamentos.implausible_caps(mcap, close_m), f"{RESULTS}/fundamentos_saltos_valor_mercado.csv",
             index=False)
    last = close_m.index[-1]
    snap = pd.DataFrame({"Valor de mercado (R$ bi)": mcap.loc[last] / 1e9, "B/M": sig["_bm"].loc[last],
                         "E/P": sig["_ep"].loc[last], "ROE": sig["_roe"].loc[last],
                         "Alavancagem": sig["_lev"].loc[last]})
    save_csv(snap, f"{RESULTS}/fundamentos_ultimo_mes.csv", index_label="Ticker")
    return sig


def main(synthetic: bool = False):
    os.makedirs(RESULTS, exist_ok=True)
    px, cdi_daily = load_data(synthetic)

    adj_raw, close, vol = px["adj_close"], px["close"], px["volume"]
    ibov = dados.to_monthly_returns(px["benchmark"])["IBOV"]
    rf = dados.cdi_monthly(cdi_daily)

    # Limpeza: retornos diários acima de ±50% no preço ajustado (erros do Yahoo)
    adj, cleaning = dados.clean_prices(adj_raw, cfg.CLEAN_THRESHOLD, cfg.CLEAN_REVERT_WINDOW,
                                       cfg.CLEAN_REVERT_TOL, cfg.CLEAN_KEEP)
    save_csv(cleaning, f"{RESULTS}/limpeza_dados.csv", index=False)
    print(f"Limpeza de dados: {len(cleaning)} caso(s) tratado(s) "
          f"({', '.join(sorted(cleaning['ticker'].unique())) or 'nenhum'})")
    monthly = dados.to_monthly_returns(adj)

    elig = fatores.eligibility(adj, close, vol, cfg.MIN_HISTORY_DAYS,
                               cfg.MIN_MEDIAN_VOLUME_BRL, cfg.MIN_PRICE_BRL)

    # Benchmark principal: todas as ações elegíveis com pesos iguais, com dividendos e custos.
    # É a comparação justa com as carteiras (mesmo universo, mesmos ajustes). O Ibovespa
    # do Yahoo é índice de preço (sem dividendos) e fica só como referência.
    market, _ = carteiras.portfolio_returns(carteiras.weights_from_mask(elig), monthly,
                                            cfg.TRANSACTION_COST_BPS)

    fund_sig = load_fundamentals(synthetic, px)
    signals = build_signals(adj, monthly, fund_sig)

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
    # --- Robustez ---
    sub = robustez.por_subperiodo(all_rets, cfg.SUBPERIODS, top, MARKET)
    reg = robustez.por_regime(all_rets, robustez.regime_selic(cdi_daily), top, MARKET)
    base = {"grupos": cfg.N_GROUPS, "custo_bps": cfg.TRANSACTION_COST_BPS}
    specs = [{"nome": f"Base (tercis, {cfg.TRANSACTION_COST_BPS} bps)", **base}]
    specs += [{"nome": f"Custo de {c} bps", **base, "custo_bps": c} for c in cfg.COST_GRID_BPS]
    specs += [{"nome": f"{cfg.ALT_N_GROUPS} grupos", **base, "grupos": cfg.ALT_N_GROUPS}]
    flagged = sorted(cleaning["ticker"].unique())
    if flagged:
        monthly_raw = dados.to_monthly_returns(adj_raw)
        specs += [{"nome": "Dados brutos (sem limpeza)", **base,
                   "monthly": monthly_raw, "signals": build_signals(adj_raw, monthly_raw, fund_sig)}]
        specs += [{"nome": f"Sem as ações corrigidas ({len(flagged)})", **base, "excluir": flagged}]
    esp = robustez.por_especificacao(signals, elig, monthly, specs)
    save_csv(sub, f"{RESULTS}/robustez_subperiodos.csv", index=False)
    save_csv(reg, f"{RESULTS}/robustez_ciclos_selic.csv", index=False)
    save_csv(esp, f"{RESULTS}/robustez_especificacoes.csv", index=False)
    graficos.robustez_plot(sub, reg, esp, f"{RESULTS}/robustez.png")

    graficos.hero(all_rets, top, MARKET, f"{RESULTS}/destaque.png")
    graficos.alpha_plot(alphas, top, f"{RESULTS}/alfas.png")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", lambda x: f"{x:,.3f}")
    print("\n=== Métricas (líquidas de custos) ===")
    print(summary)
    print("\n=== Alfas (erros Newey-West) ===")
    print(alphas.loc[["const", "alfa a.a."]])
    for title, tab in [("Robustez: subperíodos", sub), ("Robustez: ciclos da Selic", reg),
                       ("Robustez: especificações", esp)]:
        print(f"\n=== {title} ===")
        print(tab.to_string(index=False))
    print(f"\nAções no universo: {adj.shape[1]}. "
          f"Período: {rets.index.min():%m/%Y} a {rets.index.max():%m/%Y}. Resultados em ./{RESULTS}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sintetico", action="store_true", help="usa dados simulados")
    main(p.parse_args().sintetico)
