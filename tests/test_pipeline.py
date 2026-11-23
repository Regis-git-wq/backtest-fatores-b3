"""Testes de sanidade do backtest (rodar com: python -m tests.test_pipeline).

1. Sinal aleatório -> long-short sem retorno relevante.
2. Sinal "trapaceiro" que usa o retorno do mês seguinte -> retorno absurdo.
   Se isso acontece, o alinhamento temporal está certo: o sinal de t só ganha
   dinheiro quando enxerga t+1, ou seja, o código não vaza o futuro por conta própria.
3. O sinal de momentum de t não muda se apagarmos os dados posteriores a t (sem look-ahead).
4. Custos maiores reduzem o retorno da long-short (as duas pontas pagam custos).
5. A limpeza de dados neutraliza um desdobramento não ajustado, remove um pico que
   reverte e não mexe em dados sem problema.
6. O valor de mercado trata desdobramentos e units sem saltos implausíveis.
7. Os fundamentos só entram no sinal depois da data de entrega à CVM.
"""
import numpy as np
import pandas as pd

from src import dados, fatores, carteiras
from tests.dados_sinteticos import gerar


def main():
    px, _ = gerar()
    adj = px["adj_close"]
    monthly = dados.to_monthly_returns(adj)
    elig = fatores.eligibility(adj, px["close"], px["volume"], 252, 0, 0)

    rng = np.random.default_rng(0)
    rand_sig = pd.DataFrame(rng.normal(size=monthly.shape), index=monthly.index, columns=monthly.columns)
    ls_rand = carteiras.sort_backtest(rand_sig, elig, monthly, 3, 0)["returns"]["Long-Short"]
    t_rand = ls_rand.mean() / ls_rand.std() * np.sqrt(len(ls_rand))
    print(f"1) sinal aleatório: média LS = {ls_rand.mean():.4f}/mês, t = {t_rand:.2f}")
    assert abs(t_rand) < 3

    cheat = monthly.shift(-1)
    ls_cheat = carteiras.sort_backtest(cheat, elig, monthly, 3, 0)["returns"]["Long-Short"]
    print(f"2) sinal com o futuro: média LS = {ls_cheat.mean():.4f}/mês (deve ser enorme)")
    assert ls_cheat.mean() > 0.03

    cut = monthly.index[100]
    full = fatores.momentum(monthly).loc[cut]
    trunc = fatores.momentum(monthly.loc[:cut]).loc[cut]
    assert np.allclose(full.dropna(), trunc.dropna())
    vol_full = fatores.low_volatility(adj).loc[cut]
    vol_trunc = fatores.low_volatility(adj.loc[:cut]).loc[cut]
    assert np.allclose(vol_full.dropna(), vol_trunc.dropna())
    print("3) sinais em t idênticos com e sem dados futuros: OK")

    mom = fatores.momentum(monthly)
    ls0 = carteiras.sort_backtest(mom, elig, monthly, 3, 0)["returns"]["Long-Short"].mean()
    ls50 = carteiras.sort_backtest(mom, elig, monthly, 3, 50)["returns"]["Long-Short"].mean()
    print(f"4) long-short com custo 0: {ls0:.4f}/mês; com 50 bps: {ls50:.4f}/mês (deve cair)")
    assert ls50 < ls0 - 0.0005

    # 5) Limpeza: desdobramento não ajustado (salto permanente) e pico de 2 dias
    clean_ref = adj[["ACAO03", "ACAO04"]].dropna()
    dirty = clean_ref.copy()
    t_split, t_spike = dirty.index[1500], dirty.index[2000]
    dirty.loc[:t_split - pd.Timedelta(days=1), "ACAO03"] *= 3      # queda de ~67% no dia do "desdobramento"
    dirty.loc[t_spike:dirty.index[2001], "ACAO04"] *= 2.2          # pico de +120% que some 2 dias depois
    fixed, report = dados.clean_prices(dirty)
    assert set(report["tipo"]) == {"salto permanente", "pico revertido"}, report
    r_ok = clean_ref["ACAO03"].pct_change().dropna()
    r_fixed = fixed["ACAO03"].pct_change().dropna()
    assert np.allclose(r_ok.drop(t_split), r_fixed.drop(t_split)) and abs(r_fixed[t_split]) < 1e-12
    assert fixed.loc[t_spike:dirty.index[2001], "ACAO04"].isna().all()
    assert np.allclose(fixed["ACAO04"].dropna(), clean_ref["ACAO04"].drop([t_spike, dirty.index[2001]]))
    untouched, rep0 = dados.clean_prices(clean_ref)
    assert rep0.empty and np.allclose(untouched, clean_ref)
    print("5) limpeza: desdobramento neutralizado, pico removido, dados limpos intactos: OK")

    # 6) Valor de mercado: desdobramento e unit tratados, sem saltos implausíveis
    from src import fundamentos
    from tests.dados_sinteticos import gerar_fundamentos
    tmap, fund, shares, splits = gerar_fundamentos(px)
    close_m = px["close"].resample("ME").last()
    mcap = fundamentos.market_cap(close_m, splits, tmap, shares)
    assert fundamentos.implausible_caps(mcap, close_m).empty
    m = pd.Timestamp("2016-06-30")
    assert np.isclose(mcap.loc[m, "ACAO10"], close_m.loc[m, "ACAO10"] / 5 * 1e9)
    assert np.isclose(mcap.loc[pd.Timestamp("2017-06-30"), "ACAO05"],
                      close_m.loc[pd.Timestamp("2017-06-30"), "ACAO05"] * 2 * 1e9)
    early = shares.copy()
    early.loc[(early.cnpj == tmap.loc[tmap.ticker == "ACAO05", "cnpj"].iloc[0]) & (early.acoes == 2e9),
              "data"] = pd.Timestamp("2018-03-01")  # FRE registra a aprovação 3 meses antes
    early = pd.concat([early, pd.DataFrame({"cnpj": [tmap.cnpj.iloc[1]] * 3,
                                            "data": pd.to_datetime(["2012-01-01", "2013-01-01", "2014-01-01"]),
                                            "acoes": [1e9, 1e8, 1e9]})])   # erro de digitação no meio
    fixed_sh, rep = fundamentos.align_share_changes(early, splits, tmap)
    assert fundamentos.implausible_caps(fundamentos.market_cap(close_m, splits, tmap, fixed_sh), close_m).empty
    assert set(rep["acao"]) == {"movida para a data do split", "removida (desfeita no registro seguinte)"}
    bad = mcap.copy()
    bad.loc["2015-01-31":"2015-06-30", "ACAO20"] *= 10        # trecho errado que vai e volta
    bad.loc["2019-01-31":, "ACAO21"] *= 3                      # salto moderado sem volta (fusão): mantido
    bad.loc[:"2013-12-31", "ACAO22"] *= 50                     # salto extremo sem volta: antes é descartado
    fixed_mc, segs = fundamentos.drop_inconsistent_segments(bad, close_m)
    assert fixed_mc.loc["2015-01-31":"2015-06-30", "ACAO20"].isna().all()
    assert fixed_mc["ACAO21"].notna().sum() == bad["ACAO21"].notna().sum()
    assert fixed_mc.loc[:"2013-12-31", "ACAO22"].isna().all() and fixed_mc.loc["2014-01-31":, "ACAO22"].notna().all()
    assert len(segs) == 2
    for txt, n in [("1 KLBN3 + 4 KLBN4", 5), ("1 ON / 2 PN", 3), ("1 ENG3 e 4 ENGI4", 5),
                   ("2 ações preferenciais e 1 ação ordinária", 3), ("1 PN + 3 Recibos de Subscrição", None)]:
        assert fundamentos.parse_unit(txt) == n, txt
    print("6) valor de mercado: desdobramento e unit corretos, sem saltos: OK")

    # 7) Fundamentos sem look-ahead: o exercício de 2015 só aparece a partir de mar/2016
    months = close_m.index
    pit = fundamentos.point_in_time(fund, tmap, months)
    t0, cnpj0 = tmap.iloc[0]["ticker"], tmap.iloc[0]["cnpj"]
    pl = fund[fund.cnpj == cnpj0].set_index("exercicio")["pl_ctrl"]
    assert np.isclose(pit["pl_ctrl"].loc[pd.Timestamp("2016-02-29"), t0], pl[pd.Timestamp("2014-12-31")])
    assert np.isclose(pit["pl_ctrl"].loc[pd.Timestamp("2016-03-31"), t0], pl[pd.Timestamp("2015-12-31")])
    cut = pd.Timestamp("2019-08-31")
    pit_cut = fundamentos.point_in_time(fund[fund.disponivel_em <= cut], tmap, months[months <= cut])
    sig_full = fundamentos.signals(pit, mcap, [])["Valor"].loc[:cut]
    sig_cut = fundamentos.signals(pit_cut, mcap.loc[:cut], [])["Valor"]
    assert np.allclose(sig_full.fillna(0), sig_cut.fillna(0))
    print("7) fundamentos: só entram depois de entregues; sinais iguais sem dados futuros: OK")
    print("Todos os testes passaram.")


if __name__ == "__main__":
    main()
