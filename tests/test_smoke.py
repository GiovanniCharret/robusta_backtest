# Importa o módulo do pacote só para provar que o pythonpath está correto.
import robusta
# pandas para checar o tipo do índice da fixture.
import pandas as pd


# Teste de fumaça: garante que o pacote importa e a fixture funciona.
def test_package_imports_and_fixture_loads(synthetic_prices):
    """
    Por quê: validar o scaffolding (import do pacote + fixture) antes de
    qualquer lógica de negócio.

    Lógica: Entrada (fixture) → Fase 1 checa o pacote → Fase 2 checa o df → Saída (asserts).
    """
    # Fase 1: o módulo `robusta` foi importado sem erro.
    assert robusta is not None
    # Fase 2: a fixture entregou um DataFrame com a coluna Close e 300 linhas.
    assert "Close" in synthetic_prices.columns and len(synthetic_prices) == 300


# Teste extra (lacuna TESTES.md #2): fixture determinística e índice de datas ordenado.
def test_fixture_is_deterministic_and_dated(synthetic_prices):
    """
    Por quê: a reprodutibilidade da fixture é a base de todos os testes; travar o
    primeiro Close e o tipo/ordem do índice evita surpresas silenciosas.

    Lógica: Entrada (fixture) → Fase 1 valor fixo → Fase 2 índice → Fase 3 schema → Saída.
    """
    # Fase 1: primeiro Close = 100 + 8*sin(0) + 3*sin(0) = 100.0 (determinístico).
    assert round(synthetic_prices["Close"].iloc[0], 6) == 100.0
    # Fase 2: índice é de datas e está ordenado de forma crescente.
    assert isinstance(synthetic_prices.index, pd.DatetimeIndex)
    assert synthetic_prices.index.is_monotonic_increasing
    # Fase 3: schema OHLCV completo presente.
    assert list(synthetic_prices.columns) == ["Open", "High", "Low", "Close", "Volume"]
