"""
analytics.py — Capa de análisis (sin UI)
========================================
Toda la lógica de cálculo vive aquí, separada de la presentación (scouting_app.py)
y de la persistencia (storage.py).

Contiene:
    - Diccionario de resultados "positivos" por acción (para % de acierto).
    - flatten_events()        -> DataFrame normalizado de una o varias sesiones.
    - player_metrics()        -> métricas agregadas por jugador (para radar/tablas).
    - team_metrics()          -> métricas agregadas de equipo (goles, tiros, etc.).
    - zone_grid_counts()      -> matriz 3x3 de conteos para el mapa de calor.
    - radar_axes()            -> ejes normalizados 0-100 para el gráfico spider.
    - predict_player_trend()  -> proyección por tendencia (siempre disponible).
    - train_outcome_model()   -> modelo scikit-learn (cuando hay datos suficientes).

Diseño defensivo: todas las funciones aceptan listas vacías y devuelven
estructuras vacías en lugar de lanzar excepciones, para que la UI no se rompa.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Any


# ----------------------------------------------------------------------------
# QUÉ CUENTA COMO "ÉXITO" EN CADA TIPO DE RESULTADO
# ----------------------------------------------------------------------------
# Etiqueta de "jugador" que marca una acción colectiva de equipo.
# Debe coincidir con EQUIPO_TAG en scouting_app.py.
EQUIPO_TAG = "★ EQUIPO"

# IMPORTANTE: estos son los CÓDIGOS que add_event guarda realmente (el 2º
# elemento de cada tupla RES_* en scouting_app.py), no las etiquetas de botón.
SUCCESS_CODES = {"Correcto", "Encontrado", "A puerta", "Gol"}
FAIL_CODES = {"Fallo", "No encontrado", "Fuera/Interceptado"}
# Eventos puntuales que no entran en el % de acierto.
NEUTRAL_CODES = {"—", "Falta", "Tarjeta amarilla", "Tarjeta roja",
                 "Penalti provocado", "Penalti cometido"}

# Acciones que representan un disparo (para métricas de equipo)
SHOT_ACTIONS = {"Remate", "Remate de cabeza", "Remate desde fuera", "Llegada 2ª línea",
                "Tiro"}
# Acciones que representan un pase (para % de pases completados)
PASS_ACTIONS = {
    "Pase progresivo", "Pase entre líneas", "Pase al espacio",
    "Cambio de orientación", "Pase filtrado", "Pase en conducción",
    "Pase de primera", "Pase bajo presión", "Pase en largo",
    "Salida de balón", "Pase clave", "Centro lateral",
    # acciones de equipo
    "Circulación / posesión", "Progresión con balón", "Llegada a último tercio",
    "Centro al área",
}
DRIBBLE_ACTIONS = {"Regate 1v1", "Desborde por banda", "Recorte / cambio ritmo"}
DEFENSE_ACTIONS = {
    "Entrada / tackle", "Intercepción", "Recuperación", "Despeje",
    "Duelo aéreo def.", "Duelo 1v1 def.", "Presión fuerza error",
    "Cobertura", "Marcaje al hombre", "Bloqueo tiro/centro", "Repliegue",
    # acciones de equipo
    "Presión alta", "Robo / intercepción", "Duelo defensivo",
}

# Las 6 dimensiones del radar (ejes del spider chart)
RADAR_DIMENSIONS = [
    "Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón", "Volumen",
]


def is_success(code: str) -> bool:
    return code in SUCCESS_CODES


def is_attempt(code: str) -> bool:
    """¿Este resultado cuenta para un ratio de acierto (éxito o fallo)?"""
    return code in SUCCESS_CODES or code in FAIL_CODES


# ----------------------------------------------------------------------------
# NORMALIZACIÓN DE EVENTOS
# ----------------------------------------------------------------------------
def flatten_events(sessions: list[dict[str, Any]]) -> pd.DataFrame:
    """Aplana los eventos de una lista de sesiones en un único DataFrame.

    Cada sesión es un dict como el que devuelve storage.load_session.
    Añade columnas de contexto del partido a cada evento.
    Tolera sesiones sin eventos y zonas en formato antiguo ("2º tercio")
    o nuevo (rejilla "M-C", etc.).
    """
    rows: list[dict[str, Any]] = []
    for s in sessions:
        events = s.get("events") or []
        sess_meta = {
            "session_id": s.get("id", ""),
            "sesion": s.get("nombre", ""),
            "competicion": s.get("competicion", ""),
            "fecha": s.get("fecha", ""),
            "equipo_local": s.get("equipo_local", ""),
            "equipo_visitante": s.get("equipo_visitante", ""),
        }
        for ev in events:
            row = dict(sess_meta)
            row.update({
                "jugador": ev.get("jugador", ""),
                "minuto": ev.get("minuto", 0.0),
                "minuto_fmt": ev.get("minuto_fmt", ""),
                "accion": ev.get("accion", ""),
                "resultado": ev.get("resultado", ""),
                "zona": ev.get("zona", ""),
                # zona_x/zona_y para rejilla 3x3 (si existen); si no, se derivan
                "zona_x": ev.get("zona_x"),
                "zona_y": ev.get("zona_y"),
            })
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[
            "session_id", "sesion", "competicion", "fecha", "equipo_local",
            "equipo_visitante", "jugador", "minuto", "minuto_fmt", "accion",
            "resultado", "zona", "zona_x", "zona_y",
        ])
    df = pd.DataFrame(rows)
    df["exito"] = df["resultado"].apply(is_success)
    df["intento"] = df["resultado"].apply(is_attempt)
    return df


# ----------------------------------------------------------------------------
# CATEGORÍA DE CADA ACCIÓN (para el radar)
# ----------------------------------------------------------------------------
def _action_category(accion: str) -> str:
    if accion in PASS_ACTIONS or accion == "Asistencia":
        return "Pase"
    if accion in DRIBBLE_ACTIONS or accion in {"Conducción progresiva", "Protección de balón", "Pared", "Recibe entre líneas"}:
        return "Regate"
    if accion in SHOT_ACTIONS or accion == "Generación de ocasión":
        return "Finalización"
    if accion in DEFENSE_ACTIONS:
        return "Defensa"
    if accion in {"Desmarque de ruptura", "Desmarque de apoyo", "Ataque al palo",
                  "Desmarque de arrastre", "Amplía el campo", "Ofrece línea de pase"}:
        return "Mov. sin balón"
    return "Otros"


# ----------------------------------------------------------------------------
# MÉTRICAS POR JUGADOR
# ----------------------------------------------------------------------------
def player_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve un DataFrame con una fila por jugador y métricas resumidas.
    Excluye las acciones colectivas (jugador == EQUIPO_TAG)."""
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df = df[df["jugador"] != EQUIPO_TAG]
    if df.empty:
        return pd.DataFrame()
    df["categoria"] = df["accion"].apply(_action_category)

    out = []
    for jugador, g in df.groupby("jugador"):
        intentos = g[g["intento"]]
        total_acc = len(g)
        aciertos = int(g["exito"].sum())
        pct = round(100 * aciertos / len(intentos), 1) if len(intentos) else 0.0

        # Conteos por categoría
        cat_counts = g["categoria"].value_counts().to_dict()

        # % acierto por categoría (solo intentos)
        cat_pct = {}
        for cat in ["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón"]:
            sub = g[g["categoria"] == cat]
            sub_int = sub[sub["intento"]]
            cat_pct[cat] = (round(100 * sub["exito"].sum() / len(sub_int), 1)
                            if len(sub_int) else 0.0)

        out.append({
            "jugador": jugador,
            "acciones": total_acc,
            "aciertos": aciertos,
            "pct_acierto": pct,
            "pases": cat_counts.get("Pase", 0),
            "regates": cat_counts.get("Regate", 0),
            "finalizacion": cat_counts.get("Finalización", 0),
            "defensa": cat_counts.get("Defensa", 0),
            "mov_sin_balon": cat_counts.get("Mov. sin balón", 0),
            "pct_pase": cat_pct["Pase"],
            "pct_regate": cat_pct["Regate"],
            "pct_finalizacion": cat_pct["Finalización"],
            "pct_defensa": cat_pct["Defensa"],
            "pct_mov": cat_pct["Mov. sin balón"],
        })
    res = pd.DataFrame(out).sort_values("acciones", ascending=False)
    return res.reset_index(drop=True)


