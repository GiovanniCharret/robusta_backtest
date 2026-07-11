# Path para a pasta de saída e o caminho do master.
from pathlib import Path
# importlib carrega cada módulo-indicador pelo nome (roster dirigido por config).
import importlib
# pandas para concat/sort e o ExcelWriter.
import pandas as pd
# Download de preços (único ponto de rede).
from robusta.data import load_prices
# Runner genérico: orquestração + escrita + legenda compartilhadas.
from robusta.runner import build_summary, write_outputs, summary_dictionary
# Parâmetros centralizados.
from robusta import config


# Concatena os summaries e ordena por [family, chave-de-ranking] desc.
def build_master(summaries) -> pd.DataFrame:
    """
    Por quê: o master permite rankear os indicadores entre si. Como logit e ols usam
    métricas de escalas diferentes, a chave de ranking é lift (logit) / coef (ols), e
    `family` é a chave PRIMÁRIA de ordenação → lift e coef nunca são comparados entre si.

    Lógica (Entrada → Saída):
      Entrada: lista de summaries (um por indicador; params diferentes viram NaN no concat).
      Fase 1: concatena tudo num só DataFrame.
      Fase 2: chave de ranking por linha (lift se logit, senão coef).
      Fase 3: ordena por [family asc, chave desc], NaN por último; descarta a chave temporária.
      Saída: master ordenado, pronto para o summary_ALL.
    """
    # Fase 1: concatena (união de colunas; params ausentes viram NaN).
    master = pd.concat(summaries, ignore_index=True)
    # Fase 2: chave de ranking = lift nas linhas logit; coef nas demais (ols).
    sort_key = master["lift"].where(master["family"] == "logit", master["coef"])
    # Fase 3: ordena por família (primária) e pela chave (desc), NaN no fim; chave temporária removida.
    master = (
        master.assign(_sort=sort_key)
        .sort_values(["family", "_sort"], ascending=[True, False], na_position="last")
        .drop(columns="_sort")
        .reset_index(drop=True)
    )
    # Saída: master rankeável.
    return master


# Escreve o master em disco (.xlsx) com abas 'ranking' + 'dicionário'.
def write_master(master, outdir="output") -> Path:
    """
    Por quê: entregar o summary_ALL num arquivo à parte, com a legenda ao lado.

    Lógica (Entrada → Saída):
      Entrada: master e a pasta de saída.
      Fase 1: garante a pasta.
      Fase 2: grava 'ranking' (dados) e 'dicionário' (legenda derivada das colunas).
      Saída: caminho do summary_ALL.xlsx.
    """
    # Fase 1: normaliza a pasta e cria se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho do master.
    path = out / "summary_ALL.xlsx"
    # Fase 2: writer para as duas abas.
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Fase 2: aba de dados.
        master.to_excel(writer, sheet_name="ranking", index=False)
        # Fase 2: aba de legenda (mesma função do runner, cobre params variados).
        summary_dictionary(master).to_excel(writer, sheet_name="dicionário", index=False)
    # Saída: caminho escrito.
    return path


# Orquestração pura: de um df de preços a todos os arquivos + o master (sem rede).
def run_all(prices, indicators, param_grids, horizons, min_events: int = 5, outdir="output") -> pd.DataFrame:
    """
    Por quê: separar a consolidação (testável, sem rede) do I/O da main. Itera o
    roster, roda cada indicador com seu grid, grava o par por indicador e o master.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV, roster, grids por indicador, horizontes, mín. eventos e pasta.
      Fase 1: para cada nome do roster, importa o módulo e roda build_summary com seu grid.
      Fase 2: grava analysis_/summary_ do indicador; acumula o summary.
      Fase 3: concatena os summaries no master e grava o summary_ALL.
      Saída: o master (também escrito em disco).
    """
    # Acumulador dos summaries por indicador.
    summaries = []
    # Fase 1: percorre o roster na ordem de config.INDICATORS.
    for name in indicators:
        # Fase 1: importa o módulo-indicador pelo nome.
        module = importlib.import_module(f"robusta.indicators.{name}")
        # Fase 1: grid do indicador (fonte única = config.PARAM_GRIDS).
        grid = param_grids[name]
        # Fase 1: roda o pipeline do indicador (sem rede).
        analysis, summary = build_summary(prices, module, grid, horizons, min_events=min_events)
        # Fase 2: grava o par de arquivos do indicador.
        write_outputs(analysis, summary, name, outdir)
        # Fase 2: guarda o summary para o master.
        summaries.append(summary)
    # Fase 3: monta e grava o master.
    master = build_master(summaries)
    write_master(master, outdir)
    # Saída: o master consolidado.
    return master


# Entrypoint de linha de comando: baixa 1×, roda o roster e grava tudo.
def main(ticker: str = config.TICKER, period: str = config.PERIOD) -> None:
    """
    Por quê: ponto de entrada humano do multi-indicador; concentra o I/O (download +
    escrita). TODOS os parâmetros vêm de config.py.

    Lógica (Entrada → Saída):
      Entrada: ticker e janela relativa (defaults de config).
      Fase 1: baixa os preços uma única vez (rede).
      Fase 2: roda run_all com o roster e os grids do config.
      Saída: arquivos por indicador + summary_ALL.xlsx na pasta do config.
    """
    # Fase 1: download único dos preços.
    prices = load_prices(ticker, period)
    # Fase 2: consolida tudo (arquivos por indicador + master).
    master = run_all(
        prices, config.INDICATORS, config.PARAM_GRIDS, config.HORIZONS,
        min_events=config.MIN_EVENTS, outdir=config.OUTPUT_DIR,
    )
    # Saída: feedback no console.
    print(f"summary_ALL.xlsx ({len(master)} linhas) + pares por indicador salvos em {config.OUTPUT_DIR}/")


# Permite rodar como script: `python -m robusta.run_all`.
if __name__ == "__main__":
    # Chama main com os defaults do config.
    main()
