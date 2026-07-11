# Path para criar a pasta output e escrever os .xlsx.
from pathlib import Path
# pandas para o tipo do df e o ExcelWriter.
import pandas as pd
# add_labels cria o alvo deslocado (genérico, independente de indicador).
from robusta.target import add_labels
# run_sweep é o motor agnóstico (recebe o módulo do indicador por injeção).
from robusta.sweep import run_sweep


# Legenda por coluna: grupo + significado + como ler. Cobre métricas fixas E params de todos os indicadores.
_COLUMN_DESC = {
    # --- identificação comum ---
    "ticker": ("identificação", "Ticker do ativo (modo multi-ticker)", "Nome B3 sem sufixo (ex.: PETR4). Presente só quando o run varre a lista de tickers."),
    "indicator": ("identificação", "Indicador técnico testado", "mma, mme, obv, vwap, rsi, macd, donchian, bollinger, alto_volume, exaustao_atr."),
    "horizon": ("identificação", "Dias à frente que o alvo olha", "Ex.: 20, 45, 90."),
    "family": ("identificação", "Pergunta que o modelo responde", "logit = 'subiu? (0/1)'; ols = 'quanto rendeu? (% contínuo)'."),
    # --- params por indicador (aparecem conforme o grid) ---
    "window": ("identificação", "Janela do indicador, em dias", "Ex.: 10, 20, 50, 200."),
    "tol": ("identificação", "Tolerância do rompimento (fração acima do valor)", "0 = toca; 0.015 = 1,5%; 0.03 = 3%."),
    "persist": ("identificação", "Persistência do estado (dias mantendo o estado após o onset)", "0 = onset puro; k = onset + k dias no estado, carimbado 1x no dia da confirmação (sem vazamento)."),
    "confirm": ("identificação", "Confirmação de PREÇO após o evento (só alto_volume/exaustao_atr)", "0 = evento puro; k = Close segurou ≥ Close do dia do evento por k dias; 1 no k-ésimo dia (sem vazamento)."),
    "mult": ("identificação", "Multiplicador do limiar (volume/ATR sobre a média)", "1.5 = 1,5× a média; 2.0 = 2×."),
    "atr_period": ("identificação", "Janela do ATR, em dias", "Ex.: 14."),
    "low": ("identificação", "Piso do RSI para sair do sobrevendido", "Ex.: 30 (onset = cruzar 30 p/ cima)."),
    "fast": ("identificação", "EMA rápida do MACD", "Ex.: 12."),
    "slow": ("identificação", "EMA lenta do MACD", "Ex.: 26."),
    "sig": ("identificação", "EMA da linha de sinal do MACD", "Ex.: 9."),
    "N": ("identificação", "Janela do canal de Donchian (máxima de N dias)", "Ex.: 20, 55."),
    "n_std": ("identificação", "Nº de desvios-padrão da banda de Bollinger", "Ex.: 2.0."),
    # --- amostra ---
    "n": ("amostra", "Nº de dias usados no ajuste (após remover NA das pontas)", "Cai com horizon e window."),
    "n_eventos": ("amostra", "Nº de dias com onset (dummy = 1)", "Poucos eventos = estimativa frágil; leia junto com r2/coef."),
    # --- métricas ---
    "r2": ("métrica", "Poder explicativo: pseudo-R² McFadden (logit) ou R² clássico (ols)", "0 = não explica; maior = melhor. Compare só dentro da mesma family. NÃO serve para cross-ranking."),
    "coef": ("métrica", "Efeito do onset sobre o alvo", "logit: log-odds (exp = razão de chances); ols: variação no retorno. Sinal indica direção."),
    "p_value": ("métrica", "Significância estatística do coef", "<0.05 = 'significativo'; com n alto quase tudo fica significativo (exploratório)."),
    "llf": ("métrica", "Log-likelihood (qualidade do ajuste)", "Diagnóstico; maior = melhor. Só compare dentro da mesma family."),
    "accuracy": ("métrica", "Só logit: % de acerto subir/não, in-sample", "~0.53 = pouco acima do acaso; NaN no ols."),
    "status": ("métrica", "Resultado do ajuste", "ok / sem_eventos / separacao / erro."),
    # --- associação 2×2 (só logit) ---
    "odds_ratio": ("associação 2×2", "Razão de chances de subir no onset vs dia normal", "Só logit. >1 = favorece alta; ≈ exp(coef). NaN no ols."),
    "lift": ("associação 2×2", "Quantas vezes mais provável subir após o onset vs a taxa-base", "Só logit. 1 = igual à base; 1,3 = 30% mais provável. Chave de ranking do logit. NaN no ols."),
    "fisher_p": ("associação 2×2", "p-valor do teste exato de Fisher na tabela 2×2", "Só logit. <0,05 = associação significativa; à prova de falha. NaN no ols."),
}


