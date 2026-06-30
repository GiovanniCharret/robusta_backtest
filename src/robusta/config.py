"""
config.py — Painel único de parâmetros ajustáveis do experimento.

Por quê: antes, os "botões" do estudo (ticker, janela de dados, janelas da média,
tolerâncias, horizontes, mínimo de eventos, pasta de saída) ficavam hardcoded e
espalhados dentro do run_mma.py. Aqui ficam todos juntos, nomeados e comentados —
para ajuste manual rápido SEM tocar na lógica. Edite este arquivo e rode de novo;
nenhum outro código precisa mudar.

Lógica: não há execução; é só dados (constantes), agrupados por etapa do pipeline
(Dados → Indicador → Alvo → Modelagem → Saída).
"""

# === Dados (yfinance) ===
# Ticker do ativo a baixar (ex.: "^BVSP" Ibovespa, "PETR4.SA", "AAPL", "^GSPC").
TICKER = "^BVSP"
# Janela RELATIVA de histórico, até hoje (ex.: "5y", "10y", "max").
PERIOD = "10y"

# === Indicador: média móvel (mma) ===
# Janelas (em dias) da média móvel a varrer — a "mma_list".
MMA_WINDOWS = [5, 10, 20, 50, 200]
# Tolerâncias do rompimento (fração acima da média): 0.0 = toca; 0.01 = 1%; 0.03 = 3%.
TOLERANCES = [0.0, 0.01, 0.03]

# === Alvo (variável dependente) ===
# Horizontes (dias à frente) que o alvo olha — a "daylist".
HORIZONS = [10, 20, 30, 45, 90]

# === Modelagem ===
# Mínimo de rompimentos para ajustar um modelo (abaixo disso → status "sem_eventos").
MIN_EVENTS = 5

# === Saída ===
# Pasta onde os arquivos .xlsx são gravados.
OUTPUT_DIR = "output"
