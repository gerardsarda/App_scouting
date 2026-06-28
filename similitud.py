"""
similitud.py — Modelo de similitud Nivel 1 integrado en la app.

Construye el vector por-90 de un jugador ojeado (28 features), lo estandariza
(z-score) contra el grupo de tops de su posición del CSV, y devuelve el ranking
de parecidos por similitud coseno + perfil de en qué destaca/floja.

Autónomo: usa los helpers de analytics.py (minutos_de_jugador, zonas), NO depende
del MCP ni de dossier.py. El CSV de tops se lee del repo (mismo directorio).
"""
from __future__ import annotations
import os
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

import analytics

# CSV de tops: en el repo, junto a este archivo.
CSV_TOPS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CSV_TOPS.csv")

# --- Resultados (strings exactos del esquema) ---
EXITO = "Correcto"
GOL = "Gol"
FUERA, BLOQUEADO, REGATEADO, NO_ENCONTRADO = "Fuera", "Bloqueado", "Regateado", "No encontrado"
FALLO = "Fallo"

PASES_9 = ["Pase atrás", "Pase progresivo", "Pase lateral", "Pase entre líneas",
           "Pase en largo", "Pase al espacio", "Centro lateral",
           "Cambio de orientación", "Pase de primera"]
REMATES_TIRO = ["Remate", "Remate de cabeza", "Remate desde fuera",
                "Remate a balón parado", "Falta directa a puerta"]
DUELOS_TOTALES = ["Duelo aéreo def.", "Duelo aéreo of.", "Regate 1v1",
                  "Duelo 1v1 def.", "Duelo en ABP def.", "Duelo en córner def."]
AEREOS = ["Duelo aéreo def.", "Duelo aéreo of.", "Duelo en ABP def.", "Duelo en córner def."]
ACC_DEFENSIVAS = ["Entrada / tackle", "Intercepción", "Despeje", "Recuperación",
                  "Bloqueo tiro/centro", "Duelo 1v1 def.", "Anticipación"]
RECUPERACIONES = ["Intercepción", "Recuperación", "Duelo 1v1 def.", "Anticipación"]
POSESION_3T = ["Recuperación", "Intercepción", "Entrada / tackle",
               "Presión fuerza error", "Duelo 1v1 def.", "Anticipación"]
PERDIDAS_POR_FALLO = ["Regate 1v1", "Conducción progresiva", "Control difícil",
                      "Protección de balón"]
PERDIDA_SIEMPRE = "Error grave / pérdida"
FALTAS_RECIBIDAS = ["Falta recibida", "Penalti provocado"]

TOQUES_EXCLUIR = {"Sprint def.", "Sprint of. sin balón", "Sprint of. con balón",
                  "Pase clave", "Asistencia", "Presión fuerza error",
                  "Tarjeta amarilla", "Tarjeta roja", "Penalti cometido",
                  "Falta recibida", "Pase bajo presión"}
DESMARQUES = {"Desmarque de apoyo", "Desmarque de arrastre", "Desmarque de ruptura",
              "Ofrece línea de pase", "Recibe entre líneas", "Amplía el campo",
              "Entrada en área rival"}

# Las 28 features del modelo, en orden.
FEATURES = [
    "Goles", "Tiro", "Asistencias", "Pases completados", "Pases completados %",
    "Tiros largos precisos", "Balones largos precisos %", "Centros completados",
    "Regates realizados", "Regates realizados %", "Duelos ganados",
    "Duelos ganados %", "Aéreo ganado", "% de duelos aéreos ganados",
    "Pérdidas de balón", "Faltas recibidas", "Acciones defensivas", "Entradas",
    "Intercepciones", "Tiros bloqueados", "Faltas", "Recuperaciones",
    "Regateado", "Despejes", "Posesion ganada en 3r Tercio", "Toques",
    "Tarjetas amarillas", "Tarjetas rojas",
]


def _es_tercio_ofensivo(ev) -> bool:
    """True si la acción ocurrió en el último tercio. Usa zona_x==2 (rejilla nueva)
    o la zona antigua de texto."""
    zx = ev.get("zona_x")
    if zx is not None and zx != "":
        try:
            return int(zx) == 2
        except (ValueError, TypeError):
            pass
    z = (ev.get("zona") or "").lower()
    return "3er tercio" in z or "ofensiv" in z


