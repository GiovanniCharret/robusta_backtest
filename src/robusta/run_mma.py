# Path só é usado indiretamente via runner; mantemos pandas para o tipo.
import pandas as pd
# As peças do pipeline específicas do mma.
from robusta.data import load_prices
from robusta.indicators import mma
# Runner genérico: orquestração + escrita + legenda (compartilhados).
from robusta import runner
# Parâmetros ajustáveis centralizados.
from robusta import config


# Wrapper fino: mantém a assinatura histórica do mma e delega ao runner genérico.
def build_summary(prices: pd.DataFrame, *, windows, tols, horizons, persists=(0,), min_events: int = 5):
    """
    Por quê: preservar a interface pública do mma (usada por testes e pela main),
    montando o grid {window,tol,persist} e delegando ao runner genérico.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV + listas de janelas, tolerâncias, horizontes, persistências.
      Fase 1: monta o grid do mma (persist é só mais uma dimensão).
      Fase 2/Saída: delega a build_summary genérico injetando o módulo mma.
    """
    # Fase 1: grid de parâmetros do mma.
    grid = {"window": windows, "tol": tols, "persist": list(persists)}
    # Fase 2/Saída: runner genérico com o módulo mma.
    return runner.build_summary(prices, mma, grid, horizons, min_events=min_events)



# Wrapper fino: escreve as saídas do mma delegando ao runner (nome fixo "mma").
def write_outputs(analysis, summary, outdir="output"):
    """
    Por quê: manter a assinatura histórica (sem `name`) que os testes do mma usam,
    fixando o nome do indicador em "mma" e delegando a escrita ao runner.

    Lógica: Entrada (analysis, summary, pasta) → Saída (caminhos), via runner.
    """
    # Saída: delega ao runner com o nome do indicador fixo.
    return runner.write_outputs(analysis, summary, "mma", outdir)


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
        # Persistências do rompimento (config.PERSISTENCES; 0 = rompimento puro).
        persists=config.PERSISTENCES,
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
