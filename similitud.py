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
# OJO: sin "Presión fuerza error" a propósito. FotMob no cuenta como posesión
# ganada el presionar y forzar el error (solo el robo efectivo), así que incluirlo
# inflaba esta feature a 2.18/90 frente a 0.91 de los tops: +7.9 desviaciones de
# sesgo en TODOS los ojeados por igual, que ensuciaba el parecido. Sin ella queda
# en 0.98 vs 0.91. La presión sigue valorándose en el % de acierto y en la nota;
# esto es solo el vector de comparación.
POSESION_3T = ["Recuperación", "Intercepción", "Entrada / tackle",
               "Duelo 1v1 def.", "Anticipación"]
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
    "MP": "MC organizador", "MED": "MC organizador",
}


def _cargar_sim_cfg():
    """Carga la config de similitud (Fase 3) del diccionario canónico."""
    import json
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "diccionario_resultados.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f).get("similitud", {})
    except Exception:
        return {}
_SIM_CFG = _cargar_sim_cfg()
MIN_MINUTOS = float(_SIM_CFG.get("min_minutos", 90))
MINUTOS_SOLIDO = float(_SIM_CFG.get("minutos_solido", 270))
# Features que se calculan pero NO se comparan: su definición no casa con la del
# CSV de tops, así que el z-score las dispara y sesgan a todos los ojeados por
# igual. Ver el comentario del bloque "similitud" en el JSON.
FEATURES_EXCLUIDAS = set(_SIM_CFG.get("features_excluidas", []))


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


def vectores_ojeados(sesiones: list[dict[str, Any]], min_minutos=None) -> list[dict]:
    """Vector por-90 de CADA jugador de la propia base, listo para el pool.

    Aplica el umbral de muestra: por debajo de `min_minutos` el vector por-90 es
    ruido (pocas acciones extrapoladas a 90' dan valores extremos que se cuelan
    arriba del ranking sin significar nada), así que el jugador no entra. Los que
    entran pero no llegan a `minutos_solido` se marcan `atenuado`: se muestran,
    pero avisando, en vez de esconderlos.
    """
    umbral = MIN_MINUTOS if min_minutos is None else float(min_minutos)
    nombres = set()
    for s in sesiones:
        for e in (s.get("events") or []):
            if e.get("jugador"):
                nombres.add(e["jugador"])

    out = []
    for n in sorted(nombres):
        v = construir_vector(sesiones, n)
        if "error" in v:
            continue
        mins = v["muestra"]["minutos_total"]
        if mins < umbral:
            continue
        equipo = ""
        for s in sesiones:
            ji = (s.get("jugadores_info") or {}).get(n) or {}
            if ji.get("equipo"):
                equipo = ji["equipo"]
                break
        out.append({"jugador": n, "posicion": v["posicion"], "equipo": equipo,
                    "vector": v["vector"], "muestra": v["muestra"],
                    "atenuado": mins < MINUTOS_SOLIDO})
    return out


def _coseno(a, b) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0


