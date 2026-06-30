# Path para criar a pasta output e escrever os CSVs.
from pathlib import Path
# pandas para o tipo do df.
import pandas as pd
# As peças do pipeline.
from robusta.data import load_prices
from robusta.target import add_labels
from robusta.indicators import mma
from robusta.sweep import run_sweep
# Parâmetros ajustáveis centralizados (ticker, grids, period, saída).
from robusta import config


# Orquestração pura: de um df de preços às duas saídas (sem rede).
def build_summary(prices: pd.DataFrame, *, windows, tols, horizons, min_events: int = 5):
    """
    Por quê: separar a orquestração (testável, sem rede) do I/O (main). Recebe um
    df já carregado para que o teste e2e injete preços sintéticos.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV + listas de janelas, tolerâncias e horizontes.
      Fase 1: cria os rótulos ret_{h}d/y_{h}d no df-fundação.
      Fase 2: monta o grid de parâmetros do mma.
      Fase 3: roda o sweep com o módulo mma (acumula colunas + resume).
      Saída: (analysis_df, summary_df).
    """
    # Fase 1: anexa as colunas-alvo para todos os horizontes.
    labeled = add_labels(prices, horizons=horizons)
    # Fase 2: grid de parâmetros do indicador.
    grid = {"window": windows, "tol": tols}
    # Fase 3/Saída: executa o sweep injetando o módulo plug-in mma.
    return run_sweep(labeled, mma, grid, horizons, min_events=min_events)


# Constrói a tabela-legenda (dicionário) das colunas do summary.
def summary_dictionary() -> pd.DataFrame:
    """
    Por quê: o summary é denso; uma legenda ao lado dos dados (2ª aba do .xlsx)
    evita que o leitor precise consultar a documentação para entender cada coluna.

    Lógica (Entrada → Saída):
      Entrada: nenhuma (conteúdo fixo, espelha o schema de modeling/sweep).
      Fase 1: monta uma linha por coluna do summary (grupo + significado + como ler).
      Saída: DataFrame com colunas [coluna, grupo, significado, como_ler].
    """
    # Fase 1: uma linha por coluna do summary, na ordem em que aparecem.
    linhas = [
        # --- identificação: qual teste é esta linha ---
        {"coluna": "indicator", "grupo": "identificação", "significado": "Indicador técnico testado", "como_ler": "Hoje só 'mma' (média móvel simples)."},
        {"coluna": "window", "grupo": "identificação", "significado": "Janela da média móvel, em dias", "como_ler": "5, 10, 20, 50, 200."},
        {"coluna": "tol", "grupo": "identificação", "significado": "Tolerância do rompimento (fração acima da média p/ contar como evento)", "como_ler": "0 = toca a média; 0.01 = 1%; 0.03 = 3%."},
        {"coluna": "horizon", "grupo": "identificação", "significado": "Dias à frente que o alvo olha", "como_ler": "10, 20, 30, 45, 90."},
        {"coluna": "family", "grupo": "identificação", "significado": "Pergunta que o modelo responde", "como_ler": "logit = 'subiu? (0/1)'; ols = 'quanto rendeu? (% contínuo)'."},
        # --- amostra: quanto dado entrou ---
        {"coluna": "n", "grupo": "amostra", "significado": "Nº de dias usados no ajuste (após remover NA das pontas)", "como_ler": "Cai com horizon e window."},
        {"coluna": "n_eventos", "grupo": "amostra", "significado": "Nº de dias com rompimento (dummy = 1)", "como_ler": "Poucos eventos = estimativa frágil; leia junto com r2/coef."},
        # --- métricas: o que o modelo achou ---
        {"coluna": "r2", "grupo": "métrica", "significado": "Poder explicativo: pseudo-R² McFadden (logit) ou R² clássico (ols)", "como_ler": "0 = não explica nada; maior = melhor. Compare só dentro da mesma family."},
        {"coluna": "coef", "grupo": "métrica", "significado": "Efeito do rompimento sobre o alvo", "como_ler": "logit: log-odds (exp(coef) = razão de chances); ols: variação no retorno (0.0146 = +1,46 p.p.). Sinal +/- indica direção."},
        {"coluna": "p_value", "grupo": "métrica", "significado": "Significância estatística do coef", "como_ler": "<0.05 = 'significativo'; com n alto quase tudo fica significativo (trate como exploratório)."},
        {"coluna": "llf", "grupo": "métrica", "significado": "Log-likelihood (qualidade do ajuste)", "como_ler": "Diagnóstico; maior (menos negativo) = melhor. Só compare dentro da mesma family."},
        {"coluna": "accuracy", "grupo": "métrica", "significado": "Só logit: % de acerto subir/não, in-sample", "como_ler": "~0.53 = pouco acima do acaso; NaN no ols (não se aplica)."},
        {"coluna": "status", "grupo": "métrica", "significado": "Resultado do ajuste do modelo", "como_ler": "ok / sem_eventos (poucos rompimentos) / separacao / erro."},
        # --- associação 2×2: medidas diretas da tabela rompimento × alta (só logit) ---
        {"coluna": "odds_ratio", "grupo": "associação 2×2", "significado": "Razão de chances de subir em dia de rompimento vs dia normal (tabela 2×2)", "como_ler": "Só logit. >1 = rompimento favorece alta; ≈ exp(coef). NaN no ols / se indefinido."},
        {"coluna": "lift", "grupo": "associação 2×2", "significado": "Quantas vezes mais provável subir após o rompimento vs a taxa-base", "como_ler": "Só logit. 1 = igual à base; 1,3 = 30% mais provável. NaN no ols."},
        {"coluna": "fisher_p", "grupo": "associação 2×2", "significado": "p-valor do teste exato de Fisher na tabela 2×2", "como_ler": "Só logit. <0,05 = associação significativa; à prova de falha (não quebra). NaN no ols."},
    ]
    # Saída: DataFrame com a ordem de colunas fixada.
    return pd.DataFrame(linhas, columns=["coluna", "grupo", "significado", "como_ler"])


