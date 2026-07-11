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
MMA_WINDOWS = [10, 26, 50, 200]
# Tolerâncias do rompimento (fração acima da média): 0.0 = toca; 0.01 = 1%; 0.03 = 3%.
TOLERANCES = [0.0, 0.015, 0.03]
# Persistências do onset (dias mantendo o ESTADO após o onset): 0 = onset puro;
# k = onset + k dias no estado. Carimbadas no dia da confirmação (one-shot).
# Varrida pelos 8 indicadores de REGIME (via PARAM_GRIDS); run_mma standalone também usa.
PERSISTENCES = [0, 1, 2, 3, 4]

# === Alvo (variável dependente) ===
# Horizontes (dias à frente) que o alvo olha — a "daylist".
HORIZONS = [20, 45, 90]

# === Modelagem ===
# Mínimo de rompimentos para ajustar um modelo (abaixo disso → status "sem_eventos").
MIN_EVENTS = 5

# === Saída ===
# Pasta onde os arquivos .xlsx são gravados.
OUTPUT_DIR = "output"

# === Roster multi-indicador (run_all) ===
# Nomes dos módulos em src/robusta/indicators/ a rodar no run_all.
INDICATORS = ["mma", "mme", "obv", "vwap", "alto_volume",
              "exaustao_atr", "rsi", "macd", "donchian", "bollinger"]

# Grid de parâmetros por indicador (painel único; ajuste manual).
# Regras: indicadores de REGIME varrem PERSISTENCES; os de EVENTO pontual
# (alto_volume, exaustao_atr) ficam em persist=[0] — 2+ dias consecutivos do
# estado deles é raríssimo; o módulo suporta, ativar aqui é trocar a lista.
PARAM_GRIDS = {
    "mma":          {"window": [10, 26, 50, 200], "tol": [0.0, 0.015, 0.03], "persist": PERSISTENCES},
    "mme":          {"window": [10, 26, 50, 200], "tol": [0.0, 0.015, 0.03], "persist": PERSISTENCES},
    "obv":          {"window": [20, 50], "persist": PERSISTENCES},
    "vwap":         {"window": [20, 50], "tol": [0.0, 0.015], "persist": PERSISTENCES},
    "alto_volume":  {"window": [20], "mult": [1.5, 2.0], "tol": [0.0, 0.005], "persist": [0], "confirm": [0, 1, 2, 3, 4]},
    "exaustao_atr": {"atr_period": [14], "mult": [1.5, 2.0], "tol": [0.0, 0.005], "persist": [0], "confirm": [0, 1, 2, 3, 4]},
    "rsi":          {"window": [14], "low": [30], "persist": PERSISTENCES},
    "macd":         {"fast": [12], "slow": [26], "sig": [9], "persist": PERSISTENCES},
    "donchian":     {"N": [20, 55], "persist": PERSISTENCES},
    "bollinger":    {"window": [20], "n_std": [2.0], "persist": PERSISTENCES},
}

'''
Rodar o pipeline real (gera os .xlsx) — precisa do PYTHONPATH=src

# PowerShell (seu shell padrão):

$env:PYTHONPATH="src" 

uv run python -m robusta.run_mma
'''