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
    - agregados_expectativa() / predecir_acierto() -> predicción de acierto
      por jugador con suavizado jerárquico (Fase 5).

Diseño defensivo: todas las funciones aceptan listas vacías y devuelven
estructuras vacías en lugar de lanzar excepciones, para que la UI no se rompa.
"""

from __future__ import annotations
import unicodedata
import pandas as pd
import numpy as np
from typing import Any


def _norm_equipo(s: Any) -> str:
    """Normaliza un nombre de equipo para comparar (minúsculas, sin tildes,
    sin espacios sobrantes)."""
    s = str(s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return s


def _rival_partido(g: pd.DataFrame) -> str:
    """Devuelve el equipo RIVAL de un partido desde la óptica del jugador
    scouteado. Usa el equipo del jugador EN ESE PARTIDO (columna
    `equipo_jugador`, ver flatten_events) para saber si juega de local o de
    visitante; el rival es el OTRO equipo. Si no se puede determinar (sin
    equipo o sin coincidencia), cae al visitante.

    Multi-equipo: el equipo es por partido, no el global de la ficha. Un mismo
    jugador puede aparecer con su selección y con su club, y el rival tiene que
    salir bien en los dos casos."""
    local = g["equipo_local"].iloc[0] if "equipo_local" in g.columns else ""
    visit = g["equipo_visitante"].iloc[0] if "equipo_visitante" in g.columns else ""
    equipo_jug = ""
    if "equipo_jugador" in g.columns and len(g):
        equipo_jug = g["equipo_jugador"].iloc[0]
    if not equipo_jug and "jugador_info" in g.columns and len(g):
        # Fallback para DataFrames construidos a mano (tests) sin la columna.
        ficha = g["jugador_info"].iloc[0]
        if isinstance(ficha, dict):
            equipo_jug = ficha.get("equipo", "")
    ej = _norm_equipo(equipo_jug)
    if ej:
        if ej == _norm_equipo(local):
            return visit or local
        if ej == _norm_equipo(visit):
            return local or visit
    return visit or local


# ----------------------------------------------------------------------------
# QUÉ CUENTA COMO "ÉXITO" EN CADA TIPO DE RESULTADO
# ----------------------------------------------------------------------------
# Etiqueta de "jugador" que marca una acción colectiva de equipo.
# Debe coincidir con EQUIPO_TAG en scouting_app.py.
EQUIPO_TAG = "★ EQUIPO"

# IMPORTANTE: estos son los CÓDIGOS que add_event guarda realmente (el 2º
# elemento de cada tupla RES_* en scouting_app.py), no las etiquetas de botón.
SUCCESS_CODES = {"Correcto", "Encontrado", "A puerta", "Gol"}
FAIL_CODES = {"Fallo", "No encontrado", "Fuera/Interceptado", "Fuera",
              "Bloqueado", "Barrera", "Regateado", "Control fácil fallado"}
# Éxito PARCIAL: cuenta como intento y como medio acierto (0.5). Es el caso del
# duelo defensivo donde el jugador no recupera pero aguanta/retrasa la jugada.
PARTIAL_CODES = {"Retrasó/aguantó"}
# Eventos puntuales que no entran en el % de acierto.
NEUTRAL_CODES = {"—", "Falta", "Tarjeta amarilla", "Tarjeta roja",
                 "Penalti provocado", "Penalti cometido", "Movimiento sin pase", "Sprint"}

# --- Diccionario canónico versionado (Fase 0) ---------------------------------
# Si existe 'diccionario_resultados.json' junto a este archivo, se usa como
# ÚNICA fuente de verdad de qué es éxito/fallo/parcial/neutro. Así se edita a
# mano sin tocar código. Si no existe, se usan los conjuntos de arriba (fallback).
def _cargar_diccionario_canonico():
    import os, json
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "diccionario_resultados.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        global SUCCESS_CODES, FAIL_CODES, PARTIAL_CODES, NEUTRAL_CODES
        if d.get("exito"):   SUCCESS_CODES = set(d["exito"])
        if d.get("fallo"):   FAIL_CODES = set(d["fallo"])
        if d.get("parcial"): PARTIAL_CODES = set(d["parcial"])
        if d.get("neutro"):  NEUTRAL_CODES = set(d["neutro"])
        return d.get("pesos", {})
    except Exception:
        return {}

_PESOS_CANONICOS = _cargar_diccionario_canonico()

# Acciones que representan un disparo (para métricas de equipo)
SHOT_ACTIONS = {"Remate", "Remate de cabeza", "Remate desde fuera", "Llegada 2ª línea",
                "Tiro", "Remate a balón parado", "Falta directa a puerta"}
# Acciones que representan un pase (para % de pases completados)
PASS_ACTIONS = {
    "Pase atrás", "Pase lateral",
    "Pase progresivo", "Pase entre líneas", "Pase al espacio",
    "Cambio de orientación",
    "Pase de primera", "Pase en largo",
    "Centro lateral",
    # acciones de equipo
    "Circulación / posesión", "Progresión con balón", "Llegada a último tercio",
    "Centro al área",
}
# Etiquetas que CUALIFICAN un pase ya existente (no son un pase adicional):
# no se cuentan en el cómputo de pases ni en el % de acierto de pase, para no
# inflar el volumen ni distorsionar el porcentaje.
PASE_COMPLEMENTO = {"Pase clave", "Pase bajo presión", "Asistencia"}
DRIBBLE_ACTIONS = {"Regate 1v1", "Recorte / cambio ritmo"}
DEFENSE_ACTIONS = {
    "Entrada / tackle", "Intercepción", "Anticipación", "Recuperación", "Despeje",
    "Duelo aéreo def.", "Duelo 1v1 def.", "Presión fuerza error",
    "Cobertura", "Bloqueo tiro/centro", "Repliegue",
    "Marcaje en centro", "Despeje en ABP def.", "Duelo en ABP def.",
    # acciones de equipo
    "Presión alta", "Robo / intercepción", "Duelo defensivo",
}

# Las 6 dimensiones del radar (ejes del spider chart)
RADAR_DIMENSIONS = [
    "Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón", "Volumen",
]


# --- Diccionario POR ACCIÓN (v2): clasificación específica de cada acción ---
_DIC_ACCIONES = {}
if isinstance(_PESOS_CANONICOS, dict):
    pass  # _PESOS_CANONICOS viene del cargador; el detalle por acción se lee aquí:
def _cargar_dic_por_accion():
    import os, json
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "diccionario_resultados.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("acciones", {}), d.get("pesos", {"exito":1.0,"parcial":0.5,"fallo":0.0})
    except Exception:
        return {}, {"exito":1.0,"parcial":0.5,"fallo":0.0}
_DIC_ACCIONES, _PESOS = _cargar_dic_por_accion()

# Acciones cuyo diccionario NO tiene ningún resultado de éxito ni parcial
# (faltas, tarjetas, penalti cometido, error grave...). Cuentan como intento y
# pesan siempre 0.0, así que en el predictor entrarían con un 0% garantizado y
# además ensuciarían el prior de su categoría. Se derivan del diccionario, no
# se listan a mano: una acción nueva sin éxito se recoge sola.
_ACCIONES_SIN_EXITO = frozenset(
    a for a, spec in _DIC_ACCIONES.items()
    if not (spec.get("exito") or spec.get("parcial"))
)


def predecible(accion: str) -> bool:
    """¿Tiene esta acción algún resultado de éxito posible? Predecir el
    '% de acierto' de una falta o una tarjeta no significa nada."""
    return accion not in _ACCIONES_SIN_EXITO


def _cargar_nota_cfg():
    """Carga la config del sistema de NOTA (Fase 2) del diccionario canónico."""
    import os, json
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "diccionario_resultados.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f).get("nota", {})
    except Exception:
        return {}
_NOTA_CFG = _cargar_nota_cfg()


def _cargar_exp_cfg():
    """Carga la config del predictor de acierto (Fase 5) del diccionario canónico."""
    import os, json
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "diccionario_resultados.json")
    defaults = {"k": 8.0, "min_muestra_resumen": 3, "umbral_destaca": 15.0}
    try:
        with open(ruta, encoding="utf-8") as f:
            cfg = json.load(f).get("expectativa", {})
        return {**defaults, **{k: cfg[k] for k in defaults if k in cfg}}
    except Exception:
        return defaults
_EXP_CFG = _cargar_exp_cfg()


def _clase_por_accion(accion, code):
    """Devuelve la clase de (accion, code) según el diccionario por acción, o None.
    Clases: exito, parcial, fallo, fallo_parcial, fallo_medio, fallo_grave, neutro.
    Las variantes de fallo (parcial/medio/grave) se tratan como 'fallo' para el
    % de acierto actual; sus pesos negativos solo se usan en el sistema de nota."""
    spec = _DIC_ACCIONES.get(accion)
    if not spec:
        return None
    for clase in ("exito", "parcial", "fallo", "fallo_parcial", "fallo_medio",
                  "fallo_grave", "neutro"):
        if code in spec.get(clase, []):
            return clase
    return None


# Clases que, para el % de acierto de hoy, cuentan como intento fallado.
_CLASES_FALLO = {"fallo", "fallo_parcial", "fallo_medio", "fallo_grave"}


def is_success(code: str, accion: str = None) -> bool:
    """¿Es éxito? Si se da la acción y está en el diccionario, clasifica por
    acción; si no, usa los conjuntos globales (compatibilidad)."""
    if accion is not None:
        c = _clase_por_accion(accion, code)
        if c is not None:
            return c == "exito"
    return code in SUCCESS_CODES


def is_attempt(code: str, accion: str = None) -> bool:
    """¿Cuenta para un ratio de acierto (éxito, parcial o cualquier fallo)?"""
    if accion is not None:
        c = _clase_por_accion(accion, code)
        if c is not None:
            return c in ("exito", "parcial") or c in _CLASES_FALLO
    return code in SUCCESS_CODES or code in FAIL_CODES or code in PARTIAL_CODES


def success_weight(code: str, accion: str = None) -> float:
    """Peso de acierto para el % ACTUAL: 1.0 éxito, 0.5 parcial, 0.0 cualquier
    fallo. Los pesos negativos por gravedad (fallo_grave, etc.) NO se aplican
    aquí; están definidos en el diccionario para el sistema de nota (Fase 2)."""
    if accion is not None:
        c = _clase_por_accion(accion, code)
        if c is not None:
            if c == "exito":
                return _PESOS.get("exito", 1.0)
            if c == "parcial":
                return _PESOS.get("parcial", 0.5)
            return 0.0  # todos los fallos: 0 en el % actual (no restan)
    if code in SUCCESS_CODES:
        return 1.0
    if code in PARTIAL_CODES:
        return 0.5
    return 0.0


# ----------------------------------------------------------------------------
# NORMALIZACIÓN DE EVENTOS
# ----------------------------------------------------------------------------
def flatten_events(sessions: list[dict[str, Any]],
                   equipos_principales: dict[str, str] | None = None) -> pd.DataFrame:
    """Aplana los eventos de una lista de sesiones en un único DataFrame.

    Cada sesión es un dict como el que devuelve storage.load_session.
    Añade columnas de contexto del partido a cada evento.

    `equipos_principales` ({jugador: equipo}) es opcional y solo se usa como
    FALLBACK de la columna `equipo_jugador` cuando una sesión antigua no trae
    el equipo del jugador en su `jugadores_info`.
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
            # minuto de descanso PROPIO de este partido (para separar 1ª/2ª parte
            # correctamente; cada partido puede tener el suyo).
            "minuto_descanso": (s.get("minuto_descanso")
                                or (s.get("meta") or {}).get("minuto_descanso") or 45),
            # nivel propio/rival del partido (para el ajuste por dificultad de la
            # NOTA, palanca 3). Viaja en cada evento; es constante dentro del partido.
            "nivel_propio": ((s.get("meta") or {}).get("nivel_propio")
                             or s.get("nivel_propio") or "Medio"),
            "nivel_rival": ((s.get("meta") or {}).get("nivel_rival")
                            or s.get("nivel_rival") or "Medio"),
        }
        pos_map = s.get("posiciones") or {}
        info_map = s.get("jugadores_info") or {}
        for ev in events:
            row = dict(sess_meta)
            jugador = ev.get("jugador", "")
            # PRIORIDAD de posición: la ficha del jugador (jugadores_info) manda
            # siempre, porque es la posición real y actual. Solo si la ficha no la
            # tiene, se usa el dict de posiciones de la sesión, y por último la que
            # quedó pegada en el evento (puede estar obsoleta, p. ej. un jugador
            # recolocado o un error antiguo). Esto evita que un evento viejo con
            # "POR" sobreescriba al MC que figura en la ficha.
            ficha = info_map.get(jugador) or {}
            posicion = ficha.get("pos") or pos_map.get(jugador) or ev.get("posicion", "")
            # EQUIPO DEL JUGADOR EN ESTE PARTIDO. Un jugador puede tener varios
            # equipos (selección absoluta, sub-20, club), así que el equipo es
            # por partido: manda el de `jugadores_info` de ESTA sesión. Solo si
            # esa sesión no lo trae se cae al equipo principal de la ficha
            # global (el que también da la bandera).
            equipo_jug = (ficha.get("equipo")
                          or (equipos_principales or {}).get(jugador, "") or "")
            row.update({
                "jugador": jugador,
                "jugador_info": ficha,
                "equipo_jugador": equipo_jug,
                "posicion": posicion,
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
            "equipo_visitante", "jugador", "equipo_jugador", "posicion",
            "minuto", "minuto_fmt", "accion", "resultado", "zona",
            "zona_x", "zona_y",
        ])
    df = pd.DataFrame(rows)
    # Garantizar columnas esperadas aunque los eventos sean antiguos.
    for col in ["posicion", "equipo_jugador", "zona", "zona_x", "zona_y",
                "minuto", "accion", "resultado"]:
        if col not in df.columns:
            df[col] = "" if col not in ("minuto", "zona_x", "zona_y") else None
    df["posicion"] = df["posicion"].fillna("")
    df["equipo_jugador"] = df["equipo_jugador"].fillna("")
    # Clasificación POR ACCIÓN (diccionario canónico v2): cada evento se evalúa
    # según los resultados válidos de SU acción. Fallback global si la acción no
    # está en el diccionario. Vale para datos viejos y nuevos, sin retaggear.
    df["exito"] = df.apply(lambda r: is_success(r["resultado"], r["accion"]), axis=1)
    df["intento"] = df.apply(lambda r: is_attempt(r["resultado"], r["accion"]), axis=1)
    df["peso"] = df.apply(lambda r: success_weight(r["resultado"], r["accion"]), axis=1)
    return df


