"""Parâmetros do backtest. Altere aqui em vez de mexer no código."""

# Período de análise (os primeiros 12 meses servem só para calcular sinais)
START_DATE = "2010-01-01"
END_DATE = "2025-12-31"

# Universo: ações líquidas da B3 (sufixo .SA é adicionado no download).
# ATENÇÃO: lista de empresas que existem hoje -> há viés de sobrevivência.
# Ver README ("Limitações") para como corrigir com a composição histórica do Ibovespa.
TICKERS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "ABEV3", "B3SA3", "WEGE3",
    "RENT3", "SUZB3", "ITSA4", "BPAC11", "PRIO3", "RADL3", "EQTL3", "LREN3",
    "GGBR4", "GOAU4", "CSNA3", "USIM5", "CMIG4", "SBSP3", "KLBN11", "TOTS3",
    "VIVT3", "TIMS3", "CSAN3", "UGPA3", "HYPE3", "MULT3", "CYRE3", "MRVE3",
    "EZTC3", "BRAP4", "CPFE3", "ENGI11", "TAEE11", "EGIE3", "SANB11", "BBSE3",
    "PSSA3", "MGLU3", "RAIL3", "SLCE3", "SMTO3", "FLRY3", "ALPA4",
    "YDUQ3", "COGN3", "MDIA3", "GRND3", "DXCO3", "BEEF3", "ENEV3", "ALOS3",
    "PCAR3", "CVCB3", "POSI3", "ECOR3", "SAPR11", "LIGT3",
]
# Removidas por não terem dados no Yahoo Finance: ODPV3, STBP3, TRPL4.

# Ibovespa do Yahoo: índice de PREÇO (sem dividendos). Usado só como referência;
# o benchmark principal é a carteira igualmente ponderada do próprio universo.
BENCHMARK = "^BVSP"

# Filtros de elegibilidade (aplicados no fim de cada mês de formação)
MIN_HISTORY_DAYS = 252          # pelo menos 1 ano de preços
MIN_MEDIAN_VOLUME_BRL = 5e6     # volume financeiro mediano diário (últimos 63 pregões)
MIN_PRICE_BRL = 1.0             # evita "penny stocks"

# Montagem das carteiras
N_GROUPS = 3                    # tercis (universo pequeno -> tercis, não quintis)
TRANSACTION_COST_BPS = 10       # custo por lado sobre o giro (0,10%)

# Janelas dos sinais
MOM_LOOKBACK = 12               # momentum 12-1: retorno de t-12 até t-1
MOM_SKIP = 1
VOL_WINDOW_DAYS = 252           # baixa volatilidade: desvio-padrão diário em 1 ano

# Regressões
NEWEY_WEST_LAGS = 6

# Arquivo opcional com fatores do NEFIN-USP (ver README)
NEFIN_FILE = "data/nefin_factors.csv"

# Análises de robustez
SUBPERIODS = [("2011", "2015"), ("2016", "2020"), ("2021", "2025")]
COST_GRID_BPS = [0, 25, 50]      # além do custo-base acima
ALT_N_GROUPS = 5                 # quintis, como alternativa aos tercis

# Limpeza de dados (retornos diários acima de ±50% no preço ajustado do Yahoo)
CLEAN_THRESHOLD = 0.5
CLEAN_REVERT_WINDOW = 5         # pregões para o preço voltar ao nível anterior (pico)
CLEAN_REVERT_TOL = 0.25         # "perto do nível anterior" = dentro de ±25%
# Eventos reais a manter sem correção: lista de (ticker, "AAAA-MM-DD"). Vazia por padrão.
CLEAN_KEEP = []

# Fundamentos (CVM): fatores de valor e qualidade
USE_FUNDAMENTALS = True
FUND_YEARS = range(2010, 2026)       # anos de DFP e FRE a baixar
FUND_MAX_AGE_MONTHS = 18             # exercício mais velho que isso não entra no sinal
# Bancos e seguradoras: alavancagem não faz sentido; a qualidade usa só o ROE
FINANCIALS = ["ITUB4", "BBDC4", "BBAS3", "SANB11", "BPAC11", "BBSE3", "PSSA3"]
# Tickers que a FCA da CVM não liga a um CNPJ (conferidos manualmente)
CNPJ_OVERRIDES = {
    "CSNA3": {"cnpj": "33.042.730/0001-04", "empresa": "CIA SIDERURGICA NACIONAL"},
    "BPAC11": {"cnpj": "30.306.294/0001-45", "empresa": "BCO BTG PACTUAL S.A.", "acoes_por_unit": 3},
}
