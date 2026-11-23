"""Fundamentos da CVM (dados abertos) para os fatores de valor e qualidade.

Fontes (https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/):
- DFP: demonstrações anuais (balanço e DRE) e a data em que cada uma foi entregue (DT_RECEB)
- FRE: capital social, com a quantidade de ações e a data de aprovação de cada alteração
- FCA: valores mobiliários, para ligar o código de negociação (ticker) ao CNPJ

Regra de ouro (sem look-ahead): um exercício só entra no sinal do fim do mês t se já
tinha sido entregue à CVM até t. Os valores usados são os da versão mais recente do
documento (reapresentações podem introduzir um viés pequeno; ver README).
"""
from __future__ import annotations

import io
import os
import re
import zipfile

import numpy as np
import pandas as pd
import requests

BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
CACHE_DIR = "data/cvm"


# ---------------------------------------------------------------- download e leitura

def _zip(doc: str, year: int) -> zipfile.ZipFile | None:
    """Baixa (com cache) o zip anual de um documento da CVM: 'DFP', 'FRE' ou 'FCA'."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = f"{CACHE_DIR}/{doc.lower()}_{year}.zip"
    if not os.path.exists(path):
        r = requests.get(f"{BASE_URL}/{doc}/DADOS/{doc.lower()}_cia_aberta_{year}.zip", timeout=300)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return zipfile.ZipFile(path)


def _read(z: zipfile.ZipFile, name: str, usecols=None) -> pd.DataFrame:
    if name not in z.namelist():
        return pd.DataFrame()
    return pd.read_csv(z.open(name), sep=";", encoding="latin-1", dtype=str, usecols=usecols)


# ---------------------------------------------------------------- ticker -> CNPJ

def parse_unit(text: str) -> int | None:
    """Número de ações por unit a partir do texto livre da CVM
    ("1 KLBN3 + 4 KLBN4", "1 ON / 2 PN", "1 ação ordinária e 4 ações preferenciais").
    Recibos de subscrição e BDRs não contam."""
    if not isinstance(text, str) or "recibo" in text.lower():
        return None
    nums = [int(n) for n in re.findall(r"(?<![A-Z0-9])(\d+)\s*(?:a[cç][aãoõ]+e?s?\s+)?(?:ON|PN|[A-Z]{3,4}\d|ordin|prefer)",
                                         text, flags=re.IGNORECASE)]
    return sum(nums) if nums else None


def ticker_map(tickers: list[str], years=range(2018, 2026),
               overrides: dict[str, dict] | None = None) -> pd.DataFrame:
    """Liga cada ticker ao CNPJ da companhia (FCA, valores mobiliários).
    Para units, informa quantas ações cada unit representa e quando começou a ser negociada.
    `overrides` completa tickers que a FCA não traz: {ticker: {"cnpj": ..., "acoes_por_unit": ...}}."""
    frames = []
    for y in years:
        z = _zip("FCA", y)
        if z is None:
            continue
        v = _read(z, f"fca_cia_aberta_valor_mobiliario_{y}.csv")
        v["ano"] = y
        frames.append(v)
    v = pd.concat(frames)
    v = v[v["Codigo_Negociacao"].isin(tickers)].sort_values("ano")
    last = v.groupby("Codigo_Negociacao").last()
    out = pd.DataFrame({
        "ticker": last.index,
        "cnpj": last["CNPJ_Companhia"].values,
        "empresa": last["Nome_Empresarial"].values,
        "acoes_por_unit": [parse_unit(c) if "Unit" in str(t) else 1
                           for c, t in zip(last["Composicao_BDR_Unit"], last["Valor_Mobiliario"])],
        "inicio_negociacao": pd.to_datetime(last["Data_Inicio_Negociacao"], errors="coerce").values,
    })
    for t, info in (overrides or {}).items():
        if t in tickers and t not in set(out["ticker"]):
            out = pd.concat([out, pd.DataFrame([{"ticker": t, "cnpj": info["cnpj"], "empresa": info.get("empresa", t),
                                                 "acoes_por_unit": info.get("acoes_por_unit", 1),
                                                 "inicio_negociacao": pd.NaT}])])
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- demonstrações (DFP)

def _pick(df: pd.DataFrame, pattern: str, level: int | None = None) -> pd.Series:
    """Valor por (CNPJ, DT_REFER) da primeira conta cujo nome casa com o padrão."""
    m = df["DS_CONTA"].str.contains(pattern, case=False, regex=True, na=False)
    if level is not None:
        m &= df["CD_CONTA"].str.count(r"\.") == level
    sub = df[m].sort_values("CD_CONTA")
    return sub.groupby(["CNPJ_CIA", "DT_REFER"])["valor"].first()


def _pick_last(df: pd.DataFrame, pattern: str, level: int) -> pd.Series:
    m = df["DS_CONTA"].str.contains(pattern, case=False, regex=True, na=False)
    m &= df["CD_CONTA"].str.count(r"\.") == level
    sub = df[m].sort_values("CD_CONTA")
    return sub.groupby(["CNPJ_CIA", "DT_REFER"])["valor"].last()


def _statement(z: zipfile.ZipFile, kind: str, year: int, cnpjs: set[str]) -> pd.DataFrame:
    df = _read(z, f"dfp_cia_aberta_{kind}_{year}.csv",
               usecols=["CNPJ_CIA", "DT_REFER", "ESCALA_MOEDA", "ORDEM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"])
    if df.empty:
        return df
    df = df[df["CNPJ_CIA"].isin(cnpjs) & (df["ORDEM_EXERC"] == "ÚLTIMO")].copy()
    scale = np.where(df["ESCALA_MOEDA"].str.upper() == "MIL", 1000.0, 1.0)
    df["valor"] = pd.to_numeric(df["VL_CONTA"], errors="coerce") * scale
    return df


def _extract(bpa: pd.DataFrame, bpp: pd.DataFrame, dre: pd.DataFrame, consolidated: bool) -> pd.DataFrame:
    if bpa.empty or bpp.empty or dre.empty:
        return pd.DataFrame()
    ativo = bpa[bpa["CD_CONTA"] == "1"].groupby(["CNPJ_CIA", "DT_REFER"])["valor"].first()
    # o nome da conta de lucro varia ("Lucro/Prejuízo Consolidado do Período",
    # "Lucro ou Prejuízo Líquido Consolidado do Período", ...): pega a última conta de nível 1
    # que começa com "Lucro" e fala do período/exercício (exclui lucro por ação, 3.99)
    dre_lucro = dre[~dre["CD_CONTA"].str.startswith("3.99")]
    lucro_pat = r"^Lucro.*(?:Per[ií]odo|Exerc[ií]cio)"
    if consolidated:
        pl = _pick(bpp, r"^Patrim[oô]nio L[ií]quido Consolidado", 1)
        lucro_total = _pick_last(dre_lucro, lucro_pat, 1)
        lucro_ctrl = _pick(dre, r"Atribu[ií]do a S[oó]cios da (?:Empresa )?Controladora", 2)
    else:
        pl = _pick(bpp, r"^Patrim[oô]nio L[ií]quido", 1)
        lucro_total = _pick_last(dre_lucro, lucro_pat, 1)
        lucro_ctrl = pd.Series(dtype=float)
    minor = _pick(bpp, r"N[aã]o Controladores", 2)
    out = pd.DataFrame({"ativo": ativo, "pl_total": pl, "minoritarios": minor,
                        "lucro_total": lucro_total, "lucro_ctrl": lucro_ctrl})
    out["minoritarios"] = out["minoritarios"].fillna(0.0)
    out["pl_ctrl"] = out["pl_total"] - out["minoritarios"]
    # alguns emissores deixam a conta dos controladores zerada: usa o lucro total
    zero_ctrl = (out["lucro_ctrl"].fillna(0) == 0) & (out["lucro_total"].fillna(0) != 0)
    out["lucro_ctrl"] = out["lucro_ctrl"].where(~zero_ctrl).fillna(out["lucro_total"])
    out["fonte"] = "consolidada" if consolidated else "individual"
    return out


def statements(cnpjs: list[str], years=range(2010, 2026)) -> pd.DataFrame:
    """Uma linha por (CNPJ, exercício) com ativo, PL e lucro (dos controladores), em R$,
    e a data em que a primeira versão foi entregue à CVM (disponivel_em).
    Usa a demonstração consolidada; se ela faltar ou vier zerada, usa a individual."""
    cnpjs = set(cnpjs)
    rows = []
    for y in years:
        z = _zip("DFP", y)
        if z is None:
            continue
        idx = _read(z, f"dfp_cia_aberta_{y}.csv", usecols=["CNPJ_CIA", "DT_REFER", "DT_RECEB"])
        idx = idx[idx["CNPJ_CIA"].isin(cnpjs)]
        receb = idx.groupby(["CNPJ_CIA", "DT_REFER"])["DT_RECEB"].min()
        con = _extract(*(_statement(z, f"{k}_con", y, cnpjs) for k in ["BPA", "BPP", "DRE"]), consolidated=True)
        ind = _extract(*(_statement(z, f"{k}_ind", y, cnpjs) for k in ["BPA", "BPP", "DRE"]), consolidated=False)
        bad = con.index[(con["pl_total"].fillna(0) == 0) | (con["lucro_total"].fillna(0) == 0)] if not con.empty else []
        merged = pd.concat([con.drop(index=bad, errors="ignore"),
                            ind[~ind.index.isin(con.drop(index=bad, errors="ignore").index)]])
        if merged.empty:
            continue
        merged.index = pd.MultiIndex.from_tuples(merged.index, names=["CNPJ_CIA", "DT_REFER"])
        merged["disponivel_em"] = receb.reindex(merged.index).values
        rows.append(merged)
    out = pd.concat(rows).reset_index().rename(columns={"CNPJ_CIA": "cnpj", "DT_REFER": "exercicio"})
    out["exercicio"] = pd.to_datetime(out["exercicio"])
    out["disponivel_em"] = pd.to_datetime(out["disponivel_em"])
    return out.dropna(subset=["disponivel_em"]).sort_values(["cnpj", "exercicio"]).reset_index(drop=True)


# ---------------------------------------------------------------- número de ações (FRE)

def share_counts(cnpjs: list[str], years=range(2010, 2026)) -> pd.DataFrame:
    """Histórico do número total de ações (capital integralizado) por data de aprovação.
    Junta todos os FRE; para cada (CNPJ, data) fica a informação do formulário mais recente."""
    cnpjs = set(cnpjs)
    frames = []
    for y in years:
        z = _zip("FRE", y)
        if z is None:
            continue
        c = _read(z, f"fre_cia_aberta_capital_social_{y}.csv",
                  usecols=["CNPJ_Companhia", "Versao", "Tipo_Capital", "Data_Autorizacao_Aprovacao",
                           "Quantidade_Total_Acoes"])
        c = c[c["CNPJ_Companhia"].isin(cnpjs)].copy()
        c["ano_fre"] = y
        frames.append(c)
    c = pd.concat(frames)
    c["acoes"] = pd.to_numeric(c["Quantidade_Total_Acoes"], errors="coerce")
    c["data"] = pd.to_datetime(c["Data_Autorizacao_Aprovacao"], errors="coerce")
    c["versao"] = pd.to_numeric(c["Versao"], errors="coerce")
    c = c.dropna(subset=["acoes", "data"])
    c = c[c["acoes"] > 0]
    # preferência: Integralizado; se a companhia não informa, usa Emitido
    c["prio"] = c["Tipo_Capital"].map({"Capital Integralizado": 0, "Capital Emitido": 1}).fillna(9)
    c = c[c["prio"] < 9].sort_values(["CNPJ_Companhia", "data", "prio", "ano_fre", "versao"],
                                     ascending=[True, True, True, False, False])
    c = c.groupby(["CNPJ_Companhia", "data"]).first().reset_index()
    return c.rename(columns={"CNPJ_Companhia": "cnpj"})[["cnpj", "data", "acoes"]]


def align_share_changes(shares: pd.DataFrame, splits: dict[str, pd.Series], tmap: pd.DataFrame,
                        window_days: int = 270, tol: float = 0.30) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Corrige o descasamento de datas entre o FRE e o preço.

    O FRE registra um desdobramento/grupamento/bonificação na data de APROVAÇÃO; o preço só
    muda na data de EXECUÇÃO (a data do split no Yahoo). Se uma mudança no nº de ações tem a
    mesma razão de um split do Yahoo a até `window_days` dias, ela é movida para a data do split.
    A razão pode diferir em até `tol` (30%), porque às vezes o desdobramento vem junto com
    uma emissão ou um cancelamento de ações (ex.: MGLU3 em 2019, 8:1 mais emissão).
    Também remove registros isolados que são desfeitos logo depois sem split (erro de digitação:
    o nº de ações cai 10× e volta no formulário seguinte). Retorna (ações corrigidas, relatório)."""
    by_cnpj = tmap.groupby("cnpj")["ticker"].first().to_dict()
    out, log = [], []
    for cnpj, g in shares.sort_values("data").groupby("cnpj"):
        g = g[g["acoes"].ne(g["acoes"].shift())].copy().reset_index(drop=True)  # tira repetições
        sp = splits.get(by_cnpj.get(cnpj), pd.Series(dtype=float))
        sp_dates = [(pd.Timestamp(d).tz_localize(None) if pd.Timestamp(d).tzinfo else pd.Timestamp(d)).normalize()
                    for d in sp.index]
        matched = [False] * len(g)
        for i in range(1, len(g)):
            r = g.loc[i, "acoes"] / g.loc[i - 1, "acoes"]
            best = None
            if abs(np.log(r)) <= np.log(1.01):  # mudança pequena (emissão, recompra): não é split
                continue
            for d, ratio in zip(sp_dates, sp.values):
                if (abs(np.log(r / ratio)) <= np.log(1 + tol) and abs(np.log(ratio)) > np.log(1.01)
                        and abs((d - g.loc[i, "data"]).days) <= window_days):
                    if best is None or abs((d - g.loc[i, "data"]).days) < abs((best - g.loc[i, "data"]).days):
                        best = d
            if best is not None:
                matched[i] = True
                if best != g.loc[i, "data"]:
                    log.append({"cnpj": cnpj, "ticker": by_cnpj.get(cnpj), "data_fre": g.loc[i, "data"],
                                "data_split": best, "razao": r, "acao": "movida para a data do split"})
                    g.loc[i, "data"] = best
        # erro de digitação: salto grande sem split, desfeito no registro seguinte
        drop = set()
        for i in range(1, len(g) - 1):
            r1 = g.loc[i, "acoes"] / g.loc[i - 1, "acoes"]
            r2 = g.loc[i + 1, "acoes"] / g.loc[i, "acoes"]
            if (not matched[i] and not matched[i + 1] and abs(np.log(r1)) > np.log(1.5)
                    and abs(r1 * r2 - 1) <= 0.10):
                drop.add(i)
                log.append({"cnpj": cnpj, "ticker": by_cnpj.get(cnpj), "data_fre": g.loc[i, "data"],
                            "data_split": pd.NaT, "razao": r1, "acao": "removida (desfeita no registro seguinte)"})
        g = g.drop(index=list(drop))
        g["ordem"] = range(len(g))
        # duas mudanças movidas para o mesmo split: vale a mais recente no FRE
        g = g.sort_values(["data", "ordem"]).drop_duplicates("data", keep="last").drop(columns="ordem")
        out.append(g)
    report = pd.DataFrame(log, columns=["cnpj", "ticker", "data_fre", "data_split", "razao", "acao"])
    return pd.concat(out).reset_index(drop=True), report


