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


# Lê a lista de tickers líquidos de uma planilha local (coluna `tickers`).
def load_tickers(path) -> list[str]:
    """
    Por quê: o modo multi-ticker itera uma lista mantida à mão numa planilha
    (src/entrada/); centralizar a leitura aqui mantém TODO o I/O de dados
    (rede e arquivos locais) neste módulo, deixando o resto do pipeline puro.

    Lógica (Entrada → Saída):
      Entrada: caminho de um .xlsx com a coluna `tickers` (nomes SEM sufixo, ex.: PETR4).
      Fase 1: lê a planilha.
      Fase 2: descarta células vazias e apara espaços, preservando a ordem.
      Saída: lista de strings na ordem da planilha.
    """
    # Fase 1: lê a planilha (engine openpyxl, a mesma usada na escrita das saídas).
    df = pd.read_excel(path)
    # Fase 2/Saída: sem NaN, como str e sem espaços nas pontas, na ordem original.
    return [str(t).strip() for t in df["tickers"].dropna()]


# Baixa os preços de um ticker e devolve o df-fundação OHLCV normalizado.
def load_prices(ticker: str, period: str = "10y") -> pd.DataFrame:
    """
    Por quê: concentrar TODO o acesso à rede num único ponto, para que os demais
    módulos sejam puros e testáveis. Usa uma janela RELATIVA (period) em vez de
    datas fixas, para os dados não envelhecerem. Não é coberto por teste (usa rede).

    Lógica (Entrada → Saída):
      Entrada: ticker e janela relativa (period: "5y", "10y", "max", ...).
      Fase 1: baixa os últimos `period` de dados via yfinance (janela móvel até hoje).
      Fase 2: achata colunas MultiIndex se houver.
      Fase 3: normaliza para OHLCV ordenado.
      Saída: df-fundação pronto para add_labels.
    """
    # Fase 1: download bruto pelo period (auto_adjust=True usa preços ajustados no Close).
    raw = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    # Fase 2: yfinance pode devolver colunas MultiIndex (1 ticker) → achata.
    if isinstance(raw.columns, pd.MultiIndex):
        # Mantém o primeiro nível (Open/High/.../Close), descartando o ticker.
        raw.columns = raw.columns.get_level_values(0)
    # Fase 3/Saída: normaliza e devolve.
    return normalize_ohlcv(raw)
