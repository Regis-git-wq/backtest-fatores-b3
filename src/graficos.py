"""Gráficos do projeto, todos com o mesmo estilo.

Cores fixas por entidade (a mesma estratégia tem sempre a mesma cor em todos os gráficos);
benchmarks em cinza, para que as estratégias se destaquem.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BENCH, CDI_GRAY = "#52514e", "#a3a29c"

STRATEGY_COLOR = {"Momentum": BLUE, "Baixa_Vol": ORANGE, "Combinado": AQUA}
STRATEGY_LABEL = {"Momentum": "Momentum", "Baixa_Vol": "Baixa volatilidade", "Combinado": "Combinado"}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": INK_2, "ytick.color": INK_2, "xtick.labelsize": 10, "ytick.labelsize": 10,
    "legend.frameon": False, "legend.fontsize": 10, "font.size": 10,
    "lines.linewidth": 2, "lines.solid_capstyle": "round",
})


def _subtitle(ax, text: str):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK_2, fontsize=10, va="bottom")


def _log_wealth_axis(ax):
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(mticker.FixedLocator([0.5, 1, 2, 3, 5, 10, 20]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R$ {v:g}".replace(".", ",")))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())


def _end_labels(ax, wealth: pd.DataFrame, colors: dict, labels: dict):
    """Rótulo direto no fim de cada linha, com o valor final; afasta rótulos que colidem."""
    last = wealth.iloc[-1].sort_values()
    ys, min_gap = [], 1.09  # distância mínima (razão, escala log)
    for name, v in last.items():
        y = v if not ys or v / ys[-1] >= min_gap else ys[-1] * min_gap
        ys.append(y)
        ax.annotate(f"{labels[name]}  R$ {v:.1f}".replace(".", ","), xy=(wealth.index[-1], v),
                    xytext=(wealth.index[-1] + pd.Timedelta(days=60), y),
                    color=INK, fontsize=10, va="center",
                    arrowprops=dict(arrowstyle="-", color=colors[name], lw=1) if abs(y - v) / v > 0.02 else None)


def hero(rets_by_strategy: dict[str, pd.DataFrame], top: str, market: str, path: str):
    """Gráfico de destaque: melhor grupo de cada estratégia vs universo e CDI."""
    any_r = next(iter(rets_by_strategy.values()))
    series = {STRATEGY_LABEL[k]: v[top] for k, v in rets_by_strategy.items() if k != "Combinado"}
    series["Universo (pesos iguais)"] = any_r[market]
    series["CDI"] = any_r["CDI"]
    wealth = (1 + pd.DataFrame(series)).cumprod()
    wealth = pd.concat([pd.DataFrame(1.0, index=[wealth.index[0] - pd.offsets.MonthEnd(1)],
                                     columns=wealth.columns), wealth])
    colors = {"Momentum": BLUE, "Baixa volatilidade": ORANGE,
              "Universo (pesos iguais)": BENCH, "CDI": CDI_GRAY}
    styles = {"Universo (pesos iguais)": "-", "CDI": "--"}

    fig, ax = plt.subplots(figsize=(11, 5.6))
    for c in wealth:
        ax.plot(wealth.index, wealth[c], color=colors[c], ls=styles.get(c, "-"),
                lw=2.4 if c in ("Momentum", "Baixa volatilidade") else 1.8, label=c)
    _log_wealth_axis(ax)
    _end_labels(ax, wealth, colors, {c: c for c in wealth})
    ax.set_xlim(wealth.index[0], wealth.index[-1] + pd.Timedelta(days=1400))
    years = pd.date_range(f"{wealth.index[0].year + 1}", f"{wealth.index[-1].year + 1}", freq="2YS")
    ax.set_xticks(years, [f"{y:%Y}" for y in years])
    ax.grid(axis="x", visible=False)
    ax.spines["bottom"].set_bounds(mdates.date2num(wealth.index[0]), mdates.date2num(wealth.index[-1]))
    ax.set_title("Quanto valeria R$ 1 investido em 2011", pad=26)
    _subtitle(ax, f"Melhor tercil de cada estratégia, rebalanceamento mensal, líquido de custos · "
                  f"{wealth.index[1]:%m/%Y}–{wealth.index[-1]:%m/%Y} · escala log")
    ax.legend(loc="upper left", ncol=4, bbox_to_anchor=(0, 1.0))
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def alpha_plot(alphas: pd.DataFrame, top: str, path: str):
    """Alfa anual (CAPM) com intervalo de 95%, para o melhor tercil e a long-short."""
    rows = []
    for (strat, port), sub in alphas[alphas.modelo == "CAPM"].groupby(["estrategia", "carteira"], sort=False):
        b, t = sub.loc["const", "coef"], sub.loc["const", "t"]
        se = abs(b / t) if t else np.nan
        ann = lambda m: (1 + m) ** 12 - 1  # mesma anualização das tabelas
        rows.append((strat, port, ann(b), ann(b - 1.96 * se), ann(b + 1.96 * se), t))
    df = pd.DataFrame(rows, columns=["estrategia", "carteira", "alfa", "lo", "hi", "t"])

    strategies = list(dict.fromkeys(df.estrategia))
    label_x = df.hi.max() + 0.015
    fig, ax = plt.subplots(figsize=(11, 4.8))
    offsets = {top: -0.17, "Long-Short": 0.17}
    colors = {top: BLUE, "Long-Short": ORANGE}
    names = {top: "Melhor tercil", "Long-Short": "Long-short (melhor − pior)"}
    for port in [top, "Long-Short"]:
        d = df[df.carteira == port].set_index("estrategia").loc[strategies]
        y = np.arange(len(strategies)) + offsets[port]
        ax.hlines(y, d.lo, d.hi, color=colors[port], lw=2)
        ax.scatter(d.alfa, y, s=70, color=colors[port], zorder=3, edgecolor=SURFACE, linewidth=2,
                   label=names[port])
        for yi, (a, t) in zip(y, zip(d.alfa, d.t)):
            star = " *" if abs(t) > 1.96 else ""
            ax.text(label_x, yi, f"{a:+.1%}  (t = {t:.2f}){star}".replace(".", ","),
                    va="center", color=INK, fontsize=10)
    ax.axvline(0, color=INK_2, lw=1)
    ax.set_yticks(range(len(strategies)), [STRATEGY_LABEL[s] for s in strategies], fontsize=11, color=INK)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="y", visible=False)
    ax.set_xlim(right=df.hi.max() + 0.12)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Alfa anual em relação ao mercado (CAPM)", pad=26)
    _subtitle(ax, "Ponto = estimativa; linha = intervalo de 95% (erros Newey-West); * significativo a 5%")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def cumulative(rets: pd.DataFrame, name: str, top: str, market: str, path: str):
    """Melhor e pior grupo de uma estratégia vs universo e CDI."""
    color = STRATEGY_COLOR.get(name, BLUE)
    cols = {top: f"Melhor tercil ({top})", "G1": "Pior tercil (G1)",
            market: "Universo (pesos iguais)", "CDI": "CDI"}
    wealth = (1 + rets[list(cols)]).cumprod().rename(columns=cols)
    colors = {cols[top]: color, cols["G1"]: color, cols[market]: BENCH, "CDI": CDI_GRAY}
    styles = {cols["G1"]: ":", "CDI": "--"}
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in wealth:
        ax.plot(wealth.index, wealth[c], color=colors[c], ls=styles.get(c, "-"),
                lw=2.4 if c == cols[top] else 1.8, label=c)
    _log_wealth_axis(ax)
    ax.set_title(f"{STRATEGY_LABEL.get(name, name)}: melhor vs pior tercil", pad=26)
    _subtitle(ax, "R$ 1 investido, líquido de custos, escala log")
    ax.legend(loc="upper left", ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def drawdown(rets: pd.DataFrame, name: str, top: str, market: str, path: str):
    color = STRATEGY_COLOR.get(name, BLUE)
    w = (1 + rets[[top, market]]).cumprod()
    dd = w / w.cummax() - 1
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.fill_between(dd.index, dd[top], 0, color=color, alpha=0.15, lw=0)
    ax.plot(dd.index, dd[top], color=color, label=f"Melhor tercil ({top})")
    ax.plot(dd.index, dd[market], color=BENCH, lw=1.5, label="Universo (pesos iguais)")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
    ax.set_title(f"{STRATEGY_LABEL.get(name, name)}: queda em relação ao pico (drawdown)", pad=12)
    ax.legend(loc="lower left", ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