def _norm_filas(Z):
    """Lleva cada fila a longitud 1.

    Sin esto el mapa y el ranking se contradicen: el ranking mide COSENO (el
    ángulo entre perfiles) y un mapa mide DISTANCIA entre puntos, que son dos
    varas distintas. Con las filas normalizadas se cumple |a-b|² = 2-2·cos(a,b),
    o sea que la distancia pasa a ser función directa del coseno y el mapa sí es
    la sombra del espacio que mide el ranking.

    No altera el ranking: el coseno es invariante a escala.
    """
    n = np.linalg.norm(Z, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return Z / n


def _z_de_vector(vector: dict, features, col_mean, safe_std):
    """Proyecta un vector suelto (feature -> valor) a la escala z de los tops.
    Las features sin dato se imputan a la media del grupo, o sea z=0 (neutro)."""
    v = np.array([float(vector.get(f)) if vector.get(f) is not None else np.nan
                  for f in features], dtype=float)
    nan = np.isnan(v)
    v[nan] = col_mean[nan]
    return (v - col_mean) / safe_std


def _z_space(posicion_csv: str, vectores_extra=None) -> dict:
    """FUENTE ÚNICA del espacio de comparación: el ranking y el mapa PCA beben de
    aquí, y por eso no pueden contradecirse.

    La población de referencia son SOLO los tops de la posición: ellos fijan la
    media y la desviación. Los ojeados se PROYECTAN en esa escala, no la definen
    (con un puñado de ojeados la desviación sería ruido y un solo jugador raro
    deformaría la escala de todos los demás).
    """
    df = _leer_csv_tops()
    grupo = df[df["Posición"] == posicion_csv].copy()
    if grupo.empty:
        raise ValueError(f"No hay tops con posición '{posicion_csv}'.")

    tabla = grupo[FEATURES].apply(pd.to_numeric, errors="coerce")
    features = [f for f in FEATURES
                if f not in FEATURES_EXCLUIDAS and not tabla[f].isna().all()]
    excluidas = [f for f in FEATURES if f not in features]

    X = tabla[features].to_numpy(dtype=float).copy()
    col_mean = np.nanmean(X, axis=0)
    col_std = np.nanstd(X, axis=0)
    X[np.where(np.isnan(X))] = np.take(col_mean, np.where(np.isnan(X))[1])
    safe_std = np.where(col_std == 0, 1.0, col_std)
    Z_tops = (X - col_mean) / safe_std
    meta_tops = [{"nombre": getattr(r, "Jugador"), "equipo": getattr(r, "Equipo")}
                 for r in grupo.itertuples(index=False)]

    extra = list(vectores_extra or [])
    Z_extra = (np.vstack([_z_de_vector(it["vector"], features, col_mean, safe_std)
                          for it in extra])
               if extra else np.empty((0, len(features))))

    return {"features": features, "excluidas": excluidas,
            "Z_tops": Z_tops, "meta_tops": meta_tops,
            "Z_extra": Z_extra, "meta_extra": extra,
            "col_mean": col_mean, "safe_std": safe_std}


def similitud_nivel1(vector_ojeado: dict, posicion_csv: str,
                     jugador_nombre="Ojeado", fiabilidad="baja", top_n=5,
                     pool=None) -> dict:
    """Ranking de parecidos del jugador: contra los tops del CSV y, si se pasa
    `pool` (ver `vectores_ojeados`), también contra la propia base.

    Las dos listas van separadas porque responden preguntas distintas: el top
    dice a qué referencia se parece; el ojeado, qué alternativa de tu lista cubre
    el mismo perfil. Comparten z-space, así que los % sí son comparables.
    """
    try:
        esp = _z_space(posicion_csv, pool)
    except ValueError as e:
        df = _leer_csv_tops()
        return {"error": str(e),
                "posiciones_disponibles": sorted(df["Posición"].unique().tolist())}

    features, excluidas = esp["features"], esp["excluidas"]
    z_oj = _z_de_vector(vector_ojeado, features, esp["col_mean"], esp["safe_std"])

    sims = [(m["nombre"], m["equipo"], _coseno(z_oj, esp["Z_tops"][i]))
            for i, m in enumerate(esp["meta_tops"])]
    sims.sort(key=lambda x: x[2], reverse=True)

    # Contra la propia base. Se excluye el propio jugador: consigo mismo el
    # coseno es 1.0 y encabezaría siempre su propio ranking.
    sims_oj = []
    for i, m in enumerate(esp["meta_extra"]):
        if m["jugador"] == jugador_nombre:
            continue
        sims_oj.append({"jugador": m["jugador"], "equipo": m.get("equipo", ""),
                        "similitud": round(_coseno(z_oj, esp["Z_extra"][i]), 3),
                        "atenuado": bool(m.get("atenuado")),
                        "partidos": (m.get("muestra") or {}).get("partidos")})
    sims_oj.sort(key=lambda x: x["similitud"], reverse=True)

    # Métricas donde un valor ALTO es NEGATIVO (cuantas menos, mejor).
    # Para el perfil "destaca/floja" se invierte su z: destacar = tener pocas.
    NEGATIVAS = {"Pérdidas de balón", "Faltas", "Regateado",
                 "Tarjetas amarillas", "Tarjetas rojas"}
    # z "orientado a bueno": en las negativas, menos es mejor -> z invertido
    perfil_bueno = []
    for f, z in zip(features, z_oj):
        z_b = -z if f in NEGATIVAS else z
        perfil_bueno.append((f, z, z_b))
    perfil_bueno.sort(key=lambda x: x[2], reverse=True)
    # destaca: mejor que la media en sentido "bueno" (z_b alto)
    destaca = [(f, round(z, 2)) for f, z, zb in perfil_bueno if zb > 0.5][:5]
    # floja: peor que la media (z_b bajo)
    floja = [(f, round(z, 2)) for f, z, zb in perfil_bueno if zb < -0.5][-5:]

    return {
        "jugador": jugador_nombre, "posicion": posicion_csv, "fiabilidad": fiabilidad,
        "n_tops": len(esp["meta_tops"]), "features_usadas": len(features),
        "features_excluidas": excluidas,
        "ranking": [{"top": n, "equipo": e, "similitud": round(s, 3)} for n, e, s in sims[:top_n]],
        "ranking_ojeados": sims_oj[:top_n],
        "destaca": destaca, "floja": floja,
        "aviso": "Muestra pequeña: resultado ORIENTATIVO." if fiabilidad == "baja" else "",
    }


def mapa_pca(posicion_csv: str, pool=None, jugador_foco=None,
             vector_foco=None, n_cargas=3) -> dict:
    """Mapa 2D de perfiles del bloque de posición, vía PCA.

    El PCA se ajusta SOLO con los tops y los ojeados se proyectan encima. Así los
    ejes NO se mueven al taguear un jugador nuevo y el mapa es estable entre
    sesiones (si se ajustara con los ojeados, cada partido redibujaría el mapa
    entero). Usa el mismo z-space que el ranking, así que los dos cuentan lo
    mismo.

    Aplastar 28 dimensiones a 2 PIERDE información siempre: por eso se devuelve
    `var_explicada`. El mapa es un croquis para orientarse; la medida es el
    coseno, que sí usa las 28 dimensiones enteras.
    """
    try:
        esp = _z_space(posicion_csv, pool)
    except ValueError as e:
        return {"error": str(e)}

    if esp["Z_tops"].shape[0] < 3:
        return {"error": f"Solo hay {esp['Z_tops'].shape[0]} top(s) en '{posicion_csv}': "
                         "hacen falta al menos 3 para trazar 2 ejes."}

    # Normalizar ANTES del PCA es lo que hace que la distancia en el mapa
    # signifique lo mismo que el coseno del ranking (ver _norm_filas).
    Z_tops = _norm_filas(esp["Z_tops"])
    Z_extra = _norm_filas(esp["Z_extra"]) if len(esp["meta_extra"]) else esp["Z_extra"]
    centro = Z_tops.mean(axis=0)
    # PCA por SVD: los 2 primeros componentes son el "ángulo de linterna" que más
    # separa a los tops entre sí, o sea la sombra 2D que menos información pierde.
    _, S, Vt = np.linalg.svd(Z_tops - centro, full_matrices=False)
    comp = Vt[:2]
    var = S ** 2
    total = float(var.sum())
    var_exp = [(float(var[i] / total) if total > 0 else 0.0) for i in range(min(2, len(var)))]
    while len(var_exp) < 2:
        var_exp.append(0.0)

    def proyecta(Z):
        return (Z - centro) @ comp.T

    puntos = []
    for m, (x, y) in zip(esp["meta_tops"], proyecta(Z_tops)):
        puntos.append({"nombre": m["nombre"], "equipo": m["equipo"], "tipo": "top",
                       "x": float(x), "y": float(y), "atenuado": False, "foco": False})
    if len(esp["meta_extra"]):
        for m, (x, y) in zip(esp["meta_extra"], proyecta(Z_extra)):
            puntos.append({"nombre": m["jugador"], "equipo": m.get("equipo", ""),
                           "tipo": "ojeado", "x": float(x), "y": float(y),
                           "atenuado": bool(m.get("atenuado")),
                           "foco": m["jugador"] == jugador_foco})

    # El jugador en foco puede no estar en el pool (p.ej. no llega al umbral de
    # minutos). Se pinta igual, atenuado, para que no falte del mapa que mira.
    if jugador_foco and vector_foco and not any(p["foco"] for p in puntos):
        z = _z_de_vector(vector_foco, esp["features"], esp["col_mean"], esp["safe_std"])
        x, y = proyecta(_norm_filas(z.reshape(1, -1)))[0]
        puntos.append({"nombre": jugador_foco, "equipo": "", "tipo": "ojeado",
                       "x": float(x), "y": float(y), "atenuado": True, "foco": True})

    # Nombre de cada eje: las features que más pesan en él. Sin esto los ejes son
    # "PC1" y "PC2" y el mapa es inleíble.
    ejes = []
    for i in range(2):
        cargas = sorted(zip(esp["features"], comp[i]),
                        key=lambda t: abs(t[1]), reverse=True)
        ejes.append({"var": var_exp[i],
                     "cargas": [(f, round(float(c), 2)) for f, c in cargas[:n_cargas]]})

    return {"puntos": puntos, "var_explicada": var_exp, "ejes": ejes,
            "n_tops": Z_tops.shape[0], "n_ojeados": len(esp["meta_extra"])}
