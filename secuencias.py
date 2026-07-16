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


# ----------------------------------------------------------------------------
# CONSUMIDORES
# ----------------------------------------------------------------------------
def _del_jugador(secs: pd.DataFrame, jugador: str) -> pd.DataFrame:
    if secs is None or len(secs) == 0:
        return pd.DataFrame(columns=_COLS)
    return secs[secs["jugador"] == jugador]


def continuidad(secs: pd.DataFrame, jugador: str,
                minutos: float | None = None) -> dict[str, float]:
    """Eje descriptivo: ¿aparece y se va, o sostiene la jugada?

    Cuenta TODAS las secuencias (también las de una acción): si se excluyeran,
    el largo medio y los % saldrían inflados. `minutos` = minutos jugados, para
    el por-90 (None -> secuencias_90 = 0.0).
    """
    d = _del_jugador(secs, jugador)
    n = len(d)
    if n == 0:
        return {"n_secuencias": 0, "largo_medio": 0.0, "pct_peligro": 0.0,
                "pct_perdida": 0.0, "secuencias_90": 0.0}
    return {
        "n_secuencias": n,
        "largo_medio": float(d["n_acciones"].mean()),
        "pct_peligro": float(100.0 * (d["desenlace"] == "peligro").sum() / n),
        "pct_perdida": float(100.0 * (d["desenlace"] == "perdida").sum() / n),
        "secuencias_90": float(90.0 * n / minutos) if minutos else 0.0,
    }


def top_secuencias(secs: pd.DataFrame, jugador: str, n: int = 10,
                   ascendente: bool = False,
                   desenlace: str | None = None) -> pd.DataFrame:
    """Localizador de jugadas para vídeo: las cadenas de más (o menos) valor,
    con su minuto de entrada. Exige `min_acciones`: una acción suelta no es una
    jugada que se pueda recortar."""
    d = _del_jugador(secs, jugador)
    d = d[d["n_acciones"] >= MIN_ACCIONES]
    if desenlace:
        d = d[d["desenlace"] == desenlace]
    return d.sort_values("valor", ascending=ascendente).head(n)


def patrones_bigrama(secs: pd.DataFrame, jugador: str,
                     accion_origen: str) -> pd.DataFrame:
    """Tras `accion_origen`, ¿qué hace? Distribución de la acción siguiente
    dentro de la misma cadena, con veces y %."""
    d = _del_jugador(secs, jugador)
    siguientes: list[str] = []
    for acciones in d["acciones"]:
        for i, a in enumerate(acciones[:-1]):
            if a == accion_origen:
                siguientes.append(acciones[i + 1])
    if not siguientes:
        return pd.DataFrame(columns=["siguiente", "veces", "pct"])
    out = (pd.Series(siguientes).value_counts()
           .rename_axis("siguiente").reset_index(name="veces"))
    out["pct"] = 100.0 * out["veces"] / out["veces"].sum()
    return out


def patrones_familia(secs: pd.DataFrame, jugador: str,
                     min_repes: int | None = None) -> pd.DataFrame:
    """Trigramas por FAMILIA de acción (ej. Progresa con balón > Encara >
    Sirve peligro), con el nº de veces.

    Por familia y no por acción exacta a propósito: medido sobre la base real,
    los trigramas de acción exacta no se repiten por jugador (1 solo caso en
    4.491 eventos). Ver el diseño de la Fase 4, §3.
    """
    umbral = MIN_REPETICIONES if min_repes is None else int(min_repes)
    d = _del_jugador(secs, jugador)
    patrones: list[str] = []
    for fams in d["familias"]:
        for i in range(len(fams) - 2):
            patrones.append(" > ".join(fams[i:i + 3]))
    if not patrones:
        return pd.DataFrame(columns=["patron", "veces"])
    out = (pd.Series(patrones).value_counts()
           .rename_axis("patron").reset_index(name="veces"))
    out = out[out["veces"] >= umbral]
    return out.reset_index(drop=True)