def construir_vector(sesiones: list[dict[str, Any]], jugador: str) -> dict[str, Any]:
    """Vector de 28 features por-90 del jugador + metadatos de muestra."""
    eventos, minutos_total, partidos = [], 0, 0
    info_jugador: dict = {}
    posiciones: dict[str, int] = defaultdict(int)

    for s in sesiones:
        evs = [e for e in (s.get("events") or []) if e.get("jugador") == jugador]
        mins = analytics.minutos_de_sesion_jugador(s, jugador)
        if not (evs or mins > 0):
            continue
        partidos += 1
        minutos_total += mins
        eventos.extend(evs)
        if not info_jugador:
            info_jugador = (s.get("jugadores_info") or {}).get(jugador, {})

    if partidos == 0:
        return {"error": f"No hay datos para '{jugador}'."}

    factor = (90.0 / minutos_total) if minutos_total > 0 else 0.0

    total_accion: dict[str, int] = defaultdict(int)
    exito_accion: dict[str, int] = defaultdict(int)
    fallo_accion: dict[str, int] = defaultdict(int)
    res_accion: dict[tuple, int] = defaultdict(int)
    gol_total, posesion_3t = 0, 0

    for e in eventos:
        a, r = e.get("accion", ""), e.get("resultado", "")
        if e.get("posicion"):
            posiciones[e["posicion"]] += 1
        total_accion[a] += 1
        res_accion[(a, r)] += 1
        if r == EXITO:
            exito_accion[a] += 1
        elif r in (FUERA, BLOQUEADO, REGATEADO, NO_ENCONTRADO, FALLO):
            fallo_accion[a] += 1
        if r == GOL:
            gol_total += 1
        if a in POSESION_3T and r == EXITO and _es_tercio_ofensivo(e):
            posesion_3t += 1

    def st(accs): return sum(total_accion.get(a, 0) for a in accs)
    def se(accs): return sum(exito_accion.get(a, 0) for a in accs)
    def sf(accs): return sum(fallo_accion.get(a, 0) for a in accs)
    def p90(n): return round(n * factor, 2)
    def pct(num, den): return round(num / den * 100, 1) if den > 0 else None

    pases_ok = se(PASES_9)
    pases_intentos = pases_ok + sf(PASES_9)
    largos_ok = exito_accion.get("Pase en largo", 0)
    largos_fail = fallo_accion.get("Pase en largo", 0)
    regate_ok = exito_accion.get("Regate 1v1", 0)
    regate_fail = fallo_accion.get("Regate 1v1", 0)
    duelos_ok = se(DUELOS_TOTALES)
    duelos_total = st(DUELOS_TOTALES)
    aereos_ok = se(AEREOS)
    aereos_total = st(AEREOS)
    perdidas = (sf(PERDIDAS_POR_FALLO)
                + total_accion.get("Control fácil fallado", 0)
                + total_accion.get(PERDIDA_SIEMPRE, 0))

    toques = 0
    for a, n in total_accion.items():
        if a in TOQUES_EXCLUIR:
            continue
        if a in DESMARQUES:
            toques += (n - res_accion.get((a, NO_ENCONTRADO), 0))
        else:
            toques += n

    tiros_largos = exito_accion.get("Pase en largo", 0) + exito_accion.get("Cambio de orientación", 0)

    vector = {
        "Goles": p90(gol_total),
        "Tiro": p90(st(REMATES_TIRO)),
        "Asistencias": p90(total_accion.get("Asistencia", 0)),
        "Pases completados": p90(pases_ok),
        "Pases completados %": pct(pases_ok, pases_intentos),
        "Tiros largos precisos": p90(tiros_largos),
        "Balones largos precisos %": pct(largos_ok, largos_ok + largos_fail),
        "Centros completados": p90(exito_accion.get("Centro lateral", 0)),
        "Regates realizados": p90(regate_ok),
        "Regates realizados %": pct(regate_ok, regate_ok + regate_fail),
        "Duelos ganados": p90(duelos_ok),
        "Duelos ganados %": pct(duelos_ok, duelos_total),
        "Aéreo ganado": p90(aereos_ok),
        "% de duelos aéreos ganados": pct(aereos_ok, aereos_total),
        "Pérdidas de balón": p90(perdidas),
        "Faltas recibidas": p90(st(FALTAS_RECIBIDAS)),
        "Acciones defensivas": p90(se(ACC_DEFENSIVAS)),
        "Entradas": p90(total_accion.get("Entrada / tackle", 0)),
        "Intercepciones": p90(exito_accion.get("Intercepción", 0)),
        "Tiros bloqueados": p90(exito_accion.get("Bloqueo tiro/centro", 0)),
        "Faltas": p90(total_accion.get("Falta", 0)),
        "Recuperaciones": p90(se(RECUPERACIONES)),
        "Regateado": p90(res_accion.get(("Duelo 1v1 def.", REGATEADO), 0)),
        "Despejes": p90(total_accion.get("Despeje", 0) + total_accion.get("Despeje en ABP def.", 0)),
        "Posesion ganada en 3r Tercio": p90(posesion_3t),
        "Toques": p90(toques),
        "Tarjetas amarillas": p90(total_accion.get("Tarjeta amarilla", 0)),
        "Tarjetas rojas": p90(total_accion.get("Tarjeta roja", 0)),
    }
    pos = info_jugador.get("pos", "") or (max(posiciones, key=posiciones.get) if posiciones else "")
    return {
        "jugador": jugador, "posicion": pos,
        "muestra": {"partidos": partidos, "minutos_total": minutos_total,
                    "fiabilidad": ("alta" if partidos >= 8 else
                                   "media" if partidos >= 5 else "baja")},
        "vector": vector,
    }