# ---------------------------------------------------------------- valor de mercado

def split_factor(splits: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Fator que desfaz o ajuste de desdobramento do Yahoo: produto dos splits posteriores a t."""
    f = pd.Series(1.0, index=index)
    for d, ratio in splits.items():
        d = pd.Timestamp(d)
        d = (d.tz_localize(None) if d.tzinfo else d).normalize()
        if ratio and ratio > 0:
            f[f.index < d] *= ratio
    return f


def market_cap(close_monthly: pd.DataFrame, splits: dict[str, pd.Series], tmap: pd.DataFrame,
               shares: pd.DataFrame) -> pd.DataFrame:
    """Valor de mercado no fim de cada mês: preço sem ajuste de desdobramento × nº de ações.
    Para units, o preço por ação é o preço da unit ÷ ações por unit (a partir do início da unit)."""
    out = pd.DataFrame(index=close_monthly.index, columns=close_monthly.columns, dtype=float)
    for _, row in tmap.iterrows():
        t = row["ticker"]
        if t not in close_monthly:
            continue
        raw = close_monthly[t] * split_factor(splits.get(t, pd.Series(dtype=float)), close_monthly.index)
        per_unit = row["acoes_por_unit"]
        if per_unit and per_unit > 1:
            # Se o Yahoo registra um "split" com a mesma razão da unit, a série antes dele é de
            # uma ação isolada (ex.: KLBN11 antes de 2014): divide só a partir dessa data.
            sp = splits.get(t, pd.Series(dtype=float))
            creation = [pd.Timestamp(d).tz_localize(None).normalize() if pd.Timestamp(d).tzinfo
                        else pd.Timestamp(d).normalize()
                        for d, r in sp.items() if abs(r / per_unit - 1) <= 0.01]
            is_unit = close_monthly.index >= min(creation) if creation else np.ones(len(raw), bool)
            raw = raw.where(~is_unit, raw / per_unit)
        sh = shares[shares["cnpj"] == row["cnpj"]].set_index("data")["acoes"].sort_index()
        if sh.empty:
            continue
        n = sh.reindex(sh.index.union(close_monthly.index)).ffill().reindex(close_monthly.index)
        out[t] = raw * n
    return out


def drop_inconsistent_segments(mcap: pd.DataFrame, close_monthly: pd.DataFrame, jump: float = 2.0,
                               max_months: int = 24, tol: float = 0.25,
                               extreme: float = 4.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarta trechos de valor de mercado que não são confiáveis, em vez de dar um palpite.

    1. Salto implausível seguido de salto inverso (o nível volta): o trecho entre os dois
       está errado (nº de ações e preço em bases diferentes).
    2. Salto extremo (≥ `extreme` vezes) sem volta: na conferência com os dados reais, o
       trecho ANTERIOR era o errado (ex.: SANB11 antes de 2014, RAIL3 antes de ago/2015).
    Saltos moderados sem volta (fusões, aumentos de capital) são mantidos."""
    out = mcap.copy()
    log = []
    rel = (mcap / mcap.shift(1)) / (close_monthly / close_monthly.shift(1))
    for t in mcap.columns:
        r = rel[t]
        jumps = r[(r > jump) | (r < 1 / jump)]
        used = set()
        dates = list(jumps.index)
        for i, d1 in enumerate(dates):
            if d1 in used:
                continue
            for d2 in dates[i + 1:]:
                months = (d2.year - d1.year) * 12 + d2.month - d1.month
                if months > max_months:
                    break
                if d2 not in used and abs(np.log(jumps[d1] * jumps[d2])) <= np.log(1 + tol):
                    seg = (out.index >= d1) & (out.index < d2)
                    out.loc[seg, t] = np.nan
                    used.update([d1, d2])
                    log.append({"ticker": t, "inicio": d1, "fim": d2, "meses_descartados": int(seg.sum()),
                                "motivo": "salto que volta"})
                    break
        extremes = [d for d in dates if d not in used and abs(np.log(jumps[d])) >= np.log(extreme) - 1e-9]
        if extremes:
            d = max(extremes)
            seg = out.index < d
            out.loc[seg, t] = np.nan
            log.append({"ticker": t, "inicio": out.index[0], "fim": d, "meses_descartados": int(seg.sum()),
                        "motivo": "salto extremo sem volta"})
    return out, pd.DataFrame(log, columns=["ticker", "inicio", "fim", "meses_descartados", "motivo"])


def implausible_caps(mcap: pd.DataFrame, close_monthly: pd.DataFrame, jump: float = 2.0) -> pd.DataFrame:
    """Meses em que o valor de mercado muda mais de `jump` vezes sem o preço ajustado
    acompanhar: sinal de nº de ações ou desdobramento errado. Só para auditoria."""
    ratio = mcap / mcap.shift(1)
    price = close_monthly / close_monthly.shift(1)
    rel = (ratio / price).stack()
    bad = rel[(rel > jump) | (rel < 1 / jump)]
    return bad.rename("salto_relativo").reset_index().rename(columns={"level_0": "mes", "level_1": "ticker"})


# ---------------------------------------------------------------- sinais

def point_in_time(fund: pd.DataFrame, tmap: pd.DataFrame, months: pd.DatetimeIndex,
                  max_age_months: int = 18) -> dict[str, pd.DataFrame]:
    """Para cada fim de mês, o último exercício já entregue à CVM (e não velho demais).
    Retorna um DataFrame (meses × tickers) por variável."""
    cols = ["ativo", "pl_total", "pl_ctrl", "lucro_ctrl"]
    out = {c: pd.DataFrame(index=months, columns=tmap["ticker"], dtype=float) for c in cols}
    for _, row in tmap.iterrows():
        f = fund[fund["cnpj"] == row["cnpj"]].sort_values(["disponivel_em", "exercicio"])
        if f.empty:
            continue
        for m in months:
            known = f[f["disponivel_em"] <= m]
            if known.empty:
                continue
            last = known.sort_values("exercicio").iloc[-1]
            if (m - last["exercicio"]).days > max_age_months * 30.5:
                continue
            for c in cols:
                out[c].loc[m, row["ticker"]] = last[c]
    return out


def _z(df: pd.DataFrame) -> pd.DataFrame:
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1), axis=0)


