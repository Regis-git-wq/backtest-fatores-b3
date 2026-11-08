"""Testes de sanidade do backtest (rodar com: python -m tests.test_pipeline).

1. Sinal aleatório -> long-short sem retorno relevante.
2. Sinal "trapaceiro" que usa o retorno do mês seguinte -> retorno absurdo.
   Se isso acontece, o alinhamento temporal está certo: o sinal de t só ganha
   dinheiro quando enxerga t+1, ou seja, o código não vaza o futuro por conta própria.
3. O sinal de momentum de t não muda se apagarmos os dados posteriores a t (sem look-ahead).
"""
import numpy as np
import pandas as pd

import config as cfg
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
    print("Todos os testes passaram.")


if __name__ == "__main__":
    main()
