# Importa pandas para construir o DataFrame de preços sintético.
import pandas as pd
# Importa numpy para gerar a série determinística (sem aleatoriedade).
import numpy as np
# Importa o decorator de fixture do pytest.
import pytest


# Fixture reutilizada por vários testes: preços sintéticos determinísticos.
@pytest.fixture
def synthetic_prices():
    """
    Por quê: vários testes precisam de um DataFrame OHLCV realista porém
    determinístico (sem rede, sem aleatoriedade) para checar rótulos, dummies,
    fit e sweep de forma reprodutível.

    Lógica (Entrada → Saída):
      Entrada: nenhum argumento.
      Fase 1: cria um índice de datas úteis.
      Fase 2: gera um Close com tendência + ondas senoidais (cruza médias).
      Fase 3: deriva OHLCV simples a partir do Close.
      Saída: DataFrame indexado por data com colunas OHLCV.
    """
    # Fase 1: 300 dias úteis a partir de uma data fixa.
    idx = pd.bdate_range("2020-01-01", periods=300)
    # Fase 2: vetor de posições 0..299 para compor a série.
    t = np.arange(len(idx))
    # Fase 2: Close = nível base + tendência leve + duas ondas (gera cruzamentos).
    close = 100 + 0.05 * t + 8 * np.sin(t / 13) + 3 * np.sin(t / 3.0)
    # Fase 3: monta o DataFrame OHLCV derivando High/Low/Open/Volume do Close.
    df = pd.DataFrame(
        {
            # Open aproximado pelo Close do dia anterior (primeiro = próprio Close).
            "Open": np.r_[close[0], close[:-1]],
            # High = Close + 0.5 (banda superior simples).
            "High": close + 0.5,
            # Low = Close - 0.5 (banda inferior simples).
            "Low": close - 0.5,
            # Close é a própria série gerada.
            "Close": close,
            # Volume constante (irrelevante para mma, mas mantém o schema OHLCV).
            "Volume": 1_000_000,
        },
        # Índice de datas criado na Fase 1.
        index=idx,
    )
    # Saída: DataFrame pronto para os testes.
    return df


# Fixture com Volume determinístico e VARIÁVEL, para indicadores de volume/range.
@pytest.fixture
def synthetic_prices_volume():
    """
    Por quê: obv, vwap, alto_volume e exaustao_atr dependem de um Volume que muda
    dia a dia; a `synthetic_prices` tem Volume constante e não geraria sinal útil.

    Lógica (Entrada → Saída):
      Entrada: nenhum argumento.
      Fase 1: índice de 300 dias úteis a partir de uma data fixa.
      Fase 2: Close com tendência + ondas (gera cruzamentos), como na outra fixture.
      Fase 3: Volume determinístico, variável e sempre positivo.
      Fase 4: deriva OHLCV do Close + o Volume da Fase 3.
      Saída: DataFrame OHLCV indexado por data.
    """
    # Fase 1: 300 dias úteis a partir de uma data fixa.
    idx = pd.bdate_range("2020-01-01", periods=300)
    # Fase 2: vetor de posições 0..299.
    t = np.arange(len(idx))
    # Fase 2: Close = nível base + tendência leve + duas ondas (cruzamentos).
    close = 100 + 0.05 * t + 8 * np.sin(t / 13) + 3 * np.sin(t / 3.0)
    # Fase 3: Volume base + onda + rampa (sempre > 0; varia dia a dia).
    volume = (1_000_000 + 400_000 * np.sin(t / 7.0) + 2_000 * t).astype(int)
    # Fase 4: monta o OHLCV derivando High/Low/Open do Close e usando o Volume acima.
    df = pd.DataFrame(
        {
            # Open ≈ Close do dia anterior (primeiro = próprio Close).
            "Open": np.r_[close[0], close[:-1]],
            # High = Close + 0.5.
            "High": close + 0.5,
            # Low = Close - 0.5.
            "Low": close - 0.5,
            # Close é a série gerada.
            "Close": close,
            # Volume variável da Fase 3.
            "Volume": volume,
        },
        # Índice de datas da Fase 1.
        index=idx,
    )
    # Saída: DataFrame pronto para os testes de volume/range.
    return df