def signals(pit: dict[str, pd.DataFrame], mcap: pd.DataFrame, financials: list[str]) -> dict[str, pd.DataFrame]:
    """Sinais orientados para que valor maior = mais atrativo.
    - Valor: média dos z-scores de B/M (PL ÷ valor de mercado) e E/P (lucro ÷ valor de mercado)
    - Qualidade: média dos z-scores de ROE e de baixa alavancagem (1 − PL/ativo);
      alavancagem não vale para bancos e seguradoras, que usam só o ROE."""
    mcap = mcap.reindex_like(pit["pl_ctrl"])
    pl = pit["pl_ctrl"].where(pit["pl_ctrl"] > 0)
    bm = pl / mcap
    ep = pit["lucro_ctrl"] / mcap
    roe = pit["lucro_ctrl"] / pl
    lev = 1 - pit["pl_total"] / pit["ativo"]
    lev[[c for c in lev.columns if c in financials]] = np.nan
    # winsoriza para que poucos valores extremos não dominem o z-score
    clip = lambda d: d.clip(d.quantile(0.02, axis=1), d.quantile(0.98, axis=1), axis=0)
    value = pd.concat([_z(clip(bm)), _z(clip(ep))]).groupby(level=0).mean()
    both_value = bm.notna() & ep.notna()
    quality = pd.concat([_z(clip(roe)), _z(clip(-lev))]).groupby(level=0).mean()
    has_roe = roe.notna()
    return {
        "Valor": value.where(both_value).reindex(pit["pl_ctrl"].index),
        "Qualidade": quality.where(has_roe).reindex(pit["pl_ctrl"].index),
        "_bm": bm, "_ep": ep, "_roe": roe, "_lev": lev,
    }


def coverage(sig: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Quantas ações têm cada sinal, em dezembro de cada ano (para auditoria)."""
    dec = {k: v[v.index.month == 12].notna().sum(axis=1) for k, v in sig.items()}
    out = pd.DataFrame(dec)
    out.index = out.index.year
    return out
