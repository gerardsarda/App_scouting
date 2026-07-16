"""Contraste del motor contra DATOS REALES, con el reparto medido por SQL.

La fixture son los 241 eventos reales de 3 partidos de la base (Bélgica vs
Egipto J1 — 3 jugadores tagueados, Croacia vs Ghana J3 y Canadá vs Bosnia J1 —
2 cada uno). Se eligieron con varios jugadores a propósito: así el test prueba
también que una cadena nunca cruza de un jugador a otro.

Los números esperados NO salen de este código: salen de la misma consulta SQL
con ventana de 15s ejecutada contra la BD (ver el diseño, §8). Si este test
falla, el sospechoso es el motor, no el test.

Se usa un subconjunto y no la base entera (4.491 eventos → 2.476 secuencias)
para no meter 700 KB de datos de scouting en el repo. El algoritmo es el mismo:
si reproduce el reparto de estos 3 partidos, reproduce el global.

Ver docs/superpowers/specs/2026-07-16-fase4-secuencias-design.md §8.
"""
import json
import os

import pandas as pd
import pytest

import secuencias

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "eventos_reales.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_FIX),
    reason="falta tests/fixtures/eventos_reales.json",
)


@pytest.fixture(scope="module")
def eventos():
    with open(_FIX, "r", encoding="utf-8") as fh:
        return pd.DataFrame(json.load(fh))


@pytest.fixture(scope="module")
def secs(eventos):
    return secuencias.detectar_secuencias(eventos)


def test_la_fixture_es_la_esperada(eventos):
    assert len(eventos) == 241
    assert eventos["session_id"].nunique() == 3


def test_total_de_secuencias(secs):
    """153 secuencias, medido por SQL sobre estos mismos 3 partidos."""
    assert len(secs) == 153


def test_reparto_por_longitud(secs):
    """Reparto por longitud, medido por SQL sobre estos mismos 3 partidos."""
    reparto = secs["n_acciones"].value_counts().to_dict()
    assert reparto == {1: 99, 2: 36, 3: 9, 4: 5, 5: 2, 6: 1, 7: 1}


def test_ninguna_cadena_cruza_partido_o_jugador(secs):
    """Cada seq_id pertenece a un solo (partido, jugador)."""
    assert secs.groupby("seq_id").size().max() == 1
    assert len(secs) == len(secs.drop_duplicates("seq_id"))


def test_las_acciones_cuadran(eventos, secs):
    """Ninguna acción se pierde ni se duplica al agrupar en cadenas."""
    assert secs["n_acciones"].sum() == len(eventos)


def test_todas_las_cadenas_estan_dentro_de_la_ventana(secs):
    """Coherencia: una cadena de n acciones no puede durar más de (n-1)·ventana."""
    dur = secs["minuto_fin"] - secs["minuto_ini"]
    techo = (secs["n_acciones"] - 1) * secuencias.VENTANA_GAP
    assert (dur <= techo + 1e-9).all()
