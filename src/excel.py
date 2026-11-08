"""Exporta os resultados do backtest para uma planilha Excel já formatada.

Abas geradas:
- Resumo: métricas de cada estratégia, com destaques de cor
- Alfas: regressões (CAPM e, se houver, NEFIN) com significância
- Uma aba por estratégia: retornos mensais, patrimônio acumulado, drawdown e gráficos
- Parâmetros: configuração usada no backtest
- Como ler: explicação de cada métrica

Os números são valores calculados em Python (não fórmulas), para que o arquivo abra
pronto em qualquer aplicativo, inclusive no celular.
"""
from __future__ import annotations

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.axis import DateAxis
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _date_axis(chart, label_low: bool = False):
    """Eixo X de datas. O eixo Y precisa apontar para o id do eixo de datas (500);
    sem isso o Excel considera o arquivo corrompido."""
    chart.x_axis = DateAxis(crossAx=100)
    chart.x_axis.number_format = "yyyy"
    chart.x_axis.majorTimeUnit = "years"
    chart.y_axis.crossAx = 500
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    if label_low:
        chart.x_axis.tickLblPos = "low"

FONT = "Arial"
NAVY = "1F3864"
LIGHT = "D9E1F2"
GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
RED_FILL = PatternFill("solid", fgColor="FFC7CE")
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
BAND_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)

PCT = "0.0%;-0.0%;-"
PCT2 = "0.00%;-0.00%;-"
DEC2 = "0.00;-0.00;-"


def _labels(n_groups: int) -> dict:
    lab = {f"G{g}": f"Grupo {g}" for g in range(1, n_groups + 1)}
    lab["G1"] = "Pior grupo (G1)"
    lab[f"G{n_groups}"] = f"Melhor grupo (G{n_groups})"
    lab["Long-Short"] = f"Long-Short (G{n_groups} − G1)"
    return lab


def _title(ws, text: str, subtitle: str | None = None):
    ws["A1"] = text
    ws["A1"].font = Font(name=FONT, size=14, bold=True, color=NAVY)
    if subtitle:
        ws["A2"] = subtitle
        ws["A2"].font = Font(name=FONT, size=10, italic=True, color="595959")
    ws.sheet_view.showGridLines = False


def _header(ws, row: int, col: int, values: list[str]):
    for j, v in enumerate(values):
        c = ws.cell(row=row, column=col + j, value=v)
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
    ws.row_dimensions[row].height = 32


def _cell(ws, row, col, value, fmt=None, bold=False, fill=None, align="center"):
    c = ws.cell(row=row, column=col, value=value)
    c.font = Font(name=FONT, bold=bold)
    c.border = BOX
    c.alignment = Alignment(horizontal=align, vertical="center")
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    return c


