# pandas para reler o xlsx escrito.
import pandas as pd
# A orquestração pura e a escrita de saída sob teste.
from robusta.run_mma import build_summary, write_outputs


# Teste e2e (sem rede): df sintético → (analysis, summary) coerentes.
def test_build_summary_end_to_end(synthetic_prices):
    """
    Por quê: provar que as peças se conectam ponta a ponta (rótulo → dummy → fit →
    summary) e que as DUAS saídas saem corretas, sem tocar a rede.

    Lógica: Entrada (preços sintéticos) → Fase 1 build_summary → Fase 2 summary
    → Fase 3 analysis → Saída.
    """
    # Fase 1: roda o pipeline com um grid pequeno.
    analysis, summary = build_summary(
        synthetic_prices, windows=[5, 20], tols=[0.0], horizons=[10, 20], min_events=1
    )
    # Fase 2: 2 janelas × 1 tol × 2 horizontes × 2 famílias = 8 linhas de modelo.
    assert len(summary) == 8
    # Fase 2: schema essencial do summary presente (com family e r2 unificado).
    assert {"indicator", "window", "tol", "horizon", "family", "r2", "status"} <= set(summary.columns)
    assert set(summary["family"]) == {"logit", "ols"}
    assert (summary["indicator"] == "mma").all()
    # Fase 3: analysis é por-dia, com rótulos e retorno acumulados.
    assert "y_10d" in analysis.columns and "ret_10d" in analysis.columns
    # Saída: uma linha por dia (mesmo tamanho da entrada).
    assert len(analysis) == len(synthetic_prices)


# Lacuna TESTES.md #41 (MÉDIA): build_summary não muta o df prices de entrada.
def test_build_summary_does_not_mutate_prices(synthetic_prices):
    """
    Por quê: o chamador (ou um teste seguinte) pode reusar `prices`; o pipeline não
    pode enfiar colunas de rótulo/indicador no df original.

    Lógica: Entrada (prices só-OHLCV) → Fase 1 build_summary → Fase 2 original intacto.
    """
    # Entrada: snapshot das colunas originais.
    cols_antes = list(synthetic_prices.columns)
    # Fase 1: roda o pipeline (descarta as saídas).
    build_summary(synthetic_prices, windows=[5], tols=[0.0], horizons=[10], min_events=1)
    # Fase 2/Saída: o df original continua exatamente OHLCV.
    assert list(synthetic_prices.columns) == cols_antes


# Lacuna TESTES.md #42 (MÉDIA): min_events alto → todos os modelos viram sem_eventos.
def test_build_summary_min_events_degrades(synthetic_prices):
    """
    Por quê: provar que o parâmetro min_events é repassado até os fits através de
    build_summary → run_sweep → fit_*.

    Lógica: Entrada (preços) → Fase 1 build_summary com min_events impossível → Saída.
    """
    # Fase 1: min_events impossível para qualquer fatia da série.
    _, summary = build_summary(
        synthetic_prices, windows=[20], tols=[0.0], horizons=[10], min_events=10_000
    )
    # Saída: todos os modelos degradam para sem_eventos.
    assert (summary["status"] == "sem_eventos").all()


# Correção: a exportação é em .xlsx. Testa a escrita sem rede (em tmp_path).
def test_write_outputs_writes_readable_xlsx(synthetic_prices, tmp_path):
    """
    Por quê: a saída precisa ser .xlsx (não .csv); este teste prova que os dois
    arquivos são gravados na pasta e podem ser relidos pelo pandas (engine openpyxl),
    sem tocar a rede.

    Lógica: Entrada (build_summary sintético) → Fase 1 write_outputs → Fase 2 arquivos
    existem → Fase 3 relê o summary → Saída.
    """
    # Entrada: gera as duas saídas a partir de preços sintéticos.
    analysis, summary = build_summary(
        synthetic_prices, windows=[5, 20], tols=[0.0], horizons=[10], min_events=1
    )
    # Fase 1: escreve na pasta temporária do teste.
    analysis_path, summary_path = write_outputs(analysis, summary, outdir=tmp_path)
    # Fase 2: ambos os arquivos .xlsx existem com os nomes corretos.
    assert analysis_path.name == "analysis_mma.xlsx" and analysis_path.exists()
    assert summary_path.name == "summary_mma.xlsx" and summary_path.exists()
    # Fase 3: o summary relido bate em nº de linhas e tem a coluna family.
    back = pd.read_excel(summary_path)
    # Saída: roundtrip íntegro.
    assert len(back) == len(summary) and "family" in back.columns
