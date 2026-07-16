"""Fase 4 — Métricas de secuencia INDIVIDUAL.

Una secuencia es una cadena de acciones consecutivas del MISMO jugador en el
MISMO partido, separadas por menos de `ventana_gap` minutos. No reconstruye la
jugada colectiva (la base sólo tiene 1-3 jugadores tagueados por partido: la
cadena de equipo tendría 19 eslabones invisibles).

Es un eje de análisis aparte: NO toca la nota ni el % de acierto. El % mide
fiabilidad, la nota mide impacto, la secuencia mide CONTINUIDAD.

El valor de cada acción NO se define aquí: se reusa `analytics.nota_evento`,
que ya tiene el criterio de scout calibrado (Fase 2).
"""
from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd

import analytics

# ----------------------------------------------------------------------------
# CONFIG (bloque "secuencias" del diccionario canónico)
# ----------------------------------------------------------------------------
_DIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "diccionario_resultados.json")


def _cargar_cfg() -> dict[str, Any]:
    try:
        with open(_DIC_PATH, "r", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("secuencias", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


_CFG = _cargar_cfg()
VENTANA_GAP = float(_CFG.get("ventana_gap", 0.25))
MIN_ACCIONES = int(_CFG.get("min_acciones", 2))
MIN_REPETICIONES = int(_CFG.get("min_repeticiones", 3))
_FAMILIAS = _CFG.get("familias", {}) or {}
_FAMILIA_DEF = _CFG.get("familia_default", "Otros")
_PELIGRO = set(_CFG.get("desenlace_peligro", []) or [])

_COLS = ["session_id", "sesion", "jugador", "seq_id", "minuto_ini", "minuto_fin",
         "n_acciones", "acciones", "familias", "cadena", "valor", "desenlace"]


def familia(accion: str) -> str:
    """Familia de la acción (para los patrones de trigrama)."""
    return _FAMILIAS.get(accion, _FAMILIA_DEF)


def _desenlace(accion: str, resultado: str) -> str:
    """Desenlace de la cadena, marcado por su ÚLTIMA acción."""
    if accion in _PELIGRO:
        return "peligro"
    clase = analytics._clase_por_accion(accion, resultado)
    if clase in analytics._CLASES_FALLO:
        return "perdida"
    return "neutro"


def detectar_secuencias(df: pd.DataFrame) -> pd.DataFrame:
    """Cadenas de acciones consecutivas del mismo jugador y partido.

    Corta cuando el hueco con la acción anterior supera `ventana_gap` minutos.
    Devuelve TODAS las secuencias, incluidas las de una sola acción (la cabecera
    de continuidad las necesita para que la longitud media no mienta); los
    consumidores que exigen cadena filtran por `min_acciones`.
    """
    if df is None or len(df) == 0 or "minuto" not in df.columns:
        return pd.DataFrame(columns=_COLS)

    d = df.copy()
    d["minuto"] = pd.to_numeric(d["minuto"], errors="coerce")
    d = d[d["minuto"].notna()]
    if len(d) == 0:
        return pd.DataFrame(columns=_COLS)

    # Orden ESTABLE: dos eventos del mismo minuto conservan el orden de tagueo
    # (el índice original refleja el orden real de la lista `events`).
    d = d.sort_values(["session_id", "jugador", "minuto"], kind="stable")

    gap = d.groupby(["session_id", "jugador"], sort=False)["minuto"].diff()
    corte = (gap.isna()) | (gap > VENTANA_GAP)
    d["seq_id"] = corte.cumsum()

    filas = []
    for seq_id, g in d.groupby("seq_id", sort=True):
        acciones = list(g["accion"])
        ult = g.iloc[-1]
        valor = 0.0
        for _, ev in g.iterrows():
            v = analytics.nota_evento(ev["accion"], ev.get("resultado", ""),
                                      ev.get("zona_x"))
            if v is not None:
                valor += v
        filas.append({
            "session_id": g.iloc[0]["session_id"],
            "sesion": g.iloc[0].get("sesion", ""),
            "jugador": g.iloc[0]["jugador"],
            "seq_id": int(seq_id),
            "minuto_ini": float(g["minuto"].iloc[0]),
            "minuto_fin": float(g["minuto"].iloc[-1]),
            "n_acciones": len(g),
            "acciones": acciones,
            "familias": [familia(a) for a in acciones],
            "cadena": " > ".join(acciones),
            "valor": round(valor, 3),
            "desenlace": _desenlace(ult["accion"], ult.get("resultado", "")),
        })
    return pd.DataFrame(filas, columns=_COLS)
