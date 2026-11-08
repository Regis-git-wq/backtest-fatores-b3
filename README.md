# Backtest de Estratégias Fatoriais na B3

Este projeto testa se estratégias de **momentum** e **baixa volatilidade** geraram retorno acima do mercado brasileiro, com custos de transação, testes de significância e regressões de alfa.

[![Rodar backtest](https://github.com/Regis-git-wq/backtest-fatores-b3/actions/workflows/backtest.yml/badge.svg)](https://github.com/Regis-git-wq/backtest-fatores-b3/actions/workflows/backtest.yml)
[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Regis-git-wq/backtest-fatores-b3/blob/main/rodar_no_colab.ipynb)

**📊 Resultados mais recentes:** [`resultados/resultados_backtest.xlsx`](resultados/resultados_backtest.xlsx), atualizados automaticamente todo mês pelo GitHub Actions.

> Status: v1, com fatores de preço (momentum e baixa volatilidade). Em desenvolvimento: fatores fundamentalistas (valor e qualidade) com dados da CVM.

## Pergunta de pesquisa

Fatores documentados na literatura internacional (Jegadeesh & Titman, 1993; Ang et al., 2006; Frazzini & Pedersen, 2014) geram prêmio de risco ou alfa no mercado acionário brasileiro depois dos custos de transação?

## Metodologia

| Etapa | Escolha |
|---|---|
| Universo | Cerca de 60 ações líquidas da B3 (ver `config.py`) |
| Período | 2011–2025, mensal (2010 é usado só para calcular os sinais) |
| Elegibilidade | ≥ 1 ano de histórico, volume financeiro mediano ≥ R$ 5 mi/dia, preço ≥ R$ 1 |
| Momentum 12-1 | Retorno acumulado de t-12 a t-1, sem o último mês (que costuma reverter) |
| Baixa volatilidade | Volatilidade diária anualizada dos últimos 252 pregões (sinal invertido) |
| Combinado | Média dos z-scores dos dois sinais |
| Carteiras | Tercis igualmente ponderados, rebalanceamento mensal |
| Custos | 10 bps por lado sobre o giro efetivo, já considerando a variação dos pesos ao longo do mês |
| Taxa livre de risco | CDI (série SGS 12 do Banco Central) |
| Benchmark | Ibovespa |
| Inferência | Alfa de CAPM e, opcionalmente, do modelo de 5 fatores do NEFIN-USP, com erros-padrão Newey-West (6 defasagens) |

O sinal é sempre calculado com informação disponível até o fim do mês *t*, e a carteira é mantida durante *t+1*.

## Validação

`tests/test_pipeline.py` faz três checagens de sanidade com um mercado simulado:

1. **Sinal aleatório** → long-short sem retorno significativo (t ≈ 0).
2. **Sinal que vê o futuro** → retorno absurdo. Isso confirma que o alinhamento temporal funciona: o código só ganha dinheiro quando recebe informação de *t+1*.
3. **Sem look-ahead** → os sinais de uma data não mudam quando os dados posteriores são apagados.

O mercado simulado (`tests/dados_sinteticos.py`) embute um efeito de momentum conhecido, e o backtest o recupera (long-short com t ≈ 2,2).

## Como rodar

**Sem instalar nada:** clique no botão *Open in Colab* acima e depois em *Ambiente de execução → Executar tudo*.

**No computador:**

```bash
pip install -r requirements.txt
python -m tests.test_pipeline   # testes de sanidade
python main.py --sintetico      # pipeline completo com dados simulados
python main.py                  # dados reais (baixa do Yahoo Finance e do BCB; fica em cache em data/)
```

Os resultados vão para `results/`:
- **`resultados_backtest.xlsx`: planilha formatada, pronta para abrir — resumo com destaques de cor, alfas, uma aba por estratégia com gráficos e dados mensais, parâmetros e um glossário**
- `metricas.csv`: retorno, volatilidade, Sharpe, estatística t, drawdown máximo e giro de cada carteira
- `regressoes_alfa.csv`: alfas e betas com estatísticas t
- `acumulado_*.png` e `drawdown_*.png`: gráficos
- `retornos_suspeitos.csv`: retornos diários acima de ±50%, para auditar erros de ajuste do Yahoo

**Fatores NEFIN (opcional):** baixe os fatores diários ou mensais em nefin.com.br, monte um CSV com as colunas `date, Rm_minus_Rf, SMB, HML, WML, IML` (mensal, em decimal) e salve em `data/nefin_factors.csv`.

## Estrutura

```
config.py              parâmetros (universo, período, filtros, custos)
main.py                executa o backtest e gera tabelas e gráficos
src/dados.py           download e cache de preços, CDI e fatores NEFIN
src/fatores.py         sinais e filtro de elegibilidade
src/carteiras.py       formação das carteiras, retornos, giro e custos
src/metricas.py        métricas de desempenho e regressões
src/excel.py           exporta os resultados para Excel formatado
tests/                 mercado simulado e testes de sanidade
```

## Limitações (e como pretendo tratá-las)

- **Viés de sobrevivência:** o universo usa empresas listadas hoje, e o Yahoo não traz ações deslistadas. Isso tende a inflar os retornos. *Correção planejada:* usar a composição histórica do Ibovespa (carteiras quadrimestrais da B3).
- **Qualidade dos dados do Yahoo:** ajustes de proventos e desdobramentos às vezes têm erros. O código marca retornos diários extremos para conferência manual.
- **Universo pequeno:** tercis com cerca de 20 ações deixam as carteiras pouco diversificadas e os resultados sensíveis a poucas empresas.
- **Custos simplificados:** o custo é fixo em bps e não modela o impacto de mercado nem a liquidez de cada ação.

## Próximos passos

- [ ] Fatores **valor** (book-to-market, lucro/preço) e **qualidade** (ROE, alavancagem) com demonstrações da CVM, respeitando a defasagem de divulgação
- [ ] Universo pela composição histórica do Ibovespa
- [ ] Análise de robustez: subperíodos, ponderação por valor de mercado, quintis vs tercis, custos de 0 a 50 bps
- [ ] Desempenho em ciclos de alta e queda da Selic
- [ ] Relatório final em PDF com as conclusões
