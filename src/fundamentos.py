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


def ticker_map(tickers: list[str], years=range(2018, 2026)) -> pd.DataFrame:
    """Liga cada ticker ao CNPJ da companhia (FCA, valores mobiliários).
    Para units, informa quantas ações cada unit representa e quando começou a ser negociada."""
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
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- demonstrações (DFP)

def _pick(df: pd.DataFrame, pattern: str, level: int | None = None) -> pd.Series:
    """Valor por (CNPJ, DT_REFER) da primeira conta cujo nome casa com o padrão."""
    m = df["DS_CONTA"].str.contains(pattern, case=False, regex=True, na=False)
    if level is not None:
        m &= df["CD_CONTA"].str.count(r"\.") == level
    sub = df[m].sort_values("CD_CONTA")
    return sub.groupby(["CNPJ_CIA", "DT_REFER"])["valor"].first()


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
    if consolidated:
        pl = _pick(bpp, r"^Patrim[oô]nio L[ií]quido Consolidado", 1)
        lucro_total = _pick(dre, r"^Lucro/Preju[ií]zo Consolidado do Per[ií]odo", 1)
        lucro_ctrl = _pick(dre, r"Atribu[ií]do a S[oó]cios da Empresa Controladora", 2)
    else:
        pl = _pick(bpp, r"^Patrim[oô]nio L[ií]quido", 1)
        lucro_total = _pick(dre, r"^Lucro/Preju[ií]zo do Per[ií]odo", 1)
        lucro_ctrl = pd.Series(dtype=float)
    minor = _pick(bpp, r"N[aã]o Controladores", 2)
    out = pd.DataFrame({"ativo": ativo, "pl_total": pl, "minoritarios": minor,
                        "lucro_total": lucro_total, "lucro_ctrl": lucro_ctrl})
    out["minoritarios"] = out["minoritarios"].fillna(0.0)
    out["pl_ctrl"] = out["pl_total"] - out["minoritarios"]
    out["lucro_ctrl"] = out["lucro_ctrl"].fillna(out["lucro_total"])
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
        merged["disponivel_em"] = receb.reindex(merged.index)
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
            start = row["inicio_negociacao"]
            is_unit = close_monthly.index >= start if pd.notna(start) else np.ones(len(raw), bool)
            raw = raw.where(~is_unit, raw / per_unit)
        sh = shares[shares["cnpj"] == row["cnpj"]].set_index("data")["acoes"].sort_index()
        if sh.empty:
            continue
        n = sh.reindex(sh.index.union(close_monthly.index)).ffill().reindex(close_monthly.index)
        out[t] = raw * n
    return out


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
