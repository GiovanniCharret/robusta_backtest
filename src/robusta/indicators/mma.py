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


# Nome canônico da coluna-dummy (rompimento puro ou persistência de k dias).
def signal_col(window: int, tol: float = 0.0, persist: int = 0) -> str:
    """
    Por quê: o sweep precisa descobrir o nome da dummy a partir dos parâmetros,
    sem conhecer o indicador por dentro. Um mesmo (janela, tol) pode gerar o
    rompimento puro (persist=0) OU uma persistência de k dias (persist=k>0).

    Lógica: Entrada (janela, tolerância, persist) → Saída (nome canônico):
      persist=0 → `mma_w{window}_t{tol}_break` (retrocompatível);
      persist=k → `mma_w{window}_t{tol}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, tolerância, k).
        return f"mma_w{window}_t{tol}_persist{persist}"
    # Saída: nome da dummy de rompimento para (janela, tolerância).
    return f"mma_w{window}_t{tol}_break"


# Acrescenta ao df-fundação o valor da média, o estado, o rompimento e (opcional) a persistência.
def add_columns(df: pd.DataFrame, window: int, tol: float = 0.0, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: este é o PLUG-IN. Em vez de devolver uma série solta, ACRESCENTA suas
    colunas ao df-fundação (igual ao legado), para revisão linha a linha. Trocar
    de indicador = escrever outro arquivo com a mesma interface.

    Lógica (Entrada → Saída):
      Entrada: df-fundação com Close, janela, tolerância e persistência (0 = desligada).
      Fase 1: calcula a média móvel simples e a grava em mma_w{window}.
      Fase 2: grava o ESTADO "acima da banda" (Close > mma*(1+tol)).
      Fase 3: grava o EVENTO de cruzamento (acima hoje e não-acima ontem) = a dummy de rompimento.
      Fase 4: se persist>0, grava a dummy de PERSISTÊNCIA (rompeu e ficou above por mais k dias).
      Saída: o df-fundação com as colunas anexadas (3 sempre; +1 se persist>0).
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
    # Fase 4: persistência opcional (rompimento + k dias mantendo-se above, one-shot na confirmação).
    if persist:
        # Fase 4: streak = nº de dias consecutivos com o MESMO valor de above, terminando em t.
        streak = above.groupby((above != above.shift()).cumsum()).cumcount() + 1
        # Fase 4: persist acende SÓ quando above=1 e a sequência atual tem exatamente k+1 dias
        # (rompimento no início + k dias acima); usa só passado/presente → sem vazamento.
        df[signal_col(window, tol, persist)] = (above & (streak == persist + 1)).astype("Int8")
    # Saída: df-fundação enriquecido.
    return df