def _widths(ws, widths: dict):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def _resumo(wb, summary: pd.DataFrame, period: str, n_groups: int):
    ws = wb.active
    ws.title = "Resumo"
    _title(ws, "Backtest de Estratégias Fatoriais na B3 — Resumo",
           f"Período: {period} · Retornos mensais líquidos de custos · Taxa livre de risco: CDI")
    cols = ["Estratégia", "Carteira", "Retorno a.a.", "Volatilidade a.a.", "Sharpe",
            "Estatística t", "Drawdown máximo", "% meses positivos", "Giro mensal médio", "Meses"]
    _header(ws, 4, 1, cols)
    lab = _labels(n_groups)
    r = 5
    first = r
    for strat, block in summary.groupby("Estratégia", sort=False):
        start = r
        for port, row in block.iterrows():
            is_ls = port == "Long-Short"
            is_ref = port in ("Ibovespa", "CDI")
            fill = PatternFill("solid", fgColor=LIGHT) if is_ls else (BAND_FILL if is_ref else None)
            _cell(ws, r, 1, strat.replace("_", " "), bold=True, fill=fill)
            _cell(ws, r, 2, lab.get(port, port), bold=is_ls, fill=fill, align="left")
            _cell(ws, r, 3, row["Retorno a.a."], PCT, fill=fill)
            _cell(ws, r, 4, row["Volatilidade a.a."], PCT, fill=fill)
            _cell(ws, r, 5, None if pd.isna(row["Sharpe"]) else row["Sharpe"], DEC2, fill=fill)
            _cell(ws, r, 6, None if pd.isna(row["t (média excesso)"]) else row["t (média excesso)"], DEC2, fill=fill)
            _cell(ws, r, 7, row["Max drawdown"], PCT, fill=fill)
            _cell(ws, r, 8, row["% meses positivos"], PCT, fill=fill)
            g = row.get("Giro mensal médio")
            _cell(ws, r, 9, None if pd.isna(g) else g, PCT, fill=fill)
            _cell(ws, r, 10, int(row["Meses"]), "0", fill=fill)
            r += 1
        ws.merge_cells(start_row=start, end_row=r - 1, start_column=1, end_column=1)
        ws.cell(row=start, column=1).alignment = Alignment(horizontal="center", vertical="center",
                                                           text_rotation=90)
        r += 1  # linha em branco entre estratégias
    last = r - 2

    # Sharpe: escala de cor vermelho -> branco -> verde
    ws.conditional_formatting.add(
        f"E{first}:E{last}",
        ColorScaleRule(start_type="num", start_value=-1, start_color="F8696B",
                       mid_type="num", mid_value=0, mid_color="FFFFFF",
                       end_type="num", end_value=1, end_color="63BE7B"))
    # Estatística t: verde se significativa a 5% (|t| > 1,96), vermelha se significativamente negativa
    ws.conditional_formatting.add(f"F{first}:F{last}",
                                  CellIsRule(operator="greaterThan", formula=["1.96"], fill=GREEN_FILL))
    ws.conditional_formatting.add(f"F{first}:F{last}",
                                  CellIsRule(operator="lessThan", formula=["-1.96"], fill=RED_FILL))

    note = r + 1
    notes = [
        "Leitura rápida:",
        "• Sharpe: retorno acima do CDI por unidade de risco (na Long-Short, retorno bruto, pois a carteira é autofinanciada).",
        "• Estatística t em verde: média do excesso de retorno estatisticamente diferente de zero a 5% (|t| > 1,96).",
        "• Long-Short: compra o melhor grupo e vende o pior; mede o prêmio do fator isoladamente.",
        "• Detalhes de cada métrica na aba 'Como ler'.",
    ]
    for i, t in enumerate(notes):
        c = ws.cell(row=note + i, column=1, value=t)
        c.font = Font(name=FONT, size=9, bold=(i == 0), color="404040")
    _widths(ws, {"A": 7, "B": 26, "C": 12, "D": 13, "E": 10, "F": 11, "G": 13, "H": 12, "I": 12, "J": 8})
    ws.freeze_panes = "C5"


def _alfas(wb, alphas: pd.DataFrame, n_groups: int):
    ws = wb.create_sheet("Alfas")
    _title(ws, "Regressões de alfa",
           "Excesso de retorno da carteira regredido nos fatores · Erros-padrão Newey-West")
    lab = _labels(n_groups)
    cols = ["Estratégia", "Carteira", "Modelo", "Alfa mensal", "Alfa anualizado", "t do alfa",
            "p-valor do alfa", "Significativo a 5%?", "Beta de mercado", "R²", "Meses"]
    _header(ws, 4, 1, cols)
    r = 5
    keys = alphas[["estrategia", "carteira", "modelo"]].drop_duplicates().itertuples(index=False)
    for strat, port, model in keys:
        sub = alphas[(alphas.estrategia == strat) & (alphas.carteira == port) & (alphas.modelo == model)]
        get = lambda name, col="coef": sub.loc[name, col] if name in sub.index else None
        beta_name = "Mercado" if "Mercado" in sub.index else "Rm_minus_Rf"
        p = get("const", "p-valor")
        sig = p is not None and p < 0.05
        _cell(ws, r, 1, strat.replace("_", " "), bold=True)
        _cell(ws, r, 2, lab.get(port, port), align="left")
        _cell(ws, r, 3, model)
        _cell(ws, r, 4, get("const"), PCT2)
        _cell(ws, r, 5, get("alfa a.a."), PCT, bold=True)
        _cell(ws, r, 6, get("const", "t"), DEC2)
        _cell(ws, r, 7, p, "0.000")
        _cell(ws, r, 8, "Sim" if sig else "Não", fill=GREEN_FILL if sig else None, bold=sig)
        _cell(ws, r, 9, get(beta_name), DEC2)
        _cell(ws, r, 10, get("R²"), DEC2)
        n = get("N")
        _cell(ws, r, 11, None if n is None else int(n), "0")
        r += 1

    # fatores adicionais do NEFIN, se houver
    extra = [f for f in ["SMB", "HML", "WML", "IML"] if f in alphas.index]
    if extra:
        r += 1
        ws.cell(row=r, column=1, value="Cargas nos demais fatores (modelo NEFIN)").font = Font(name=FONT, bold=True)
        r += 1
        _header(ws, r, 1, ["Estratégia", "Carteira"] + extra)
        r += 1
        nef = alphas[alphas.modelo == "NEFIN 5F"]
        for (strat, port), sub in nef.groupby(["estrategia", "carteira"], sort=False):
            _cell(ws, r, 1, strat, bold=True)
            _cell(ws, r, 2, lab.get(port, port), align="left")
            for j, f in enumerate(extra):
                _cell(ws, r, 3 + j, sub.loc[f, "coef"], DEC2)
            r += 1

    c = ws.cell(row=r + 1, column=1,
                value="Alfa: retorno não explicado pelos fatores de risco. Alfa positivo e significativo "
                      "indica ganho que o mercado (ou os fatores NEFIN) não explica.")
    c.font = Font(name=FONT, size=9, color="404040")
    _widths(ws, {"A": 13, "B": 26, "C": 11, "D": 11, "E": 12, "F": 10, "G": 11, "H": 13,
                 "I": 11, "J": 8, "K": 8})
    ws.freeze_panes = "A5"