# ----------------------------------------------------------------------------
# MULTI-EQUIPO / MULTI-POSICIÓN DE UN JUGADOR
# ----------------------------------------------------------------------------
# Un jugador puede aparecer con varios equipos (selección absoluta, sub-20,
# club) y en varias posiciones. Los datos se agregan por NOMBRE, así que estas
# dos funciones sirven para enseñar de dónde vienen y para filtrar.

def _por_partido(df, jugador: str, col: str) -> list[tuple[str, int]]:
    """Valores distintos de `col` para un jugador, con el nº de PARTIDOS en que
    aparece cada uno, ordenados de más a menos. Cuenta partidos, no acciones:
    un valor que sale en un solo partido con 80 eventos no debe ir primero."""
    if df is None or df.empty or col not in df.columns:
        return []
    d = df[df["jugador"] == jugador]
    d = d[d[col].astype(str).str.strip() != ""]
    if d.empty:
        return []
    conteo = d.groupby(col)["session_id"].nunique().to_dict()
    return sorted(((str(k), int(v)) for k, v in conteo.items()),
                  key=lambda t: (-t[1], t[0]))


def equipos_de_jugador(df, jugador: str) -> list[tuple[str, int]]:
    """[(equipo, nº de partidos)] del jugador, desc. Para el filtro de equipo
    del dashboard y para la cabecera."""
    return _por_partido(df, jugador, "equipo_jugador")


def posiciones_de_jugador(df, jugador: str) -> list[tuple[str, int]]:
    """[(posición, nº de partidos)] del jugador, desc. La posición sale de la
    ficha de cada partido (ver flatten_events), que es donde el scout apunta en
    qué puesto jugó ese día."""
    return _por_partido(df, jugador, "posicion")


