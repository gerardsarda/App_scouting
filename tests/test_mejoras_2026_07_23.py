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


# --- P3: mapas sensibles a aciertos -----------------------------------------

def test_zone_grid_solo_exito_cuenta_solo_aciertos():
    df = _df([("Ana", "Regate 1v1", "Correcto"), ("Ana", "Regate 1v1", "Fallo")],
             zona_x=2, zona_y=1)
    assert int(analytics.zone_grid_counts(df).sum()) == 2
    assert int(analytics.zone_grid_counts(df, solo_exito=True).sum()) == 1


# --- P5: franjas de prórroga ------------------------------------------------

def test_franjas_incluyen_prorroga():
    assert (90, 105) in analytics.FRANJAS_15
    assert (105, 200) in analytics.FRANJAS_15
    assert analytics.FRANJA_LABELS[-2:] == ["90-105", "105+"]


def test_influencia_separa_105():
    df = _df([("Ana", "Regate 1v1", "Correcto"), ("Ana", "Regate 1v1", "Correcto")])
    df.loc[0, "minuto"] = 95.0
    df.loc[1, "minuto"] = 110.0
    r = analytics.influencia_por_minuto(df, "Ana")
    i1 = analytics.FRANJA_LABELS.index("90-105")
    i2 = analytics.FRANJA_LABELS.index("105+")
    assert r["volumen"][i1] == 1
    assert r["volumen"][i2] == 1


# --- P6: evolución por-90 ---------------------------------------------------

def test_serie_temporal_por90_usa_minutos_del_partido():
    df = _df([("Ana", "Pase progresivo", "Correcto"),
              ("Ana", "Pase progresivo", "Fallo")])
    df["jugador_info"] = [{"min_in": 0, "min_out": 45}, {"min_in": 0, "min_out": 45}]
    serie = analytics.serie_temporal(df, "Ana", ["Pase progresivo"], "totales90")
    assert len(serie) == 1
    assert serie[0]["valor"] == 4.0
    serie_ac = analytics.serie_temporal(df, "Ana", ["Pase progresivo"], "aciertos90")
    assert serie_ac[0]["valor"] == 2.0


# --- P1: motor de Estadísticas ----------------------------------------------

def test_seccion_stats_reparte_bien():
    assert analytics._seccion_stats("Duelo en ABP def.") == "ABP"
    assert analytics._seccion_stats("Remate a balón parado") == "ABP"
    assert analytics._seccion_stats("Tarjeta amarilla") == "Disciplina"
    assert analytics._seccion_stats("Penalti cometido") == "Disciplina"
    assert analytics._seccion_stats("Penalti provocado") != "Disciplina"
    assert analytics._seccion_stats("Remate") == "Ataque"
    assert analytics._seccion_stats("Regate 1v1") == "Ataque"
    assert analytics._seccion_stats("Pase atrás") == "Pase"
    assert analytics._seccion_stats("Despeje") == "Defensa"


def test_estadisticas_pliega_pase_progresivo():
    df = _df([("Ana", "Pase progresivo", "Correcto"),
              ("Ana", "Pase entre líneas", "Correcto"),
              ("Ana", "Pase atrás", "Fallo")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    labels = [f["label"] for f in out["Pase"]]
    assert "Pase progresivo" in labels
    assert "Pase entre líneas" not in labels
    fila = next(f for f in out["Pase"] if f["label"] == "Pase progresivo")
    assert fila["total"] == 2
    assert fila["aciertos"] == 2
    assert fila["tiene_pct"] is True


def test_estadisticas_incluye_agregadas():
    df = _df([("Ana", "Pase progresivo", "Fallo"), ("Ana", "Regate 1v1", "Fallo")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    assert "Agregadas" in out
    perd = next(f for f in out["Agregadas"] if f["label"] == "Pérdidas")
    assert perd["total"] == 2 and perd["tiene_pct"] is False


def test_estadisticas_disciplina_es_conteo_no_pct():
    df = _df([("Ana", "Tarjeta amarilla", "Tarjeta amarilla"),
              ("Ana", "Falta", "Falta")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    for f in out["Disciplina"]:
        assert f["tiene_pct"] is False, f["label"]
        assert f["pct"] is None
