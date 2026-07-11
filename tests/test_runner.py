# pandas para reler o xlsx e checar colunas.
import pandas as pd
# As peças genéricas sob teste.
from robusta.runner import build_summary, write_outputs, summary_dictionary
# O mma serve de indicador-cobaia (já existe e é conhecido).
from robusta.indicators import mma


# Teste: build_summary genérico roda qualquer módulo via injeção.
def test_generic_build_summary_runs_any_indicator(synthetic_prices):
    """
    Por quê: provar que o runner é agnóstico ao indicador — recebe o MÓDULO e um
    grid arbitrário e devolve (analysis, summary) coerentes, sem conhecer o mma.

    Lógica: Entrada (preços + módulo mma + grid) → Fase 1 build_summary → Fase 2
    contagem/schema → Saída.
    """
    # Fase 1: grid pequeno do mma, dois horizontes.
    analysis, summary = build_summary(
        synthetic_prices, mma, {"window": [5, 20], "tol": [0.0]}, [10, 20], min_events=1
    )
    # Fase 2: 2 janelas × 1 tol × 2 horizontes × 2 famílias = 8 linhas.
    assert len(summary) == 8
    # Fase 2: schema essencial + indicador correto.
    assert {"indicator", "horizon", "family", "r2", "status"} <= set(summary.columns)
    assert (summary["indicator"] == "mma").all()
    # Saída: analysis é 1 linha por dia.
    assert len(analysis) == len(synthetic_prices)


# Teste: o dicionário cobre EXATAMENTE as colunas do summary (params variam).
def test_summary_dictionary_matches_columns(synthetic_prices):
    """
    Por quê: cada indicador tem params diferentes (window/tol/persist, N, mult...);
    o dicionário precisa ter uma linha por coluna real do summary — nem mais, nem menos.

    Lógica: Entrada (summary do mma com persist) → Fase 1 summary_dictionary → Saída.
    """
    # Fase 1: summary com a coluna extra `persist` no grid.
    _, summary = build_summary(
        synthetic_prices, mma, {"window": [5], "tol": [0.0], "persist": [0]}, [10], min_events=1
    )
    # Fase 1: gera a legenda a partir das colunas reais.
    dic = summary_dictionary(summary)
    # Saída: cobertura exata (inclui a coluna `persist`).
    assert set(dic["coluna"]) == set(summary.columns)
    assert "persist" in set(dic["coluna"])


# Teste: write_outputs genérico usa o `name` no nome dos arquivos.
def test_generic_write_outputs_names_files_by_indicator(synthetic_prices, tmp_path):
    """
    Por quê: o run_all grava um par por indicador; o nome do arquivo tem de derivar
    do `name` passado (não fixo em "mma").

    Lógica: Entrada (summary) → Fase 1 write_outputs(name='mma') → Fase 2 nomes/abas → Saída.
    """
    # Entrada: gera as saídas.
    analysis, summary = build_summary(
        synthetic_prices, mma, {"window": [5], "tol": [0.0]}, [10], min_events=1
    )
    # Fase 1: escreve em tmp com o nome do indicador.
    apath, spath = write_outputs(analysis, summary, "mma", outdir=tmp_path)
    # Fase 2: nomes derivados do `name`.
    assert apath.name == "analysis_mma.xlsx" and spath.name == "summary_mma.xlsx"
    # Saída: o summary.xlsx tem as duas abas.
    sheets = pd.ExcelFile(spath).sheet_names
    assert "summary" in sheets and "dicionário" in sheets
