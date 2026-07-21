"""Tests del motor de expectativa de acierto (Fase 5).

Fixtures SINTÉTICAS y deterministas: no tocan Supabase ni la red. Los valores
esperados del suavizado se calculan a mano con k=8 (ver el plan).
"""
import pandas as pd
import pytest

import analytics


def test_set_de_posicion_mapea_los_6_sets_mas_por():
    assert analytics.set_de_posicion("EXT") == "EXT"
    assert analytics.set_de_posicion("MP") == "MP"
    assert analytics.set_de_posicion("DC") == "DC"
    assert analytics.set_de_posicion("DFC") == "DFC"
    assert analytics.set_de_posicion("LD") == "LAT"
    assert analytics.set_de_posicion("LI") == "LAT"
    assert analytics.set_de_posicion("POR") == "POR"
    # MED (mediocentro ofensivo) agrupa con la mediapunta (decisión del usuario).
    assert analytics.set_de_posicion("MED") == "MP"
    # EI/ED (extremos) siguen cayendo en EXT sin colisionar con MED.
    assert analytics.set_de_posicion("EI") == "EXT"
    assert analytics.set_de_posicion("ED") == "EXT"
    assert analytics.set_de_posicion("MC") == "MC/MCD"
    assert analytics.set_de_posicion("") == "MC/MCD"


def test_sugerir_set_mantiene_comportamiento_para_el_radar():
    try:
        import scouting_app
    except Exception as e:
        pytest.skip(f"No se puede importar scouting_app fuera de Streamlit: {e}")

    # POR cae en MC/MCD para el radar (no hay set POR en el spider).
    # MED va con MP (mediapunta), decisión del usuario.
    esperado = {"EXT": "EXT", "MED": "MP", "LD": "LAT", "MC": "MC/MCD",
                "DFC": "DFC", "DC": "DC", "POR": "MC/MCD", "MP": "MP", "": "MC/MCD"}
    for pos, exp in esperado.items():
        assert scouting_app._sugerir_set(pos, None) == exp


def test_cfg_expectativa_tiene_defaults():
    cfg = analytics._EXP_CFG
    assert cfg["k"] == 8.0
    assert cfg["min_muestra_resumen"] == 3
    assert cfg["umbral_destaca"] == 15.0


def test_tercio_de_prioriza_zona_x_y_cae_al_texto():
    assert analytics._tercio_de(0, "lo que sea") == 0
    assert analytics._tercio_de(2, "") == 2
    assert analytics._tercio_de(None, "1er tercio · Centro") == 0
    assert analytics._tercio_de(None, "2º tercio · Banda der.") == 1
    assert analytics._tercio_de(None, "3er tercio · Centro") == 2
    assert analytics._tercio_de(None, "zona rara") is None


def _df_pp(rows):
    """rows = lista de (jugador, posicion, zona_x, intento, peso).
    Construye el df mínimo que consume el motor de expectativa."""
    return pd.DataFrame(
        [{"jugador": j, "posicion": p, "accion": "Pase progresivo",
          "zona": "2º tercio · Centro", "zona_x": zx, "intento": i, "peso": w}
         for (j, p, zx, i, w) in rows]
    )


def _fixture_pp():
    # Central (DFC): 20 intentos, 19 aciertos (peso 1) + 1 fallo (peso 0)
    # Lateral (LD):  10 intentos, 10 aciertos
    # Punta (DC):     4 intentos,  0 aciertos
    rows = []
    rows += [("Central", "DFC", 1, True, 1.0)] * 19 + [("Central", "DFC", 1, True, 0.0)]
    rows += [("Lateral", "LD", 1, True, 1.0)] * 10
    rows += [("Punta", "DC", 1, True, 0.0)] * 4
    return _df_pp(rows)