def _estrategia(wb, name: str, rets: pd.DataFrame, n_groups: int):
    ws = wb.create_sheet(name.replace("_", " "))
    _title(ws, f"{name.replace('_', ' ')} — retornos mensais e evolução",
           "Retornos líquidos de custos · Patrimônio: valor de R$ 1 investido no início")
    lab = _labels(n_groups)
    ports = list(rets.columns)
    nice = [lab.get(p, p) for p in ports]
    n_cols = len(ports)

    # gráficos no topo; tabelas começam na linha T0
    T0 = 40
    # bloco 1: retornos | bloco 2: patrimônio | bloco 3: drawdown
    c_ret, c_cum, c_dd = 2, 2 + n_cols + 1, 2 + 2 * (n_cols + 1)
    t = ws.cell(row=T0 - 2, column=1, value="Dados mensais")
    t.font = Font(name=FONT, size=12, bold=True, color=NAVY)
    for start, title in [(c_ret, "Retorno mensal"), (c_cum, "Patrimônio acumulado (R$)"),
                         (c_dd, "Drawdown")]:
        ws.merge_cells(start_row=T0, end_row=T0, start_column=start, end_column=start + n_cols - 1)
        c = ws.cell(row=T0, column=start, value=title)
        c.font = Font(name=FONT, bold=True, color=NAVY)
        c.alignment = Alignment(horizontal="center")
        c.fill = PatternFill("solid", fgColor=LIGHT)
    _header(ws, T0 + 1, 1, ["Mês"])
    for start in (c_ret, c_cum, c_dd):
        _header(ws, T0 + 1, start, nice)

    cum = (1 + rets).cumprod()
    dd = cum / cum.cummax() - 1
    for i, (date, row) in enumerate(rets.iterrows()):
        r = T0 + 2 + i
        c = ws.cell(row=r, column=1, value=date.to_pydatetime())
        c.number_format = "mmm/yyyy"
        c.font = Font(name=FONT)
        for j, p in enumerate(ports):
            for start, val, fmt in [(c_ret, row[p], PCT), (c_cum, cum.iloc[i][p], "0.00"),
                                    (c_dd, dd.iloc[i][p], PCT)]:
                x = ws.cell(row=r, column=start + j, value=float(val))
                x.number_format = fmt
                x.font = Font(name=FONT, size=9)
    last = T0 + 1 + len(rets)
    H, D = T0 + 1, T0 + 2  # linha do cabeçalho e primeira linha de dados

    # retornos negativos em vermelho
    rng = f"{get_column_letter(c_ret)}{D}:{get_column_letter(c_ret + n_cols - 1)}{last}"
    ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"],
                                                  font=Font(color="C00000")))

    # gráficos nativos do Excel (ao lado das tabelas)
    show = [p for p in ports if p not in ("Long-Short",)]
    chart = LineChart()
    chart.title = "Patrimônio acumulado (R$ 1 investido, escala log)"
    chart.y_axis.title = "R$"
    chart.y_axis.scaling.logBase = 10
    chart.height, chart.width = 9, 20
    for p in show:
        j = ports.index(p)
        ref = Reference(ws, min_col=c_cum + j, min_row=H, max_row=last)
        chart.add_data(ref, titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=D, max_row=last))
    _date_axis(chart)
    for s in chart.series:
        s.smooth = False
        s.graphicalProperties.line.width = 20000
    ws.add_chart(chart, "B4")

    top = f"G{n_groups}"
    ch2 = LineChart()
    ch2.title = "Drawdown: melhor grupo vs Ibovespa"
    ch2.height, ch2.width = 7, 20
    ch2.y_axis.number_format = "0%"
    for p in [top, "Ibovespa"]:
        if p in ports:
            j = ports.index(p)
            ch2.add_data(Reference(ws, min_col=c_dd + j, min_row=H, max_row=last), titles_from_data=True)
    ch2.set_categories(Reference(ws, min_col=1, min_row=D, max_row=last))
    _date_axis(ch2, label_low=True)  # datas embaixo do gráfico, não na linha do zero
    for s in ch2.series:
        s.smooth = False
    ws.add_chart(ch2, "B23")

    ch3 = LineChart()
    ch3.title = "Long-Short acumulado (prêmio do fator)"
    ch3.height, ch3.width = 9, 17
    j = ports.index("Long-Short")
    ch3.add_data(Reference(ws, min_col=c_cum + j, min_row=H, max_row=last), titles_from_data=True)
    ch3.set_categories(Reference(ws, min_col=1, min_row=D, max_row=last))
    _date_axis(ch3)
    ch3.series[0].smooth = False
    ch3.legend = None
    ws.add_chart(ch3, "M4")

    ws.column_dimensions["A"].width = 10
    for col in range(2, c_dd + n_cols):
        ws.column_dimensions[get_column_letter(col)].width = 11
    for col in (c_cum - 1, c_dd - 1):
        ws.column_dimensions[get_column_letter(col)].width = 2


