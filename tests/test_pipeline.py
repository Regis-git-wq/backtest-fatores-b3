"""Testes de sanidade do backtest (rodar com: python -m tests.test_pipeline).

1. Sinal aleatório -> long-short sem retorno relevante.
2. Sinal "trapaceiro" que usa o retorno do mês seguinte -> retorno absurdo.
   Se isso acontece, o alinhamento temporal está certo: o sinal de t só ganha
   dinheiro quando enxerga t+1, ou seja, o código não vaza o futuro por conta própria.
3. O sinal de momentum de t não muda se apagarmos os dados posteriores a t (sem look-ahead).
4. Custos maiores reduzem o retorno da long-short (as duas pontas pagam custos).
5. A limpeza de dados neutraliza um desdobramento não ajustado, remove um pico que
   reverte e não mexe em dados sem problema.
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
    print("Todos os testes passaram.")


if __name__ == "__main__":
    main()
