<div align="center">

# Factor Investing in Brazil: Momentum and Low Volatility

**A backtest of factor strategies in the Brazilian stock market (2011–2025)**

[![Run backtest](https://github.com/Regis-git-wq/backtest-fatores-b3/actions/workflows/backtest.yml/badge.svg)](https://github.com/Regis-git-wq/backtest-fatores-b3/actions/workflows/backtest.yml)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Regis-git-wq/backtest-fatores-b3/blob/main/rodar_no_colab.ipynb)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![License MIT](https://img.shields.io/badge/license-MIT-green)

[🇧🇷 Português](README.md) · 🇺🇸 English

</div>

---

Do **momentum** and **low-volatility** strategies, well documented in international markets, work on B3 (Brazil's stock exchange)? This project answers with a 15-year backtest, net of transaction costs, with significance tests, alpha regressions and robustness checks.

> Code comments and chart labels are in Portuguese. R$ = Brazilian real; CDI = Brazil's interbank rate, used as the risk-free rate.

<p align="center">
  <img src="resultados/destaque.png" alt="Cumulative wealth of each strategy's top tercile vs the universe and the CDI" width="100%">
</p>

## Key results

| | Momentum | Low volatility | Combined | Universe (equal-weighted) | CDI |
|---|:---:|:---:|:---:|:---:|:---:|
| **Annual return** | **16.6%** | 14.3% | 16.2% | 11.8% | 9.7% |
| **Annual volatility** | 21.1% | **16.6%** | 17.7% | 21.9% | — |
| **Sharpe ratio** | 0.40 | 0.33 | **0.42** | 0.20 | — |
| **Max drawdown** | −41.3% | **−30.7%** | −32.1% | −36.5% | — |
| **Annual alpha (CAPM)** | +4.8% \* | +2.6% | +4.3% \* | — | — |

<sub>Top tercile of each strategy, Feb 2011–Dec 2025, monthly rebalancing, net of costs. \* significant at 5%.</sub>

- 📈 **Momentum and the combined strategy generate alpha over the full period.** The momentum top tercile beats the market by 4.8% a year on a risk-adjusted basis (t = 2.07); the combined strategy by 4.3% (t = 2.56).
- 🛡️ **Low volatility earns more than the universe with less risk:** the lowest volatility and shallowest drawdown of all portfolios. Its 2.6% alpha is not significant (t = 1.43).
- ⚠️ **The gain comes from risk adjustment, not raw return.** The simple excess return over the universe (4.2% a year for momentum) is not significant (t = 1.61). Alpha shows up because the portfolios have betas below 1.
- ⚖️ **Long-short portfolios have negative market beta** (−0.37 for momentum, −0.73 for low volatility). The raw momentum premium is 8.7% a year (t = 1.66); its CAPM alpha is 10.8% (t = 2.32).

<p align="center">
  <img src="resultados/alfas.png" alt="Annual alpha with 95% confidence intervals" width="100%">
</p>

## Robustness: does the result hold up?

Partly. The tests below show where it is fragile.

<p align="center">
  <img src="resultados/robustez.png" alt="Long-short premium by subperiod, Selic cycle and specification" width="100%">
</p>

- **Concentrated in 2011–2015.** In that period the long-short premium was 27% a year for momentum (t = 3.51) and 22% for low volatility (t = 2.56). From 2016 on, momentum is close to zero, and low volatility lost 26% a year in 2016–2020 (t = −2.24).
- **Stronger in Selic hiking cycles.** In months of rising policy rates, the low-volatility top tercile beat the universe by 10.3% a year (t = 2.79). With stable or falling rates, no excess return is significant.
- **Sensitive to costs.** Momentum's excess over the universe falls from 4.5% a year with no costs to 2.6% at 50 bps per side.
- **Not driven by data errors, but dependent on a few stocks.** Cleaning handled 10 extreme daily returns in 5 stocks ([report](resultados/limpeza_dados.csv)), all classified as permanent jumps (mishandled splits and spin-offs, such as GPA's). With or without cleaning, the momentum long-short premium is 8.7% a year. Without those 5 stocks, however, it falls to 6.3%.
- **Quintiles** give similar or larger premiums (11.7% a year for momentum), also without statistical significance.

Tables: [`robustez_subperiodos.csv`](resultados/robustez_subperiodos.csv), [`robustez_ciclos_selic.csv`](resultados/robustez_ciclos_selic.csv) and [`robustez_especificacoes.csv`](resultados/robustez_especificacoes.csv). Full tables in [`resultados/`](resultados/) (semicolon-separated CSVs, decimal comma).

## Methodology

| Step | Choice |
|---|---|
| **Universe** | 61 liquid stocks listed on B3 |
| **Period** | Feb 2011 – Dec 2025 (179 months); 2010 is used only to compute the first signals |
| **Eligibility** | ≥ 1 year of history, median daily traded value ≥ R$ 5M, price ≥ R$ 1 |
| **Momentum 12-1** | Cumulative return over the past 12 months, skipping the most recent one (short-term reversal) |
| **Low volatility** | Annualized daily volatility over the past 252 trading days |
| **Combined** | Average of the two signals' z-scores |
| **Portfolios** | Equal-weighted terciles, rebalanced monthly |
| **Costs** | 10 bps per side on actual turnover |
| **Data cleaning** | Daily returns beyond ±50% in the adjusted price: a spike that reverts within 5 trading days is removed; a permanent jump (mishandled split or spin-off) has that day's return set to zero. Report in `limpeza_dados.csv` |
| **Benchmark** | Equal-weighted portfolio of all eligible stocks, with dividends and costs |
| **Risk-free rate** | CDI (Central Bank of Brazil, SGS series 12) |
| **Inference** | CAPM alpha with Newey-West standard errors; optional NEFIN-USP 5-factor model |

Signals use only information available at the end of month *t*; portfolios are held during *t+1*.

<details>
<summary><b>🧪 Validation: how I know the code doesn't "see the future"</b></summary>
<br>

`tests/test_pipeline.py` runs five checks on a simulated market:

1. **Random signal:** the long-short return is not significant (t ≈ 0).
2. **Signal that peeks at next month:** returns are absurdly high, confirming the time alignment: the code only makes "free money" when it is given future information.
3. **No look-ahead:** a date's signals don't change when all later data is deleted.
4. **Costs:** higher transaction costs reduce the long-short return, since both legs pay costs.
5. **Data cleaning:** an unadjusted split is neutralized, a reverting spike is removed, and clean data is left untouched.

The simulated market embeds a known momentum effect, and the backtest recovers it (t ≈ 2.2). Tests run automatically on GitHub Actions on every code change.

</details>

## How to run

| Option | How |
|---|---|
| **Browser** (no install) | [Open in Colab](https://colab.research.google.com/github/Regis-git-wq/backtest-fatores-b3/blob/main/rodar_no_colab.ipynb) → *Runtime → Run all* |
| **GitHub** | *Actions → Rodar backtest → Run workflow*; results are saved to `resultados/` |
| **Local** | `pip install -r requirements.txt`, then `python main.py` (or `python main.py --sintetico` to run offline) |

## Limitations

- **Survivorship bias:** the universe uses currently listed companies, which inflates absolute returns. The effect is smaller for comparisons between terciles and against the universe, which share the same bias.
- **Yahoo Finance data:** adjusted prices contain occasional errors. Automatic cleaning handles moves beyond ±50% in a day ([report](resultados/limpeza_dados.csv)), but smaller errors slip through. The robustness analysis compares against the raw data.
- **Small universe:** terciles of about 20 stocks make results sensitive to a few names.
- **Simplified costs:** a flat bps cost, with no market-impact model.

## Next steps

- [ ] **Value** and **quality** factors from CVM financial statements
- [ ] Historical Ibovespa constituents, to remove survivorship bias
- [x] Robustness: subperiods, Selic (policy rate) cycles, quintiles, costs from 0 to 50 bps (`robustez_*.csv` tables)
- [ ] Value weighting

## References

- Jegadeesh, N.; Titman, S. (1993). Returns to Buying Winners and Selling Losers. *Journal of Finance*.
- Ang, A.; Hodrick, R.; Xing, Y.; Zhang, X. (2006). The Cross-Section of Volatility and Expected Returns. *Journal of Finance*.
- Frazzini, A.; Pedersen, L. H. (2014). Betting Against Beta. *Journal of Financial Economics*.
- NEFIN-USP: risk factors for the Brazilian market.

---

<div align="center">
<sub>Made by <a href="https://github.com/Regis-git-wq">Reginaldo</a>, Economics student at Ibmec-SP · MIT License</sub>
</div>