# ----------------------------------------------------------------------------
# CATEGORÍA DE CADA ACCIÓN (para el radar)
# ----------------------------------------------------------------------------
def _action_category(accion: str) -> str:
    if accion in PASS_ACTIONS or accion == "Asistencia":
        return "Pase"
    if accion in DRIBBLE_ACTIONS or accion in {"Conducción progresiva", "Protección de balón",
                                               "Recibe entre líneas", "Falta recibida",
                                               "Control difícil", "Control fácil fallado",
                                               "Duelo aéreo of.", "Error grave / pérdida"}:
        return "Regate"
    if accion in SHOT_ACTIONS or accion in {"Generación de ocasión", "Ocasión clara fallada"}:
        return "Finalización"
    if accion in DEFENSE_ACTIONS:
        return "Defensa"
    if accion in {"Desmarque de ruptura", "Desmarque de apoyo", "Ataque al palo",
                  "Desmarque de arrastre", "Amplía el campo", "Ofrece línea de pase",
                  "Entrada en área rival"}:
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
    if "peso" not in df.columns:
        df["peso"] = df["resultado"].apply(success_weight)
    df["categoria"] = df["accion"].apply(_action_category)

    out = []
    for jugador, g in df.groupby("jugador"):
        intentos = g[g["intento"]]
        total_acc = len(g)
        aciertos = int(g["exito"].sum())
        # El % usa el peso (parcial=0.5) sobre el nº de intentos.
        pct = round(100 * g["peso"].sum() / len(intentos), 1) if len(intentos) else 0.0

        # Conteos por categoría
        cat_counts = g["categoria"].value_counts().to_dict()

        # % acierto por categoría (peso sobre intentos)
        cat_pct = {}
        for cat in ["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón"]:
            sub = g[g["categoria"] == cat]
            sub_int = sub[sub["intento"]]
            cat_pct[cat] = (round(100 * sub["peso"].sum() / len(sub_int), 1)
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


def _tercio_de(zona_x, zona_texto=""):
    """Tercio 0/1/2 de una fila. Prioriza zona_x; si falta, lo saca del texto
    de zona ('1er/2º/3er tercio'). Devuelve None si no se puede determinar."""
    if zona_x is not None and pd.notna(zona_x):
        try:
            zx = int(zona_x)
            if 0 <= zx <= 2:
                return zx
        except (TypeError, ValueError):
            pass
    for prefijo, col in _OLD_ZONE_TO_COL.items():
        if str(zona_texto).startswith(prefijo):
            return col
    return None


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
# RANKING PARAMETRIZABLE (para el gráfico de barras filtrable)
# ----------------------------------------------------------------------------
def _ensure_posicion(d):
    """Garantiza que el DataFrame tenga columna 'posicion' (vacía si falta)."""
    if "posicion" not in d.columns:
        d = d.copy()
        d["posicion"] = ""
    return d


def filter_by_minute(df: pd.DataFrame, min_lo: float = 0, min_hi: float = 120) -> pd.DataFrame:
    """Filtra el DataFrame por rango de minutos [min_lo, min_hi]."""
    if df.empty:
        return df
    return df[(df["minuto"] >= min_lo) & (df["minuto"] <= min_hi)]


def player_ranking(df: pd.DataFrame, accion=None, posicion=None,
                   resultado="todos", metrica="conteo",
                   min_lo=0, min_hi=120, top_n=5) -> pd.DataFrame:
    """Devuelve un ranking de jugadores según filtros.

    Parámetros:
      - accion: nombre de acción a filtrar, o None / "(todas)" para todas.
      - posicion: código de posición (DC, EXT...), o None / "(todas)".
      - resultado: "todos" | "acierto" | "fallo".
      - metrica: "conteo" (nº de acciones) | "pct" (% de acierto) | "aciertos".
      - min_lo, min_hi: rango de minutos.
      - top_n: número de jugadores a devolver.

    Devuelve un DataFrame con columnas: jugador, posicion, valor, acciones,
    aciertos, pct. Ordenado de mayor a menor por la métrica elegida.
    """
    cols = ["jugador", "posicion", "valor", "acciones", "aciertos", "pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    d = _ensure_posicion(df.copy())
    # Excluir filas de equipo (no aplican al ranking de jugadores).
    d = d[d["jugador"] != EQUIPO_TAG]
    d = filter_by_minute(d, min_lo, min_hi)

    if accion and accion != "(todas)":
        if isinstance(accion, (list, tuple, set)):
            d = d[d["accion"].isin(list(accion))]
        else:
            d = d[d["accion"] == accion]
    if posicion and posicion != "(todas)":
        d = d[d["posicion"] == posicion]
    if resultado == "acierto":
        d = d[d["exito"]]
    elif resultado == "fallo":
        d = d[d["intento"] & (~d["exito"])]

    if d.empty:
        return pd.DataFrame(columns=cols)

    out = []
    for jugador, g in d.groupby("jugador"):
        intentos = g[g["intento"]]
        acciones = len(g)
        aciertos = int(g["exito"].sum())
        pct = round(100 * aciertos / len(intentos), 1) if len(intentos) else 0.0
        # posición: la más frecuente registrada para ese jugador
        pos = g["posicion"].mode().iloc[0] if not g["posicion"].mode().empty else ""
        if metrica == "pct":
            valor = pct
        elif metrica == "aciertos":
            valor = aciertos
        elif metrica == "por90":
            mins = minutos_de_jugador(df, jugador)
            valor = round(acciones * 90.0 / mins, 1) if mins else 0.0
        elif metrica == "aciertos_por90":
            mins = minutos_de_jugador(df, jugador)
            valor = round(aciertos * 90.0 / mins, 1) if mins else 0.0
        else:
            valor = acciones
        out.append({"jugador": jugador, "posicion": pos, "valor": valor,
                    "acciones": acciones, "aciertos": aciertos, "pct": pct})

    res = pd.DataFrame(out).sort_values("valor", ascending=False).head(top_n)
    return res.reset_index(drop=True)


def position_averages(df: pd.DataFrame, accion=None, metrica="pct",
                      min_lo=0, min_hi=120) -> pd.DataFrame:
    """Media de una métrica por posición. Para comparar posiciones entre sí.
    Devuelve DataFrame: posicion, valor, n_jugadores, n_acciones."""
    cols = ["posicion", "valor", "n_jugadores", "n_acciones"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    d = _ensure_posicion(df.copy())
    d = d[d["jugador"] != EQUIPO_TAG]
    d = filter_by_minute(d, min_lo, min_hi)
    d = d[d["posicion"].astype(str) != ""]
    if accion and accion != "(todas)":
        if isinstance(accion, (list, tuple, set)):
            d = d[d["accion"].isin(list(accion))]
        else:
            d = d[d["accion"] == accion]
    if d.empty:
        return pd.DataFrame(columns=cols)

    out = []
    for pos, g in d.groupby("posicion"):
        intentos = g[g["intento"]]
        acciones = len(g)
        aciertos = int(g["exito"].sum())
        pct = round(100 * aciertos / len(intentos), 1) if len(intentos) else 0.0
        n_jug = g["jugador"].nunique()
        if metrica == "conteo":
            # media de acciones por jugador de esa posición
            valor = round(acciones / n_jug, 1) if n_jug else 0.0
        elif metrica == "aciertos":
            valor = round(aciertos / n_jug, 1) if n_jug else 0.0
        else:
            valor = pct
        out.append({"posicion": pos, "valor": valor, "n_jugadores": n_jug,
                    "n_acciones": acciones})
    res = pd.DataFrame(out).sort_values("valor", ascending=False)
    return res.reset_index(drop=True)


def scatter_volume_accuracy(df: pd.DataFrame, accion=None, posicion=None,
                            min_lo=0, min_hi=120) -> pd.DataFrame:
    """Datos para dispersión volumen (x=acciones) vs acierto (y=pct).
    Una fila por jugador. Devuelve: jugador, posicion, acciones, pct."""
    cols = ["jugador", "posicion", "acciones", "pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    d = _ensure_posicion(df.copy())
    d = d[d["jugador"] != EQUIPO_TAG]
    d = filter_by_minute(d, min_lo, min_hi)
    if accion and accion != "(todas)":
        if isinstance(accion, (list, tuple, set)):
            d = d[d["accion"].isin(list(accion))]
        else:
            d = d[d["accion"] == accion]
    if posicion and posicion != "(todas)":
        d = d[d["posicion"] == posicion]
    if d.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for jugador, g in d.groupby("jugador"):
        intentos = g[g["intento"]]
        acciones = len(g)
        pct = round(100 * g["exito"].sum() / len(intentos), 1) if len(intentos) else 0.0
        pos = g["posicion"].mode().iloc[0] if not g["posicion"].mode().empty else ""
        out.append({"jugador": jugador, "posicion": pos, "acciones": acciones, "pct": pct})
    return pd.DataFrame(out).reset_index(drop=True)


# ----------------------------------------------------------------------------
# DATOS PARA EL INFORME DEL JUGADOR
# ----------------------------------------------------------------------------
# Métricas seleccionables para el bloque "Volumen de acciones" del informe.
# Cada una es (etiqueta, función que cuenta sobre el df del jugador).
def _cnt_accion(df, accion):
    return int((df["accion"] == accion).sum())

VOLUMEN_METRICAS = {
    "Pases progresivos": lambda d: _cnt_accion(d, "Pase progresivo"),
    "Pases entre líneas": lambda d: _cnt_accion(d, "Pase entre líneas"),
    "Pases al espacio": lambda d: _cnt_accion(d, "Pase al espacio"),
    "Pases clave": lambda d: _cnt_accion(d, "Pase clave"),
    "Centros": lambda d: _cnt_accion(d, "Centro lateral"),
    "Asistencias": lambda d: _cnt_accion(d, "Asistencia"),
    "Regates ganados": lambda d: int(((d["accion"] == "Regate 1v1") & d["exito"]).sum()),
    "Conducciones progresivas": lambda d: _cnt_accion(d, "Conducción progresiva"),
    "Disparos": lambda d: int(d["accion"].isin(SHOT_ACTIONS).sum()),
    "Disparos a puerta": lambda d: int((d["accion"].isin(SHOT_ACTIONS) & d["resultado"].isin({"A puerta", "Gol"})).sum()),
    "Goles": lambda d: int((d["accion"].isin(SHOT_ACTIONS) & (d["resultado"] == "Gol")).sum()),
    "Recuperaciones": lambda d: _cnt_accion(d, "Recuperación"),
    "Recuperaciones 3er tercio": lambda d: int(((d["accion"] == "Recuperación") & (d["zona_x"] == 2)).sum()),
    "Intercepciones": lambda d: _cnt_accion(d, "Intercepción"),
    "Entradas / tackles": lambda d: _cnt_accion(d, "Entrada / tackle"),
    "Duelos aéreos ganados": lambda d: int((d["accion"].isin({"Duelo aéreo def.", "Duelo aéreo of."}) & d["exito"]).sum()),
    "Faltas recibidas": lambda d: _cnt_accion(d, "Falta recibida"),
    "Pérdidas": lambda d: _cnt_accion(d, "Error grave / pérdida"),
}


def players_in_position(df, posicion):
    """Lista de jugadores que tienen la posición dada (para elegir comparación)."""
    if df.empty:
        return []
    d = df[df["jugador"] != EQUIPO_TAG]
    d = d[d["posicion"] == posicion]
    return sorted(d["jugador"].unique().tolist())


def metricas_por_90(d, minutos):
    """Normaliza el volumen de acciones a 90 minutos, para comparar con justicia
    a jugadores que han disputado tiempos distintos (promesa 20' vs top 90')."""
    if not minutos or minutos <= 0:
        return {"acciones_90": 0.0, "factor": 0.0, "minutos": minutos}
    factor = 90.0 / minutos
    return {"acciones_90": round(len(d) * factor, 1), "factor": round(factor, 2),
            "minutos": minutos}


# Peso por zona del campo: una acción exitosa en el último tercio vale más que
# en zona propia. Multiplicador suave para no distorsionar en exceso.
PESO_ZONA = {0: 0.8, 1: 1.0, 2: 1.3}   # zona_x: 0 defensa, 1 medio, 2 ataque


def acierto_ponderado_zona(d):
    """% de acierto ponderando cada acción por la importancia de su zona.
    Premia acertar arriba (donde se decide) sobre acertar en zona segura."""
    di = d[d["intento"]].copy()
    if di.empty:
        return 0.0
    di["pz"] = di["zona_x"].map(PESO_ZONA).fillna(1.0)
    num = (di["peso"] * di["pz"]).sum()
    den = di["pz"].sum()
    return round(100 * num / den, 1) if den else 0.0


def acierto_por_zona(d):
    """% de acierto y volumen desglosado por tercio. Devuelve dict por tercio,
    para no quedarse solo en el global (que mezcla lo fácil con lo difícil)."""
    zonas = {0: "1er tercio (def)", 1: "2º tercio (medio)", 2: "3er tercio (ataque)"}
    out = {}
    for zx, nombre in zonas.items():
        sub = d[d["zona_x"] == zx]
        inten = sub[sub["intento"]]
        pct = round(100 * sub["peso"].sum() / len(inten), 1) if len(inten) else None
        out[nombre] = {"acciones": int(len(sub)), "pct": pct}
    return out


# ----------------------------------------------------------------------------
# SISTEMA DE NOTA (Fase 2) — modelo de VALOR ACUMULADO (tipo rating de analista)
# ----------------------------------------------------------------------------
# nota = clip(baseline + k × Σ(valor_outcome × factor_zona), 0, 10).
# Cada (acción, clase) tiene un valor propio y ASIMÉTRICO (premio si sale bien,
# castigo si sale mal). El premio (valor≥0) usa zona direccional (ofensivas
# premian arriba, defensivas cerca de tu área); el castigo (valor<0) usa la zona
# de pérdida (más caro cuanto más cerca de tu portería, en cualquier acción).
# Los neutros y las acciones no clasificables se excluyen. Toda la config vive en
# diccionario_resultados.json → "nota", editable a mano.
_NOTA_BASELINE = float(_NOTA_CFG.get("baseline", 6.0))
_NOTA_K = float(_NOTA_CFG.get("k", 0.45))
_NOTA_EXCLUIR = set(_NOTA_CFG.get("excluir_clases", ["neutro"]))
_NOTA_VALORES = _NOTA_CFG.get("valores", {})
_NOTA_VAL_DEF = _NOTA_CFG.get("valores_default",
                             {"exito": 0.2, "parcial": 0.1, "fallo": -0.1})
_NOTA_DEFENSIVAS = set(_NOTA_CFG.get("acciones_defensivas", []))
_NOTA_SIN_ZONA = set(_NOTA_CFG.get("acciones_sin_zona", []))
_NOTA_ZONA_PREMIO_OF = {int(k): float(v) for k, v in
                        _NOTA_CFG.get("peso_zona_premio_of", {0: 0.8, 1: 1.0, 2: 1.3}).items()}
_NOTA_ZONA_PREMIO_DEF = {int(k): float(v) for k, v in
                         _NOTA_CFG.get("peso_zona_premio_def", {0: 1.3, 1: 1.0, 2: 0.8}).items()}
_NOTA_ZONA_PERDIDA = {int(k): float(v) for k, v in
                      _NOTA_CFG.get("peso_zona_perdida", {0: 1.3, 1: 1.0, 2: 0.7}).items()}
# Palanca 1 (volumen): las acciones de circulación de bajo riesgo (pases de
# seguridad + conducción) no suman lineal; su aporte POSITIVO se comprime por
# partido con techo_circulacion·tanh(Σ/techo). Palanca 3 (rival): premio y
# castigo se escalan según el escalón de nivel del rival (difícil = +mérito/−castigo).
_NOTA_CIRCULACION = set(_NOTA_CFG.get("circulacion_bajo_riesgo", []))
_NOTA_TECHO_CIRC = float(_NOTA_CFG.get("techo_circulacion", 0.0))
_NOTA_RIVAL_PREMIO = float(_NOTA_CFG.get("rival_sensibilidad_premio", 0.0))
_NOTA_RIVAL_CASTIGO = float(_NOTA_CFG.get("rival_sensibilidad_castigo", 0.0))
_NOTA_NIVEL_VAL = {str(k): float(v) for k, v in
                   _NOTA_CFG.get("nivel_valor",
                                 {"Élite": 4, "Alto": 3, "Medio": 2, "Bajo": 1}).items()}


def _valor_outcome_nota(accion, clase):
    """Valor base de (acción, clase): premio si sale bien, castigo si sale mal.
    Cae al valor por defecto de la clase si la acción no está tabulada; 0 si no
    hay ni valor específico ni por defecto para esa clase."""
    va = _NOTA_VALORES.get(accion)
    if va is not None and clase in va:
        return float(va[clase])
    if clase in _NOTA_VAL_DEF:
        return float(_NOTA_VAL_DEF[clase])
    return 0.0


def _factor_zona_nota(accion, valor, zona_x):
    """Factor de zona. Premio (valor≥0): direccional — ofensivas valen más arriba
    ({0:0.8,1:1,2:1.3}), defensivas más cerca de tu área ({0:1.3,1:1,2:0.8}).
    Castigo (valor<0): zona de pérdida ({0:1.3,1:1,2:0.7}) — perder el balón o el
    duelo duele más cerca de tu portería, en cualquier acción. Sin zona o zona
    desconocida → 1.0."""
    if accion in _NOTA_SIN_ZONA:
        return 1.0
    try:
        zx = int(zona_x)
    except (TypeError, ValueError):
        return 1.0
    if valor < 0:
        return _NOTA_ZONA_PERDIDA.get(zx, 1.0)
    tabla = _NOTA_ZONA_PREMIO_DEF if accion in _NOTA_DEFENSIVAS else _NOTA_ZONA_PREMIO_OF
    return tabla.get(zx, 1.0)


def nota_evento(accion, resultado, zona_x):
    """Contribución (float) de un evento a la nota, o None si se excluye (neutro o
    acción/resultado no clasificable). contribución = valor × factor_zona."""
    clase = _clase_por_accion(accion, resultado)
    if clase is None or clase in _NOTA_EXCLUIR:
        return None
    valor = _valor_outcome_nota(accion, clase)
    return valor * _factor_zona_nota(accion, valor, zona_x)


def _nivel_partido(d, col, defecto="Medio"):
    """Nivel (propio/rival) del partido a partir del DataFrame. Asume UN partido
    (es constante dentro de él); toma el primer valor no vacío."""
    if col not in d.columns:
        return defecto
    for v in d[col]:
        if isinstance(v, str) and v.strip():
            return v
    return defecto


def nota_jugador(d):
    """Nota 0-10 del jugador (modelo de valor acumulado). d = DataFrame de eventos
    de UN jugador en UN partido (ya filtrado por parte/contexto si procede).
    nota = clip(baseline + k × [premio·f_premio + castigo·f_castigo], 0, 10).
    Sobre el Σ de contribuciones se aplican dos ajustes de scout (Fase 2):
      · Palanca 1 (volumen): el aporte POSITIVO de la circulación de bajo riesgo
        (pases de seguridad + conducción) no crece lineal; se comprime con
        techo·tanh(Σ/techo). Los fallos de esas acciones sí restan completo.
      · Palanca 3 (rival): premio y castigo se escalan según el escalón de nivel
        del rival (difícil = más mérito y más perdón).
    Devuelve {nota, suma, n}: suma = valor acumulado ya ajustado; n = nº de
    acciones que puntúan (excluye neutros). Sin acciones válidas → nota None.
    Asume UN partido: el freno de volumen y el nivel de rival son por partido."""
    if d is None or d.empty:
        return {"nota": None, "suma": 0.0, "n": 0}
    # Palanca 3: factor de rival (difícil = +mérito / −castigo).
    delta = (_NOTA_NIVEL_VAL.get(_nivel_partido(d, "nivel_rival"), 2.0)
             - _NOTA_NIVEL_VAL.get(_nivel_partido(d, "nivel_propio"), 2.0))
    f_premio = 1.0 + _NOTA_RIVAL_PREMIO * delta
    f_castigo = 1.0 - _NOTA_RIVAL_CASTIGO * delta
    pos_circ = 0.0   # aporte positivo de la circulación de bajo riesgo (se comprime)
    pos_resto = 0.0  # resto de aportes positivos (lineal)
    neg_total = 0.0  # todos los castigos (incl. pases de circulación fallados)
    n = 0
    for accion, resultado, zx in zip(d["accion"], d["resultado"], d["zona_x"]):
        c = nota_evento(accion, resultado, zx)
        if c is None:
            continue
        n += 1
        if c >= 0:
            if accion in _NOTA_CIRCULACION:
                pos_circ += c
            else:
                pos_resto += c
        else:
            neg_total += c
    if n == 0:
        return {"nota": None, "suma": 0.0, "n": 0}
    # Palanca 1: comprimir el aporte positivo de la circulación de bajo riesgo.
    if _NOTA_TECHO_CIRC > 0:
        pos_circ = _NOTA_TECHO_CIRC * float(np.tanh(pos_circ / _NOTA_TECHO_CIRC))
    suma = (pos_circ + pos_resto) * f_premio + neg_total * f_castigo
    nota = max(0.0, min(10.0, _NOTA_BASELINE + _NOTA_K * suma))
    return {"nota": round(nota, 1), "suma": round(suma, 3), "n": n}


def nota_media_jugador(df, jugador):
    """Nota GLOBAL del jugador = media SIMPLE de sus notas por partido (cada
    partido pesa igual, no acumula). Devuelve {nota, n_partidos, n_acciones}.
    df ya viene filtrado por parte/contexto si procede. Sin partidos válidos →
    nota None. Es lo que se muestra en el badge del hero; no confundir con
    nota_jugador (valor acumulado sobre el pool, que satura con más partidos)."""
    serie = serie_nota_por_partido(df, jugador)
    if not serie:
        return {"nota": None, "n_partidos": 0, "n_acciones": 0}
    notas = [p["valor"] for p in serie]
    n_acc = sum(p["n"] for p in serie)
    media = sum(notas) / len(notas)
    return {"nota": round(media, 1), "n_partidos": len(notas), "n_acciones": n_acc}


def serie_nota_por_partido(df, jugador):
    """Nota del jugador partido a partido, para el gráfico evolutivo.
    Devuelve lista {fecha, valor, sesion, rival, n} ordenada por fecha."""
    d = df[df["jugador"] == jugador].copy()
    if d.empty:
        return []
    out = []
    for sid, g in d.groupby("session_id"):
        res = nota_jugador(g)
        if res["nota"] is None:
            continue
        fecha = g["fecha"].iloc[0] if "fecha" in g.columns and not g["fecha"].empty else sid
        sesion = g["sesion"].iloc[0] if "sesion" in g.columns and not g["sesion"].empty else sid
        rival = _rival_partido(g) or str(sesion)
        out.append({"fecha": str(fecha), "valor": res["nota"],
                    "sesion": str(sesion), "rival": str(rival), "n": res["n"]})
    out.sort(key=lambda x: x["fecha"])
    return out


def player_report_data(df_all, jugador, volumen_keys, fuente="total", session_id=None,
                       info_jugador=None):
    """Reúne todo lo que el informe necesita de un jugador.

    df_all: todas las sesiones aplanadas (de jugadores).
    jugador: nombre del jugador del informe.
    volumen_keys: lista de claves de volumen. Cada clave puede ser una acción
       ("Pase progresivo") o "Acción @ Tercio" para filtrar por tercio
       (p. ej. "Recuperación @ 3er tercio").
    fuente: "total" o "sesion" (con session_id).
    info_jugador: dict {pos, equipo, edad, foto} del jugador, si existe.
    """
    d = df_all[df_all["jugador"] == jugador].copy()
    if fuente == "sesion" and session_id:
        d = d[d["session_id"] == session_id]

    pm = player_metrics(df_all)
    fila = pm[pm["jugador"] == jugador]
    fila = fila.iloc[0].to_dict() if not fila.empty else {}

    radar_vals = radar_axes(fila, df_all) if fila else [0, 0, 0, 0, 0, 0]
    facetas = dict(zip(["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón"],
                       radar_vals[:5]))

    # Volumen de acciones flexible: cuenta cualquier acción, con filtro de tercio.
    volumen = []
    for k in volumen_keys:
        volumen.append((k, _contar_volumen(d, k)))

    grid = zone_grid_counts(d)
    por_tercio = grid.sum(axis=0).tolist()

    destacados, mejorar = strengths_weaknesses(facetas, d)

    intentos = d[d["intento"]]
    pct_global = round(100 * d["exito"].sum() / len(intentos), 1) if len(intentos) else 0.0
    # Minutos jugados: si la ficha tiene entrada/salida, usar esa ventana real
    # (clave para suplentes). Si no, caer al minuto de la última acción.
    info = info_jugador or {}
    if info.get("min_out") is not None or info.get("min_in") is not None:
        min_in = int(info.get("min_in", 0))
        min_out = int(info.get("min_out", 90))
        minutos = max(0, min_out - min_in)
    else:
        minutos = int(d["minuto"].max()) if not d.empty else 0

    # Posición real del jugador: del info, si no de sus datos.
    if info.get("pos"):
        posicion = info["pos"]
    elif not d.empty and not d["posicion"].mode().empty:
        posicion = d["posicion"].mode().iloc[0]
    else:
        posicion = ""

    # --- Métricas de analista ---
    por90 = metricas_por_90(d, minutos)
    acierto_pond = acierto_ponderado_zona(d)
    acierto_zonas = acierto_por_zona(d)

    return {
        "jugador": jugador,
        "posicion": posicion,
        "equipo": info.get("equipo", ""),
        "edad": info.get("edad", ""),
        "acciones": int(len(d)),
        "pct_global": pct_global,
        "minutos": minutos,
        "acciones_por_90": por90["acciones_90"],
        "acierto_ponderado": acierto_pond,
        "acierto_por_zona": acierto_zonas,
        "facetas": facetas,
        "radar": radar_vals,
        "volumen": volumen,
        "grid": grid.tolist(),
        "por_tercio": por_tercio,
        "destacados": destacados,
        "mejorar": mejorar,
    }


# Tercios para el volumen flexible: etiqueta -> índice de columna (zona_x)
TERCIOS_IDX = {"1er tercio": 0, "2º tercio": 1, "3er tercio": 2}


def _contar_volumen(d, clave):
    """Cuenta una métrica de volumen. La clave puede ser:
      - "Acción"                -> todas las de esa acción
      - "Acción @ 3er tercio"   -> solo en ese tercio (por zona_x)
      - "Acción ✓"              -> solo las exitosas
      - "Acción ✓ @ 3er tercio" -> exitosas en ese tercio
    """
    if d.empty:
        return 0
    accion = clave
    tercio = None
    solo_exito = False
    if " @ " in accion:
        accion, ter = accion.split(" @ ", 1)
        tercio = TERCIOS_IDX.get(ter.strip())
    if accion.endswith(" ✓"):
        accion = accion[:-2].strip()
        solo_exito = True
    sub = d[d["accion"] == accion]
    if solo_exito:
        sub = sub[sub["exito"]]
    if tercio is not None:
        sub = sub[sub["zona_x"] == tercio]
    return int(len(sub))


def opciones_volumen(df):
    """Genera la lista de opciones de volumen para el cuestionario: cada acción
    presente, su variante exitosa, y por cada tercio."""
    if df.empty:
        return []
    acciones = sorted(a for a in df["accion"].unique() if a and a != "—")
    opts = []
    for a in acciones:
        opts.append(a)
        opts.append(f"{a} ✓")
        for ter in ["1er tercio", "2º tercio", "3er tercio"]:
            opts.append(f"{a} @ {ter}")
    return opts


def strengths_weaknesses(facetas, d, umbral_alto=65, umbral_bajo=45):
    """Determina en qué destaca y qué debe mejorar, por sus datos.
    Usa el % por faceta: alto -> destaca, bajo -> mejorar. Solo considera
    facetas con un mínimo de intentos para no marcar ruido."""
    cat_min_intentos = 3
    # contar intentos por faceta
    d = d.copy()
    if not d.empty:
        d["categoria"] = d["accion"].apply(_action_category)
    destacados, mejorar = [], []
    for fac, pct in facetas.items():
        if d.empty:
            continue
        sub = d[d["categoria"] == fac]
        n_int = int(sub["intento"].sum())
        if n_int < cat_min_intentos:
            continue
        if pct >= umbral_alto:
            destacados.append((fac, pct))
        elif pct < umbral_bajo:
            mejorar.append((fac, pct))
    destacados.sort(key=lambda t: t[1], reverse=True)
    mejorar.sort(key=lambda t: t[1])
    return destacados[:4], mejorar[:3]


def player_comparison(df_all, jugador_a, jugador_b, estadisticas):
    """Compara dos jugadores en las estadísticas (facetas) elegidas.
    Devuelve lista de (faceta, pct_a, pct_b)."""
    pm = player_metrics(df_all)
    mapa = {"Pase": "pct_pase", "Regate": "pct_regate", "Finalización": "pct_finalizacion",
            "Defensa": "pct_defensa", "Mov. sin balón": "pct_mov"}
    def fila(j):
        f = pm[pm["jugador"] == j]
        return f.iloc[0].to_dict() if not f.empty else {}
    fa, fb = fila(jugador_a), fila(jugador_b)
    out = []
    for est in estadisticas:
        col = mapa.get(est)
        if col:
            out.append((est, fa.get(col, 0.0), fb.get(col, 0.0)))
    return out


def filter_by_parte(df, parte, minuto_descanso=None):
    """Filtra por parte del partido. parte: 'todo' | '1' (1ª) | '2' (2ª).
    El corte se hace con el minuto de descanso PROPIO de cada partido (columna
    'minuto_descanso' de cada evento). Si no existe esa columna, usa el valor
    'minuto_descanso' pasado como argumento, y si tampoco, 45."""
    if df.empty or parte == "todo":
        return df
    if "minuto_descanso" in df.columns:
        corte = df["minuto_descanso"].fillna(minuto_descanso or 45)
    else:
        corte = minuto_descanso or 45
    if parte == "1":
        return df[df["minuto"] < corte]
    if parte == "2":
        return df[df["minuto"] >= corte]
    return df


# ============================================================================
# SELECTOR CATEGORÍA/ACCIÓN Y MÉTRICAS GENÉRICAS (para gráficos configurables)
# ============================================================================
CATEGORIAS = ["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón", "Otros"]


def acciones_por_categoria(df, jugadores=None, posicion=None):
    """Devuelve {categoria: [acciones presentes en los datos]} para construir los
    checks del selector. Filtra por jugadores/posición si se indican."""
    d = df[df["jugador"] != EQUIPO_TAG].copy()
    if jugadores:
        d = d[d["jugador"].isin(jugadores)]
    if posicion:
        d = d[d["posicion"] == posicion]
    if d.empty:
        return {}
    d["categoria"] = d["accion"].apply(_action_category)
    out = {}
    for cat in CATEGORIAS:
        accs = sorted(d[d["categoria"] == cat]["accion"].unique())
        if accs:
            out[cat] = accs
    return out


def metrica_jugador(df, jugador, acciones, modo="aciertos"):
    """Métrica de un jugador sobre una selección de acciones.
    modo='aciertos' -> % de acierto (ponderado, parcial=0.5).
    modo='totales'  -> recuento de acciones.
    Devuelve un número (float)."""
    d = df[(df["jugador"] == jugador) & (df["accion"].isin(acciones))]
    if d.empty:
        return 0.0
    if modo == "totales":
        return float(len(d))
    intentos = d[d["intento"]] if "intento" in d.columns else d
    if "peso" in d.columns and len(intentos):
        return round(100 * d["peso"].sum() / len(intentos), 1)
    return 0.0


def distribucion_metrica(df, acciones, modo="aciertos", jugadores=None, posicion=None):
    """Para el box plot: devuelve {jugador: valor} de la métrica sobre las
    acciones elegidas, en el universo de jugadores filtrado."""
    d = df[df["jugador"] != EQUIPO_TAG].copy()
    if posicion:
        d = d[d["posicion"] == posicion]
    universo = jugadores or sorted(d["jugador"].unique())
    return {j: metrica_jugador(df, j, acciones, modo) for j in universo}


def serie_temporal(df, jugador, acciones, modo="aciertos"):
    """Para el gráfico de línea: valor de la métrica partido a partido.
    Devuelve lista de dicts {fecha, valor, sesion, rival} ordenada
    cronológicamente. 'rival' es el equipo contrario en ese partido."""
    d = df[(df["jugador"] == jugador) & (df["accion"].isin(acciones))].copy()
    if d.empty:
        return []
    out = []
    for sid, g in d.groupby("session_id"):
        fecha = g["fecha"].iloc[0] if "fecha" in g.columns and not g["fecha"].empty else sid
        sesion = g["sesion"].iloc[0] if "sesion" in g.columns and not g["sesion"].empty else sid
        # El rival: si el jugador es del equipo local, el rival es el visitante,
        # y al revés. Se determina con el equipo del jugador (jugador_info).
        rival = _rival_partido(g) or str(sesion)
        if modo == "totales":
            val = float(len(g))
        else:
            inten = g[g["intento"]]
            val = round(100 * g["peso"].sum() / len(inten), 1) if len(inten) else 0.0
        out.append({"fecha": str(fecha), "valor": val,
                    "sesion": str(sesion), "rival": str(rival)})
    out.sort(key=lambda x: x["fecha"])
    return out


def proporcion_acciones(df, jugador, por="categoria"):
    """Para el donut: proporción de acciones del jugador, agrupadas por
    'categoria' o por 'accion'. Devuelve lista de (etiqueta, conteo) desc."""
    d = df[df["jugador"] == jugador].copy()
    if d.empty:
        return []
    if por == "categoria":
        d["g"] = d["accion"].apply(_action_category)
    else:
        d["g"] = d["accion"]
    serie = d["g"].value_counts()
    return [(k, int(v)) for k, v in serie.items()]


def radar_axes_custom(df, jugador, categorias, modo="aciertos"):
    """Ejes del radar configurables: una entrada por categoría elegida.
    modo='aciertos' -> % de acierto por categoría (0-100).
    modo='totales'  -> recuento por categoría, normalizado al máximo (0-100).
    Devuelve (labels, valores)."""
    d = df[df["jugador"] == jugador].copy()
    if d.empty:
        return categorias, [0.0] * len(categorias)
    d["categoria"] = d["accion"].apply(_action_category)
    labels, vals = [], []
    if modo == "totales":
        # normalizar al máximo entre las categorías elegidas para que el radar tenga forma
        counts = {c: int((d["categoria"] == c).sum()) for c in categorias}
        mx = max(counts.values()) or 1
        for c in categorias:
            labels.append(c); vals.append(round(100 * counts[c] / mx, 1))
    else:
        for c in categorias:
            sub = d[d["categoria"] == c]
            inten = sub[sub["intento"]] if "intento" in sub.columns else sub
            v = round(100 * sub["peso"].sum() / len(inten), 1) if len(inten) else 0.0
            labels.append(c); vals.append(v)
    return labels, vals


def radar_ejes_seleccion(df, jugador, ejes, modo="aciertos"):
    """Radar con ejes arbitrarios: cada eje puede ser una CATEGORÍA (Pase, Regate...)
    o una ACCIÓN concreta (Pase atrás, Regate 1v1...). Calcula el valor de cada eje.
    modo='aciertos' -> % de acierto; 'totales' -> recuento normalizado al máximo;
    'por90' -> acciones por 90 min, normalizado al máximo entre los ejes.
    Devuelve (labels, valores)."""
    d = df[df["jugador"] == jugador].copy()
    if d.empty or not ejes:
        return ejes, [0.0] * len(ejes)
    d["categoria"] = d["accion"].apply(_action_category)
    cats_validas = set(CATEGORIAS)

    def subset(eje):
        if eje in cats_validas:
            return d[d["categoria"] == eje]
        return d[d["accion"] == eje]

    if modo == "por90":
        mins = minutos_de_jugador(df, jugador) or 0
        if mins <= 0:
            return ejes, [0.0] * len(ejes)
        p90 = {e: len(subset(e)) * 90.0 / mins for e in ejes}
        mx = max(p90.values()) or 1
        return ejes, [round(100 * p90[e] / mx, 1) for e in ejes]
    if modo == "totales":
        counts = {e: len(subset(e)) for e in ejes}
        mx = max(counts.values()) or 1
        return ejes, [round(100 * counts[e] / mx, 1) for e in ejes]
    vals = []
    for e in ejes:
        sub = subset(e)
        inten = sub[sub["intento"]] if "intento" in sub.columns else sub
        vals.append(round(100 * sub["peso"].sum() / len(inten), 1) if len(inten) else 0.0)
    return ejes, vals


def minutos_de_jugador(df_all, jugador):
    """Minutos reales jugados, desde la ficha (min_in/min_out) si existe, o el
    último minuto con acción como aproximación. Usa la primera sesión donde
    aparece su info; si juega varios partidos, suma los minutos de cada uno."""
    total = 0
    vistos = set()
    for _, row in df_all[df_all["jugador"] == jugador].iterrows():
        sid = row.get("session_id")
        if sid in vistos:
            continue
        vistos.add(sid)
        info = row.get("jugador_info") if isinstance(row.get("jugador_info"), dict) else None
        if info and (info.get("min_in") is not None or info.get("min_out") is not None):
            mi = int(info.get("min_in", 0)); mo = int(info.get("min_out", 90))
            total += max(0, mo - mi)
        else:
            sub = df_all[(df_all["jugador"] == jugador) & (df_all["session_id"] == sid)]
            total += int(sub["minuto"].max()) if not sub.empty else 0
    return total or 0


def metrica_por_90_jugador(df_all, jugador, acciones):
    """Cuenta acciones del jugador (en la selección) normalizadas a 90 minutos,
    usando sus minutos reales. Devuelve un float."""
    d = df_all[(df_all["jugador"] == jugador)]
    if acciones:
        d = d[d["accion"].isin(acciones)]
    n = len(d)
    minutos = minutos_de_jugador(df_all, jugador)
    if not minutos or minutos <= 0:
        return 0.0
    return round(n * 90.0 / minutos, 1)


def aciertos_por_90_jugador(df_all, jugador, acciones):
    """Igual que metrica_por_90_jugador pero contando solo los ACIERTOS
    (acciones exitosas), normalizados a 90 minutos. Devuelve un float."""
    d = df_all[(df_all["jugador"] == jugador)]
    if acciones:
        d = d[d["accion"].isin(acciones)]
    n_aciertos = int(d["exito"].sum()) if "exito" in d.columns else 0
    minutos = minutos_de_jugador(df_all, jugador)
    if not minutos or minutos <= 0:
        return 0.0
    return round(n_aciertos * 90.0 / minutos, 1)


# ============================================================================
# DASHBOARD DE JUGADOR — métricas por posición y filtro de modo
# ============================================================================

# Definición de las métricas del dashboard. Cada métrica tiene:
#   - label: lo que se ve en la tarjeta
#   - acciones: lista de acciones que cuenta (sumadas), o None para casos especiales
#   - especial: "goles" o "pct_pase" para los cálculos no estándar
GOL_ACTIONS = {"Remate", "Remate de cabeza", "Remate desde fuera",
               "Remate a balón parado", "Falta directa a puerta", "Tiro"}

METRICAS_DASH = {
    "regate":        {"label": "Regate 1v1", "acciones": ["Regate 1v1"]},
    "conduccion":    {"label": "Conducción prog.", "acciones": ["Conducción progresiva"]},
    "recorte":       {"label": "Recorte / ritmo", "acciones": ["Recorte / cambio ritmo"]},
    "presion":       {"label": "Presión fuerza error", "acciones": ["Presión fuerza error"]},
    "desm_ruptura":  {"label": "Desmarque ruptura", "acciones": ["Desmarque de ruptura"]},
    "remates":       {"label": "Remates", "acciones": list(SHOT_ACTIONS)},
    "goles":         {"label": "Goles", "acciones": None, "especial": "goles"},
    "centro":        {"label": "Centro lateral", "acciones": ["Centro lateral"]},
    "pase_lineas":   {"label": "Pase entre líneas", "acciones": ["Pase entre líneas"]},
    "pase_prog":     {"label": "Pase progresivo", "acciones": ["Pase progresivo", "Pase entre líneas", "Pase al espacio"]},
    "pase_clave":    {"label": "Pase clave", "acciones": ["Pase clave"]},
    "sprint_def":    {"label": "Sprint def.", "acciones": ["Sprint def."]},
    "ofrece_apoyo":  {"label": "Ofrece línea + desm. apoyo", "acciones": ["Ofrece línea de pase", "Desmarque de apoyo"]},
    "def_combinada": {"label": "Recup.+Tackle+Int.+Antic.", "acciones": ["Recuperación", "Entrada / tackle", "Intercepción", "Anticipación"]},
    "duelo_def":     {"label": "Duelo 1v1 def.", "acciones": ["Duelo 1v1 def."]},
    "duelos_aereos": {"label": "Duelos aéreos (def+of)", "acciones": ["Duelo aéreo def.", "Duelo aéreo of.", "Duelo en ABP def."]},
    "pct_pase":      {"label": "% acierto pase", "acciones": None, "especial": "pct_pase"},
    "gen_ocasion":   {"label": "Generación ocasión", "acciones": ["Generación de ocasión"]},
    "entrada_area":  {"label": "Entrada área rival", "acciones": ["Entrada en área rival"]},
    "duelo_aereo_of":{"label": "Duelo aéreo of.", "acciones": ["Duelo aéreo of."]},
    "recibe_lineas": {"label": "Recibe entre líneas", "acciones": ["Recibe entre líneas"]},
    "duelo_aereo_def":{"label": "Duelo aéreo def.", "acciones": ["Duelo aéreo def.", "Duelo en ABP def."]},
    "despeje":       {"label": "Despeje", "acciones": ["Despeje", "Despeje en ABP def."]},
    "amplia_campo":  {"label": "Amplía el campo", "acciones": ["Amplía el campo"]},
}

# Sets de 8 métricas por posición (claves de METRICAS_DASH).
SETS_POSICION = {
    "EXT": ["regate", "conduccion", "recorte", "presion", "desm_ruptura", "remates", "goles", "centro"],
    "MP":  ["pase_lineas", "pase_prog", "conduccion", "regate", "pase_clave", "sprint_def", "ofrece_apoyo", "recorte"],
    "MC/MCD": ["pase_lineas", "pase_prog", "def_combinada", "duelo_def", "conduccion", "ofrece_apoyo", "pct_pase", "duelos_aereos"],
    "DC":  ["goles", "remates", "pase_prog", "entrada_area", "duelo_aereo_of", "ofrece_apoyo", "desm_ruptura", "recibe_lineas"],
    "DFC": ["duelo_def", "duelo_aereo_def", "def_combinada", "despeje", "conduccion", "pase_lineas", "pct_pase", "pase_prog"],
    "LAT": ["duelo_def", "def_combinada", "centro", "pase_prog", "conduccion", "recorte", "despeje", "amplia_campo"],
}


def set_de_posicion(posicion: str) -> str:
    """Mapea una posición cruda a uno de los 6 sets del radar, con POR aparte.
    Fuente única de verdad; el radar (scouting_app._sugerir_set) delega aquí.
    MED (mediocentro ofensivo) agrupa con la MEDIAPUNTA (MP), decisión del usuario.
    El bloque MP va ANTES que EXT para que 'MED' no colisione con 'ED' (extremo)."""
    p = (posicion or "").upper()
    if "POR" in p:
        return "POR"
    if "MED" in p or any(x in p for x in ["MP", "MEDIAPUNTA", "ENG", "MCO"]):
        return "MP"
    if any(x in p for x in ["EXT", "EI", "ED", "BANDA", "EXTREMO"]):
        return "EXT"
    if any(x in p for x in ["DC", "DEL", "9", "PUNTA"]):
        return "DC"
    if any(x in p for x in ["DFC", "CENTRAL", "CB"]):
        return "DFC"
    if any(x in p for x in ["LAT", "LD", "LI", "CARRIL"]):
        return "LAT"
    return "MC/MCD"


def agregados_expectativa(df):
    """Agrega (aciertos_ponderados, intentos) por los niveles de la cascada de
    la Fase 5 (5 pasos de suavizado). Solo cuenta filas con intento==True;
    A = suma de 'peso', N = nº de filas. Excluye acciones de equipo y acciones
    sin éxito posible (ver `predecible`). Ver el plan/spec para el detalle.

    El nivel `accion_tercio_pos_jug` existe para poder restar la aportación del
    propio jugador a la expectativa de su posición (leave-one-out).
    """
    niveles = {"global": [0.0, 0], "categoria": {}, "accion": {},
               "accion_tercio": {}, "accion_tercio_pos": {},
               "accion_tercio_pos_jug": {}, "accion_tercio_jug": {}}
    if df is None or df.empty:
        niveles["global"] = (0.0, 0)
        return niveles

    def _bump(d, clave, w):
        a, n = d.get(clave, (0.0, 0))
        d[clave] = (a + w, n + 1)

    for _, r in df.iterrows():
        if r.get("jugador") == EQUIPO_TAG:
            continue
        if not bool(r.get("intento")):
            continue
        accion = r.get("accion", "")
        if not predecible(accion):
            continue
        tercio = _tercio_de(r.get("zona_x"), r.get("zona", ""))
        if tercio is None:
            continue
        # peso viene siempre de success_weight: float, nunca NaN.
        w = float(r.get("peso", 0.0) or 0.0)
        cat = _action_category(accion)
        setpos = set_de_posicion(r.get("posicion", ""))
        jug = r.get("jugador", "")
        niveles["global"][0] += w
        niveles["global"][1] += 1
        _bump(niveles["categoria"], cat, w)
        _bump(niveles["accion"], accion, w)
        _bump(niveles["accion_tercio"], (accion, tercio), w)
        _bump(niveles["accion_tercio_pos"], (accion, tercio, setpos), w)
        _bump(niveles["accion_tercio_pos_jug"], (accion, tercio, setpos, jug), w)
        _bump(niveles["accion_tercio_jug"], (accion, tercio, jug), w)

    niveles["global"] = (niveles["global"][0], niveles["global"][1])
    return niveles


def predecir_acierto(agg, jugador, accion, tercio, posicion, k=None):
    """Recorre la cascada (5 pasos de suavizado) y devuelve la predicción de
    acierto de (jugador, accion, tercio) suavizada hacia la expectativa de su
    posición. `agg` es la salida de agregados_expectativa. Ver spec §3.3.

    LEAVE-ONE-OUT: la expectativa de la posición EXCLUYE las acciones del propio
    jugador, para no compararlo consigo mismo. `n_pos` cuenta los casos de sus
    COMPAÑEROS de puesto; si es 0 no hay grupo y la expectativa cae al nivel
    acción+zona (cómo se le da esa acción a todo el mundo en esa zona)."""
    if k is None:
        k = _EXP_CFG["k"]

    def _smooth(pair, prior):
        a, n = pair if pair else (0.0, 0)
        return (a + k * prior) / (n + k) if (n + k) else prior

    ga, gn = agg.get("global", (0.0, 0))
    prior0 = (ga / gn) if gn else 0.5

    cat = _action_category(accion)
    setpos = set_de_posicion(posicion)

    rate_cat = _smooth(agg["categoria"].get(cat), prior0)
    rate_acc = _smooth(agg["accion"].get(accion), rate_cat)
    rate_az = _smooth(agg["accion_tercio"].get((accion, tercio)), rate_acc)

    # Nivel 3 SIN el propio jugador (leave-one-out).
    par_pos = agg["accion_tercio_pos"].get((accion, tercio, setpos))
    propio = agg.get("accion_tercio_pos_jug", {}).get((accion, tercio, setpos, jugador))
    a_pos, n_pos = par_pos if par_pos else (0.0, 0)
    a_own, n_own = propio if propio else (0.0, 0)
    par_pos_loo = (max(0.0, a_pos - a_own), max(0, n_pos - n_own))
    rate_azp = _smooth(par_pos_loo, rate_az)

    par_jug = agg["accion_tercio_jug"].get((accion, tercio, jugador))
    rate_azj = _smooth(par_jug, rate_azp)

    aj, nj = par_jug if par_jug else (0.0, 0)
    return {
        "pred": rate_azj,
        "expectativa_pos": rate_azp,
        "n_jugador": nj,
        "aciertos_jugador": aj,
        "n_pos": par_pos_loo[1],   # casos de los COMPAÑEROS, no del propio jugador
        "set": setpos,
        "categoria": cat,
    }


def resumen_expectativa_jugador(df, agg, jugador, k=None, min_muestra=None, umbral=None):
    """Combos (accion, tercio) más repetidos del jugador con su predicción vs la
    expectativa de su posición, etiquetados destaca/en linea/por debajo. Ordenado
    por la desviación más llamativa. Para el cierre de scouting (spec §4.2)."""
    if k is None:
        k = _EXP_CFG["k"]
    if min_muestra is None:
        min_muestra = _EXP_CFG["min_muestra_resumen"]
    if umbral is None:
        umbral = _EXP_CFG["umbral_destaca"]

    d = df[(df["jugador"] == jugador) & (df["jugador"] != EQUIPO_TAG)]
    d = d[d["intento"].astype(bool)]
    if d.empty:
        return []

    # posición del jugador = la más frecuente en sus filas
    posicion = ""
    if "posicion" in d.columns and not d["posicion"].dropna().empty:
        modo = d["posicion"].replace("", np.nan).dropna()
        posicion = modo.mode().iloc[0] if not modo.empty else ""

    combos = {}
    for _, r in d.iterrows():
        tercio = _tercio_de(r.get("zona_x"), r.get("zona", ""))
        if tercio is None:
            continue
        clave = (r.get("accion", ""), tercio)
        a, n = combos.get(clave, (0.0, 0))
        combos[clave] = (a + float(r.get("peso", 0.0) or 0.0), n + 1)

    filas = []
    for (accion, tercio), (a_prop, n_prop) in combos.items():
        if n_prop < min_muestra:
            continue
        out = predecir_acierto(agg, jugador, accion, tercio, posicion, k=k)
        diff_pts = int(round((out["pred"] - out["expectativa_pos"]) * 100))
        if diff_pts >= umbral:
            etiqueta = "destaca"
        elif diff_pts <= -umbral:
            etiqueta = "por debajo"
        else:
            etiqueta = "en linea"
        filas.append({
            # n_jugador coincide con out["n_jugador"] sólo porque `agg` se
            # construyó con el MISMO df: si algún día se pasa un df filtrado por
            # partido y un agg de la base entera, divergirán.
            "accion": accion, "tercio": tercio, "n_jugador": n_prop,
            "pct_real": (a_prop / n_prop) if n_prop else 0.0,
            "pred": out["pred"], "expectativa_pos": out["expectativa_pos"],
            "n_pos": out["n_pos"], "diff_pts": diff_pts, "etiqueta": etiqueta,
        })
    # Desviación más llamativa primero; a igualdad, el combo mejor evidenciado.
    filas.sort(key=lambda f: (abs(f["diff_pts"]), f["n_jugador"]), reverse=True)
    tope = _EXP_CFG.get("top_resumen", 12)
    return filas[:tope] if tope else filas


def metrica_dashboard(df_all, jugador, metrica_key, modo="total"):
    """Calcula una métrica del dashboard para un jugador en uno de los 4 modos:
       'total'        -> recuento bruto de acciones
       'aciertos'     -> recuento de acciones con éxito
       'total90'      -> recuento bruto normalizado a 90 min
       'aciertos90'   -> aciertos normalizados a 90 min
    Devuelve un número (int o float redondeado)."""
    spec = METRICAS_DASH.get(metrica_key)
    if not spec:
        return 0
    d = df_all[df_all["jugador"] == jugador]
    especial = spec.get("especial")

    # --- % acierto de pase: siempre porcentaje, ignora el modo ---
    if especial == "pct_pase":
        dp = d[d["accion"].isin(PASS_ACTIONS)]
        intentos = dp[dp["intento"]] if "intento" in dp.columns else dp
        if len(intentos) == 0:
            return 0.0
        return round(100 * dp["exito"].sum() / len(intentos), 1)

    # --- selección de filas de la métrica ---
    if especial == "goles":
        sub = d[d["accion"].isin(GOL_ACTIONS) & (d["resultado"] == "Gol")]
        # un gol es de por sí un "acierto"; total y aciertos coinciden
        n_total = len(sub)
        n_aciertos = len(sub)
    else:
        sub = d[d["accion"].isin(spec["acciones"])]
        n_total = len(sub)
        n_aciertos = int(sub["exito"].sum()) if "exito" in sub.columns else 0

    if modo == "total":
        return n_total
    if modo == "aciertos":
        return n_aciertos
    minutos = minutos_de_jugador(df_all, jugador)
    if not minutos or minutos <= 0:
        return 0.0
    base = n_total if modo == "total90" else n_aciertos
    return round(base * 90.0 / minutos, 1)


def minutos_de_sesion_jugador(sesion: dict, jugador: str) -> int:
    """Minutos jugados por un jugador en UNA sesión (partido).
    Usa min_in/min_out de su ficha si existen; si no, el último minuto con acción."""
    info = (sesion.get("jugadores_info") or {}).get(jugador, {})
    if info.get("min_in") is not None or info.get("min_out") is not None:
        mi = int(info.get("min_in", 0)); mo = int(info.get("min_out", 90))
        return max(0, mo - mi)
    evs = [e for e in (sesion.get("events") or []) if e.get("jugador") == jugador]
    if not evs:
        return 0
    mins = [e.get("minuto", 0) for e in evs if e.get("minuto") is not None]
    return int(max(mins)) if mins else 0


# ============================================================================
# AUDITORÍA DE DATOS (Fase 0, punto 4) — solo lectura, no modifica nada
# ============================================================================

def auditar_datos(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Recorre todas las sesiones y detecta combinaciones acción+resultado que
    el diccionario canónico NO reconoce (huérfanas), normalmente por nombres
    antiguos desfasados tras renombrados. No modifica nada.

    Devuelve:
      - huerfanas: lista de {accion, resultado, veces} sin clasificar
      - acciones_desconocidas: acciones que no están en el diccionario
      - resumen: totales
    """
    from collections import defaultdict
    combos = defaultdict(int)          # (accion, resultado) -> veces
    acciones_vistas = defaultdict(int) # accion -> veces
    total_eventos = 0

    for s in sessions:
        for ev in (s.get("events") or []):
            accion = ev.get("accion", "")
            resultado = ev.get("resultado", "")
            combos[(accion, resultado)] += 1
            acciones_vistas[accion] += 1
            total_eventos += 1

    huerfanas = []
    acciones_desconocidas = set()
    for (accion, resultado), veces in combos.items():
        en_dic = accion in _DIC_ACCIONES
        clase = _clase_por_accion(accion, resultado)
        if not en_dic:
            acciones_desconocidas.add(accion)
        # Huérfana = cualquier combinación que no se clasifica, ya sea porque la
        # acción no está en el diccionario o porque ese resultado no encaja en
        # ninguna categoría de esa acción. Para el scout, ambos son "dato que no
        # cuenta bien" y hay que revisarlos igual.
        if clase is None:
            motivo = "acción no está en el diccionario" if not en_dic else "resultado no reconocido"
            huerfanas.append({"accion": accion, "resultado": resultado,
                              "veces": veces, "motivo": motivo})

    huerfanas.sort(key=lambda x: x["veces"], reverse=True)
    return {
        "huerfanas": huerfanas,
        "acciones_desconocidas": sorted(acciones_desconocidas),
        "resumen": {
            "total_eventos": total_eventos,
            "combos_distintos": len(combos),
            "eventos_huerfanos": sum(h["veces"] for h in huerfanas),
            "acciones_sin_diccionario": len(acciones_desconocidas),
        },
    }


# ============================================================================
# CONTEXTO: comparación de nivel propio vs rival (Fase 1, punto 3)
# ============================================================================
_ORDEN_NIVEL = {"Élite": 4, "Alto": 3, "Medio": 2, "Bajo": 1}


def comparacion_rival(sesion: dict) -> str:
    """Compara el nivel del rival con el del equipo propio en una sesión.
    Devuelve 'superior', 'similar' o 'inferior' (desde la óptica del rival),
    o 'desconocido' si faltan datos.
    Ej: nivel_propio=Alto, nivel_rival=Élite -> el rival es 'superior'."""
    meta = sesion.get("meta") or {}
    # el nivel puede estar en meta o en match_info según de dónde venga
    np_ = meta.get("nivel_propio") or sesion.get("nivel_propio") or "Medio"
    nr = meta.get("nivel_rival") or sesion.get("nivel_rival") or "Medio"
    vp, vr = _ORDEN_NIVEL.get(np_), _ORDEN_NIVEL.get(nr)
    if vp is None or vr is None:
        return "desconocido"
    if vr > vp:
        return "superior"
    if vr < vp:
        return "inferior"
    return "similar"


def filtrar_sesiones_por_contexto(sessions: list, contexto: str) -> list:
    """Filtra las sesiones según la comparación con el rival.
    contexto: 'todos', 'superior', 'similar', 'inferior'."""
    if contexto == "todos" or not contexto:
        return sessions
    return [s for s in sessions if comparacion_rival(s) == contexto]


# ============================================================================
# INFLUENCIA POR MINUTO (Fase 5) — volumen y eficiencia por franjas de 15'
# ============================================================================
FRANJAS_15 = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90), (90, 200)]
FRANJA_LABELS = ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90", "90+"]

# Acciones "de peligro" para marcar con símbolos en el gráfico.
PELIGRO_GOL = "gol"
PELIGRO_TIRO = "tiro"
PELIGRO_CLAVE = "clave"


def influencia_por_minuto(df, jugador):
    """Para el gráfico de influencia. Devuelve, por franja de 15 minutos:
      - volumen: nº de acciones del jugador en esa franja
      - eficiencia: % de acierto (sobre acciones evaluables) en esa franja
      - peligro: lista de eventos de peligro (gol/tiro/pase clave) en esa franja
    """
    d = df[df["jugador"] == jugador].copy()
    if d.empty:
        return {"labels": FRANJA_LABELS, "volumen": [0]*7, "eficiencia": [None]*7, "peligro": [[] for _ in range(7)]}
    volumen, eficiencia, peligro = [], [], []
    for (lo, hi) in FRANJAS_15:
        fr = d[(d["minuto"] >= lo) & (d["minuto"] < hi)]
        volumen.append(int(len(fr)))
        inten = fr[fr["intento"]] if "intento" in fr.columns else fr
        if len(inten) > 0:
            eficiencia.append(round(100 * fr["exito"].sum() / len(inten)))
        else:
            eficiencia.append(None)
        # eventos de peligro en la franja
        peli = []
        for _, ev in fr.iterrows():
            acc, res = ev.get("accion", ""), ev.get("resultado", "")
            if res == "Gol":
                peli.append(PELIGRO_GOL)
            elif acc in SHOT_ACTIONS and res == "A puerta":
                peli.append(PELIGRO_TIRO)
            elif acc == "Pase clave":
                peli.append(PELIGRO_CLAVE)
        peligro.append(peli)
    return {"labels": FRANJA_LABELS, "volumen": volumen,
            "eficiencia": eficiencia, "peligro": peligro}
