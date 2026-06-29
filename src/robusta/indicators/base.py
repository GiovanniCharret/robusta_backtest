# Protocol formaliza a interface que todo indicador-plugin deve cumprir.
from typing import Protocol
# pandas para os tipos das assinaturas.
import pandas as pd


# Contrato estrutural de um indicador plugável.
class Indicator(Protocol):
    """
    Por quê: documentar — em um só lugar — a forma que qualquer indicador novo
    (mme, obv, ...) precisa ter para entrar no sweep sem mudar mais nada.

    Lógica: não há execução; é só o contrato. Toda implementação expõe NAME,
    signal_col(**params) e add_columns(df, **params), que ACRESCENTA colunas ao
    df-fundação e o devolve.
    """

    # Nome curto do indicador, usado como coluna no summary.
    NAME: str

    # Devolve o nome canônico da coluna-dummy para os parâmetros dados.
    def signal_col(self, **params) -> str:
        # Protocol: corpo vazio, só assinatura.
        ...

    # Acrescenta as colunas do indicador ao df e devolve o df.
    def add_columns(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        # Protocol: corpo vazio, só assinatura.
        ...