def _parametros(wb, params: dict):
    ws = wb.create_sheet("Parâmetros")
    _title(ws, "Parâmetros do backtest", "Definidos em config.py")
    _header(ws, 4, 1, ["Parâmetro", "Valor"])
    for i, (k, v) in enumerate(params.items()):
        _cell(ws, 5 + i, 1, k, align="left", bold=True)
        _cell(ws, 5 + i, 2, v, align="left").alignment = Alignment(wrap_text=True, vertical="center")
    _widths(ws, {"A": 36, "B": 90})


def _como_ler(wb):
    ws = wb.create_sheet("Como ler")
    _title(ws, "Como ler os resultados")
    rows = [
        ("Grupos (G1, G2, G3)", "No fim de cada mês, as ações elegíveis são ordenadas pelo sinal do fator e "
                                "divididas em grupos de mesmo tamanho. G1 tem o pior sinal e o último grupo, o melhor. "
                                "Cada grupo é uma carteira igualmente ponderada, mantida no mês seguinte."),
        ("Long-Short", "Compra o melhor grupo e vende o pior. Isola o prêmio do fator, sem exposição ao mercado como um todo."),
        ("Retorno a.a.", "Retorno anual composto (CAGR) no período, já descontados os custos de transação."),
        ("Volatilidade a.a.", "Desvio-padrão dos retornos mensais × √12."),
        ("Sharpe", "(Retorno médio − CDI) ÷ desvio-padrão, anualizado. Acima de 0,5 costuma ser considerado bom para ações."),
        ("Estatística t", "Testa se o excesso de retorno médio é diferente de zero. |t| > 1,96 indica significância a 5%."),
        ("Drawdown máximo", "Maior queda, do pico ao vale, do patrimônio acumulado."),
        ("Giro mensal médio", "Fração da carteira trocada a cada rebalanceamento. Giro alto implica custos altos."),
        ("Alfa", "Intercepto da regressão do excesso de retorno nos fatores de risco: o retorno que os fatores não explicam."),
        ("Beta de mercado", "Sensibilidade da carteira ao Ibovespa. Beta 1 acompanha o mercado; abaixo de 1, oscila menos."),
        ("Newey-West", "Correção dos erros-padrão para autocorrelação e heterocedasticidade dos retornos."),
        ("Limitação principal", "O universo usa empresas listadas hoje (viés de sobrevivência), o que tende a inflar os retornos."),
    ]
    _header(ws, 3, 1, ["Termo", "Significado"])
    for i, (k, v) in enumerate(rows):
        _cell(ws, 4 + i, 1, k, bold=True, align="left")
        c = _cell(ws, 4 + i, 2, v, align="left")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[4 + i].height = 32
    _widths(ws, {"A": 22, "B": 100})


def export_excel(path: str, summary: pd.DataFrame, alphas: pd.DataFrame,
                 rets_by_strategy: dict[str, pd.DataFrame], params: dict, n_groups: int):
    any_rets = next(iter(rets_by_strategy.values()))
    period = f"{any_rets.index.min():%m/%Y} a {any_rets.index.max():%m/%Y}"
    wb = Workbook()
    _resumo(wb, summary, period, n_groups)
    _alfas(wb, alphas, n_groups)
    for name, rets in rets_by_strategy.items():
        _estrategia(wb, name, rets, n_groups)
    _parametros(wb, params)
    _como_ler(wb)
    wb.save(path)