# Mapeo de posiciones de la app -> posiciones del CSV de tops.
MAPA_POS_CSV = {
    "EXT": "Extremo", "EI": "Extremo", "ED": "Extremo",
    "DC": "Delantero centro", "DEL": "Delantero centro",
    "DFC": "Defensa central", "CENTRAL": "Defensa central",
    "LD": "Lateral derecho", "LI": "Lateral derecho", "LAT": "Lateral derecho",
    "MCD": "MC defensivo", "MC": "MC organizador", "MCO": "MC organizador",
    "MP": "MC organizador",
}


def _leer_csv_tops() -> pd.DataFrame:
    """Lee el CSV de tops probando varias rutas y codificaciones. Lanza un error
    claro si no lo encuentra, en vez de fallar en silencio."""
    rutas = [
        CSV_TOPS_PATH,                                   # junto a similitud.py
        os.path.join(os.getcwd(), "CSV_TOPS.csv"),       # directorio de trabajo
        "CSV_TOPS.csv",                                  # relativo
    ]
    ultimo_error = None
    for ruta in rutas:
        if not os.path.exists(ruta):
            ultimo_error = f"No existe: {ruta}"
            continue
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(ruta, decimal=",", encoding=enc)
                if "Posición" in df.columns:
                    return df
                # por si el encoding rompió la tilde de la cabecera
                df.columns = [c.strip() for c in df.columns]
                col = next((c for c in df.columns if c.lower().startswith("posici")), None)
                if col:
                    df = df.rename(columns={col: "Posición"})
                    return df
                ultimo_error = f"Leído pero sin columna 'Posición'. Columnas: {list(df.columns)[:5]}"
            except Exception as e:
                ultimo_error = f"{type(e).__name__}: {e}"
    raise FileNotFoundError(f"No se pudo leer CSV_TOPS.csv. Último error: {ultimo_error}")


def posiciones_csv() -> list[str]:
    df = _leer_csv_tops()
    return sorted(df["Posición"].dropna().unique().tolist())


def similitud_nivel1(vector_ojeado: dict, posicion_csv: str,
                     jugador_nombre="Ojeado", fiabilidad="baja", top_n=5) -> dict:
    df = _leer_csv_tops()
    grupo = df[df["Posición"] == posicion_csv].copy()
    if grupo.empty:
        return {"error": f"No hay tops con posición '{posicion_csv}'.",
                "posiciones_disponibles": sorted(df["Posición"].unique().tolist())}

    tabla = grupo[FEATURES].apply(pd.to_numeric, errors="coerce")
    features = [f for f in FEATURES if not tabla[f].isna().all()]
    excluidas = [f for f in FEATURES if f not in features]

    X = tabla[features].to_numpy(dtype=float).copy()
    v = np.array([float(vector_ojeado.get(f, np.nan)) if vector_ojeado.get(f) is not None
                  else np.nan for f in features], dtype=float)

    col_mean = np.nanmean(X, axis=0)
    col_std = np.nanstd(X, axis=0)
    X[np.where(np.isnan(X))] = np.take(col_mean, np.where(np.isnan(X))[1])
    nan_v = np.isnan(v)
    v[nan_v] = col_mean[nan_v]

    safe_std = np.where(col_std == 0, 1.0, col_std)
    Z = (X - col_mean) / safe_std
    z_oj = (v - col_mean) / safe_std

    def coseno(a, b):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

    sims = []
    for i, row in enumerate(grupo.itertuples(index=False)):
        sims.append((getattr(row, "Jugador"), getattr(row, "Equipo"), coseno(z_oj, Z[i])))
    sims.sort(key=lambda x: x[2], reverse=True)

    perfil = sorted(zip(features, z_oj), key=lambda x: x[1], reverse=True)
    destaca = [(f, round(z, 2)) for f, z in perfil if z > 0.5][:5]
    floja = [(f, round(z, 2)) for f, z in perfil if z < -0.5][-5:]

    return {
        "jugador": jugador_nombre, "posicion": posicion_csv, "fiabilidad": fiabilidad,
        "n_tops": len(grupo), "features_usadas": len(features),
        "features_excluidas": excluidas,
        "ranking": [{"top": n, "equipo": e, "similitud": round(s, 3)} for n, e, s in sims[:top_n]],
        "destaca": destaca, "floja": floja,
        "aviso": "Muestra pequeña: resultado ORIENTATIVO." if fiabilidad == "baja" else "",
    }
