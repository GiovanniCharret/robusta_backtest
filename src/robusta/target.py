# pandas é a base para shift/where e o tipo Int8 anulável.
import pandas as pd


# Constrói a variável dependente deslocando datas futuras de volta para hoje.
def add_labels(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """
    Por quê: separar a criação do alvo (genérica, independente de indicador) do
    resto do pipeline. É o mecanismo de "deslocamento de datas" herdado do legado
    que transforma cada dia numa amostra rotulada; adiciona as colunas ao
    df-fundação para revisão linha a linha.

    Lógica (Entrada → Saída):
      Entrada: df-fundação com coluna Close e a lista de horizontes (a "daylist").
      Fase 1: copia o df para não mutar o original do chamador.
      Fase 2: para cada horizonte h, calcula o retorno futuro contínuo do Close.
      Fase 3: anexa ret_{h}d (contínuo) e y_{h}d (binário), preservando NA sem futuro.
      Saída: df-fundação com ret_{h}d e y_{h}d por horizonte.
    """
    # Fase 1: trabalha sobre uma cópia (não mutar a entrada do chamador).
    out = df.copy()
    # Fase 2: itera cada horizonte da daylist.
    for h in horizons:
        # Fase 2: retorno futuro contínuo = Close[t+h]/Close[t] - 1 (shift traz o futuro).
        ret = out["Close"].shift(-h) / out["Close"] - 1
        # Fase 3: anexa a coluna contínua (para revisão), espelho do var_desloc do legado.
        out[f"ret_{h}d"] = ret
        # Fase 3: série de rótulos toda NA, dtype inteiro anulável.
        label = pd.Series(pd.NA, index=out.index, dtype="Int8")
        # Fase 3: onde há retorno (não-NA), marca 1 se positivo, senão 0.
        label[ret.notna()] = (ret[ret.notna()] > 0).astype("Int8")
        # Fase 3: anexa a coluna-alvo binária.
        out[f"y_{h}d"] = label
    # Saída: df-fundação com as colunas de retorno e rótulo.
    return out