# Constrói a legenda (dicionário) a partir das colunas REAIS do summary.
def summary_dictionary(summary) -> pd.DataFrame:
    """
    Por quê: o summary é denso e seus params variam por indicador (mma tem
    window/tol/persist; donchian tem N; etc.). A legenda precisa ter exatamente
    uma linha por coluna presente — construída a partir do próprio summary para
    nunca divergir do schema.

    Lógica (Entrada → Saída):
      Entrada: DataFrame de summary (qualquer indicador).
      Fase 1: para cada coluna do summary, busca (grupo, significado, como_ler).
      Fase 2: colunas desconhecidas caem num texto genérico (à prova de falha).
      Saída: DataFrame [coluna, grupo, significado, como_ler], 1 linha por coluna.
    """
    # Acumulador das linhas da legenda.
    linhas = []
    # Fase 1: percorre as colunas na ordem em que aparecem no summary.
    for col in summary.columns:
        # Fase 1/2: descrição conhecida ou fallback genérico para param novo.
        grupo, significado, como_ler = _COLUMN_DESC.get(
            col, ("identificação", f"Parâmetro '{col}' do indicador", "Ver a definição do indicador no design.")
        )
        # Fase 1: uma linha por coluna.
        linhas.append({"coluna": col, "grupo": grupo, "significado": significado, "como_ler": como_ler})
    # Saída: DataFrame com a ordem de colunas fixada.
    return pd.DataFrame(linhas, columns=["coluna", "grupo", "significado", "como_ler"])


# Orquestração pura: de um df de preços + um módulo-indicador às duas saídas (sem rede).
def build_summary(prices, indicator, param_grid, horizons, min_events: int = 5):
    """
    Por quê: versão genérica (extraída de run_mma) — roda QUALQUER indicador via
    injeção do módulo + grid, separando orquestração (testável) do I/O.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV, o módulo do indicador, o grid {param: [valores]}, horizontes, mín. eventos.
      Fase 1: cria os rótulos ret_{h}d/y_{h}d no df-fundação.
      Fase 2/Saída: roda o sweep injetando o módulo (acumula colunas + resume).
    """
    # Fase 1: anexa as colunas-alvo para todos os horizontes.
    labeled = add_labels(prices, horizons=horizons)
    # Fase 2/Saída: sweep agnóstico com o módulo e o grid recebidos.
    return run_sweep(labeled, indicator, param_grid, horizons, min_events=min_events)


# Escreve as duas saídas de UM indicador em disco (.xlsx), nomeadas pelo `name`.
def write_outputs(analysis, summary, name, outdir="output"):
    """
    Por quê: isolar a escrita em disco e parametrizar o nome pelo indicador, para o
    run_all gravar um par por indicador reusando o mesmo código.

    Lógica (Entrada → Saída):
      Entrada: df-fundação enriquecido, summary, nome do indicador e a pasta.
      Fase 1: garante a pasta de saída.
      Fase 2: grava analysis_{name}.xlsx (índice de datas preservado).
      Fase 3: grava summary_{name}.xlsx em 2 abas (summary + dicionário).
      Saída: (caminho_analysis, caminho_summary).
    """
    # Fase 1: normaliza o destino e cria a pasta (inclusive pais) se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho e escrita do df-fundação por dia.
    analysis_path = out / f"analysis_{name}.xlsx"
    analysis.to_excel(analysis_path)
    # Fase 3: caminho do summary; writer para gravar duas abas no mesmo arquivo.
    summary_path = out / f"summary_{name}.xlsx"
    with pd.ExcelWriter(summary_path, engine="openpyxl") as writer:
        # Fase 3: 1ª aba 'summary' com os modelos.
        summary.to_excel(writer, sheet_name="summary", index=False)
        # Fase 3: 2ª aba 'dicionário' com a legenda derivada das colunas reais.
        summary_dictionary(summary).to_excel(writer, sheet_name="dicionário", index=False)
    # Saída: os dois caminhos escritos.
    return analysis_path, summary_path