def test_agregados_cuenta_por_nivel():
    agg = analytics.agregados_expectativa(_fixture_pp())
    assert agg["global"] == (29.0, 34)
    assert agg["categoria"]["Pase"] == (29.0, 34)
    assert agg["accion"]["Pase progresivo"] == (29.0, 34)
    assert agg["accion_tercio"][("Pase progresivo", 1)] == (29.0, 34)
    assert agg["accion_tercio_pos"][("Pase progresivo", 1, "DFC")] == (19.0, 20)
    assert agg["accion_tercio_pos"][("Pase progresivo", 1, "DC")] == (0.0, 4)
    assert agg["accion_tercio_jug"][("Pase progresivo", 1, "Punta")] == (0.0, 4)


def test_predecir_suaviza_el_caso_ruidoso_del_dc():
    agg = analytics.agregados_expectativa(_fixture_pp())
    # Punta: 4 intentos, 0 aciertos crudos -> NO debe salir 0%.
    out = analytics.predecir_acierto(agg, "Punta", "Pase progresivo", 1, "DC", k=8.0)
    assert out["n_jugador"] == 4
    assert out["aciertos_jugador"] == 0.0
    # Expectativa de su posición (nivel 3, set DC) y predicción (nivel 4).
    assert out["expectativa_pos"] == pytest.approx(0.5686274510, abs=1e-6)
    assert out["pred"] == pytest.approx(0.3790849673, abs=1e-6)
    assert out["set"] == "DC"


def test_predecir_alto_tape_se_queda_cerca_del_crudo():
    agg = analytics.agregados_expectativa(_fixture_pp())
    # Central: 20 intentos, 19 aciertos (95% crudo) -> predicción alta.
    out = analytics.predecir_acierto(agg, "Central", "Pase progresivo", 1, "DFC", k=8.0)
    assert out["pred"] == pytest.approx(0.9420768, abs=1e-5)
    assert out["expectativa_pos"] == pytest.approx(0.9222689, abs=1e-5)


def test_predecir_sin_datos_del_jugador_cae_a_la_expectativa():
    agg = analytics.agregados_expectativa(_fixture_pp())
    # Jugador inexistente en ese combo: pred == expectativa_pos (prior puro).
    out = analytics.predecir_acierto(agg, "Nadie", "Pase progresivo", 1, "DC", k=8.0)
    assert out["n_jugador"] == 0
    assert out["pred"] == pytest.approx(out["expectativa_pos"], abs=1e-9)


def test_resumen_incluye_combos_por_encima_del_minimo_y_etiqueta():
    df = _fixture_pp()
    agg = analytics.agregados_expectativa(df)
    filas = analytics.resumen_expectativa_jugador(
        df, agg, "Punta", k=8.0, min_muestra=3, umbral=15.0)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["accion"] == "Pase progresivo"
    assert fila["tercio"] == 1
    assert fila["n_jugador"] == 4
    assert fila["pct_real"] == pytest.approx(0.0, abs=1e-9)
    assert fila["pred"] == pytest.approx(0.3790849673, abs=1e-6)
    assert fila["expectativa_pos"] == pytest.approx(0.5686274510, abs=1e-6)
    # diff = round((0.37908 - 0.56863) * 100) = -19 -> |19| >= 15 -> "por debajo"
    assert fila["diff_pts"] == -19
    assert fila["etiqueta"] == "por debajo"


def test_resumen_descarta_combos_con_muestra_insuficiente():
    df = _df_pp([("Solo", "MC", 1, True, 1.0)] * 2)  # 2 intentos < min_muestra 3
    agg = analytics.agregados_expectativa(df)
    filas = analytics.resumen_expectativa_jugador(
        df, agg, "Solo", k=8.0, min_muestra=3, umbral=15.0)
    assert filas == []


def test_no_queda_codigo_muerto_de_prediccion_vieja():
    assert not hasattr(analytics, "predict_player_trend")
    assert not hasattr(analytics, "train_outcome_model")
    assert not hasattr(analytics, "patrones_tacticos_datos")
