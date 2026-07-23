# -*- coding: utf-8 -*-
"""Tests de las mejoras del 2026-07-23 (dashboard + sección Estadísticas)."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


def _df(filas, **cols):
    """(jugador, accion, resultado) -> df con las columnas que usa el motor.
    cols permite fijar columnas extra (zona_x, minuto...) para todas las filas."""
    base = []
    for j, a, r in filas:
        fila = {"session_id": "s1", "sesion": "S1", "fecha": "2026-01-01",
                "jugador": j, "posicion": "MC", "accion": a, "resultado": r,
                "zona_x": 1, "zona_y": 1, "minuto": 10.0}
        fila.update(cols)
        base.append(fila)
    df = pd.DataFrame(base)
    df["exito"] = df.apply(lambda x: analytics.is_success(x["resultado"], x["accion"]), axis=1)
    df["intento"] = df.apply(lambda x: analytics.is_attempt(x["resultado"], x["accion"]), axis=1)
    df["peso"] = df.apply(lambda x: analytics.success_weight(x["resultado"], x["accion"]), axis=1)
    return df


def _sesion(jug, equipo, local, visit, nivel_propio, nivel_rival, eventos,
            sid=None, min_in=0, min_out=90):
    """Sesión mínima para flatten_events. nivel_propio/nivel_rival se guardan
    tal cual en meta (= niveles de LOCAL/VISITANTE, como en la BD real)."""
    return {"id": sid or f"{local}-{visit}", "nombre": f"{local} vs {visit}",
            "fecha": "2026-01-01", "equipo_local": local, "equipo_visitante": visit,
            "meta": {"nivel_propio": nivel_propio, "nivel_rival": nivel_rival},
            "jugadores_info": {jug: {"equipo": equipo, "min_in": min_in, "min_out": min_out}},
            "events": eventos}


# --- P4: nivel de rival en perspectiva del jugador --------------------------

def test_nivel_rival_visitante_se_intercambia():
    # Nusa juega en Noruega, de VISITANTE en Irak vs Noruega. meta guarda
    # nivel_propio=Bajo (Irak, local) y nivel_rival=Alto (Noruega, visitante).
    s = _sesion("Nusa", "Noruega", "Irak", "Noruega", "Bajo", "Alto",
                [{"jugador": "Nusa", "accion": "Regate 1v1", "resultado": "Correcto",
                  "minuto": 10, "zona_x": 2, "zona_y": 1}])
    df = analytics.flatten_events([s])
    assert df.iloc[0]["nivel_propio"] == "Alto"   # su equipo (Noruega)
    assert df.iloc[0]["nivel_rival"] == "Bajo"    # el rival (Irak)


def test_nivel_rival_local_no_se_toca():
    s = _sesion("Irankunda", "Australia", "Australia", "Turquia", "Medio", "Alto",
                [{"jugador": "Irankunda", "accion": "Regate 1v1", "resultado": "Correcto",
                  "minuto": 10, "zona_x": 2, "zona_y": 1}])
    df = analytics.flatten_events([s])
    assert df.iloc[0]["nivel_propio"] == "Medio"
    assert df.iloc[0]["nivel_rival"] == "Alto"


def test_niveles_rival_de_jugador_y_filtro():
    s1 = _sesion("Nusa", "Noruega", "Irak", "Noruega", "Bajo", "Alto",
                 [{"jugador": "Nusa", "accion": "Regate 1v1", "resultado": "Correcto",
                   "minuto": 10, "zona_x": 2, "zona_y": 1}], sid="p1")
    s2 = _sesion("Nusa", "Noruega", "Noruega", "Francia", "Alto", "Élite",
                 [{"jugador": "Nusa", "accion": "Regate 1v1", "resultado": "Fallo",
                   "minuto": 20, "zona_x": 2, "zona_y": 1}], sid="p2")
    df = analytics.flatten_events([s1, s2])
    niveles = analytics.niveles_rival_de_jugador(df, "Nusa")
    assert niveles == {"p1": "Bajo", "p2": "Élite"}
    d = analytics.filtrar_por_nivel_rival(df, "Nusa", "Élite")
    assert set(d["session_id"].unique()) == {"p2"}
    # 'Todos' o vacío no filtra
    assert len(analytics.filtrar_por_nivel_rival(df, "Nusa", "Todos")) == 2
