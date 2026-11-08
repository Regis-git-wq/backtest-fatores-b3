# Backtest de Estratégias Fatoriais na B3

[![Rodar backtest](https://github.com/Regis-git-wq/backtest-fatores-b3/actions/workflows/backtest.yml/badge.svg)](https://github.com/Regis-git-wq/backtest-fatores-b3/actions/workflows/backtest.yml)
[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Regis-git-wq/backtest-fatores-b3/blob/main/rodar_no_colab.ipynb)

Este projeto testa se estratégias de **momentum** e **baixa volatilidade** geraram retorno acima do mercado brasileiro de 2011 a 2025, com custos de transação, testes de significância e regressões de alfa.

> **Status:** v1, com fatores de preço. Em desenvolvimento: fatores de valor e qualidade com dados da CVM.

## Pergunta de pesquisa

Fatores documentados na literatura internacional (Jegadeesh & Titman, 1993; Ang et al., 2006; Frazzini & Pedersen, 2014) geram prêmio no mercado acionário brasileiro depois dos custos de transação?

## Resultados

Fev/2011 a dez/2025 (179 meses), retornos mensais líquidos de custos. As carteiras são tercis igualmente ponderados.

| Carteira | Retorno a.a. | Volatilidade a.a. | Sharpe | Drawdown máx. |
|---|---:|---:|---:|---:|
| Momentum: melhor tercil | 16,7% | 21,0% | 0,41 | −41,3% |
| Momentum: pior tercil | 4,2% | 28,7% | −0,04 | −67,6% |
| Baixa vol.: tercil menos volátil | 14,8% | 16,9% | 0,36 | −30,7% |
| Baixa vol.: tercil mais volátil | 5,6% | 32,8% | 0,05 | −66,7% |
| Universo (pesos iguais) | 11,9% | 22,0% | 0,20 | −36,5% |
| CDI | 9,7% | — | — | — |

**Alfas (CAPM, mercado = universo com pesos iguais, erros Newey-West):**

| Estratégia | Alfa a.a. do melhor tercil | t | Alfa a.a. long-short | t |
|---|---:|---:|---:|---:|
| Momentum | 4,9% | 2,08 | 11,9% | 2,55 |
| Baixa volatilidade | 3,0% | 1,64 | 7,9% | 1,94 |
| Combinado | 3,5% | 2,05 | 9,7% | 2,35 |

**Leitura:**
- **Momentum** tem o resultado mais forte. O long-short (compra o melhor tercil e vende o pior) rende alfa de cerca de 12% a.a., significativo a 5%.
- **Baixa volatilidade** entrega retorno parecido com o do universo, mas com bem menos risco: a menor volatilidade e o menor drawdown entre todas as carteiras. O alfa fica no limite da significância (t ≈ 1,6 a 1,9).
- As carteiras long-short têm beta de mercado negativo (−0,37 no momentum e −0,73 na baixa volatilidade), porque o pior tercil é mais sensível ao mercado do que o melhor.

![Momentum](resultados/acumulado_Momentum.png)
![Baixa volatilidade](resultados/acumulado_Baixa_Vol.png)

Tabelas completas em [`resultados/`](resultados/): `metricas.csv`, `regressoes_alfa.csv` e os retornos mensais de cada estratégia.

## Metodologia

| Etapa | Escolha |
|---|---|
| Universo | 61 ações líquidas da B3 (ver `config.py`) |
| Período | 2011–2025, mensal (2010 é usado só para calcular os primeiros sinais) |
| Elegibilidade | ≥ 1 ano de histórico, volume financeiro mediano ≥ R$ 5 mi/dia, preço ≥ R$ 1 |
| Momentum 12-1 | Retorno acumulado de t-11 a t-1, pulando o mês mais recente, que costuma reverter |
| Baixa volatilidade | Volatilidade diária anualizada dos últimos 252 pregões (sinal invertido) |
| Combinado | Média dos z-scores dos dois sinais |
| Carteiras | Tercis igualmente ponderados, rebalanceamento mensal |
| Custos | 10 bps por lado sobre o giro efetivo, considerando a variação dos pesos ao longo do mês |
| Benchmark | Carteira igualmente ponderada de todas as ações elegíveis, com dividendos e os mesmos custos. O Ibovespa do Yahoo é um índice de preço, sem dividendos, e aparece só como referência |
| Taxa livre de risco | CDI (série SGS 12 do Banco Central) |
| Inferência | Alfa de CAPM e, opcionalmente, do modelo de 5 fatores do NEFIN-USP, com erros-padrão Newey-West (6 defasagens) |

O sinal é sempre calculado com informação disponível até o fim do mês *t*, e a carteira é mantida durante *t+1*.

## Validação

`tests/test_pipeline.py` faz três checagens de sanidade com um mercado simulado:

1. **Sinal aleatório:** a carteira long-short não tem retorno significativo (t ≈ 0).
2. **Sinal que vê o futuro:** o retorno sai absurdo, o que confirma que o alinhamento temporal funciona. O código só ganha dinheiro "de graça" quando recebe informação de *t+1*.
3. **Sem look-ahead:** os sinais de uma data não mudam quando os dados posteriores são apagados.

O mercado simulado (`tests/dados_sinteticos.py`) embute um efeito de momentum conhecido, e o backtest o recupera (long-short com t ≈ 2,2).

## Como rodar

**Sem instalar nada:** clique em *Open in Colab* (no topo da página) e depois em *Ambiente de execução → Executar tudo*.

**No computador:**

```bash
pip install -r requirements.txt
python -m tests.test_pipeline   # testes de sanidade
python main.py --sintetico      # pipeline completo com dados simulados
python main.py                  # dados reais (Yahoo Finance e Banco Central; cache em data/)
```

**No GitHub:** o backtest roda sozinho (GitHub Actions) a cada mudança no código, e os resultados são salvos em `resultados/`. Para rodar manualmente, vá em *Actions → Rodar backtest → Run workflow*.

Saídas geradas:
- `metricas.csv`: retorno, volatilidade, Sharpe, estatística t, drawdown e giro de cada carteira
- `regressoes_alfa.csv`: alfas e betas com estatísticas t e p-valores
- `retornos_<estratégia>.csv`: retornos mensais de todas as carteiras
- `acumulado_*.png` e `drawdown_*.png`: gráficos
- `retornos_suspeitos.csv`: retornos diários acima de ±50%, para auditar erros de ajuste do Yahoo

**Fatores NEFIN (opcional):** monte um CSV mensal com as colunas `date, Rm_minus_Rf, SMB, HML, WML, IML` (em decimal), a partir dos dados de nefin.com.br, e salve em `data/nefin_factors.csv`.

## Estrutura

```
config.py              parâmetros (universo, período, filtros, custos)
main.py                executa o backtest e gera tabelas e gráficos
src/dados.py           download e cache de preços, CDI e fatores NEFIN
src/fatores.py         sinais e filtro de elegibilidade
src/carteiras.py       formação das carteiras, retornos, giro e custos
src/metricas.py        métricas de desempenho e regressões
tests/                 mercado simulado e testes de sanidade
rodar_no_colab.ipynb   roda o projeto no Google Colab
```

## Limitações

- **Viés de sobrevivência:** o universo usa empresas listadas hoje, e o Yahoo não traz ações deslistadas. Isso tende a inflar os retornos absolutos. O efeito é menor nas comparações entre tercis e contra o universo, que compartilham o mesmo viés. *Correção planejada:* composição histórica do Ibovespa.
- **Qualidade dos dados do Yahoo:** há 10 retornos diários acima de ±50% ([`retornos_suspeitos.csv`](resultados/retornos_suspeitos.csv)). Parte deles é evento real, como as cisões do GPA (PCAR3) em 2021 e 2023, e parte parece erro de ajuste de proventos. Ainda não foram corrigidos.
- **Ações que deixam de negociar** no meio do mês entram com retorno zero naquele mês.
- **Universo pequeno:** tercis de cerca de 20 ações deixam os resultados sensíveis a poucas empresas.
- **Custos simplificados:** o custo é fixo em bps e não modela o impacto de mercado.

## Próximos passos

- [ ] Fatores de **valor** (book-to-market, lucro/preço) e **qualidade** (ROE, alavancagem) com demonstrações da CVM, respeitando a defasagem de divulgação
- [ ] Universo pela composição histórica do Ibovespa
- [ ] Robustez: subperíodos, ponderação por valor de mercado, quintis, custos de 0 a 50 bps
- [ ] Desempenho em ciclos de alta e queda da Selic
