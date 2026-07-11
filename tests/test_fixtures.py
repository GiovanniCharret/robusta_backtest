# Teste: a fixture de volume tem Volume variável e positivo (obv/vwap dependem disso).
def test_synthetic_prices_volume_has_variable_positive_volume(synthetic_prices_volume):
    """
    Por quê: obv/vwap/alto_volume/exaustao_atr precisam de Volume que varia; a
    fixture antiga tinha Volume constante (não geraria sinal útil).

    Lógica: Entrada (fixture) → Fase 1 schema OHLCV → Fase 2 volume varia e é > 0 → Saída.
    """
    # Fase 1: schema OHLCV presente.
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        assert col in synthetic_prices_volume.columns
    # Fase 2: Volume varia (>1 valor distinto) e é estritamente positivo.
    vol = synthetic_prices_volume["Volume"]
    assert vol.nunique() > 1
    assert (vol > 0).all()
