# pandas para rolling/shift e o tipo Int8.
import pandas as pd


# Nome do indicador, exposto para o summary e para o entrypoint.
NAME = "mma"


# Nome canônico da coluna de valor da média móvel.
def value_col(window: int) -> str:
    """
    Por quê: centralizar a convenção de nome da coluna de valor, para que sweep e
    testes não dupliquem strings mágicas.

    Lógica: Entrada (janela) → Saída (nome `mma_w{window}`).
    """
    # Saída: nome do valor da média para a janela dada.
    return f"mma_w{window}"


# Nome canônico da coluna-dummy (evento de rompimento).
def signal_col(window: int, tol: float = 0.0) -> str:
    """
    Por quê: o sweep precisa descobrir o nome da dummy a partir dos parâmetros,
    sem conhecer o indicador por dentro.

    Lógica: Entrada (janela, tolerância) → Saída (nome `mma_w{window}_t{tol}_break`).
    """
    # Saída: nome da dummy para (janela, tolerância).
    return f"mma_w{window}_t{tol}_break"


# Acrescenta ao df-fundação o valor da média, o estado e a dummy de rompimento.
def add_columns(df: pd.DataFrame, window: int, tol: float = 0.0) -> pd.DataFrame:
    """
    Por quê: este é o PLUG-IN. Em vez de devolver uma série solta, ACRESCENTA suas
    colunas ao df-fundação (igual ao legado), para revisão linha a linha. Trocar
    de indicador = escrever outro arquivo com a mesma interface.

    Lógica (Entrada → Saída):
      Entrada: df-fundação com Close, janela da média e tolerância do rompimento.
      Fase 1: calcula a média móvel simples e a grava em mma_w{window}.
      Fase 2: grava o ESTADO "acima da banda" (Close > mma*(1+tol)).
      Fase 3: grava o EVENTO de cruzamento (acima hoje e não-acima ontem) = a dummy.
      Saída: o df-fundação com as três colunas anexadas.
    """
    # Fase 1: nome e cálculo da média móvel simples do Close.
    vcol = value_col(window)
    # Fase 1: grava o valor da média (depende só da janela).
    df[vcol] = df["Close"].rolling(window).mean()
    # Fase 2: estado booleano "Close acima da banda de tolerância".
    above = df["Close"] > df[vcol] * (1 + tol)
    # Fase 2: grava o estado como Int8 (coluna *_above) para revisão.
    df[f"mma_w{window}_t{tol}_above"] = above.astype("Int8")
    # Fase 3: cruzamento = acima hoje E não-acima ontem (shift preenche o 1º dia como False).
    cross = above & ~above.shift(1, fill_value=False)
    # Fase 3: grava a dummy de evento (coluna *_break) como Int8.
    df[signal_col(window, tol)] = cross.astype("Int8")
    # Saída: df-fundação enriquecido.
    return df
