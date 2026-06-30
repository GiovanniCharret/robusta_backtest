# O módulo de configuração centralizada sob teste.
from robusta import config
# A orquestração pura, para provar que os grids do config alimentam o pipeline.
from robusta.run_mma import build_summary


# Teste: o config expõe todos os parâmetros, bem formados.
def test_config_is_wellformed():
    """
    Por quê: o config é o painel de ajustes manual; se um parâmetro sumir ou vier
    com tipo errado, o run_mma quebra. Este teste trava o contrato do config.

    Lógica: Entrada (config) → Fase 1 dados → Fase 2 grids → Fase 3 modelagem/saída → Saída.
    """
    # Fase 1: ticker e period são strings não-vazias.
    assert isinstance(config.TICKER, str) and config.TICKER
    assert isinstance(config.PERIOD, str) and config.PERIOD
    # Fase 2: os três grids são listas não-vazias.
    for grid in (config.MMA_WINDOWS, config.TOLERANCES, config.HORIZONS):
        assert isinstance(grid, list) and len(grid) >= 1
    # Fase 3: min_events é inteiro >= 1 e a pasta de saída é string não-vazia.
    assert isinstance(config.MIN_EVENTS, int) and config.MIN_EVENTS >= 1
    assert isinstance(config.OUTPUT_DIR, str) and config.OUTPUT_DIR


# Teste: os grids do config geram o nº esperado de modelos (integração, sem rede).
def test_config_grids_drive_build_summary(synthetic_prices):
    """
    Por quê: garantir que os grids do config são válidos e atravessam o pipeline —
    nº de linhas = |windows|×|tols|×|horizons|×2 famílias.

    Lógica: Entrada (config + preços sintéticos) → Fase 1 build_summary → Fase 2 contagem.
    """
    # Fase 1: roda o pipeline com EXATAMENTE os grids do config.
    _, summary = build_summary(
        synthetic_prices,
        windows=config.MMA_WINDOWS,
        tols=config.TOLERANCES,
        horizons=config.HORIZONS,
        min_events=config.MIN_EVENTS,
    )
    # Fase 2/Saída: contagem bate com o produto do grid × 2 famílias.
    esperado = len(config.MMA_WINDOWS) * len(config.TOLERANCES) * len(config.HORIZONS) * 2
    assert len(summary) == esperado
