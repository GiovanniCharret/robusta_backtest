# pandas para o tipo DataFrame e a ordenação.
import pandas as pd
# yfinance é a fonte de preços (isolada neste módulo).
import yfinance as yf


# Colunas OHLCV canônicas que o resto do pipeline assume.
_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


# Padroniza um DataFrame bruto de preços para o schema OHLCV ordenado.
def normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Por quê: blindar o pipeline contra variações da fonte (ordem das linhas,
    colunas extras). Função pura → testável sem rede. É a base do df-fundação.

    Lógica (Entrada → Saída):
      Entrada: DataFrame bruto indexado por data.
      Fase 1: valida a presença do Close (sem ele não há alvo).
      Fase 2: ordena por data crescente.
      Fase 3: seleciona apenas as colunas OHLCV presentes.
      Saída: DataFrame OHLCV ordenado (o df-fundação).
    """
    # Fase 1: Close é obrigatório; falha cedo e claro.
    if "Close" not in raw.columns:
        # Levanta erro explícito quando o Close não veio.
        raise ValueError("raw precisa da coluna 'Close'")
    # Fase 2: ordena pelo índice de datas.
    ordered = raw.sort_index()
    # Fase 3: mantém só as colunas OHLCV que existirem, na ordem canônica.
    cols = [c for c in _OHLCV if c in ordered.columns]
    # Saída: subconjunto ordenado.
    return ordered[cols]


# Baixa os preços de um ticker e devolve o df-fundação OHLCV normalizado.
def load_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Por quê: concentrar TODO o acesso à rede num único ponto, para que os demais
    módulos sejam puros e testáveis. Não é coberto por teste unitário (usa rede).

    Lógica (Entrada → Saída):
      Entrada: ticker e janela de datas (start, end).
      Fase 1: baixa os dados via yfinance.
      Fase 2: achata colunas MultiIndex se houver.
      Fase 3: normaliza para OHLCV ordenado.
      Saída: df-fundação pronto para add_labels.
    """
    # Fase 1: download bruto (auto_adjust=True usa preços ajustados no Close).
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    # Fase 2: yfinance pode devolver colunas MultiIndex (1 ticker) → achata.
    if isinstance(raw.columns, pd.MultiIndex):
        # Mantém o primeiro nível (Open/High/.../Close), descartando o ticker.
        raw.columns = raw.columns.get_level_values(0)
    # Fase 3/Saída: normaliza e devolve.
    return normalize_ohlcv(raw)