# ----------------------------------------------------------------------------
# RADAR / SPIDER
# ----------------------------------------------------------------------------
def radar_axes(metrics_row: dict[str, Any], df_all: pd.DataFrame) -> list[float]:
    """Convierte las métricas de un jugador en 6 ejes 0-100 para el radar.

    Cinco ejes son % de acierto por categoría (ya están 0-100).
    El sexto ("Volumen") se normaliza respecto al jugador con más acciones,
    para que sea comparable entre jugadores.
    """
    pm = player_metrics(df_all)
    max_acc = pm["acciones"].max() if not pm.empty else 1
    max_acc = max(int(max_acc), 1)
    volumen = round(100 * metrics_row.get("acciones", 0) / max_acc, 1)
    return [
        metrics_row.get("pct_pase", 0.0),
        metrics_row.get("pct_regate", 0.0),
        metrics_row.get("pct_finalizacion", 0.0),
        metrics_row.get("pct_defensa", 0.0),
        metrics_row.get("pct_mov", 0.0),
        volumen,
    ]


# ----------------------------------------------------------------------------
# MÉTRICAS DE EQUIPO
# ----------------------------------------------------------------------------
def team_metrics(df: pd.DataFrame, match_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Métricas agregadas del conjunto (no por jugador individual)."""
    base = {
        "total_acciones": 0, "tiros": 0, "tiros_puerta": 0, "goles_accion": 0,
        "pases": 0, "pases_ok": 0, "pct_pase": 0.0,
        "regates": 0, "regates_ok": 0, "pct_regate": 0.0,
        "recuperaciones": 0, "duelos_def": 0, "duelos_def_ok": 0,
        "faltas": 0, "amarillas": 0, "rojas": 0,
    }
    if df.empty:
        if match_info:
            base["goles_marcador"] = match_info.get("goles_local", 0)
            base["posesion"] = match_info.get("posesion_local", 50)
        return base

    base["total_acciones"] = len(df)
    shots = df[df["accion"].isin(SHOT_ACTIONS)]
    base["tiros"] = len(shots)
    base["tiros_puerta"] = int(shots["resultado"].isin({"A puerta", "Gol"}).sum())
    base["goles_accion"] = int((shots["resultado"] == "Gol").sum())

    passes = df[df["accion"].isin(PASS_ACTIONS)]
    base["pases"] = len(passes)
    base["pases_ok"] = int(passes["exito"].sum())
    base["pct_pase"] = round(100 * base["pases_ok"] / base["pases"], 1) if base["pases"] else 0.0

    dribbles = df[df["accion"].isin(DRIBBLE_ACTIONS)]
    base["regates"] = len(dribbles)
    base["regates_ok"] = int(dribbles["exito"].sum())
    base["pct_regate"] = round(100 * base["regates_ok"] / base["regates"], 1) if base["regates"] else 0.0

    base["recuperaciones"] = int((df["accion"] == "Recuperación").sum())
    duelos = df[df["accion"].isin({"Duelo 1v1 def.", "Duelo aéreo def.", "Entrada / tackle"})]
    base["duelos_def"] = len(duelos)
    base["duelos_def_ok"] = int(duelos["exito"].sum())

    base["faltas"] = int((df["resultado"] == "Falta").sum())
    base["amarillas"] = int((df["resultado"] == "Tarjeta amarilla").sum())
    base["rojas"] = int((df["resultado"] == "Tarjeta roja").sum())

    if match_info:
        base["goles_marcador"] = match_info.get("goles_local", 0)
        base["posesion"] = match_info.get("posesion_local", 50)
    return base


# ----------------------------------------------------------------------------
# REJILLA 3x3 PARA MAPA DE CALOR
# ----------------------------------------------------------------------------
# Mapeo de zona antigua (3 tercios) a columna de la rejilla, fila central.
_OLD_ZONE_TO_COL = {"1er tercio": 0, "2º tercio": 1, "3er tercio": 2}


def zone_grid_counts(df: pd.DataFrame) -> np.ndarray:
    """Devuelve una matriz 3x3 (filas = bandas, cols = tercios) con conteos.

    Soporta dos formatos de zona:
      - Nuevo: columnas zona_x (0-2) y zona_y (0-2) en cada evento.
      - Antiguo: solo 'zona' con "1er/2º/3er tercio" -> se coloca en la fila central.
    """
    grid = np.zeros((3, 3), dtype=int)
    if df.empty:
        return grid
    for _, ev in df.iterrows():
        zx, zy = ev.get("zona_x"), ev.get("zona_y")
        if pd.notna(zx) and pd.notna(zy):
            xi, yi = int(zx), int(zy)
            if 0 <= xi <= 2 and 0 <= yi <= 2:
                grid[yi, xi] += 1
        else:
            col = _OLD_ZONE_TO_COL.get(ev.get("zona", ""), 1)
            grid[1, col] += 1  # fila central por defecto
    return grid


# ----------------------------------------------------------------------------
# ML / IA TRADICIONAL
# ----------------------------------------------------------------------------
def predict_player_trend(df_player_sessions: pd.DataFrame) -> dict[str, Any]:
    """Proyección por TENDENCIA (siempre disponible, incluso con 1-2 partidos).

    Calcula el % de acierto del jugador por sesión (ordenadas por fecha) y
    ajusta una recta. Si solo hay un punto, devuelve ese valor sin pendiente.
    Devuelve un dict con la serie histórica y la proyección al siguiente partido.
    """
    out = {"historico": [], "proyeccion": None, "tendencia": "estable",
           "n_sesiones": 0, "metodo": "tendencia"}
    if df_player_sessions.empty:
        return out

    # % acierto por sesión
    serie = []
    for (sid, fecha), g in df_player_sessions.groupby(["session_id", "fecha"]):
        intentos = g[g["intento"]]
        if len(intentos) == 0:
            continue
        pct = 100 * g["exito"].sum() / len(intentos)
        serie.append({"fecha": fecha, "pct": round(pct, 1), "acciones": len(g)})
    serie.sort(key=lambda r: r["fecha"])
    out["historico"] = serie
    out["n_sesiones"] = len(serie)
    if not serie:
        return out

    ys = np.array([r["pct"] for r in serie], dtype=float)
    if len(ys) == 1:
        out["proyeccion"] = round(float(ys[0]), 1)
        return out

    xs = np.arange(len(ys), dtype=float)
    slope, intercept = np.polyfit(xs, ys, 1)
    proj = slope * len(ys) + intercept
    out["proyeccion"] = round(float(np.clip(proj, 0, 100)), 1)
    if slope > 1.5:
        out["tendencia"] = "al alza"
    elif slope < -1.5:
        out["tendencia"] = "a la baja"
    else:
        out["tendencia"] = "estable"
    return out


def train_outcome_model(df: pd.DataFrame, min_rows: int = 60) -> dict[str, Any]:
    """Entrena un modelo scikit-learn que predice si una acción será exitosa,
    a partir del tipo de acción, la zona y el minuto. Solo se entrena si hay
    suficientes intentos (min_rows). Devuelve el modelo y su fiabilidad (CV).

    Esto es IA tradicional honesta: con pocos datos avisa de baja confianza.
    """
    res = {"trained": False, "reason": "", "accuracy": None, "n": 0,
           "model": None, "encoder": None, "feature_importance": None}

    data = df[df["intento"]].copy()
    res["n"] = len(data)
    if len(data) < min_rows:
        res["reason"] = (f"Hacen falta al menos {min_rows} acciones con resultado "
                         f"éxito/fallo para entrenar (tienes {len(data)}).")
        return res

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.model_selection import cross_val_score

    data["zona_str"] = data["zona"].fillna("?").astype(str)
    data["accion"] = data["accion"].fillna("?").astype(str)
    X_cat = data[["accion", "zona_str"]]
    minuto = data[["minuto"]].fillna(0.0).to_numpy()
    y = data["exito"].astype(int).to_numpy()

    if len(np.unique(y)) < 2:
        res["reason"] = "Todas las acciones tienen el mismo resultado; no hay nada que aprender todavía."
        return res

    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    X_enc = enc.fit_transform(X_cat)
    X = np.hstack([X_enc, minuto])

    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)
    n_splits = min(5, int(np.bincount(y).min()))
    if n_splits >= 2:
        scores = cross_val_score(clf, X, y, cv=n_splits, scoring="accuracy")
        res["accuracy"] = round(float(scores.mean()), 3)
    clf.fit(X, y)

    # Importancia agregada por feature original
    importances = clf.feature_importances_
    feat_names = list(enc.get_feature_names_out(["accion", "zona_str"])) + ["minuto"]
    fi = sorted(zip(feat_names, importances), key=lambda t: t[1], reverse=True)[:10]
    res["feature_importance"] = fi
    res["model"] = clf
    res["encoder"] = enc
    res["trained"] = True
    return res
