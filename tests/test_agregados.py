# -*- coding: utf-8 -*-
"""Acciones agregadas del dashboard (Pérdidas, Progresión, Peligro, Duelos,
Disciplina) y la expansión de "Pase progresivo" al total del diccionario."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


def _df(filas):
    """(jugador, accion, resultado) -> df con las columnas que usa el motor."""
    base = [{"session_id": "s1", "sesion": "S1", "fecha": "2026-01-01",
             "jugador": j, "posicion": "MC", "accion": a, "resultado": r,
             "zona_x": 1, "zona_y": 1, "minuto": 10.0}
            for j, a, r in filas]
    df = pd.DataFrame(base)
    df["exito"] = df.apply(lambda x: analytics.is_success(x["resultado"], x["accion"]), axis=1)
    df["intento"] = df.apply(lambda x: analytics.is_attempt(x["resultado"], x["accion"]), axis=1)
    df["peso"] = df.apply(lambda x: analytics.success_weight(x["resultado"], x["accion"]), axis=1)
    return df


# --- expansión de Pase progresivo -------------------------------------------

def test_pase_prog_equiv_son_las_cinco_del_diccionario():
    assert analytics.PASE_PROG_EQUIV == [
        "Pase progresivo", "Pase entre líneas", "Pase al espacio",
        "Pase en largo", "Cambio de orientación"]


def test_mini_tarjeta_pase_prog_usa_el_total():
    assert analytics.METRICAS_DASH["pase_prog"]["acciones"] == analytics.PASE_PROG_EQUIV


def test_expandir_solo_si_la_seleccion_es_pase_progresivo_solo():
    assert analytics.expandir_pase_prog(["Pase progresivo"]) == analytics.PASE_PROG_EQUIV
    # en modo Categoría cada equivalente tiene su casilla: expandir duplicaría
    assert analytics.expandir_pase_prog(["Pase progresivo", "Pase atrás"]) == \
        ["Pase progresivo", "Pase atrás"]
    assert analytics.expandir_pase_prog(["Regate 1v1"]) == ["Regate 1v1"]


# --- composición de los agregados -------------------------------------------

def test_perdidas_son_15_acciones_y_solo_fallos():
    spec = analytics.ACCIONES_AGREGADAS["Pérdidas"]
    assert len(spec["acciones"]) == 15
    assert len(set(spec["acciones"])) == 15, "hay acciones repetidas"
    assert spec["clases"] == analytics._CLASES_FALLO
    assert spec["solo_conteo"] is True
    # decisión explícita del scout: la acción "Error grave / pérdida" NO entra
    assert "Error grave / pérdida" not in spec["acciones"]


def test_perdidas_incluye_las_cinco_del_pase_progresivo():
    accs = analytics.ACCIONES_AGREGADAS["Pérdidas"]["acciones"]
    for a in analytics.PASE_PROG_EQUIV:
        assert a in accs


@pytest.mark.parametrize("nombre", list(analytics.ACCIONES_AGREGADAS))
def test_todo_agregado_usa_acciones_del_diccionario(nombre):
    """Un typo en un nombre de acción daría un agregado silenciosamente incompleto."""
    conocidas = set(analytics._DIC_ACCIONES)
    if not conocidas:
        pytest.skip("diccionario no cargado")
    accs = set(analytics.ACCIONES_AGREGADAS[nombre]["acciones"])
    # "Duelo en córner def." no está en el diccionario; se conserva por paridad
    # con similitud.DUELOS_TOTALES (ver CLAUDE.md §7).
    assert accs - conocidas <= {"Duelo en córner def."}


def test_duelos_totales_no_derivan_de_similitud():
    """Guardarraíl: analytics no puede importar similitud (ciclo), así que la
    lista está duplicada. Si alguien toca una y no la otra, esto salta."""
    import similitud
    assert analytics._DUELOS_TOTALES == similitud.DUELOS_TOTALES


def test_perdidas_del_dashboard_es_mas_amplia_que_la_de_similitud():
    """Son dos definiciones distintas a propósito (CLAUDE.md §7). El test fija
    esa divergencia para que no se unifiquen sin decidirlo."""
    import similitud
    dash = set(analytics.ACCIONES_AGREGADAS["Pérdidas"]["acciones"])
    assert set(similitud.PERDIDAS_POR_FALLO) < dash
    assert similitud.PERDIDA_SIEMPRE not in dash


# --- cálculo -----------------------------------------------------------------

def test_perdidas_cuenta_solo_los_fallos():
    df = _df([
        ("Ana", "Pase progresivo", "Correcto"),
        ("Ana", "Pase progresivo", "Fallo"),
        ("Ana", "Regate 1v1", "Fallo"),
        ("Ana", "Control fácil fallado", "Control fácil fallado"),
        ("Ana", "Recuperación", "Correcto"),   # fuera del agregado
        ("Leo", "Pase lateral", "Fallo"),
    ])
    spec = analytics.ACCIONES_AGREGADAS["Pérdidas"]
    val = analytics.metrica_jugador(df, "Ana", spec["acciones"], "totales",
                                    clases=spec["clases"])
    assert val == 3.0
    assert analytics.metrica_jugador(df, "Leo", spec["acciones"], "totales",
                                     clases=spec["clases"]) == 1.0


def test_filtrar_clases_sin_clases_no_filtra():
    df = _df([("Ana", "Pase progresivo", "Correcto"), ("Ana", "Pase progresivo", "Fallo")])
    assert len(analytics.filtrar_clases(df, None)) == 2
    assert len(analytics.filtrar_clases(df, set())) == 2


def test_serie_temporal_respeta_las_clases():
    filas = [("Ana", "Regate 1v1", "Correcto"), ("Ana", "Regate 1v1", "Fallo")]
    df = _df(filas)
    df.loc[1, "session_id"] = "s2"
    df.loc[1, "sesion"] = "S2"
    df.loc[1, "fecha"] = "2026-01-02"
    spec = analytics.ACCIONES_AGREGADAS["Pérdidas"]
    serie = analytics.serie_temporal(df, "Ana", spec["acciones"], "totales",
                                     clases=spec["clases"])
    assert len(serie) == 1 and serie[0]["valor"] == 1.0


def test_radar_acepta_un_agregado_como_eje():
    df = _df([
        ("Ana", "Pase progresivo", "Fallo"),
        ("Ana", "Regate 1v1", "Fallo"),
        ("Ana", "Regate 1v1", "Correcto"),
        ("Ana", "Pase clave", "Correcto"),
    ])
    ejes = ["Pérdidas", "Progresión", "Peligro generado"]
    labels, vals = analytics.radar_ejes_seleccion(df, "Ana", ejes, "totales")
    assert labels == ejes
    # Pérdidas 2 (pase prog fallado + regate fallado), Progresión 3, Peligro 1
    # normalizado al máximo (3) -> 66.7, 100, 33.3
    assert vals == [66.7, 100.0, 33.3]


def test_agregados_disponibles_omite_los_vacios():
    df = _df([("Ana", "Pase progresivo", "Correcto")])
    disp = analytics.agregados_disponibles(df)
    assert "Pérdidas" in disp and "Progresión" in disp
    assert "Disciplina" not in disp
    assert "Peligro generado" not in disp
