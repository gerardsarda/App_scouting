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
    assert analytics.set_de_posicion("MED") == "MC/MCD"
    assert analytics.set_de_posicion("MC") == "MC/MCD"
    assert analytics.set_de_posicion("") == "MC/MCD"


def test_sugerir_set_mantiene_comportamiento_para_el_radar():
    try:
        import scouting_app
    except Exception as e:
        pytest.skip(f"No se puede importar scouting_app fuera de Streamlit: {e}")

    # POR cae en MC/MCD para el radar (no hay set POR en el spider), como antes.
    esperado = {"EXT": "EXT", "MED": "MC/MCD", "LD": "LAT", "MC": "MC/MCD",
                "DFC": "DFC", "DC": "DC", "POR": "MC/MCD", "MP": "MP", "": "MC/MCD"}
    for pos, exp in esperado.items():
        assert scouting_app._sugerir_set(pos, None) == exp