# Escreve as duas saídas em disco no formato .xlsx.
def write_outputs(analysis, summary, outdir="output"):
    """
    Por quê: isolar a escrita em disco (formato .xlsx, via engine openpyxl) da
    lógica e do download, para poder testá-la SEM rede e trocar o formato/local
    num só ponto. O summary leva uma 2ª aba 'dicionário' com a legenda das colunas.

    Lógica (Entrada → Saída):
      Entrada: df-fundação enriquecido, summary e a pasta de saída.
      Fase 1: garante a existência da pasta de saída.
      Fase 2: escreve o analysis (mantendo o índice de datas) em .xlsx.
      Fase 3: escreve o summary em 2 abas — 'summary' (dados) e 'dicionário' (legenda).
      Saída: tupla (caminho_analysis, caminho_summary).
    """
    # Fase 1: normaliza o destino em Path e cria a pasta (inclusive pais) se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho e escrita do df-fundação por dia (índice de datas preservado).
    analysis_path = out / "analysis_mma.xlsx"
    analysis.to_excel(analysis_path)
    # Fase 3: caminho do summary; abre um writer para gravar duas abas no mesmo arquivo.
    summary_path = out / "summary_mma.xlsx"
    with pd.ExcelWriter(summary_path, engine="openpyxl") as writer:
        # Fase 3: 1ª aba 'summary' com os modelos (sem índice numérico).
        summary.to_excel(writer, sheet_name="summary", index=False)
        # Fase 3: 2ª aba 'dicionário' com a legenda de cada coluna.
        summary_dictionary().to_excel(writer, sheet_name="dicionário", index=False)
    # Saída: os dois caminhos escritos.
    return analysis_path, summary_path


# Entrypoint de linha de comando: baixa, resume e salva os dois .xlsx.
def main(ticker: str = config.TICKER, period: str = config.PERIOD) -> None:
    """
    Por quê: ponto de entrada humano; concentra o I/O (download + escrita) fora da
    lógica pura. TODOS os parâmetros vêm de config.py — ajuste lá, não aqui.

    Lógica (Entrada → Saída):
      Entrada: ticker e janela relativa (default de config; overrideáveis).
      Fase 1: baixa os preços dos últimos `period` (rede).
      Fase 2: roda build_summary com os grids do config.
      Fase 3: escreve as duas saídas .xlsx na pasta do config.
      Saída: <OUTPUT_DIR>/analysis_mma.xlsx e summary_mma.xlsx em disco.
    """
    # Fase 1: download dos preços do ticker pela janela relativa.
    prices = load_prices(ticker, period)
    # Fase 2: gera as duas saídas usando os grids centralizados em config.py.
    analysis, summary = build_summary(
        prices,
        # Janelas da média móvel (config.MMA_WINDOWS).
        windows=config.MMA_WINDOWS,
        # Tolerâncias do rompimento (config.TOLERANCES).
        tols=config.TOLERANCES,
        # Horizontes do alvo (config.HORIZONS).
        horizons=config.HORIZONS,
        # Mínimo de eventos por modelo (config.MIN_EVENTS).
        min_events=config.MIN_EVENTS,
    )
    # Fase 3: escreve os dois .xlsx na pasta de saída do config.
    analysis_path, summary_path = write_outputs(analysis, summary, outdir=config.OUTPUT_DIR)
    # Fase 3: feedback no console de onde os arquivos foram salvos.
    print(f"{analysis_path.name} ({len(analysis)} dias) e {summary_path.name} ({len(summary)} modelos) salvos em {config.OUTPUT_DIR}/")


# Permite rodar como script: `python -m robusta.run_mma`.
if __name__ == "__main__":
    # Chama main com os defaults.
    main()
