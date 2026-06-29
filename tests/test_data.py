# pandas para montar um raw "à la yfinance".
import pandas as pd
# pytest para checar a exceção.
import pytest
# Só o helper puro é testado (load_prices usa rede e fica de fora).
from robusta.data import normalize_ohlcv


# Teste: normaliza colunas e ordena o índice.
def test_normalize_sorts_and_keeps_ohlcv():
    """
    Por quê: o yfinance pode devolver linhas fora de ordem e colunas extras; o
    pipeline assume OHLCV ordenado por data. Este helper garante isso e é puro
    (testável sem rede).

    Lógica: Entrada (raw desordenado) → Fase 1 normalize → Fase 2 asserts → Saída.
    """
    # Entrada: duas datas fora de ordem, com uma coluna extra.
    raw = pd.DataFrame(
        {"Open": [2, 1], "High": [2, 1], "Low": [2, 1], "Close": [2, 1],
         "Volume": [2, 1], "Extra": [9, 9]},
        index=pd.to_datetime(["2020-01-02", "2020-01-01"]),
    )
    # Fase 1: normaliza.
    out = normalize_ohlcv(raw)
    # Fase 2: índice ordenado (01 antes de 02).
    assert list(out.index) == sorted(out.index)
    # Fase 2: só as 5 colunas OHLCV permanecem.
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    # Saída: o Close foi reordenado junto (primeira linha = 1).
    assert out["Close"].iloc[0] == 1


# Teste: sem Close → erro explícito.
def test_normalize_requires_close():
    """
    Por quê: falhar cedo e claro se a fonte não trouxe o Close (alvo depende dele).

    Lógica: Entrada (sem Close) → Fase 1 espera ValueError → Saída.
    """
    # Entrada: raw sem a coluna Close.
    raw = pd.DataFrame({"Open": [1]}, index=pd.to_datetime(["2020-01-01"]))
    # Fase 1/Saída: deve levantar ValueError.
    with pytest.raises(ValueError):
        normalize_ohlcv(raw)


# Lacuna TESTES.md #37 (BAIXA): OHLCV parcial (faltam colunas) mas com Close → sem erro.
def test_normalize_keeps_only_present_ohlcv():
    """
    Por quê: a seleção `[c for c in _OHLCV if c in cols]` deve manter só o que
    existe, sem levantar erro quando faltam Volume/Open.

    Lógica: Entrada (só Close e High) → Fase 1 normalize → Fase 2 subconjunto → Saída.
    """
    # Entrada: apenas Close e High (sem Open/Low/Volume), com Extra a descartar.
    raw = pd.DataFrame(
        {"High": [3, 2], "Close": [3, 2], "Extra": [0, 0]},
        index=pd.to_datetime(["2020-01-02", "2020-01-01"]),
    )
    # Fase 1: normaliza sem erro.
    out = normalize_ohlcv(raw)
    # Fase 2/Saída: mantém só as OHLCV presentes, na ordem canônica.
    assert list(out.columns) == ["High", "Close"]
