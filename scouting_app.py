"""
App de Scouting en Vivo — Scouting Mundial
==========================================
Tagging de acciones de jugadores mientras ves un partido + módulos de análisis.

Secciones (navegación en la barra lateral):
    · Sesiones      -> lista, crear/abrir/borrar y panel de tagging en vivo
    · Gráficos      -> radar comparativo, campo por tercios y mapa de calor
    · Equipos       -> métricas agregadas de equipo y calculadora de posesión
    · Predicciones  -> predicción de acierto por jugador (suavizado jerárquico)

Las sesiones se guardan en Supabase. Cómo ejecutar:
    streamlit run scouting_app.py
Requisitos:
    pip install -r requirements.txt
    Rellenar .streamlit/secrets.toml con SUPABASE_URL y SUPABASE_KEY.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from streamlit.components.v1 import html as st_html
import io
import os

import storage
import analytics
import secuencias
# import report  # informe retirado de esta app; report.py se conserva para la futura app de equipos

st.set_page_config(page_title="Scouting Mundial", page_icon="◆", layout="wide")


def load_css(filename="styles.css"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css()

# ----------------------------------------------------------------------------
# PANEL DE ACCIONES
# ----------------------------------------------------------------------------
RES_OK_FALLO = [("OK", "Correcto", "ok"), ("Fallo", "Fallo", "bad")]
# Control fácil fallado: un solo botón rojo (la F). Solo se registra el error,
# porque un control fácil bien hecho no aporta info de scouting; el fallo sí.
RES_CONTROL_FACIL = [("F", "Control fácil fallado", "bad")]
RES_ENCONTRADO = [("Encontrado", "Encontrado", "ok"), ("No encontrado", "No encontrado", "bad")]
# Movimiento sin balón: "Encontrado" es éxito; "No encontrado" NO penaliza
# (el desmarque fue bueno, pero el compañero no le dio el pase). Es neutral.
RES_MOVIMIENTO = [("Encontrado", "Encontrado", "ok"),
                  ("N", "Movimiento sin pase", "neutral")]
# Remate: ahora separa "fuera" de "bloqueado" (B) para no perder info de selección de tiro.
RES_REMATE = [("Puerta", "A puerta", "ok"), ("Gol", "Gol", "gol"),
              ("Fuera", "Fuera", "bad"), ("B", "Bloqueado", "falta")]
# Duelo defensivo 1v1: éxito (recuperó), parcial naranja "R" (aguantó/retrasó), fallo (le regatearon).
RES_DUELO_DEF = [("OK", "Correcto", "ok"), ("R", "Retrasó/aguantó", "falta"), ("Fallo", "Regateado", "bad")]
# Falta directa a puerta: puerta / gol / fuera / barrera (blocked).
RES_FALTA_DIRECTA = [("Puerta", "A puerta", "ok"), ("Gol", "Gol", "gol"),
                     ("Fuera", "Fuera", "bad"), ("Barrera", "Barrera", "falta")]
RES_SIMPLE = [("Registrar", "—", "neutral")]
# Sprints: solo se registran (ni bien ni mal). Kind 'sprint' = violeta.
RES_SPRINT = [("Sprint", "Sprint", "sprint")]
RES_FALTA = [("Falta", "Falta", "falta")]
RES_AMARILLA = [("Amarilla", "Tarjeta amarilla", "amarilla")]
RES_ROJA = [("Roja", "Tarjeta roja", "roja")]
RES_PENALTI = [("Penalti", "Penalti provocado", "penalti")]
RES_PENALTI_CONTRA = [("Penalti", "Penalti cometido", "penalti-contra")]

PANEL = {
    "Construcción y pase": [
        ("Pase atrás", RES_OK_FALLO), ("Pase lateral", RES_OK_FALLO),
        ("Pase progresivo", RES_OK_FALLO), ("Pase entre líneas", RES_OK_FALLO),
        ("Pase al espacio", RES_OK_FALLO), ("Cambio de orientación", RES_OK_FALLO),
        ("Pase de primera", RES_OK_FALLO), ("Pase bajo presión", RES_OK_FALLO),
        ("Pase en largo", RES_OK_FALLO),
        ("Asistencia", RES_SIMPLE), ("Pase clave", RES_OK_FALLO),
        ("Centro lateral", RES_OK_FALLO),
    ],
    "Regate y conducción": [
        ("Regate 1v1", RES_OK_FALLO), ("Conducción progresiva", RES_OK_FALLO),
        ("Recorte / cambio ritmo", RES_OK_FALLO),
        ("Control difícil", RES_OK_FALLO),
        ("Control fácil fallado", RES_CONTROL_FACIL),
        ("Protección de balón", RES_OK_FALLO),
        ("Recibe entre líneas", RES_OK_FALLO),
        ("Duelo aéreo of.", RES_OK_FALLO),
        ("Falta recibida", RES_SIMPLE), ("Penalti provocado", RES_PENALTI),
        ("Error grave / pérdida", RES_SIMPLE),
    ],
    "Movimiento sin balón": [
        ("Desmarque de ruptura", RES_MOVIMIENTO), ("Desmarque de apoyo", RES_MOVIMIENTO),
        ("Ataque al palo", RES_MOVIMIENTO), ("Desmarque de arrastre", RES_MOVIMIENTO),
        ("Amplía el campo", RES_MOVIMIENTO), ("Ofrece línea de pase", RES_MOVIMIENTO),
        ("Entrada en área rival", RES_MOVIMIENTO),
    ],
    "Finalización": [
        ("Remate", RES_REMATE), ("Remate de cabeza", RES_REMATE),
        ("Remate desde fuera", RES_REMATE), ("Llegada 2ª línea", RES_REMATE),
        ("Ocasión clara fallada", RES_SIMPLE),
        ("Generación de ocasión", RES_OK_FALLO),
    ],
    "Defensa": [
        ("Entrada / tackle", RES_OK_FALLO), ("Intercepción", RES_OK_FALLO),
        ("Anticipación", RES_OK_FALLO),
        ("Recuperación", RES_OK_FALLO), ("Despeje", RES_OK_FALLO),
        ("Duelo aéreo def.", RES_OK_FALLO), ("Duelo 1v1 def.", RES_DUELO_DEF),
        ("Marcaje en centro", RES_OK_FALLO),
        ("Presión fuerza error", RES_OK_FALLO), ("Cobertura", RES_OK_FALLO),
        ("Bloqueo tiro/centro", RES_OK_FALLO),
        ("Repliegue", RES_OK_FALLO), ("Falta táctica", RES_SIMPLE),
        ("Falta", RES_FALTA), ("Tarjeta amarilla", RES_AMARILLA),
        ("Tarjeta roja", RES_ROJA),
        ("Penalti cometido", RES_PENALTI_CONTRA),
    ],
    "ABP": [
        ("Lanzamiento córner", RES_OK_FALLO),
        ("Lanzamiento falta lateral", RES_OK_FALLO),
        ("Falta directa a puerta", RES_FALTA_DIRECTA),
        ("Remate a balón parado", RES_REMATE),
        ("Despeje en ABP def.", RES_OK_FALLO),
        ("Duelo en ABP def.", RES_OK_FALLO),
    ],
    "Sprints": [
        ("Sprint def.", RES_SPRINT),
        ("Sprint of. sin balón", RES_SPRINT),
        ("Sprint of. con balón", RES_SPRINT),
    ],
}

# ----------------------------------------------------------------------------
# PANEL DE ACCIONES DE EQUIPO (tagging colectivo, más general que el individual)
# Resultados mixtos: éxito/fallo donde aplica, registro simple donde no.
# ----------------------------------------------------------------------------
# NOTA: el modo equipo se retiró de la UI (app dedicada solo a scouting de
# jugador). Estas constantes se conservan inertes para no tocar el resto del
# código; el código de equipo extraído está guardado aparte para la futura
# app de performance analyst de equipos.
PANEL_EQUIPO = {
    "Pases y posesión": [
        ("Salida de balón", RES_OK_FALLO),
        ("Circulación / posesión", RES_OK_FALLO),
        ("Progresión con balón", RES_OK_FALLO),
        ("Cambio de orientación", RES_OK_FALLO),
        ("Llegada a último tercio", RES_OK_FALLO),
        ("Pérdida de balón", RES_SIMPLE),
    ],
    "Ataque": [
        ("Tiro", RES_REMATE),
        ("Ocasión de gol", RES_SIMPLE),
        ("Centro al área", RES_OK_FALLO),
        ("Córner a favor", RES_SIMPLE),
        ("Llegada por banda", RES_OK_FALLO),
    ],
    "Defensa": [
        ("Recuperación", RES_OK_FALLO),
        ("Presión alta", RES_OK_FALLO),
        ("Robo / intercepción", RES_OK_FALLO),
        ("Despeje", RES_SIMPLE),
        ("Duelo defensivo", RES_OK_FALLO),
        ("Falta cometida", RES_FALTA),
        ("Tarjeta amarilla", RES_AMARILLA),
        ("Tarjeta roja", RES_ROJA),
    ],
    "Transiciones y balón parado": [
        ("Transición ofensiva", RES_OK_FALLO),
        ("Transición defensiva", RES_OK_FALLO),
        ("Contraataque", RES_SIMPLE),
        ("Saque de banda", RES_SIMPLE),
        ("Falta a favor", RES_SIMPLE),
        ("Fuera de juego provocado", RES_SIMPLE),
        ("Córner en contra", RES_SIMPLE),
    ],
}

# Tipos de sesión: las de jugadores y las de equipo son conjuntos separados.
TIPO_JUGADORES = "jugadores"
TIPO_EQUIPO = "equipo"

# Lista cerrada de posiciones (para poder filtrar de forma consistente).
# Código -> etiqueta legible.
POSICIONES = {
    "POR": "Portero",
    "DFC": "Defensa central",
    "LD": "Lateral derecho",
    "LI": "Lateral izquierdo",
    "MCD": "Mediocentro defensivo",
    "MC": "Mediocentro",
    "MED": "Mediocentro ofensivo",
    "EXT": "Extremo",
    "MP": "Mediapunta",
    "DC": "Delantero centro",
}
POSICION_CODIGOS = list(POSICIONES.keys())

# ----------------------------------------------------------------------------
# PIZARRA TÁCTICA
# Fases del juego y formaciones base. Las coordenadas son porcentajes 0-100
# sobre un campo VERTICAL (la propia portería abajo, ataque hacia arriba):
#   x = 0 (izquierda) .. 100 (derecha);  y = 0 (línea de gol propia) .. 100 (rival)
# ----------------------------------------------------------------------------
FASES = ["Presión", "Bloque medio", "Bloque bajo", "Construcción", "Ataque"]

FASE_DESC = {
    "Presión": "Presión alta: el equipo aprieta arriba para recuperar cerca de la portería rival.",
    "Bloque medio": "Bloque medio: líneas en el centro del campo, equilibrio entre presionar y proteger.",
    "Bloque bajo": "Bloque bajo: equipo replegado cerca de su área, defendiendo el espacio propio.",
    "Construcción": "Construcción: salida de balón desde atrás para progresar con posesión.",
    "Ataque": "Ataque: estructura ofensiva con el equipo volcado en campo rival.",
}

# Plantillas de formación: 11 fichas con dorsal, código de posición y (x,y) base
# en un bloque medio neutro. Luego cada fase desplaza el bloque arriba/abajo.
FORMACIONES = {
    "4-3-3": [
        (1, "POR", 50, 6),
        (2, "LD", 82, 24), (4, "DFC", 62, 18), (5, "DFC", 38, 18), (3, "LI", 18, 24),
        (6, "MCD", 50, 40), (8, "MC", 68, 50), (10, "MED", 32, 50),
        (7, "EXT", 84, 70), (9, "DC", 50, 78), (11, "EXT", 16, 70),
    ],
    "4-4-2": [
        (1, "POR", 50, 6),
        (2, "LD", 82, 24), (4, "DFC", 62, 18), (5, "DFC", 38, 18), (3, "LI", 18, 24),
        (7, "EXT", 84, 48), (6, "MC", 60, 44), (8, "MC", 40, 44), (11, "EXT", 16, 48),
        (9, "DC", 60, 74), (10, "DC", 40, 74),
    ],
    "4-2-3-1": [
        (1, "POR", 50, 6),
        (2, "LD", 82, 24), (4, "DFC", 62, 18), (5, "DFC", 38, 18), (3, "LI", 18, 24),
        (6, "MCD", 60, 38), (8, "MCD", 40, 38),
        (7, "EXT", 84, 58), (10, "MP", 50, 60), (11, "EXT", 16, 58),
        (9, "DC", 50, 80),
    ],
    "3-5-2": [
        (1, "POR", 50, 6),
        (4, "DFC", 70, 18), (5, "DFC", 50, 16), (6, "DFC", 30, 18),
        (2, "LD", 88, 44), (8, "MC", 62, 46), (10, "MED", 50, 52), (3, "MC", 38, 46), (11, "LI", 12, 44),
        (9, "DC", 60, 76), (7, "DC", 40, 76),
    ],
    "5-3-2": [
        (1, "POR", 50, 6),
        (2, "LD", 88, 30), (4, "DFC", 68, 18), (5, "DFC", 50, 15), (6, "DFC", 32, 18), (3, "LI", 12, 30),
        (8, "MC", 66, 48), (10, "MC", 50, 52), (11, "MC", 34, 48),
        (9, "DC", 60, 74), (7, "DC", 40, 74),
    ],
}

# Desplazamiento vertical (en puntos %) que aplica cada fase al bloque base,
# para reflejar dónde se sitúa el equipo en el campo.
FASE_OFFSET = {
    "Presión": +14, "Bloque medio": 0, "Bloque bajo": -16,
    "Construcción": -6, "Ataque": +12,
}

# Paneles según el tipo de registro activo.
PANELES = {TIPO_JUGADORES: PANEL, TIPO_EQUIPO: PANEL_EQUIPO}

# Distribución de bloques en dos columnas, por tipo.
DISTRIBUCION = {
    TIPO_JUGADORES: {
        "izq": ["Construcción y pase", "Movimiento sin balón"],
        "der": ["Regate y conducción", "Finalización", "Defensa", "ABP", "Sprints"],
    },
    TIPO_EQUIPO: {
        "izq": ["Pases y posesión", "Ataque"],
        "der": ["Defensa", "Transiciones y balón parado"],
    },
}

# ----------------------------------------------------------------------------
# REJILLA DEL CAMPO 3x3
# X (sentido de ataque): 0=1er tercio (def propia), 1=2º (medio), 2=3er (ataque)
# Y (bandas): 0=izquierda, 1=centro, 2=derecha
# ----------------------------------------------------------------------------
ZONA_COLS = ["1er tercio", "2º tercio", "3er tercio"]
ZONA_ROWS = ["Banda izq.", "Centro", "Banda der."]


def zona_label(x, y):
    return f"{ZONA_COLS[x]} · {ZONA_ROWS[y]}"


# ----------------------------------------------------------------------------
# ESTADO
# ----------------------------------------------------------------------------
def init_state():
    defaults = {
        "section": "Registro jugadores",
        "view": "menu",
        "reg_tipo": TIPO_JUGADORES,     # tipo de sesión que se está registrando
        "current_session_id": None,
        "events": [], "players": [], "active_player": None,
        "posiciones": {},   # {nombre_jugador: codigo_posicion}  (compatibilidad)
        "jugadores_info": {},  # {nombre: {pos, equipo, edad, foto(base64)}}
        "clock_start": None, "clock_offset": 0.0,
        "match_info": {
            "nombre": "", "equipo_local": "", "equipo_visitante": "",
            "goles_local": 0, "goles_visitante": 0, "posesion_local": 50,
            "competicion": "Mundial", "fecha": datetime.now().strftime("%Y-%m-%d"),
            "minuto_descanso": 45,
            "nivel_propio": "Medio", "nivel_rival": "Medio",
        },
        "final_notes": "",
        "zona_x": 1, "zona_y": 1,
        "pizarras": {},   # {formacion__fase: [fichas]} de la sesión de equipo abierta
        "tag_compact": False,   # vista de tagging a pantalla compacta
        "minuto_descanso": 45,  # minuto que separa 1ª de 2ª parte (configurable)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ----------------------------------------------------------------------------
# CRONÓMETRO
# ----------------------------------------------------------------------------
def current_minute():
    if st.session_state.clock_start is None:
        return st.session_state.clock_offset
    elapsed = (datetime.now() - st.session_state.clock_start).total_seconds() / 60.0
    return st.session_state.clock_offset + elapsed


def fmt_minute(m):
    total_seconds = int(m * 60)
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def clock_start():
    if st.session_state.clock_start is None:
        st.session_state.clock_start = datetime.now()


def clock_pause():
    if st.session_state.clock_start is not None:
        st.session_state.clock_offset = current_minute()
        st.session_state.clock_start = None


def clock_reset():
    st.session_state.clock_start = None
    st.session_state.clock_offset = 0.0


def clock_set_minute(minuto):
    """Fija el cronómetro en un minuto concreto sin reiniciar. Mantiene el estado
    en marcha o pausado: si corre, recoloca el inicio para que 'ahora' sea ese
    minuto; si está pausado, ajusta el offset."""
    minuto = max(0.0, float(minuto))
    if st.session_state.clock_start is not None:
        # corriendo: el inicio se recoloca para que current_minute() == minuto ahora
        st.session_state.clock_start = datetime.now()
        st.session_state.clock_offset = minuto
    else:
        # pausado: simplemente fijamos el offset
        st.session_state.clock_offset = minuto


def _reloj_texto():
    """Texto del cronómetro (minuto actual y estado)."""
    running = st.session_state.get("clock_start") is not None
    return fmt_minute(current_minute()), ("En marcha" if running else "Detenido")


# ----------------------------------------------------------------------------
# GUARDADO / CARGA DE ESTADO
# ----------------------------------------------------------------------------
def collect_session_data():
    mi = st.session_state.match_info
    return {
        "nombre": mi.get("nombre") or f"{mi['equipo_local'] or 'Local'} vs {mi['equipo_visitante'] or 'Visitante'}",
        "competicion": mi["competicion"], "fecha": mi["fecha"],
        "equipo_local": mi["equipo_local"], "equipo_visitante": mi["equipo_visitante"],
        "goles_local": mi["goles_local"], "goles_visitante": mi["goles_visitante"],
        "posesion_local": mi["posesion_local"],
        "jugadores": st.session_state.players,
        "posiciones": st.session_state.posiciones,
        "jugadores_info": st.session_state.jugadores_info,
        "events": st.session_state.events,
        "notas": st.session_state.final_notes,
        "tipo": st.session_state.reg_tipo,
        "pizarras": st.session_state.pizarras,
        "meta": {
            "minuto_descanso": mi.get("minuto_descanso", 45),
            "nivel_propio": mi.get("nivel_propio", "Medio"),
            "nivel_rival": mi.get("nivel_rival", "Medio"),
            "contexto_partido": mi.get("contexto_partido", ""),
        },
    }


def autosave():
    sid = st.session_state.current_session_id
    if sid:
        storage.save_session(sid, collect_session_data())


def load_into_state(session):
    st.session_state.current_session_id = session["id"]
    st.session_state.events = session.get("events") or []
    st.session_state.players = session.get("jugadores") or []
    st.session_state.posiciones = session.get("posiciones") or {}
    st.session_state.jugadores_info = session.get("jugadores_info") or {}
    st.session_state.active_player = st.session_state.players[0] if st.session_state.players else None
    meta = session.get("meta") or {}
    st.session_state.match_info = {
        "nombre": session.get("nombre", ""),
        "equipo_local": session.get("equipo_local", "") or "",
        "equipo_visitante": session.get("equipo_visitante", "") or "",
        "goles_local": session.get("goles_local", 0) or 0,
        "goles_visitante": session.get("goles_visitante", 0) or 0,
        "posesion_local": session.get("posesion_local", 50) or 50,
        "competicion": session.get("competicion", "Mundial") or "Mundial",
        "fecha": session.get("fecha", datetime.now().strftime("%Y-%m-%d")) or "",
        "minuto_descanso": meta.get("minuto_descanso", 45),
        "nivel_propio": meta.get("nivel_propio", "Medio"),
        "nivel_rival": meta.get("nivel_rival", "Medio"),
        "contexto_partido": meta.get("contexto_partido", ""),
    }
    st.session_state.final_notes = session.get("notas", "") or ""
    st.session_state.pizarras = session.get("pizarras") or {}
    st.session_state.reg_tipo = session.get("tipo") or TIPO_JUGADORES
    st.session_state.clock_start = None
    st.session_state.clock_offset = 0.0
    st.session_state.view = "edit"


# ----------------------------------------------------------------------------
# REGISTRO DE ACCIONES
# ----------------------------------------------------------------------------
def add_event(action, result_code):
    es_equipo = (st.session_state.reg_tipo == TIPO_EQUIPO)
    if es_equipo:
        # En sesiones de equipo el "actor" es el propio equipo.
        actor = st.session_state.match_info.get("equipo_local") or "Equipo"
    else:
        if st.session_state.active_player is None:
            st.toast("Selecciona un jugador primero")
            return
        actor = st.session_state.active_player
    minute = current_minute()
    zx, zy = st.session_state.zona_x, st.session_state.zona_y
    posicion = "" if es_equipo else st.session_state.posiciones.get(actor, "")
    st.session_state.events.append({
        "jugador": actor,
        "posicion": posicion,
        "minuto": round(minute, 2),
        "minuto_fmt": fmt_minute(minute),
        "accion": action,
        "resultado": result_code,
        "zona": zona_label(zx, zy),
        "zona_x": zx, "zona_y": zy,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })
    label = action + (f" · {result_code}" if result_code != "—" else "")
    st.toast(f"{actor} — {label}")
    autosave()


def undo_last():
    if st.session_state.events:
        removed = st.session_state.events.pop()
        st.toast(f"Deshecho: {removed['accion']}")
        autosave()
    else:
        st.toast("No hay acciones que deshacer")


# ============================================================================
# HELPERS DE DIBUJO (SVG) — campo, heatmap, radar, timeline
# Todo SVG puro inyectado con st_html, integrado en el tema neón oscuro.
# ============================================================================
# Campo sobre fondo oscuro (verde muy apagado para que los datos destaquen).
GRASS_A = "#16221b"
GRASS_B = "#101913"
LINE = "#3a4a40"          # líneas de campo tenues
INK = "#ffffff"           # texto principal sobre oscuro
# Acentos neón (coinciden con el CSS)
NEON_OK = "#15ff66"       # verde fosforito
NEON_BAD = "#ff2d55"      # rojo neón
NEON_GOLD = "#ffcc00"     # amarillo/naranja neón
NEON_ORANGE = "#ff7a1a"   # naranja neón (banda 5-7 de la nota)
NEON_SKY = "#38bdf8"      # azul cielo
TXT_LO_SVG = "#8b93a1"    # labels tenues
GRID_SVG = "#2a2e38"      # rejillas
PANEL_SVG = "#15171c"     # fondo de paneles SVG


def _color_nota(v):
    """Color de la nota por bandas (mismo criterio en badge y barras):
    [1,5)→rojo, [5,7)→naranja, [7,9)→amarillo, >=9→verde."""
    if v is None:
        return TXT_LO_SVG
    if v >= 9:
        return NEON_OK
    if v >= 7:
        return NEON_GOLD
    if v >= 5:
        return NEON_ORANGE
    return NEON_BAD



def _pitch_base_svg(w=600, h=390):
    """Devuelve los elementos SVG del césped + líneas de un campo horizontal.
    El ataque va de izquierda (tercio propio) a derecha (tercio rival)."""
    stripe = ""
    n = 6
    sw = w / n
    for i in range(n):
        col = GRASS_A if i % 2 == 0 else GRASS_B
        stripe += f'<rect x="{i*sw:.1f}" y="0" width="{sw:.1f}" height="{h}" fill="{col}"/>'
    midx = w / 2
    cy = h / 2
    r = h * 0.16
    lines = f"""
      <rect x="2" y="2" width="{w-4}" height="{h-4}" fill="none" stroke="{LINE}" stroke-width="2.5" rx="4"/>
      <line x1="{midx}" y1="2" x2="{midx}" y2="{h-2}" stroke="{LINE}" stroke-width="2.5"/>
      <circle cx="{midx}" cy="{cy}" r="{r}" fill="none" stroke="{LINE}" stroke-width="2.5"/>
      <circle cx="{midx}" cy="{cy}" r="3" fill="{LINE}"/>
      <rect x="2" y="{cy-h*0.28}" width="{w*0.14}" height="{h*0.56}" fill="none" stroke="{LINE}" stroke-width="2"/>
      <rect x="{w-2-w*0.14}" y="{cy-h*0.28}" width="{w*0.14}" height="{h*0.56}" fill="none" stroke="{LINE}" stroke-width="2"/>
      <rect x="2" y="{cy-h*0.14}" width="{w*0.055}" height="{h*0.28}" fill="none" stroke="{LINE}" stroke-width="2"/>
      <rect x="{w-2-w*0.055}" y="{cy-h*0.14}" width="{w*0.055}" height="{h*0.28}" fill="none" stroke="{LINE}" stroke-width="2"/>
    """
    return stripe + lines


def pitch_thirds_svg(grid, w=600, h=390, title=""):
    """Campo con la rejilla 3x3 y el conteo de acciones en cada celda.
    grid: matriz 3x3 numpy (filas=bandas Y, cols=tercios X)."""
    base = _pitch_base_svg(w, h)
    cw, ch = w / 3, h / 3
    total = int(grid.sum()) or 1
    cells = ""
    for yi in range(3):
        for xi in range(3):
            c = int(grid[yi, xi])
            cx = xi * cw + cw / 2
            ccy = yi * ch + ch / 2
            # opacidad proporcional al peso de la celda
            op = 0.0 if c == 0 else 0.18 + 0.55 * (c / total)
            cells += f'<rect x="{xi*cw:.1f}" y="{yi*ch:.1f}" width="{cw:.1f}" height="{ch:.1f}" fill="{NEON_GOLD}" opacity="{op:.2f}"/>'
            cells += (f'<text x="{cx:.1f}" y="{ccy:.1f}" text-anchor="middle" '
                      f'dominant-baseline="central" font-size="22" font-weight="800" '
                      f'fill="#ffffff" stroke="#000" stroke-width="0.6">{c}</text>')
    # rejilla divisoria
    grid_lines = ""
    for i in (1, 2):
        grid_lines += f'<line x1="{i*cw:.1f}" y1="0" x2="{i*cw:.1f}" y2="{h}" stroke="{LINE}" stroke-width="1" opacity="0.4" stroke-dasharray="5 5"/>'
        grid_lines += f'<line x1="0" y1="{i*ch:.1f}" x2="{w}" y2="{i*ch:.1f}" stroke="{LINE}" stroke-width="1" opacity="0.4" stroke-dasharray="5 5"/>'
    arrow = (f'<defs><marker id="ar" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto">'
             f'<path d="M0,0 L6,3 L0,6 Z" fill="#fff"/></marker></defs>'
             f'<line x1="{w*0.3}" y1="{h+18}" x2="{w*0.7}" y2="{h+18}" stroke="#fff" stroke-width="2" marker-end="url(#ar)"/>'
             f'<text x="{w*0.5}" y="{h+14}" text-anchor="middle" font-size="11" fill="{TXT_LO_SVG}">Sentido del ataque</text>')
    ttl = f'<text x="{w/2}" y="-8" text-anchor="middle" font-size="13" font-weight="800" fill="{INK}">{title}</text>' if title else ""
    return f'''<svg viewBox="-10 -28 {w+20} {h+50}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%">
      {ttl}<g>{base}{cells}{grid_lines}{arrow}</g></svg>'''


def heatmap_svg(grid, w=600, h=390):
    """Mapa de calor suave sobre el campo. Escala de color CONTINUA (verde->
    amarillo->rojo) para que las diferencias de volumen se noten de verdad."""
    base = _pitch_base_svg(w, h)
    cw, ch = w / 3, h / 3
    mx = grid.max() or 1
    mn = grid[grid > 0].min() if (grid > 0).any() else 0

    def color_continuo(t):
        """t en [0,1] -> color de verde (0) a amarillo (0.5) a rojo (1)."""
        t = max(0.0, min(1.0, t))
        if t < 0.5:
            # verde -> amarillo
            f = t / 0.5
            r = int(0x15 + (0xff - 0x15) * f)
            g = int(0xff - (0xff - 0xd6) * f)
            b = int(0x66 - (0x66 - 0x00) * f)
        else:
            # amarillo -> rojo
            f = (t - 0.5) / 0.5
            r = 0xff
            g = int(0xd6 - (0xd6 - 0x2d) * f)
            b = int(0x00 + 0x55 * f)
        return f"#{r:02x}{g:02x}{b:02x}"

    blobs = ""
    for yi in range(3):
        for xi in range(3):
            c = int(grid[yi, xi])
            if c == 0:
                continue
            cx = xi * cw + cw / 2
            ccy = yi * ch + ch / 2
            # Normalización con contraste: reparte entre el mínimo y el máximo
            # reales (no 0..max), así una celda con 2 y otra con 39 se distinguen.
            if mx > mn:
                intensity = (c - mn) / (mx - mn)
            else:
                intensity = 1.0
            # realce: raíz para que los valores bajos no queden todos aplastados
            intensity_vis = intensity ** 0.6
            rad = (cw if cw < ch else ch) * (0.5 + 0.5 * intensity_vis)
            col = color_continuo(intensity_vis)
            blobs += (f'<circle cx="{cx:.1f}" cy="{ccy:.1f}" r="{rad:.1f}" fill="{col}" '
                      f'opacity="{0.30 + 0.55*intensity_vis:.2f}" />')
    flt = ('<defs><filter id="blur"><feGaussianBlur stdDeviation="14"/></filter></defs>')
    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%">
      <g>{base}</g><g filter="url(#blur)">{flt}{blobs}</g></svg>'''


def radar_svg(axes_labels, series, w=460, h=460):
    """Spider/radar chart. series = lista de dicts {name, values(0-100), color}."""
    cx, cy = w / 2, h / 2
    R = min(w, h) * 0.36
    n = len(axes_labels)
    import math

    def point(i, val):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        rr = R * (val / 100.0)
        return cx + rr * math.cos(ang), cy + rr * math.sin(ang)

    rings = ""
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = []
        for i in range(n):
            ang = -math.pi / 2 + 2 * math.pi * i / n
            pts.append(f"{cx + R*frac*math.cos(ang):.1f},{cy + R*frac*math.sin(ang):.1f}")
        rings += f'<polygon points="{" ".join(pts)}" fill="none" stroke="{GRID_SVG}" stroke-width="1"/>'

    spokes, labels = "", ""
    for i, lab in enumerate(axes_labels):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        ex, ey = cx + R * math.cos(ang), cy + R * math.sin(ang)
        spokes += f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{GRID_SVG}" stroke-width="1"/>'
        lx, ly = cx + (R + 26) * math.cos(ang), cy + (R + 26) * math.sin(ang)
        anchor = "middle"
        if math.cos(ang) > 0.3:
            anchor = "start"
        elif math.cos(ang) < -0.3:
            anchor = "end"
        labels += (f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                   f'dominant-baseline="central" font-size="13" font-weight="700" fill="{INK}">{lab}</text>')

    polys = ""
    for s in series:
        pts = [point(i, v) for i, v in enumerate(s["values"])]
        pstr = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        polys += (f'<polygon points="{pstr}" fill="{s["color"]}" fill-opacity="0.28" '
                  f'stroke="{s["color"]}" stroke-width="3" filter="url(#glow)"/>')
        for x, y in pts:
            polys += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{s["color"]}" '
                      f'stroke="#0a0a0a" stroke-width="1.5" filter="url(#glow)"/>')

    # viewBox con margen para que las etiquetas laterales no se corten.
    m = 64
    defs = ('<defs><filter id="glow" x="-40%" y="-40%" width="180%" height="180%">'
            '<feGaussianBlur stdDeviation="3.2" result="b"/>'
            '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
            '</filter></defs>')
    bg = (f'<rect x="{-m}" y="{-m}" width="{w + 2*m}" height="{h + 2*m}" '
          f'fill="{PANEL_SVG}" rx="16"/>')
    return f'''<svg viewBox="{-m} {-m} {w + 2*m} {h + 2*m}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%">
      {defs}{bg}<g>{rings}{spokes}{polys}{labels}</g></svg>'''


def timeline_svg(events, w=1000):
    """Timeline tipo Sportscode: una fila por jugador, marcas en el eje temporal.
    Color de la marca según resultado (verde=éxito, rojo=fallo, dorado=gol)."""
    if not events:
        return "<p style='color:#6c7d72'>Sin acciones todavía.</p>"
    df = pd.DataFrame(events)
    players = list(dict.fromkeys(df["jugador"].tolist()))  # orden de aparición
    row_h = 30
    pad_l = 150
    pad_t = 40
    h = pad_t + row_h * len(players) + 24
    max_min = max(df["minuto"].max(), 1.0)
    span = max(max_min, 1.0)
    plot_w = w - pad_l - 30

    def xpos(m):
        return pad_l + plot_w * (m / span)

    # ejes verticales (cada ~ porción de tiempo)
    grid = ""
    ticks = 5
    for i in range(ticks + 1):
        m = span * i / ticks
        x = xpos(m)
        grid += f'<line x1="{x:.1f}" y1="{pad_t-6}" x2="{x:.1f}" y2="{h-18}" stroke="{GRID_SVG}" stroke-width="1"/>'
        grid += f'<text x="{x:.1f}" y="{pad_t-12}" text-anchor="middle" font-size="11" fill="{TXT_LO_SVG}">{fmt_minute(m)}</text>'

    rows = ""
    color_map = {"Correcto": NEON_OK, "Encontrado": NEON_OK, "A puerta": NEON_OK,
                 "Gol": NEON_GOLD, "Fallo": NEON_BAD, "No encontrado": NEON_BAD,
                 "Fuera/Interceptado": NEON_BAD, "Falta": "#d98300",
                 "Tarjeta amarilla": NEON_GOLD, "Tarjeta roja": NEON_BAD,
                 "Penalti provocado": "#7d4ad8", "Penalti cometido": "#9e1b2f"}
    for ri, pl in enumerate(players):
        y = pad_t + ri * row_h
        rows += f'<line x1="{pad_l}" y1="{y+row_h/2:.1f}" x2="{w-30}" y2="{y+row_h/2:.1f}" stroke="{GRID_SVG}" stroke-width="1"/>'
        rows += (f'<text x="{pad_l-10}" y="{y+row_h/2:.1f}" text-anchor="end" '
                 f'dominant-baseline="central" font-size="12" font-weight="700" fill="{INK}">{pl[:18]}</text>')
        sub = df[df["jugador"] == pl]
        for _, ev in sub.iterrows():
            x = xpos(ev["minuto"])
            col = color_map.get(ev["resultado"], "#5f7a8a")
            rows += (f'<rect x="{x-7:.1f}" y="{y+6:.1f}" width="14" height="{row_h-12}" rx="3" '
                     f'fill="{col}"><title>{ev["minuto_fmt"]} · {ev["accion"]} · {ev["resultado"]}</title></rect>')

    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMinYMin meet"
        style="display:block;width:100%;min-width:{w}px;height:{h}px;background:#ffffff;border-radius:12px;border:1px solid #d3ded5">
      <g>{grid}{rows}</g></svg>'''


def tabla_html(df_tabla, height=320, resaltar_primera=False):
    """Renderiza un DataFrame como tabla HTML con el estilo neón (oscuro, cabecera
    legible, borde verde, filas alternas). Se controla todo el color aquí, sin
    depender del componente st.dataframe (que va en iframe y no se puede estilar)."""
    import html as _html
    cols = list(df_tabla.columns)
    th = "".join(
        f'<th style="position:sticky;top:0;background:#1c1f26;color:#fff;'
        f'font-weight:700;font-size:12.5px;text-align:left;padding:11px 14px;'
        f'border-bottom:2px solid #15ff66;white-space:nowrap;">{_html.escape(str(c))}</th>'
        for c in cols)
    filas = ""
    for i, (_, row) in enumerate(df_tabla.iterrows()):
        bg = "#181b21" if i % 2 else "#15171c"
        borde = ""
        if resaltar_primera and i == 0:
            bg = "rgba(21,255,102,0.10)"
            borde = "box-shadow:inset 3px 0 0 #15ff66;"
        celdas = ""
        for j, c in enumerate(cols):
            val = row[c]
            txt = "" if val is None else str(val)
            align = "left" if j < 2 else "right"
            color = "#fff" if j == 0 else "#d7dbe2"
            peso = "700" if j == 0 else "500"
            celdas += (f'<td style="padding:10px 14px;text-align:{align};color:{color};'
                       f'font-weight:{peso};font-size:13px;border-bottom:1px solid #23262f;'
                       f'white-space:nowrap;">{_html.escape(txt)}</td>')
        filas += f'<tr style="background:{bg};{borde}">{celdas}</tr>'
    tabla = (
        f'<div style="max-height:{height}px;overflow:auto;border:1px solid #2a2e38;'
        f'border-radius:12px;background:#15171c;font-family:-apple-system,Segoe UI,Roboto,sans-serif;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{th}</tr></thead><tbody>{filas}</tbody></table></div>')
    st_html(tabla, height=height + 16)


def render_svg(svg, height):
    """Renderiza un SVG dentro de un contenedor de altura fija que SÍ coincide
    con la altura reservada por st_html, de modo que no se corte ni desborde.
    El SVG se ajusta al contenedor manteniendo proporción (preserveAspectRatio)."""
    wrapper = (f"<div style='width:100%;height:{height}px;display:flex;"
               f"align-items:center;justify-content:center;font-family:sans-serif;'>{svg}</div>")
    st_html(wrapper, height=height + 8)


def barras_ranking_svg(rk, unidad, w=720):
    """Barras horizontales de ranking. rk: DataFrame con jugador, posicion, valor.
    La barra superior (mayor valor) se resalta en dorado."""
    n = len(rk)
    row_h = 46
    pad_t, pad_l, pad_r = 20, 200, 60
    h = pad_t + row_h * n + 16
    plot_w = w - pad_l - pad_r
    vmax = max(rk["valor"].max(), 1)
    bars = ""
    for i, (_, r) in enumerate(rk.iterrows()):
        y = pad_t + i * row_h
        bw = plot_w * (r["valor"] / vmax)
        col = NEON_GOLD if i == 0 else NEON_OK
        etiqueta = f"{r['jugador']} ({r['posicion']})" if r["posicion"] else str(r["jugador"])
        etiqueta = etiqueta[:24]
        val_txt = f"{r['valor']:g}" + ("%" if unidad == "% acierto" else "")
        bars += (f'<text x="{pad_l-10}" y="{y+row_h/2:.1f}" text-anchor="end" '
                 f'dominant-baseline="central" font-size="14" font-weight="700" '
                 f'fill="{INK}">{etiqueta}</text>')
        bars += (f'<rect x="{pad_l}" y="{y+8:.1f}" width="{max(bw,2):.1f}" height="{row_h-18}" '
                 f'rx="5" fill="{col}"/>')
        bars += (f'<text x="{pad_l+max(bw,2)+8:.1f}" y="{y+row_h/2:.1f}" '
                 f'dominant-baseline="central" font-size="13" font-weight="800" '
                 f'fill="{INK}">{val_txt}</text>')
    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMinYMin meet" style="display:block;width:100%;height:{h}px;">
      <g>{bars}</g></svg>'''


def dispersion_svg(sc, w=640, h=400):
    """Dispersión volumen (x=acciones) vs acierto (y=pct). sc: DataFrame con
    jugador, posicion, acciones, pct."""
    pad = 54
    plot_w, plot_h = w - pad - 20, h - pad - 30
    xmax = max(sc["acciones"].max(), 1)
    ymax = 100
    def px(v): return pad + plot_w * (v / xmax)
    def py(v): return (h - pad) - plot_h * (v / ymax)
    # ejes y rejilla
    grid = (f'<line x1="{pad}" y1="{h-pad}" x2="{w-20}" y2="{h-pad}" stroke="#9fb0a4" stroke-width="1.5"/>'
            f'<line x1="{pad}" y1="20" x2="{pad}" y2="{h-pad}" stroke="{TXT_LO_SVG}" stroke-width="1.5"/>')
    for f in (0, 25, 50, 75, 100):
        y = py(f)
        grid += f'<line x1="{pad}" y1="{y:.1f}" x2="{w-20}" y2="{y:.1f}" stroke="{GRID_SVG}" stroke-width="1"/>'
        grid += f'<text x="{pad-8}" y="{y:.1f}" text-anchor="end" dominant-baseline="central" font-size="11" fill="{TXT_LO_SVG}">{f}%</text>'
    grid += (f'<text x="{pad+plot_w/2:.0f}" y="{h-14}" text-anchor="middle" font-size="12" '
             f'font-weight="700" fill="{INK}">Nº de acciones</text>')
    grid += (f'<text x="16" y="{20+plot_h/2:.0f}" text-anchor="middle" font-size="12" font-weight="700" '
             f'fill="{INK}" transform="rotate(-90 16 {20+plot_h/2:.0f})">% de acierto</text>')
    pts = ""
    for _, r in sc.iterrows():
        x, y = px(r["acciones"]), py(r["pct"])
        nombre = str(r["jugador"]).split(" - ")[-1][:12]
        pts += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{NEON_OK}" fill-opacity="0.85" stroke="#0a6e2b" stroke-width="1"/>'
        # Si el punto está en el tercio derecho, la etiqueta va a su izquierda.
        if x > pad + plot_w * 0.7:
            pts += (f'<text x="{x-9:.1f}" y="{y:.1f}" text-anchor="end" dominant-baseline="central" '
                    f'font-size="11" fill="{INK}">{nombre}</text>')
        else:
            pts += (f'<text x="{x+9:.1f}" y="{y:.1f}" dominant-baseline="central" font-size="11" '
                    f'fill="{INK}">{nombre}</text>')
    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%;">
      <g>{grid}{pts}</g></svg>'''


def mapa_perfiles_svg(mapa, enlaces=None, w=680, h=470):
    """Mapa 2D de perfiles (PCA). `mapa`: salida de similitud.mapa_pca().
    `enlaces`: [{'jugador','similitud'}] con los parecidos REALES por coseno.

    La posición de los puntos la pone el PCA, que a lo grande es fiable pero en
    las distancias cortas reordena a los vecinos (aplastar 28 dimensiones a 2
    pierde la mitad de la información). Por eso los parecidos de verdad van
    DIBUJADOS con líneas desde el jugador en foco: la vara de medir es el coseno,
    no lo que se vea cerca en el mapa."""
    pad_l, pad_r, pad_t, pad_b = 60, 24, 26, 62
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    pts = mapa["puntos"]
    xs = [p["x"] for p in pts]; ys = [p["y"] for p in pts]
    x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
    mx = (x1 - x0) * 0.12 or 1.0; my = (y1 - y0) * 0.12 or 1.0
    x0, x1, y0, y1 = x0 - mx, x1 + mx, y0 - my, y1 + my

    def px(v): return pad_l + plot_w * ((v - x0) / (x1 - x0))
    def py(v): return (h - pad_b) - plot_h * ((v - y0) / (y1 - y0))

    # marco + ejes en el centro (origen = media de los tops)
    g = (f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" '
         f'fill="{PANEL_SVG}" stroke="{GRID_SVG}" stroke-width="1" rx="6"/>')
    if x0 < 0 < x1:
        g += (f'<line x1="{px(0):.1f}" y1="{pad_t}" x2="{px(0):.1f}" y2="{h-pad_b}" '
              f'stroke="{GRID_SVG}" stroke-width="1" stroke-dasharray="3 4"/>')
    if y0 < 0 < y1:
        g += (f'<line x1="{pad_l}" y1="{py(0):.1f}" x2="{w-pad_r}" y2="{py(0):.1f}" '
              f'stroke="{GRID_SVG}" stroke-width="1" stroke-dasharray="3 4"/>')

    foco = next((p for p in pts if p.get("foco")), None)
    pos_de = {p["nombre"]: p for p in pts}

    # --- Anticolisión de etiquetas ---
    # Los puntos se apelotonan, así que una etiqueta fija encima del punto se pisa
    # con la del vecino. Se prueban 4 posiciones y se coge la primera libre.
    ocupados = []

    def _libre(caja):
        ax0, ay0, ax1, ay1 = caja
        return not any(not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)
                       for bx0, by0, bx1, by1 in ocupados)

    def _etiqueta(x, y, txt, size, r):
        """Coloca el texto en el primer hueco libre alrededor del punto."""
        an = len(txt) * size * 0.52
        for dx, dy, anchor in ((0, -(r + 5), "middle"), (0, r + 11, "middle"),
                               (r + 4, 4, "start"), (-(r + 4), 4, "end")):
            tx, ty = x + dx, y + dy
            x0 = tx - (an / 2 if anchor == "middle" else (an if anchor == "end" else 0))
            caja = (x0, ty - size, x0 + an, ty + 3)
            if _libre(caja):
                ocupados.append(caja)
                return tx, ty, anchor
        ocupados.append((x - an / 2, y - r - size - 5, x + an / 2, y - r - 2))
        return x, y - r - 5, "middle"

    # Líneas a los parecidos REALES (coseno), no a los que caen cerca en el mapa.
    # El % se pone al 62% del trazado (no en el centro) para que los tres enlaces
    # no amontonen sus etiquetas en el mismo sitio.
    lin = ""
    for e in (enlaces or []):
        d = pos_de.get(e["jugador"])
        if not d or not foco:
            continue
        fx, fy, dx_, dy_ = px(foco["x"]), py(foco["y"]), px(d["x"]), py(d["y"])
        lin += (f'<line x1="{fx:.1f}" y1="{fy:.1f}" x2="{dx_:.1f}" y2="{dy_:.1f}" '
                f'stroke="{NEON_GOLD}" stroke-width="1.4" stroke-opacity="0.5" '
                f'stroke-dasharray="5 4"/>')
        tx, ty = fx + (dx_ - fx) * 0.62, fy + (dy_ - fy) * 0.62
        txt = f'{int(round(e["similitud"]*100))}%'
        an = len(txt) * 5.4
        ocupados.append((tx - an / 2 - 3, ty - 11, tx + an / 2 + 3, ty + 3))
        lin += (f'<rect x="{tx-an/2-3:.1f}" y="{ty-10:.1f}" width="{an+6:.1f}" height="13" '
                f'rx="3" fill="{PANEL_SVG}" fill-opacity="0.92"/>'
                f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="10" '
                f'font-weight="800" fill="{NEON_GOLD}">{txt}</text>')

    # puntos: tops de fondo, ojeados encima, foco el último (arriba del todo)
    def dibuja(p):
        x, y = px(p["x"]), py(p["y"])
        nom = str(p["nombre"])[:14]
        if p["tipo"] == "top":
            tx, ty, an = _etiqueta(x, y, nom, 9, 5)
            return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="none" '
                    f'stroke="{TXT_LO_SVG}" stroke-width="1.4" stroke-opacity="0.75"/>'
                    f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{an}" font-size="9" '
                    f'fill="{TXT_LO_SVG}">{nom}</text>')
        if p.get("foco"):
            tx, ty, an = _etiqueta(x, y, nom, 11, 11)
            return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{NEON_GOLD}" '
                    f'fill-opacity="0.18"/>'
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{NEON_GOLD}" '
                    f'stroke="#7a5c00" stroke-width="1.2"/>'
                    f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{an}" font-size="11" '
                    f'font-weight="800" fill="{NEON_GOLD}">{nom}</text>')
        dash = ' stroke-dasharray="3 2"' if p.get("atenuado") else ""
        op = "0.55" if p.get("atenuado") else "0.95"
        tx, ty, an = _etiqueta(x, y, nom, 10, 6)
        return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{NEON_SKY}" '
                f'fill-opacity="{op}" stroke="#0b5c86" stroke-width="1.2"{dash}/>'
                f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{an}" font-size="10" '
                f'font-weight="700" fill="{INK}" fill-opacity="{op}">{nom}</text>')

    # dibuja() RESERVA el hueco de la etiqueta al ejecutarse, así que el orden de
    # las llamadas fija la prioridad. Se reserva en orden de importancia (foco,
    # luego ojeados, y los tops con lo que quede), pero se pinta en orden de
    # capas (tops al fondo, foco arriba del todo). Por eso van en dos pasos.
    svg_foco = dibuja(foco) if foco else ""
    svg_ojeados = "".join(dibuja(p) for p in pts
                          if p["tipo"] == "ojeado" and not p.get("foco"))
    svg_tops = "".join(dibuja(p) for p in pts if p["tipo"] == "top")
    cuerpo = svg_tops + lin + svg_ojeados + svg_foco

    # Nombre de cada eje: las features que más pesan, y de qué lado están.
    def etiqueta(eje):
        return ", ".join(f for f, _ in eje["cargas"][:2])
    ex, ey = mapa["ejes"][0], mapa["ejes"][1]
    lado_x = "→" if ex["cargas"][0][1] > 0 else "←"
    lado_y = "↑" if ey["cargas"][0][1] > 0 else "↓"
    g += (f'<text x="{pad_l+plot_w/2:.0f}" y="{h-30}" text-anchor="middle" font-size="11" '
          f'font-weight="700" fill="{INK}">Eje 1 · {ex["var"]:.0%} — {etiqueta(ex)} '
          f'<tspan fill="{TXT_LO_SVG}">({lado_x} más)</tspan></text>')
    g += (f'<text x="18" y="{pad_t+plot_h/2:.0f}" text-anchor="middle" font-size="11" '
          f'font-weight="700" fill="{INK}" transform="rotate(-90 18 {pad_t+plot_h/2:.0f})">'
          f'Eje 2 · {ey["var"]:.0%} — {etiqueta(ey)} '
          f'<tspan fill="{TXT_LO_SVG}">({lado_y} más)</tspan></text>')
    g += (f'<text x="{pad_l}" y="{h-12}" font-size="10" fill="{TXT_LO_SVG}">'
          f'○ top · ● ojeado · ◌ punteado = muestra justa · '
          f'- - - parecido real (coseno)</text>')

    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%;">
      <g>{g}{cuerpo}</g></svg>'''


def _pitch_vertical_svg(w=440, h=660):
    """Césped + líneas de un campo VERTICAL (portería propia abajo)."""
    stripe = ""
    n = 7
    sh = h / n
    for i in range(n):
        col = GRASS_A if i % 2 == 0 else GRASS_B
        stripe += f'<rect x="0" y="{i*sh:.1f}" width="{w}" height="{sh:.1f}" fill="{col}"/>'
    cx = w / 2
    midy = h / 2
    r = w * 0.18
    lines = f"""
      <rect x="3" y="3" width="{w-6}" height="{h-6}" fill="none" stroke="{LINE}" stroke-width="2.5" rx="4"/>
      <line x1="3" y1="{midy}" x2="{w-3}" y2="{midy}" stroke="{LINE}" stroke-width="2.5"/>
      <circle cx="{cx}" cy="{midy}" r="{r}" fill="none" stroke="{LINE}" stroke-width="2.5"/>
      <circle cx="{cx}" cy="{midy}" r="3" fill="{LINE}"/>
      <rect x="{cx-w*0.28}" y="3" width="{w*0.56}" height="{h*0.14}" fill="none" stroke="{LINE}" stroke-width="2"/>
      <rect x="{cx-w*0.28}" y="{h-3-h*0.14}" width="{w*0.56}" height="{h*0.14}" fill="none" stroke="{LINE}" stroke-width="2"/>
      <rect x="{cx-w*0.13}" y="3" width="{w*0.26}" height="{h*0.055}" fill="none" stroke="{LINE}" stroke-width="2"/>
      <rect x="{cx-w*0.13}" y="{h-3-h*0.055}" width="{w*0.26}" height="{h*0.055}" fill="none" stroke="{LINE}" stroke-width="2"/>
    """
    return stripe + lines


def boxplot_svg(dist, destacado, titulo, w=640, h=300):
    """Box plot horizontal de la distribución {jugador: valor}, marcando 'destacado'.
    Muestra min, Q1, mediana, Q3, max y un punto neón por el jugador elegido."""
    import numpy as np
    vals = [v for v in dist.values() if v is not None]
    if not vals:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"></svg>'
    arr = np.array(vals, dtype=float)
    vmin, vmax = float(arr.min()), float(arr.max())
    q1, med, q3 = (float(np.percentile(arr, p)) for p in (25, 50, 75))
    rango = (vmax - vmin) or 1.0
    M = 60; plot_w = w - 2 * M; midy = h // 2
    def X(v): return M + (v - vmin) / rango * plot_w
    box_top, box_h = midy - 38, 76
    val_dest = dist.get(destacado)
    partes = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:{h}px;">',
        f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>',
        f'<text x="{M}" y="28" fill="{INK}" font-size="13" font-weight="700" font-family="sans-serif">{titulo}</text>',
        # bigotes
        f'<line x1="{X(vmin):.1f}" y1="{midy}" x2="{X(q1):.1f}" y2="{midy}" stroke="{TXT_LO_SVG}" stroke-width="2"/>',
        f'<line x1="{X(q3):.1f}" y1="{midy}" x2="{X(vmax):.1f}" y2="{midy}" stroke="{TXT_LO_SVG}" stroke-width="2"/>',
        f'<line x1="{X(vmin):.1f}" y1="{midy-12}" x2="{X(vmin):.1f}" y2="{midy+12}" stroke="{TXT_LO_SVG}" stroke-width="2"/>',
        f'<line x1="{X(vmax):.1f}" y1="{midy-12}" x2="{X(vmax):.1f}" y2="{midy+12}" stroke="{TXT_LO_SVG}" stroke-width="2"/>',
        # caja Q1-Q3
        f'<rect x="{X(q1):.1f}" y="{box_top}" width="{X(q3)-X(q1):.1f}" height="{box_h}" '
        f'fill="{NEON_SKY}" fill-opacity="0.18" stroke="{NEON_SKY}" stroke-width="2" rx="4"/>',
        # mediana
        f'<line x1="{X(med):.1f}" y1="{box_top}" x2="{X(med):.1f}" y2="{box_top+box_h}" stroke="{NEON_SKY}" stroke-width="2.5"/>',
        # etiquetas de escala
        f'<text x="{X(vmin):.1f}" y="{midy+34}" fill="{TXT_LO_SVG}" font-size="9" text-anchor="middle" font-family="sans-serif">{round(vmin)}</text>',
        f'<text x="{X(vmax):.1f}" y="{midy+34}" fill="{TXT_LO_SVG}" font-size="9" text-anchor="middle" font-family="sans-serif">{round(vmax)}</text>',
        f'<text x="{X(med):.1f}" y="{box_top-6}" fill="{NEON_SKY}" font-size="9" text-anchor="middle" font-family="sans-serif">med {round(med)}</text>',
    ]
    if val_dest is not None:
        partes.append(
            f'<circle cx="{X(val_dest):.1f}" cy="{midy}" r="8" fill="{NEON_OK}" stroke="#04210f" stroke-width="1.5"/>')
        partes.append(
            f'<text x="{X(val_dest):.1f}" y="{box_top+box_h+24}" fill="{NEON_OK}" font-size="11" '
            f'font-weight="700" text-anchor="middle" font-family="sans-serif">{destacado}: {round(val_dest)}</text>')
    partes.append('</svg>')
    return "".join(partes)


def _oscurecer(hex_col, factor=0.6):
    """Oscurece un color hex multiplicando sus componentes por factor (<1)."""
    h = hex_col.lstrip("#")
    if len(h) != 6:
        return hex_col
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def linea_temporal_svg(series, titulo, modo, w=680, h=340):
    """Gráfico de evolución multi-jugador. series = lista de dicts:
       {name, color, puntos: [{rival, valor}]}.
    Eje X = rival de cada partido. Hasta 3 jugadores, cada uno con su color;
    los puntos van del mismo color pero más oscuros y marcados."""
    # Recoger el eje X común (rivales, en el orden del primer jugador con datos).
    eje_x = []
    for s in series:
        if s.get("puntos"):
            eje_x = [p["rival"] for p in s["puntos"]]
            break
    n = len(eje_x)
    if n < 2:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
                f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>'
                f'<text x="{w/2}" y="{h/2}" fill="{TXT_LO_SVG}" font-size="12" '
                f'text-anchor="middle" font-family="sans-serif">Se necesitan al menos '
                f'2 partidos</text></svg>')

    todos_vals = [p["valor"] for s in series for p in s.get("puntos", [])]
    if modo == "aciertos":
        vmax = 100.0
    elif modo == "nota":
        vmax = 10.0
    else:
        vmax = (max(todos_vals) * 1.15) if todos_vals else 1.0
    vmax = vmax or 1.0
    M = 52; plot_w = w - 2 * M; plot_h = h - 96; top = 46

    def X(i): return M + (i / (n - 1)) * plot_w
    def Y(v): return top + plot_h - (v / vmax) * plot_h

    partes = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:{h}px;">',
        '<defs><filter id="glowL" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="3" result="b"/><feMerge>'
        '<feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
        f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>',
        f'<text x="{M}" y="26" fill="{INK}" font-size="13" font-weight="700" font-family="sans-serif">{titulo}</text>',
        f'<line x1="{M}" y1="{top+plot_h}" x2="{w-M}" y2="{top+plot_h}" stroke="{GRID_SVG}" stroke-width="1.5"/>',
        f'<line x1="{M}" y1="{top}" x2="{M}" y2="{top+plot_h}" stroke="{GRID_SVG}" stroke-width="1.5"/>',
    ]
    # Etiquetas del eje X (rival), comunes
    for i, riv in enumerate(eje_x):
        etq = (riv or "")[:12]
        partes.append(f'<text x="{X(i):.1f}" y="{top+plot_h+18}" fill="{TXT_LO_SVG}" '
                      f'font-size="8.5" text-anchor="middle" font-family="sans-serif">{etq}</text>')
    # Una línea por jugador
    for s in series:
        pts = s.get("puntos", [])
        if len(pts) < 2:
            continue
        color = s.get("color", NEON_SKY)
        color_pt = _oscurecer(color, 0.62)
        poly = " ".join(f"{X(i):.1f},{Y(p['valor']):.1f}" for i, p in enumerate(pts))
        partes.append(f'<polyline points="{poly}" fill="none" stroke="{color}" '
                      f'stroke-width="3" filter="url(#glowL)"/>')
        for i, p in enumerate(pts):
            partes.append(f'<circle cx="{X(i):.1f}" cy="{Y(p["valor"]):.1f}" r="5" '
                          f'fill="{color_pt}" stroke="{color}" stroke-width="2"/>')
            etq_val = f'{p["valor"]:.1f}' if modo == "nota" else f'{round(p["valor"])}'
            partes.append(f'<text x="{X(i):.1f}" y="{Y(p["valor"])-10:.1f}" fill="{INK}" '
                          f'font-size="9.5" text-anchor="middle" font-family="sans-serif">{etq_val}</text>')
    partes.append('</svg>')
    return "".join(partes)


def barras_nota_svg(series, titulo="Nota (0-10)", w=680, h=340):
    """Evolución de la NOTA en BARRAS. Cada barra se colorea por banda de nota
    ([1,5)→rojo, [5,7)→naranja, [7,9)→amarillo, >=9→verde). Hasta 3 jugadores:
    barras agrupadas por rival; la identidad del jugador va en su color de borde
    y en la leyenda. series = [{name, color, puntos:[{rival, valor}]}]."""
    jugs = [s for s in series if s.get("puntos")]
    eje_x = jugs[0]["puntos"] if jugs else []
    n = len(eje_x)
    if n < 1:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
                f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>'
                f'<text x="{w/2}" y="{h/2}" fill="{TXT_LO_SVG}" font-size="12" '
                f'text-anchor="middle" font-family="sans-serif">Sin datos</text></svg>')

    vmax = 10.0
    M = 52; plot_w = w - 2 * M; plot_h = h - 96; top = 46
    base_y = top + plot_h

    def Y(v): return base_y - (v / vmax) * plot_h

    ng = max(1, len(jugs))
    group_w = plot_w / n
    inner = group_w * 0.72          # ancho útil dentro del grupo
    gap = 4 if ng > 1 else 0
    bw = max(6.0, (inner - gap * (ng - 1)) / ng)

    partes = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:{h}px;">',
        f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>',
        f'<text x="{M}" y="26" fill="{INK}" font-size="13" font-weight="700" '
        f'font-family="sans-serif">{titulo}</text>',
    ]
    # Líneas guía en los límites de banda (5, 7, 9) y eje base
    for lim in (5, 7, 9):
        partes.append(f'<line x1="{M}" y1="{Y(lim):.1f}" x2="{w-M}" y2="{Y(lim):.1f}" '
                      f'stroke="{GRID_SVG}" stroke-width="1" stroke-dasharray="3 4"/>')
        partes.append(f'<text x="{M-6}" y="{Y(lim)+3:.1f}" fill="{TXT_LO_SVG}" font-size="8" '
                      f'text-anchor="end" font-family="sans-serif">{lim}</text>')
    partes.append(f'<line x1="{M}" y1="{base_y}" x2="{w-M}" y2="{base_y}" '
                  f'stroke="{GRID_SVG}" stroke-width="1.5"/>')

    for i in range(n):
        gx = M + i * group_w + (group_w - inner) / 2  # inicio del grupo centrado
        # etiqueta de rival
        riv = (eje_x[i].get("rival") or "")[:12]
        partes.append(f'<text x="{M + i*group_w + group_w/2:.1f}" y="{base_y+18}" '
                      f'fill="{TXT_LO_SVG}" font-size="8.5" text-anchor="middle" '
                      f'font-family="sans-serif">{riv}</text>')
        for j, s in enumerate(jugs):
            pts = s["puntos"]
            if i >= len(pts):
                continue
            v = pts[i]["valor"]
            col = _color_nota(v)
            x = gx + j * (bw + gap)
            y = Y(v)
            bh = base_y - y
            partes.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                          f'rx="3" fill="{col}" fill-opacity="0.9" '
                          f'stroke="{s.get("color", col)}" stroke-width="1.5"/>')
            partes.append(f'<text x="{x + bw/2:.1f}" y="{y-5:.1f}" fill="{INK}" '
                          f'font-size="9.5" font-weight="700" text-anchor="middle" '
                          f'font-family="sans-serif">{v:.1f}</text>')
    partes.append('</svg>')
    return "".join(partes)


def influencia_svg(datos_por_jugador, titulo, w=760, h=610):
    """Gráfico de influencia por minuto, estilo neón.
    datos_por_jugador = lista de {name, color, data} con data de
    analytics.influencia_por_minuto. ARRIBA barras de volumen por franja de 15';
    ABAJO líneas de eficiencia con símbolos de peligro (★ gol, ▲ tiro, ◆ clave)."""
    if not datos_por_jugador:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"></svg>'
    labels = datos_por_jugador[0]["data"]["labels"]
    n = len(labels)
    M = 54
    plot_w = w - 2 * M
    top_v = 56; h_v = 200
    top_e = top_v + h_v + 78; h_e = 170
    max_vol = max([max(d["data"]["volumen"]) for d in datos_por_jugador] + [1])

    def X(i): return M + (i + 0.5) * (plot_w / n)

    partes = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:{h}px;">',
        '<defs><filter id="glowI" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="3" result="b"/><feMerge>'
        '<feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
        f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>',
        f'<text x="{M}" y="30" fill="{INK}" font-size="14" font-weight="800" font-family="sans-serif">{titulo}</text>',
        f'<text x="{M}" y="{top_v-8}" fill="{TXT_LO_SVG}" font-size="11" font-weight="700" font-family="sans-serif">VOLUMEN — acciones por franja de 15\'</text>',
        f'<line x1="{M}" y1="{top_v+h_v}" x2="{w-M}" y2="{top_v+h_v}" stroke="{GRID_SVG}" stroke-width="1.5"/>',
    ]
    nj = len(datos_por_jugador)
    franja_w = plot_w / n
    bar_w = min(franja_w / (nj + 1), 34)
    for i in range(n):
        base_x = M + i * franja_w + (franja_w - bar_w * nj) / 2
        for j, d in enumerate(datos_por_jugador):
            v = d["data"]["volumen"][i]
            bh = (v / max_vol) * (h_v - 10)
            bx = base_x + j * bar_w
            by = top_v + h_v - bh
            partes.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w-3:.1f}" height="{bh:.1f}" '
                          f'rx="3" fill="{d["color"]}" fill-opacity="0.85" filter="url(#glowI)"/>')
            if v > 0:
                partes.append(f'<text x="{bx+(bar_w-3)/2:.1f}" y="{by-4:.1f}" fill="{INK}" '
                              f'font-size="9" text-anchor="middle" font-family="sans-serif">{v}</text>')
        partes.append(f'<text x="{X(i):.1f}" y="{top_v+h_v+16:.1f}" fill="{TXT_LO_SVG}" '
                      f'font-size="9" text-anchor="middle" font-family="sans-serif">{labels[i]}</text>')

    partes.append(f'<text x="{M}" y="{top_e-10}" fill="{TXT_LO_SVG}" font-size="11" font-weight="700" font-family="sans-serif">EFICIENCIA — % acierto por franja (símbolos = peligro)</text>')
    partes.append(f'<line x1="{M}" y1="{top_e+h_e}" x2="{w-M}" y2="{top_e+h_e}" stroke="{GRID_SVG}" stroke-width="1.5"/>')
    partes.append(f'<line x1="{M}" y1="{top_e}" x2="{M}" y2="{top_e+h_e}" stroke="{GRID_SVG}" stroke-width="1.5"/>')
    for pct in (50, 100):
        yy = top_e + h_e - (pct / 100) * h_e
        partes.append(f'<line x1="{M}" y1="{yy:.1f}" x2="{w-M}" y2="{yy:.1f}" stroke="{GRID_SVG}" stroke-width="0.7" stroke-dasharray="4 4"/>')
        partes.append(f'<text x="{M-6}" y="{yy+3:.1f}" fill="{TXT_LO_SVG}" font-size="8" text-anchor="end" font-family="sans-serif">{pct}%</text>')

    def Ye(v): return top_e + h_e - (v / 100.0) * h_e
    simbolos = {"gol": "★", "tiro": "▲", "clave": "◆"}
    # etiquetas de franja en el eje X de la eficiencia
    for i, lab in enumerate(labels):
        partes.append(f'<text x="{X(i):.1f}" y="{top_e+h_e+16:.1f}" fill="{TXT_LO_SVG}" '
                      f'font-size="9" text-anchor="middle" font-family="sans-serif">{lab}</text>')
    for jd, d in enumerate(datos_por_jugador):
        efs = d["data"]["eficiencia"]
        color = d["color"]
        pts = [(X(i), Ye(v)) for i, v in enumerate(efs) if v is not None]
        if len(pts) >= 2:
            poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            partes.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="3" filter="url(#glowI)"/>')
        for i, v in enumerate(efs):
            if v is None:
                continue
            partes.append(f'<circle cx="{X(i):.1f}" cy="{Ye(v):.1f}" r="4.5" fill="{_oscurecer(color,0.62)}" stroke="{color}" stroke-width="2"/>')
        # símbolos de peligro DEBAJO del gráfico (una fila por jugador, escalonada)
        fila_y = top_e + h_e + 30 + jd * 14
        for i, peli in enumerate(d["data"]["peligro"]):
            for k, tipo in enumerate(peli[:4]):
                sx = X(i) - 12 + k * 9
                partes.append(f'<text x="{sx:.1f}" y="{fila_y:.1f}" fill="{color}" font-size="12" '
                              f'text-anchor="middle" font-family="sans-serif">{simbolos.get(tipo,"·")}</text>')
    partes.append(f'<text x="{w-M}" y="{h-10}" fill="{TXT_LO_SVG}" font-size="9" '
                  f'text-anchor="end" font-family="sans-serif">★ gol   ▲ tiro a puerta   ◆ pase clave</text>')
    partes.append('</svg>')
    return "".join(partes)


def donut_svg(datos, jugador, w=520, h=520):
    """Donut de proporción de acciones. datos = [(etiqueta, conteo)] desc.
    (Ya no se usa en el dashboard, se conserva por si se reutiliza.)"""
    import math
    total = sum(c for _, c in datos) or 1
    cx, cy, r, rin = w * 0.5, 165, 130, 78
    paleta = [NEON_SKY, NEON_OK, NEON_GOLD, NEON_BAD, "#a855f7", "#fb7185",
              "#38d39f", "#fbbf24", "#22d3ee", "#f97316", "#84cc16", "#e879f9"]
    partes = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMin meet" style="display:block;width:100%;height:{h}px;">',
        f'<rect width="{w}" height="{h}" fill="{PANEL_SVG}" rx="14"/>',
        f'<text x="{w/2:.0f}" y="34" fill="{INK}" font-size="15" font-weight="800" '
        f'text-anchor="middle" font-family="sans-serif">{jugador} · acciones</text>',
    ]
    ang = -90.0
    for i, (etq, c) in enumerate(datos):
        frac = c / total
        ang2 = ang + frac * 360
        large = 1 if (ang2 - ang) > 180 else 0
        x1 = cx + r * math.cos(math.radians(ang)); y1 = cy + r * math.sin(math.radians(ang))
        x2 = cx + r * math.cos(math.radians(ang2)); y2 = cy + r * math.sin(math.radians(ang2))
        col = paleta[i % len(paleta)]
        # relleno translúcido + borde del mismo color, marcado (estilo tagger)
        partes.append(
            f'<path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f} L {cx:.1f} {cy:.1f} Z" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="2"/>')
        ang = ang2
    # agujero
    partes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rin}" fill="{PANEL_SVG}"/>')
    partes.append(f'<text x="{cx:.1f}" y="{cy-4:.1f}" fill="{INK}" font-size="30" font-weight="800" '
                  f'text-anchor="middle" font-family="sans-serif">{total}</text>')
    partes.append(f'<text x="{cx:.1f}" y="{cy+18:.1f}" fill="{TXT_LO_SVG}" font-size="11" '
                  f'text-anchor="middle" font-family="sans-serif">acciones</text>')
    # leyenda en rejilla de 2 columnas, debajo del donut
    ly0 = cy + r + 36
    col_w = w / 2
    for i, (etq, c) in enumerate(datos):
        col = paleta[i % len(paleta)]
        cx_leg = 24 + (i % 2) * col_w
        cy_leg = ly0 + (i // 2) * 26
        if cy_leg > h - 12:
            break
        pct = round(100 * c / total)
        partes.append(f'<rect x="{cx_leg}" y="{cy_leg-11}" width="13" height="13" rx="3" '
                      f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>')
        partes.append(f'<text x="{cx_leg+20}" y="{cy_leg}" fill="{INK}" font-size="12.5" '
                      f'font-family="sans-serif">{etq[:18]} · {pct}%</text>')
    partes.append('</svg>')
    return "".join(partes)


def pizarra_svg(fichas, w=440, h=660, color="#0b3d91"):
    """Dibuja la pizarra con las fichas. fichas: lista de dicts con
    {dorsal, pos, x, y} en porcentajes (x 0-100 izq->der, y 0-100 gol propio->rival).
    El campo es vertical: y=0 abajo (portería propia), y=100 arriba (ataque)."""
    base = _pitch_vertical_svg(w, h)

    def sx(xp): return (xp / 100.0) * w
    def sy(yp): return h - (yp / 100.0) * h  # invertir: 0% abajo

    chips = ""
    rad = 17
    for f in fichas:
        cx, cy = sx(f["x"]), sy(f["y"])
        col = "#c8a200" if f.get("pos") == "POR" else color
        chips += (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad}" fill="{col}" '
                  f'stroke="#ffffff" stroke-width="2.5"/>')
        chips += (f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" dominant-baseline="central" '
                  f'font-size="15" font-weight="800" fill="#ffffff">{f["dorsal"]}</text>')
        chips += (f'<text x="{cx:.1f}" y="{cy+rad+12:.1f}" text-anchor="middle" '
                  f'font-size="11" font-weight="700" fill="#ffffff" '
                  f'stroke="{INK}" stroke-width="0.5">{f.get("pos","")}</text>')
    # Flecha de sentido de ataque (hacia arriba)
    arrow = (f'<defs><marker id="arUp" markerWidth="10" markerHeight="10" refX="3" refY="3" orient="auto">'
             f'<path d="M0,6 L3,0 L6,6 Z" fill="#fff"/></marker></defs>'
             f'<line x1="{w-18}" y1="{h*0.7}" x2="{w-18}" y2="{h*0.3}" stroke="#fff" '
             f'stroke-width="2" marker-end="url(#arUp)" opacity="0.85"/>')
    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%;">
      <g>{base}{chips}{arrow}</g></svg>'''


def formacion_a_fichas(formacion, fase):
    """Genera la lista de fichas de una formación aplicando el desplazamiento
    vertical de la fase. Devuelve lista de dicts {dorsal, pos, x, y}."""
    offset = FASE_OFFSET.get(fase, 0)
    fichas = []
    for dorsal, pos, x, y in FORMACIONES[formacion]:
        ny = y + offset
        # El portero apenas se mueve; el resto sí acompaña la fase.
        if pos == "POR":
            ny = y + offset * 0.2
        ny = max(2, min(98, ny))
        fichas.append({"dorsal": dorsal, "pos": pos, "x": float(x), "y": float(ny)})
    return fichas


# ============================================================================
# NAVEGACIÓN PRINCIPAL (barra lateral)
# ============================================================================
def render_nav():
    with st.sidebar:
        st.markdown("<div class='hud-kicker'>Scouting Mundial</div>", unsafe_allow_html=True)
        st.markdown("### Navegación")
        secciones = ["Registro jugadores", "Gráficos", "Secuencias", "Predicciones"]
        for sec in secciones:
            is_active = (st.session_state.section == sec)
            if st.button(sec, key=f"nav-{sec}", use_container_width=True,
                         type=("primary" if is_active else "secondary")):
                # Al cambiar de sección de registro, volvemos al menú de esa sección.
                if sec == "Registro jugadores" and st.session_state.section != sec:
                    st.session_state.view = "menu"
                st.session_state.section = sec
                st.rerun()
        st.divider()


# ============================================================================
# MENÚ DE SESIONES (parametrizado por tipo: jugadores o equipo)
# ============================================================================
def render_menu(tipo=TIPO_JUGADORES):
    es_equipo = (tipo == TIPO_EQUIPO)
    st.session_state.reg_tipo = tipo
    if es_equipo:
        kicker = "Registro de equipos · panel de control"
        titulo = "Sesiones de equipo"
        ayuda = ("Cada sesión de equipo guarda un partido analizado a nivel colectivo, "
                 "con acciones generales del conjunto. Separadas de las de jugadores.")
        ph = "Ej: España vs Brasil — análisis de equipo"
    else:
        kicker = "Registro de jugadores · panel de control"
        titulo = "Sesiones de jugadores"
        ayuda = ("Cada sesión guarda un partido con sus jugadores y todas las acciones "
                 "individuales registradas. Se guarda automáticamente en la nube.")
        ph = "Ej: España vs Brasil — cuartos"
    st.markdown(f"<div class='hud-kicker'>{kicker}</div>", unsafe_allow_html=True)
    st.markdown(f"# {titulo}")
    st.caption(ayuda)

    with st.container():
        c1, c2, c3 = st.columns([3, 2, 1])
        nombre = c1.text_input("Nombre de la nueva sesión", placeholder=ph,
                               key=f"new_session_name_{tipo}")
        competicion = c2.text_input("Competición", value="Mundial", key=f"new_session_comp_{tipo}")
        c3.write(""); c3.write("")
        if c3.button("Crear sesión", type="primary", use_container_width=True, key=f"create_{tipo}"):
            if nombre.strip():
                sid = storage.create_session(nombre.strip(), competicion.strip() or "Mundial", tipo=tipo)
                if sid:
                    new_sess = storage.load_session(sid)
                    if new_sess:
                        load_into_state(new_sess)
                        st.rerun()
            else:
                st.warning("Pon un nombre a la sesión antes de crearla.")

    st.divider()
    st.markdown("### Sesiones guardadas")
    sessions = storage.list_sessions(tipo=tipo)
    if not sessions:
        st.info("Aún no tienes sesiones guardadas de este tipo. Crea la primera arriba.")
        return

    for s in sessions:
        with st.container():
            cols = st.columns([3.5, 1.5, 1.2, 1.2, 1, 1])
            local = s.get("equipo_local") or ""
            visit = s.get("equipo_visitante") or ""
            if local or visit:
                marcador = f"{local or 'Local'} {s.get('goles_local',0)}–{s.get('goles_visitante',0)} {visit or 'Visitante'}"
            else:
                marcador = "(sin equipos definidos)"
            cols[0].markdown(
                f"**{s['nombre']}**  \n"
                f"<span class='session-sub'>{marcador} · {s.get('competicion','')} · {s.get('fecha','')}</span>",
                unsafe_allow_html=True)
            if es_equipo:
                cols[1].metric("Tipo", "Equipo")
            else:
                cols[1].metric("Jugadores", s.get("num_jugadores", 0))
            updated = s.get("updated_at", "")
            if updated:
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    updated = dt.strftime("%d/%m %H:%M")
                except Exception:
                    pass
            cols[3].markdown(f"<div class='session-sub' style='padding-top:1.2rem;'>Editada<br>{updated}</div>",
                             unsafe_allow_html=True)
            if cols[4].button("Abrir", key=f"open_{s['id']}", use_container_width=True, type="primary"):
                full = storage.load_session(s["id"])
                if full:
                    load_into_state(full)
                    st.rerun()
            if cols[5].button("Borrar", key=f"del_{s['id']}", use_container_width=True):
                if st.session_state.get("confirm_delete") == s["id"]:
                    if storage.delete_session(s["id"]):
                        st.session_state.pop("confirm_delete", None)
                        st.rerun()
                else:
                    st.session_state["confirm_delete"] = s["id"]
                    st.warning(f"Pulsa Borrar otra vez para confirmar el borrado de «{s['nombre']}».")
            st.markdown("<hr class='session-sep'>", unsafe_allow_html=True)


# ============================================================================
# SECCIÓN: SESIONES — panel de edición (tagging en vivo)
# ============================================================================
def render_edit():
    shortcuts_js = """
    <script>
    (function() {
        if (window._scouting_shortcuts_installed) return;
        window._scouting_shortcuts_installed = true;
        const clickByKeyPrefix = (prefix) => {
            const doc = window.parent.document;
            const el = doc.querySelector('[class*="st-key-' + prefix + '"]');
            if (el) { const b = el.querySelector('button'); if (b) { b.click(); return true; } }
            return false;
        };
        window.parent.document.addEventListener('keydown', function(e) {
            const tag = (e.target && e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
            if (e.key === 'z' || e.key === 'Z') { if (clickByKeyPrefix('sc-undo')) e.preventDefault(); return; }
            if (e.code === 'Space') { if (clickByKeyPrefix('sc-clock-toggle')) e.preventDefault(); return; }
            if (e.key === 'ArrowLeft') { if (clickByKeyPrefix('sc-player-prev')) e.preventDefault(); return; }
            if (e.key === 'ArrowRight') { if (clickByKeyPrefix('sc-player-next')) e.preventDefault(); return; }
            // Teclas 1-9: fijar zona de la rejilla 3x3.
            // 1=1er tercio izq, 2=1er tercio centro, 3=1er tercio der, 4=2º izq ... 9=3er der.
            if (e.key >= '1' && e.key <= '9') {
                const n = parseInt(e.key, 10) - 1;
                const tercio = Math.floor(n / 3);   // 0,1,2
                const banda = n % 3;                // 0=izq,1=centro,2=der
                if (clickByKeyPrefix('zona-' + tercio + '-' + banda)) e.preventDefault();
                return;
            }
        }, true);
    })();
    </script>
    """
    st_html(shortcuts_js, height=0)

    # --- SIDEBAR ---
    with st.sidebar:
        if st.button("← Volver al listado", use_container_width=True):
            autosave()
            st.session_state.view = "menu"
            st.rerun()
        st.header("Configuración")
        with st.expander("Datos del partido", expanded=True):
            mi = st.session_state.match_info
            old = dict(mi)
            mi["nombre"] = st.text_input("Nombre de la sesión", mi.get("nombre", ""))
            mi["competicion"] = st.text_input("Competición", mi["competicion"])
            mi["fecha"] = st.text_input("Fecha", mi["fecha"])
            c1, c2 = st.columns(2)
            mi["equipo_local"] = c1.text_input("Equipo local", mi["equipo_local"])
            mi["equipo_visitante"] = c2.text_input("Equipo visitante", mi["equipo_visitante"])
            c3, c4 = st.columns(2)
            mi["goles_local"] = c3.number_input("Goles local", min_value=0, value=mi["goles_local"], step=1)
            mi["goles_visitante"] = c4.number_input("Goles visit.", min_value=0, value=mi["goles_visitante"], step=1)
            mi["posesion_local"] = st.slider("Posesión local (%)", 0, 100, mi["posesion_local"])
            st.caption(f"Posesión visitante: {100 - mi['posesion_local']}%")
            mi["minuto_descanso"] = st.number_input(
                "Minuto de descanso (separa 1ª/2ª parte)", min_value=1, max_value=160,
                value=int(mi.get("minuto_descanso", 45)), step=1)
            NIVELES = ["Élite", "Alto", "Medio", "Bajo"]
            cn1, cn2 = st.columns(2)
            mi["nivel_propio"] = cn1.selectbox(
                "Nivel del equipo propio", NIVELES,
                index=NIVELES.index(mi.get("nivel_propio", "Medio")) if mi.get("nivel_propio") in NIVELES else 2)
            mi["nivel_rival"] = cn2.selectbox(
                "Nivel del rival", NIVELES,
                index=NIVELES.index(mi.get("nivel_rival", "Medio")) if mi.get("nivel_rival") in NIVELES else 2)
            st.caption("El nivel sirve para contextualizar el rendimiento: no es lo mismo "
                       "rendir contra un rival de élite que contra uno de nivel bajo.")
            mi["contexto_partido"] = st.text_area(
                "Contexto del partido (opcional)",
                value=mi.get("contexto_partido", ""),
                placeholder="Ej.: Bélgica dominó en campo rival casi todo el partido; "
                            "Egipto solo presionó arriba en los minutos finales.",
                help="Notas de flujo del partido que los números no capturan. La IA las "
                     "usará para interpretar mejor el rendimiento del jugador.")
            if mi != old:
                autosave()
        st.divider()
        es_equipo = (st.session_state.reg_tipo == TIPO_EQUIPO)
        if not es_equipo:
            st.subheader("Jugadores")
            with st.expander("➕ Añadir jugador", expanded=not st.session_state.players):
                new_player = st.text_input("Nombre", placeholder="Ej: 10 - Messi", key="new_player_input")
                cpa, cpb = st.columns(2)
                new_pos = cpa.selectbox("Posición", POSICION_CODIGOS,
                                        format_func=lambda c: f"{c} · {POSICIONES[c]}", key="new_player_pos")
                new_edad = cpb.number_input("Edad", min_value=14, max_value=50, value=23, key="new_player_edad")
                new_equipo = st.text_input(
                    "Equipo principal (bandera)", key="new_player_equipo",
                    placeholder="Ej: México",
                    help="El equipo de referencia del jugador, normalmente su "
                         "selección. Es el que decide la bandera del dashboard "
                         "y NO cambia de un partido a otro.")
                new_equipo_part = st.text_input(
                    "Equipo en este partido", key="new_player_equipo_partido",
                    placeholder="Déjalo vacío si juega con su equipo principal",
                    help="Con qué equipo juega HOY: selección, sub-20 o club. "
                         "Se guarda solo en este partido; el histórico no se toca.")
                cme, cms = st.columns(2)
                new_min_in = cme.number_input("Minuto de entrada", min_value=0, value=0, key="new_player_min_in",
                                              help="0 si es titular. Para un suplente, el minuto en que entró.")
                new_min_out = cms.number_input("Minuto de salida", min_value=0, value=90, key="new_player_min_out",
                                               help="Minuto en que fue sustituido. Déjalo en el final si jugó hasta el pitido.")
                st.caption("Las fotos y banderas se suben a mano al bucket 'fotos' de "
                           "Supabase (carpetas jugadores/ y banderas/), con el nombre del "
                           "jugador y del país en minúsculas. La app las muestra sola.")
                if st.button("Guardar jugador", use_container_width=True, type="primary"):
                    name = new_player.strip()
                    if name and name not in st.session_state.players:
                        st.session_state.players.append(name)
                        st.session_state.posiciones[name] = new_pos
                        ficha_completa = {
                            "pos": new_pos, "equipo": new_equipo.strip(),
                            "edad": int(new_edad),
                            "min_in": int(new_min_in), "min_out": int(new_min_out),
                        }
                        # Guardar la ficha (sin fotos: viven en el bucket) en 'jugadores'.
                        # OJO: a 'jugadores' va el equipo PRINCIPAL; el equipo de
                        # este partido vive solo en la sesión, para no pisar el
                        # histórico de un jugador que cambia de equipo.
                        storage.upsert_ficha_jugador(name, ficha_completa)
                        st.session_state.jugadores_info[name] = dict(
                            ficha_completa,
                            equipo=(new_equipo_part.strip() or new_equipo.strip()))
                        if st.session_state.active_player is None:
                            st.session_state.active_player = name
                        autosave()
                        st.rerun()
                    elif name in st.session_state.players:
                        st.warning("Ese jugador ya existe.")

            if st.session_state.players:
                sel = st.radio("Jugador activo", st.session_state.players,
                               index=st.session_state.players.index(st.session_state.active_player)
                               if st.session_state.active_player in st.session_state.players else 0,
                               format_func=lambda n: f"{n}  ({st.session_state.posiciones.get(n,'?')})")
                if sel != st.session_state.active_player:
                    st.session_state.active_player = sel
                # Editor de datos del jugador activo (plegado, no estorba).
                with st.expander(f"Editar datos de {sel}", expanded=False):
                    # Ficha desde la tabla nueva (con fallback a sesión antigua).
                    _sess_cache = st.session_state.get("_sessions_cache", [])
                    info = storage.resolver_ficha(sel, _sess_cache)
                    if not info:
                        info = st.session_state.jugadores_info.get(sel, {})
                    cur_pos = st.session_state.posiciones.get(sel) or info.get("pos")
                    idx_pos = POSICION_CODIGOS.index(cur_pos) if cur_pos in POSICION_CODIGOS else 0
                    e1, e2 = st.columns(2)
                    edit_pos = e1.selectbox("Posición", POSICION_CODIGOS, index=idx_pos,
                                            format_func=lambda c: f"{c} · {POSICIONES[c]}", key=f"editpos_{sel}")
                    edit_edad = e2.number_input("Edad", 14, 50, int(info.get("edad", 23)), key=f"editedad_{sel}")
                    edit_equipo = st.text_input(
                        "Equipo principal (bandera)", info.get("equipo", ""),
                        key=f"editeq_{sel}",
                        help="Equipo de referencia del jugador (su selección). "
                             "Decide la bandera del dashboard y es el mismo en "
                             "todos los partidos.")
                    # Equipo EN ESTE PARTIDO: sale de la sesión abierta, no de la
                    # ficha global. Un jugador puede tener selección, sub-20 y club.
                    _eq_part_actual = (st.session_state.jugadores_info.get(sel, {})
                                       .get("equipo") or info.get("equipo", ""))
                    edit_equipo_part = st.text_input(
                        "Equipo en este partido", _eq_part_actual,
                        key=f"editeqp_{sel}",
                        help="Con qué equipo juega en ESTE partido. Se guarda "
                             "solo aquí: no modifica los partidos ya grabados.")
                    em1, em2 = st.columns(2)
                    edit_min_in = em1.number_input("Minuto de entrada", min_value=0,
                                                   value=int(info.get("min_in", 0)), key=f"editmin_in_{sel}",
                                                   help="0 si es titular.")
                    edit_min_out = em2.number_input("Minuto de salida", min_value=0,
                                                    value=int(info.get("min_out", 90)), key=f"editmin_out_{sel}")
                    if st.button("Guardar cambios", key=f"savej_{sel}", use_container_width=True):
                        st.session_state.posiciones[sel] = edit_pos
                        ficha_completa = dict(info)
                        ficha_completa.update({"pos": edit_pos, "edad": int(edit_edad),
                                               "equipo": edit_equipo.strip(),
                                               "min_in": int(edit_min_in), "min_out": int(edit_min_out)})
                        ficha_completa.pop("foto", None)
                        ficha_completa.pop("bandera", None)
                        storage.upsert_ficha_jugador(sel, ficha_completa)
                        st.session_state.jugadores_info[sel] = {
                            "pos": edit_pos,
                            "equipo": (edit_equipo_part.strip()
                                       or edit_equipo.strip()),
                            "edad": int(edit_edad),
                            "min_in": int(edit_min_in), "min_out": int(edit_min_out),
                        }
                        autosave()
                        st.rerun()
            else:
                st.info("Añade al menos un jugador para empezar.")
            st.divider()
        st.subheader("Cronómetro")

        @st.fragment(run_every="2s")
        def _crono_box():
            running = st.session_state.clock_start is not None
            estado = "En marcha" if running else "Detenido"
            st.metric("Tiempo de partido", fmt_minute(current_minute()),
                      delta=estado, delta_color="off")

        _crono_box()
        running = st.session_state.clock_start is not None
        cc1, cc2 = st.columns(2)
        if cc1.button("Iniciar" if not running else "Pausar", use_container_width=True, key="sc-clock-toggle"):
            if running: clock_pause()
            else: clock_start()
            st.rerun()
        if cc2.button("Reiniciar", use_container_width=True):
            clock_reset(); st.rerun()
        with st.expander("⚙ Ajustar minuto manualmente", expanded=False):
            st.caption("Por si tras una desconexión necesitas poner el cronómetro "
                       "en el minuto real del partido sin reiniciar.")
            aj1, aj2 = st.columns([2, 1])
            min_obj = aj1.number_input("Minuto", min_value=0,
                                       value=int(current_minute()), step=1, key="set-min")
            seg_obj = aj2.number_input("Seg", min_value=0, max_value=59, value=0, step=1, key="set-seg")
            if st.button("Fijar minuto", use_container_width=True, key="set-min-btn"):
                clock_set_minute(min_obj + seg_obj / 60.0)
                st.rerun()
        st.divider()
        with st.expander("Atajos de teclado", expanded=False):
            atajos = ("- **Z** — Deshacer\n"
                      "- **Espacio** — Iniciar/pausar cron\n"
                      "- **1-9** — Fijar zona (1=1er tercio izq · 2=centro · 3=der · "
                      "4-6=2º tercio · 7-9=3er tercio)\n")
            if not es_equipo:
                atajos += "- **← / →** — Jugador anterior/siguiente"
            st.markdown(atajos)

    # --- CABECERA ---
    mi = st.session_state.match_info
    titulo = f"{mi['equipo_local'] or 'Local'} {mi['goles_local']} - {mi['goles_visitante']} {mi['equipo_visitante'] or 'Visitante'}"
    running = st.session_state.clock_start is not None
    rec = ("<span class='rec-dot'></span>Grabando · " if running else "")
    modo_txt = "Registro de equipo" if es_equipo else "Scouting en vivo"
    st.markdown(f"<div class='hud-kicker'>{rec}{modo_txt} · {mi['competicion']}</div>", unsafe_allow_html=True)
    st.markdown(f"# {titulo}")

    # En modo EQUIPO, ofrecer dos pestañas dentro de la sesión: tagging y pizarra.
    if es_equipo:
        sub = st.radio("Vista", ["Tagging en vivo", "Pizarra táctica"],
                       horizontal=True, key="equipo_subview", label_visibility="collapsed")
        if sub == "Pizarra táctica":
            render_pizarra_sesion()
            return

    # --- BOTÓN PANTALLA DE TAGGING COMPACTA (solo jugadores) ---
    compacto = st.session_state.get("tag_compact", False)
    if not es_equipo:
        tcol1, tcol2 = st.columns([3, 1])
        with tcol2:
            if not compacto:
                if st.button("⛶ Pantalla de tagging", use_container_width=True, key="tag-full-on"):
                    st.session_state.tag_compact = True
                    st.rerun()
            else:
                if st.button("✕ Salir de pantalla completa", use_container_width=True,
                             key="tag-full-off", type="primary"):
                    st.session_state.tag_compact = False
                    st.rerun()

    if compacto and not es_equipo:
        # CSS: colapsar sidebar, compactar paddings, maximizar zona de tagging.
        st.markdown("""
        <style>
          section[data-testid="stSidebar"] { display: none !important; }
          div[data-testid="stAppViewContainer"] .main .block-container {
              padding-top: 1rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }
          .compact-hide { display: none !important; }
        </style>
        <div class="compact-tag">
        """, unsafe_allow_html=True)
        # Barra superior compacta: cronómetro + controles, todo en una fila
        running = st.session_state.clock_start is not None
        b = st.columns([1.4, 1, 1, 1])
        with b[0]:
            @st.fragment(run_every="2s")
            def _crono_compact():
                st.markdown(f"<div style='font-size:1.5rem;font-weight:800;color:var(--txt-hi)'>"
                            f"⏱ {fmt_minute(current_minute())}</div>", unsafe_allow_html=True)
            _crono_compact()
        if b[1].button("Pausar" if running else "Iniciar", use_container_width=True, key="cmp-clock-toggle"):
            (clock_pause() if running else clock_start()); st.rerun()
        if b[2].button("Reiniciar", use_container_width=True, key="cmp-reset"):
            clock_reset(); st.rerun()
        if b[3].button("Deshacer (Z)", use_container_width=True, key="sc-undo"):
            undo_last(); st.rerun()

    # --- CHIPS DE JUGADOR (solo en modo jugadores) ---
    if not es_equipo and st.session_state.players:
        st.markdown("<div class='chips-label'>Jugador activo</div>", unsafe_allow_html=True)
        chip_cols = st.columns(min(len(st.session_state.players), 6) + 1)
        idx_actual = (st.session_state.players.index(st.session_state.active_player)
                      if st.session_state.active_player in st.session_state.players else 0)
        for i, jugador in enumerate(st.session_state.players[:6]):
            is_active = (jugador == st.session_state.active_player)
            with chip_cols[i]:
                if st.button(jugador, key=f"sc-player-pick-{i}--{jugador}", use_container_width=True,
                             type=("primary" if is_active else "secondary")):
                    st.session_state.active_player = jugador
                    st.rerun()
        nav = chip_cols[-1]
        with nav:
            sub_a, sub_b = st.columns(2)
            if sub_a.button("‹", key="sc-player-prev", use_container_width=True, help="Jugador anterior"):
                if st.session_state.players:
                    st.session_state.active_player = st.session_state.players[(idx_actual-1) % len(st.session_state.players)]
                    st.rerun()
            if sub_b.button("›", key="sc-player-next", use_container_width=True, help="Jugador siguiente"):
                if st.session_state.players:
                    st.session_state.active_player = st.session_state.players[(idx_actual+1) % len(st.session_state.players)]
                    st.rerun()

    if not compacto:
        bar1, bar2 = st.columns([3, 1])
        with bar1:
            if es_equipo:
                st.success(f"Registrando: {mi['equipo_local'] or 'Equipo'}  ·  minuto {fmt_minute(current_minute())}")
            elif st.session_state.active_player:
                st.success(f"Jugador: {st.session_state.active_player}  ·  minuto {fmt_minute(current_minute())}")
            else:
                st.warning("Sin jugador asignado — añádelo en el panel lateral.")
        with bar2:
            if st.button("Deshacer (Z)", use_container_width=True, key="sc-undo"):
                undo_last(); st.rerun()

    # --- SELECTOR DE ZONA: REJILLA 3x3 ---
    st.markdown("<div class='chips-label'>Zona del campo (rejilla 3×3) — pulsa la celda donde ocurre la acción</div>",
                unsafe_allow_html=True)
    zcol_field, zcol_hint = st.columns([2, 1])
    with zcol_field:
        # 3 filas (bandas) x 3 columnas (tercios). El ataque va de izq->der.
        for yi in range(3):
            row = st.columns(3)
            for xi in range(3):
                is_active = (st.session_state.zona_x == xi and st.session_state.zona_y == yi)
                lab = f"{ZONA_COLS[xi].split()[0]}·{ZONA_ROWS[yi].split()[-1][:3]}"
                if row[xi].button(lab, key=f"zona-{xi}-{yi}", use_container_width=True,
                                  type=("primary" if is_active else "secondary")):
                    st.session_state.zona_x = xi
                    st.session_state.zona_y = yi
                    st.rerun()
    with zcol_hint:
        st.info(f"Zona activa:\n\n**{zona_label(st.session_state.zona_x, st.session_state.zona_y)}**\n\n"
                "Izquierda = tu defensa · Derecha = ataque")

    st.caption("El minuto y la zona se sellan al pulsar cada acción.")

    # --- PANEL DE ACCIONES ---
    # El resultado se indica por COLOR: verde=OK, rojo=Fallo, amarillo=Gol.
    # El texto del botón se reduce a un icono breve para tagueo rápido.
    ICONO_RES = {"ok": "✓", "bad": "✕", "gol": "GOL", "sprint": "⚡"}

    def render_action(action, results, compact=False):
        n = len(results)
        if compact:
            # Nombre estrecho y botones pegados, para que quepa todo.
            name_w = 2.4 if n <= 2 else 2.0
            cols = st.columns([name_w] + [0.9] * n)
        else:
            name_w = 3.0 if n <= 2 else 2.2
            cols = st.columns([name_w] + [1.2] * n)
        cols[0].markdown(f"<div class='action-name'>{action}</div>", unsafe_allow_html=True)
        for i, (label, code, kind) in enumerate(results):
            txt = ICONO_RES.get(kind, label)
            tip = code if code not in ("—",) else label  # ayuda con el significado real
            if cols[i + 1].button(txt, key=f"res-{kind}--{action}--{code}",
                                  use_container_width=True, help=tip):
                add_event(action, code); st.rerun()

    def render_block(title, actions, compact=False):
        st.markdown(f"<div class='block-head'>{title}</div>", unsafe_allow_html=True)
        for action, results in actions:
            render_action(action, results, compact=compact)

    panel_activo = PANELES[st.session_state.reg_tipo]
    distribucion = DISTRIBUCION[st.session_state.reg_tipo]

    if compacto:
        # 2 columnas anchas; las categorías se reparten equilibradas entre ellas.
        # Cada categoría es un bloque separado. Nombre completo a la izquierda,
        # Cada categoría en su CAJA con borde, en filas de 4 para aprovechar
        # el ancho. Nombre de acción a la izquierda y botones ✓/✕ a la derecha.
        categorias = list(panel_activo.keys())
        por_fila = 4
        for inicio in range(0, len(categorias), por_fila):
            fila = categorias[inicio:inicio + por_fila]
            cols = st.columns(por_fila)
            for col, nombre in zip(cols, fila):
                with col:
                    with st.container(border=True):
                        render_block(nombre, panel_activo[nombre], compact=True)
    else:
        col_izq, col_der = st.columns(2)
        with col_izq:
            for nombre in distribucion["izq"]:
                render_block(nombre, panel_activo[nombre]); st.markdown("")
        with col_der:
            for nombre in distribucion["der"]:
                render_block(nombre, panel_activo[nombre]); st.markdown("")

    # --- TIMELINE / RESUMEN / NOTAS ---
    if compacto:
        # Vista compacta: solo un timeline fino y el cierre del contenedor.
        if st.session_state.events:
            svg = timeline_svg(st.session_state.events, w=1000)
            n_players = len(set(e["jugador"] for e in st.session_state.events))
            tl_h = 50 + 28 * max(n_players, 1)
            st_html(f"<div style='font-family:sans-serif;width:100%;overflow-x:auto;'>{svg}</div>",
                    height=tl_h + 12, scrolling=False)
        st.markdown("</div>", unsafe_allow_html=True)  # cierra .compact-tag
        return

    # --- TIMELINE (en expander: no se redibuja en cada toque, mejora rendimiento) ---
    st.divider()
    if st.session_state.events:
        with st.expander("📊 Timeline del partido", expanded=False):
            st.markdown("<div class='session-sub'>Cada barra es una acción, situada en su minuto. "
                        "Verde = éxito · Rojo = fallo · Dorado = gol.</div>",
                        unsafe_allow_html=True)
            svg = timeline_svg(st.session_state.events, w=1000)
            n_players = len(set(e["jugador"] for e in st.session_state.events))
            tl_h = 64 + 30 * max(n_players, 1) + 30
            st_html(f"<div style='font-family:sans-serif;width:100%;overflow-x:auto;'>{svg}</div>",
                    height=tl_h + 16, scrolling=False)

        with st.expander("Ver registro cronológico en tabla", expanded=False):
            df = pd.DataFrame(st.session_state.events)
            jugadores_con_eventos = sorted(df["jugador"].unique())
            filtro = st.multiselect("Filtrar por jugador", jugadores_con_eventos, default=jugadores_con_eventos)
            df_f = df[df["jugador"].isin(filtro)] if filtro else df
            orden = "minuto" if "minuto" in df_f.columns else "minuto_fmt"
            df_f = df_f.sort_values(orden)
            tabla_reg = df_f[["minuto_fmt", "jugador", "accion", "resultado", "zona"]].rename(
                columns={"minuto_fmt": "Minuto", "jugador": "Jugador", "accion": "Acción",
                         "resultado": "Resultado", "zona": "Zona"})
            tabla_html(tabla_reg, height=300)
    else:
        st.info("Todavía no has registrado ninguna acción. Pulsa los botones del panel para empezar.")

    # --- NOTAS + EXPORTACIÓN ---
    st.divider()
    st.subheader("Notas y exportación")
    notas_old = st.session_state.final_notes
    st.session_state.final_notes = st.text_area(
        "Notas finales del partido", st.session_state.final_notes,
        placeholder="Ej: El 10 baja mucho a recibir, buen primer toque...", height=110)
    if st.session_state.final_notes != notas_old:
        autosave()

    def build_csv():
        output = io.StringIO()
        mi = st.session_state.match_info
        notes_clean = st.session_state.final_notes.replace('\n', ' ').strip()
        match_cols = {
            "competicion": mi["competicion"], "fecha": mi["fecha"],
            "equipo_local": mi["equipo_local"], "equipo_visitante": mi["equipo_visitante"],
            "goles_local": mi["goles_local"], "goles_visitante": mi["goles_visitante"],
            "posesion_local_pct": mi["posesion_local"], "posesion_visitante_pct": 100 - mi["posesion_local"],
            "notas_partido": notes_clean,
        }
        col_order = list(match_cols.keys()) + ["minuto", "minuto_decimal", "jugador",
                                               "accion", "resultado", "zona", "zona_x", "zona_y", "hora_real"]
        if st.session_state.events:
            df = pd.DataFrame(st.session_state.events)
            df = df.rename(columns={"minuto_fmt": "minuto", "minuto": "minuto_decimal", "timestamp": "hora_real"})
            for col, val in match_cols.items():
                df[col] = val
            # Garantizar que existen todas las columnas esperadas (datos antiguos
            # pueden no tener zona_x/zona_y/hora_real)
            for c in col_order:
                if c not in df.columns:
                    df[c] = ""
            df = df[col_order]
            df.to_csv(output, index=False)
        else:
            df = pd.DataFrame([{**match_cols, "minuto": "", "minuto_decimal": "", "jugador": "",
                                "accion": "", "resultado": "", "zona": "", "zona_x": "", "zona_y": "",
                                "hora_real": ""}])[col_order]
            df.to_csv(output, index=False)
        return output.getvalue().encode("utf-8-sig")

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
    nombre_archivo = f"scouting_{mi['equipo_local'] or 'partido'}_{fecha_str}.csv".replace(" ", "_")
    st.download_button("Exportar datos a CSV", data=build_csv(), file_name=nombre_archivo,
                       mime="text/csv", use_container_width=True, type="primary")
    st.caption(f"Se exportarán {len(st.session_state.events)} acciones con su zona de rejilla (zona_x, zona_y).")


# ============================================================================
# SECCIÓN: GRÁFICOS — radar comparativo, campo por tercios, mapa de calor
# ============================================================================
@st.cache_data(ttl=300)
def _load_all_flat(tipo=None):
    """Carga las sesiones (del tipo indicado) y las aplana.
    Cacheado 5 min para no releer toda la BD constantemente (mejora rendimiento).
    Tras guardar cambios se llama a st.cache_data.clear() para refrescar al instante."""
    sessions = storage.load_all_sessions(tipo=tipo)
    # Equipo PRINCIPAL de cada jugador (tabla 'jugadores'). Solo se usa como
    # fallback de `equipo_jugador` en sesiones antiguas que no lo traigan; el
    # equipo de cada partido manda siempre.
    principales = {f.get("nombre", ""): f.get("equipo", "") or ""
                   for f in storage.list_jugadores() if f.get("nombre")}
    return sessions, analytics.flatten_events(sessions, principales)


def _selector_cat_accion(df, key, jugadores=None, posicion=None, label="Métrica",
                         incluir_todas=False):
    """Selector reutilizable Categoría/Acción con checks.
    Devuelve (lista_acciones_seleccionadas, etiqueta_legible).
    Si incluir_todas=True, añade una opción 'Todas' (por defecto) que no filtra:
    devuelve todas las acciones presentes."""
    mapa = analytics.acciones_por_categoria(df, jugadores=jugadores, posicion=posicion)
    if not mapa:
        st.info("No hay acciones para los filtros actuales.")
        return [], ""
    todas_accs = sorted({a for accs in mapa.values() for a in accs})
    opciones = (["Todas", "Categoría", "Acción concreta"] if incluir_todas
                else ["Categoría", "Acción concreta"])
    modo = st.radio(f"{label}: filtrar por", opciones, horizontal=True, key=f"{key}-modo")
    if modo == "Todas":
        return todas_accs, "Todas las acciones"
    if modo == "Categoría":
        cat = st.selectbox("Categoría", list(mapa.keys()), key=f"{key}-cat")
        accs_cat = mapa.get(cat, [])
        with st.expander(f"Acciones incluidas en «{cat}» ({len(accs_cat)})", expanded=False):
            seleccion = [a for a in accs_cat
                         if st.checkbox(a, value=True, key=f"{key}-chk-{a}")]
        if not seleccion:
            st.warning("Marca al menos una acción.")
        return seleccion, cat
    else:
        acc = st.selectbox("Acción", todas_accs, key=f"{key}-acc")
        return [acc], acc


def render_graficos():
    st.markdown("<div class='hud-kicker'>Análisis · gráficos</div>", unsafe_allow_html=True)
    st.markdown("# Gráficos y comparativas")
    st.caption("Analiza los datos de los jugadores scouteados.")

    if st.button("↻ Recargar datos", key="reload-graf"):
        st.cache_data.clear(); st.rerun()

    _graficos_jugadores()






def _graficos_jugadores():
    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. "
                "Ve a **Registro jugadores**, crea una sesión y registra acciones.")
        return

    # ---------- Controles del dashboard en el PANEL LATERAL ----------
    jugadores = sorted(df["jugador"].unique())
    with st.sidebar:
        st.markdown("### Dashboard")
        jugador = st.selectbox("Jugador", jugadores, key="dash-jug")
        # Equipos y posiciones del jugador, calculados sobre el df SIN FILTRAR:
        # son su identidad (van al hero enteros) y la base del filtro de equipo.
        equipos_jug = analytics.equipos_de_jugador(df, jugador)
        posiciones_jug = analytics.posiciones_de_jugador(df, jugador)
        # Posición MÁS FRECUENTE: solo para sugerir el set de métricas, que
        # necesita una sola. El hero las enseña todas.
        pos_jug = posiciones_jug[0][0] if posiciones_jug else ""
        # Filtro de equipo. Por defecto "Todos" -> los datos salen unidos, que
        # es el comportamiento que se quiere de base.
        eq_opts = {"Todos los equipos": None}
        for _eq, _n in equipos_jug:
            eq_opts[f"{_eq} ({_n})"] = _eq
        equipo_lbl = st.selectbox(
            "Equipo", list(eq_opts.keys()), key="dash-equipo",
            help="Filtra los partidos por el equipo con el que jugó. "
                 "'Todos' junta selección, categorías inferiores y club.")
        equipo_sel = eq_opts.get(equipo_lbl)
        # A partir de aquí, `d_jug` ya respeta el equipo elegido para que el
        # selector de partido no ofrezca partidos de otro equipo.
        d_jug = df[df["jugador"] == jugador]
        if equipo_sel is not None:
            d_jug = d_jug[d_jug["equipo_jugador"] == equipo_sel]
        set_keys = list(analytics.SETS_POSICION.keys())
        sugerido = _sugerir_set(pos_jug, set_keys)
        set_pos = st.selectbox("Set de métricas (posición)", set_keys,
                               index=set_keys.index(sugerido), key="dash-set")
        modo_lbl = st.radio("Valores de las tarjetas",
                            ["Total", "Aciertos", "Total /90", "Aciertos /90"],
                            key="dash-modo")
        # Filtro por partido: solo los partidos que ha jugado el jugador
        # seleccionado. Sustituye al antiguo filtro de 1ª/2ª parte.
        part_items = []  # (fecha, label, session_id)
        for sid, g in d_jug.groupby("session_id"):
            rival = analytics._rival_partido(g) or str(g["sesion"].iloc[0])
            fecha = str(g["fecha"].iloc[0]) if "fecha" in g.columns else ""
            lbl = f"{rival}" + (f" · {fecha}" if fecha else "")
            part_items.append((fecha, lbl, sid))
        part_items.sort(key=lambda t: t[0])
        part_opts = {"Todos los partidos": None}
        for _f, lbl, sid in part_items:
            # Evita colisión de etiquetas idénticas (mismo rival, misma fecha)
            key_lbl = lbl if lbl not in part_opts else f"{lbl} ({sid[:4]})"
            part_opts[key_lbl] = sid
        partido_lbl = st.selectbox("Partido", list(part_opts.keys()),
                                   key="dash-partido")
        # Filtro de contexto: comparar nivel propio vs rival de cada partido.
        ctx_lbl = st.radio("Nivel del rival (vs tu equipo)",
                           ["Todos", "Rival superior", "Rival similar", "Rival inferior"],
                           key="dash-ctx",
                           help="Filtra los partidos según si el rival era de nivel "
                                "superior, similar o inferior al equipo propio.")

    modo = {"Total": "total", "Aciertos": "aciertos",
            "Total /90": "total90", "Aciertos /90": "aciertos90"}[modo_lbl]
    partido_sid = part_opts.get(partido_lbl)
    ctx = {"Todos": "todos", "Rival superior": "superior",
           "Rival similar": "similar", "Rival inferior": "inferior"}[ctx_lbl]

    # Filtro de EQUIPO. Va el PRIMERO de todos para que arrastre a todo lo que
    # viene después (tarjetas, radar, mapas, nota, influencia, evolución y
    # similitud). Se filtra por session_id y no por la columna `equipo_jugador`
    # para que las sesiones se queden enteras: los gráficos que comparan con
    # otros jugadores necesitan el resto de filas de ese partido.
    if equipo_sel is not None:
        sids_eq = set(df[(df["jugador"] == jugador)
                         & (df["equipo_jugador"] == equipo_sel)]["session_id"].unique())
        df = df[df["session_id"].isin(sids_eq)]
        if df.empty:
            st.warning(f"No hay acciones de {jugador} con {equipo_sel}.")
            return

    # Filtrar por contexto de rival. El conteo es de los partidos DEL JUGADOR
    # seleccionado que cumplen el contexto, no del total de la base de datos.
    if ctx != "todos":
        sesiones_ctx = analytics.filtrar_sesiones_por_contexto(sessions, ctx)
        ids_ctx = {s.get("id") for s in sesiones_ctx}
        # partidos de ESTE jugador dentro de ese contexto
        sids_jugador = set(df[df["jugador"] == jugador]["session_id"].unique())
        ids_jug_ctx = ids_ctx & sids_jugador
        n_part = len(ids_jug_ctx)
        st.info(f"Filtro de contexto: **{ctx_lbl}** → {jugador} jugó "
                f"{n_part} partido(s) así. "
                + ("Muestra muy pequeña, resultado orientativo." if 0 < n_part <= 2 else ""))
        df = df[df["session_id"].isin(ids_ctx)]
        if df[df["jugador"] == jugador].empty:
            st.warning(f"{jugador} no tiene partidos con rival {ctx_lbl.lower()}.")
            return
    # Filtro por partido concreto (si no es "Todos los partidos").
    if partido_sid is not None:
        df = df[df["session_id"] == partido_sid]
        if df[df["jugador"] == jugador].empty:
            st.warning("No hay acciones de ese jugador en el partido seleccionado.")
            return

    mins_jug = analytics.minutos_de_jugador(df, jugador)

    # ---------- CABECERA VISUAL del jugador (bandera de fondo + foto + datos) ----------
    # Ficha del jugador (posición, equipo, edad, minutos) desde la tabla nueva.
    info = storage.resolver_ficha(jugador, sessions)
    # BANDERA: siempre la del equipo PRINCIPAL de la ficha (la selección), pase
    # lo que pase con el filtro. Así no hay que subir escudos de club al bucket
    # y la cabecera no cambia de fondo al filtrar.
    equipo_principal = info.get("equipo", "")
    edad = info.get("edad", "")
    # Fotos del bucket público. Se resuelve en el servidor cuál extensión existe
    # (.PNG / .png / .jpg...), cacheado. Si no hay foto, hueco limpio.
    foto_url = storage.url_foto_jugador(jugador).get("url", "")
    bandera_url = storage.url_bandera(equipo_principal).get("url", "")
    foto_html = (f"<img src='{foto_url}' class='dash-hero-foto' alt=''/>"
                 if foto_url else "<div class='dash-hero-foto-ph'>Sin foto</div>")
    bandera_img = (f"<img src='{bandera_url}' class='dash-hero-bg' alt=''/>"
                   if bandera_url else "")
    edad_txt = f" · {edad} años" if edad else ""
    # EQUIPOS y POSICIONES: SIEMPRE todos, con filtro o sin él. El hero es la
    # identidad del jugador (dónde y de qué ha jugado), no la selección de datos
    # que se está mirando. Por eso las listas vienen del df sin filtrar.
    equipos_txt = " · ".join(e for e, _ in equipos_jug) or equipo_principal
    equipos_txt = f" · {equipos_txt}" if equipos_txt else ""
    pos_txt = " · ".join(p for p, _ in posiciones_jug) or (pos_jug or "—")
    # NOTA (examen, Fase 2): media SIMPLE de las notas por partido (cada partido
    # pesa igual, no acumula sobre el pool). df ya filtrado por partido/contexto.
    nota_res = analytics.nota_media_jugador(df, jugador)
    nv = nota_res.get("nota")
    nota_col = _color_nota(nv)
    nota_txt = "n/d" if nv is None else f"{nv:.1f}"
    # Aviso de fiabilidad en tooltip (no en texto fijo): pocos partidos o pocas acc.
    np_ = nota_res["n_partidos"]
    fiab_title = ("Sin acciones que puntúen" if nv is None
                  else (f"Media de {np_} partido{'s' if np_ != 1 else ''}"
                        + (" · muestra baja" if np_ < 3 else "")))
    nota_html = (
        f"<div title='{fiab_title}' style='position:absolute;top:50%;right:26px;"
        f"transform:translateY(-50%);z-index:3;width:78px;height:78px;border-radius:50%;"
        f"display:flex;align-items:center;justify-content:center;"
        f"background:rgba(0,0,0,.45);border:3px solid {nota_col};"
        f"box-shadow:0 0 18px {nota_col}66, inset 0 0 12px rgba(0,0,0,.5);'>"
        f"<span style='font-size:32px;line-height:1;font-weight:900;color:{nota_col};"
        f"text-shadow:0 0 10px {nota_col}66;'>{nota_txt}</span>"
        f"</div>")
    st.markdown(
        f"<div class='dash-hero'>"
        f"  {bandera_img}"
        f"  <div class='dash-hero-overlay'></div>"
        f"  {foto_html}"
        f"  <div class='dash-hero-info'>"
        f"    <div class='dash-hero-name'>{jugador}</div>"
        f"    <div class='dash-hero-meta'>{pos_txt}{equipos_txt}{edad_txt} · {mins_jug} min</div>"
        f"    <div class='dash-hero-tag'>Set: {set_pos} · {modo_lbl}"
        f"{f' · Filtro: {equipo_sel}' if equipo_sel else ''}</div>"
        f"  </div>"
        f"  {nota_html}"
        f"</div>", unsafe_allow_html=True)

    # ---------- 8 TARJETAS DE MÉTRICAS ----------
    claves = analytics.SETS_POSICION[set_pos]
    filas = [claves[:4], claves[4:8]]
    for fila in filas:
        cols = st.columns(4)
        for col, key in zip(cols, fila):
            spec = analytics.METRICAS_DASH[key]
            es_pct = spec.get("especial") == "pct_pase"
            val = analytics.metrica_dashboard(df, jugador, key, modo)
            # Valor secundario entre paréntesis: los aciertos en el mismo "marco"
            # que el modo activo. En modo Total -> aciertos totales; en Total/90
            # -> aciertos/90. En los modos de aciertos no hay secundario.
            sec_txt = ""
            if not es_pct:
                if modo == "total":
                    ac = analytics.metrica_dashboard(df, jugador, key, "aciertos")
                    sec_txt = f" <span class='dash-card-sec'>({ac})</span>"
                elif modo == "total90":
                    ac90 = analytics.metrica_dashboard(df, jugador, key, "aciertos90")
                    sec_txt = f" <span class='dash-card-sec'>({ac90})</span>"
            val_txt = f"{val}%" if es_pct else f"{val}"
            with col:
                st.markdown(
                    f"<div class='dash-card'>"
                    f"<div class='dash-card-val'>{val_txt}{sec_txt}</div>"
                    f"<div class='dash-card-lbl'>{spec['label']}</div>"
                    f"</div>", unsafe_allow_html=True)

    st.divider()

    # ---------- GRÁFICOS DEL DASHBOARD ----------
    # --- Radar (comparar contra un jugador a elegir, ejes configurables) ---
    st.markdown("#### Radar comparativo")
    otros = ["(ninguno)"] + [j for j in jugadores if j != jugador]
    j_comp = st.selectbox("Comparar contra", otros, key="dash-radar-comp")
    eje_modo = st.radio("Ejes del radar", ["Categorías", "Acciones concretas"],
                        horizontal=True, key="dash-radar-ejemodo")
    mapa = analytics.acciones_por_categoria(df)
    if eje_modo == "Categorías":
        disp = [c for c in analytics.CATEGORIAS if c in mapa and c != "Otros"]
        ejes = st.multiselect("Categorías a mostrar (3-8)", disp,
                              default=disp[:6], key="dash-radar-ejes-cat")
    else:
        todas = sorted({a for accs in mapa.values() for a in accs})
        ejes = st.multiselect("Acciones a mostrar (3-8)", todas,
                              default=todas[:6], key="dash-radar-ejes-acc")
    if len(ejes) < 3:
        st.info("Elige al menos 3 ejes para el radar.")
    else:
        ejes = ejes[:8]
        modo_radar = "totales" if modo in ("total", "total90") else "aciertos"
        series = []
        labels, v1 = analytics.radar_ejes_seleccion(df, jugador, ejes, modo_radar)
        series.append({"name": jugador, "values": v1, "color": NEON_SKY})
        if j_comp != "(ninguno)":
            _, v2 = analytics.radar_ejes_seleccion(df, j_comp, ejes, modo_radar)
            series.append({"name": j_comp, "values": v2, "color": NEON_GOLD})
        svg = radar_svg(labels, series)
        render_svg(svg, height=440)
        for s in series:
            st.markdown(f"<span style='color:{s['color']};font-weight:800'>● {s['name']}</span>",
                        unsafe_allow_html=True)

    g3, g4 = st.columns(2)

    # --- Mapa de calor ---
    with g3:
        st.markdown("#### Mapa de calor")
        grid = analytics.zone_grid_counts(df[df["jugador"] == jugador])
        svg = heatmap_svg(grid)
        render_svg(svg, height=360)

    # --- Mapa de acciones (campo por tercios) ---
    with g4:
        st.markdown("#### Mapa de acciones (por tercios)")
        grid = analytics.zone_grid_counts(df[df["jugador"] == jugador])
        factor = 1.0
        if modo in ("total90", "aciertos90") and mins_jug:
            factor = 90.0 / mins_jug
        sufijo = "por 90 min" if modo in ("total90", "aciertos90") else "totales"
        svg = pitch_thirds_svg(grid * factor, title=f"Acciones · {sufijo}")
        render_svg(svg, height=360)

    # --- Influencia por minuto (volumen + eficiencia, hasta 3 jugadores) ---
    st.markdown("#### Influencia por minuto")
    st.caption("Cuánto participa y con qué eficacia el jugador en cada franja de 15'. "
               "Los símbolos marcan acciones de peligro (gol, tiro a puerta, pase clave).")
    inf_comp = st.multiselect("Comparar con (hasta 2 jugadores más)",
                              [j for j in jugadores if j != jugador],
                              max_selections=2, key="dash-inf-comp")
    colores_inf = [NEON_SKY, NEON_GOLD, "#a855f7"]
    jugs_inf = [jugador] + inf_comp
    datos_inf = []
    for idx, jug in enumerate(jugs_inf):
        datos_inf.append({"name": jug, "color": colores_inf[idx % 3],
                          "data": analytics.influencia_por_minuto(df, jug)})
    if any(sum(d["data"]["volumen"]) > 0 for d in datos_inf):
        svg = influencia_svg(datos_inf, f"Influencia — {' vs '.join(jugs_inf)}")
        render_svg(svg, height=610)
        for d in datos_inf:
            st.markdown(f"<span style='color:{d['color']};font-weight:800'>● {d['name']}</span>",
                        unsafe_allow_html=True)
    else:
        st.info("Sin acciones para mostrar la influencia por minuto.")

    # --- Evolución (a lo ancho, hasta 3 jugadores) ---
    st.markdown("#### Evolución partido a partido")
    accs, etq = _selector_cat_accion(df, "dash-evolsel", label="Métrica de evolución")
    comp3 = st.multiselect("Comparar con (hasta 2 jugadores más)",
                           [j for j in jugadores if j != jugador],
                           max_selections=2, key="dash-evol-comp")
    if accs:
        modo_ev = "totales" if modo in ("total", "total90") else "aciertos"
        colores = [NEON_SKY, NEON_GOLD, "#a855f7"]
        jugs_evol = [jugador] + comp3
        series = []
        for idx, jug in enumerate(jugs_evol):
            serie = analytics.serie_temporal(df, jug, accs, modo_ev)
            if serie:
                series.append({"name": jug, "color": colores[idx % 3],
                               "puntos": [{"rival": p["rival"], "valor": p["valor"]} for p in serie]})
        if not series or all(len(s["puntos"]) < 2 for s in series):
            st.info("Necesitas al menos 2 partidos para ver evolución.")
        else:
            svg = linea_temporal_svg(series, f"{etq}", modo_ev)
            render_svg(svg, height=340)
            for s in series:
                st.markdown(f"<span style='color:{s['color']};font-weight:800'>● {s['name']}</span>",
                            unsafe_allow_html=True)

    # --- Evolución de la NOTA (examen partido a partido) ---
    st.markdown("#### Evolución de la nota")
    st.caption("Nota 0-10 por partido (valor acumulado: impacto de las acciones, "
               "no % de acierto). Color por banda: rojo <5, naranja 5-7, "
               "amarillo 7-9, verde ≥9. Respeta partido y contexto activos.")
    colores_n = [NEON_SKY, NEON_GOLD, "#a855f7"]
    jugs_nota = [jugador] + comp3
    series_n = []
    for idx, jug in enumerate(jugs_nota):
        serie = analytics.serie_nota_por_partido(df, jug)
        if serie:
            series_n.append({"name": jug, "color": colores_n[idx % 3],
                             "puntos": [{"rival": p["rival"], "valor": p["valor"]} for p in serie]})
    if not series_n:
        st.info("Aún no hay partidos con acciones que puntúen para la nota.")
    else:
        svg = barras_nota_svg(series_n, "Nota (0-10)")
        render_svg(svg, height=340)
        for s in series_n:
            st.markdown(f"<span style='color:{s['color']};font-weight:800'>● {s['name']}</span>",
                        unsafe_allow_html=True)

    # ---------- SIMILITUD CON JUGADORES TOP (Nivel 1) ----------
    st.divider()
    st.markdown("#### ¿A qué jugador top se parece?")
    st.caption("Compara el perfil por-90 del jugador contra una base de jugadores "
               "élite de su posición (similitud coseno tras estandarizar). "
               "Con pocos partidos el resultado es orientativo.")
    import similitud
    pos_csv_sug = similitud.MAPA_POS_CSV.get((pos_jug or "").upper(), "")
    try:
        pos_disponibles = similitud.posiciones_csv()
    except Exception as e:
        pos_disponibles = []
        st.error(f"No se pudo leer la base de tops: {e}")
    if not pos_disponibles:
        st.warning("No se encuentra la base de jugadores top (CSV_TOPS.csv). "
                   "Verifica que el archivo está en el repo, junto a similitud.py.")
    else:
        idx = pos_disponibles.index(pos_csv_sug) if pos_csv_sug in pos_disponibles else 0
        pos_csv = st.selectbox("Comparar como (posición de referencia)",
                               pos_disponibles, index=idx, key="dash-sim-pos")
        if st.button("Calcular similitud", key="dash-sim-btn"):
            with st.spinner("Calculando perfil y comparando con los tops..."):
                vec = similitud.construir_vector(sessions, jugador)
                if "error" in vec:
                    st.error(vec["error"])
                else:
                    fiab = vec["muestra"]["fiabilidad"]
                    # Pool de la propia base, solo del mismo bloque de posición.
                    pool = [p for p in similitud.vectores_ojeados(sessions)
                            if similitud.MAPA_POS_CSV.get((p["posicion"] or "").upper()) == pos_csv]
                    res = similitud.similitud_nivel1(vec["vector"], pos_csv, jugador,
                                                     fiab, pool=pool)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        m = vec["muestra"]
                        st.caption(f"Muestra: {m['partidos']} partidos · {m['minutos_total']} min · "
                                   f"fiabilidad {fiab}")
                        if res.get("aviso"):
                            st.warning(res["aviso"])
                        st.markdown("**Jugadores top más parecidos:**")
                        for i, r in enumerate(res["ranking"], 1):
                            pct = int(round(r["similitud"] * 100))
                            st.markdown(
                                f"<div class='sim-row'>"
                                f"<span class='sim-rank'>{i}</span>"
                                f"<span class='sim-name'>{r['top']}</span>"
                                f"<span class='sim-team'>{r['equipo']}</span>"
                                f"<span class='sim-score'>{pct}%</span></div>",
                                unsafe_allow_html=True)

                        # --- Ranking contra la propia base (Fase 3) ---
                        st.markdown("**De tu base, quién cubre el mismo perfil:**")
                        if not res["ranking_ojeados"]:
                            st.caption(f"No hay otros jugadores tuyos en «{pos_csv}» con "
                                       f"muestra suficiente ({int(similitud.MIN_MINUTOS)}' mínimo).")
                        else:
                            for i, r in enumerate(res["ranking_ojeados"], 1):
                                pct = int(round(r["similitud"] * 100))
                                marca = (" <span class='sim-team'>· muestra justa</span>"
                                         if r["atenuado"] else "")
                                st.markdown(
                                    f"<div class='sim-row'>"
                                    f"<span class='sim-rank'>{i}</span>"
                                    f"<span class='sim-name'>{r['jugador']}</span>"
                                    f"<span class='sim-team'>{r['equipo']}</span>"
                                    f"<span class='sim-score'>{pct}%</span>{marca}</div>",
                                    unsafe_allow_html=True)

                        # --- Mapa de perfiles (PCA) ---
                        st.markdown("#### Mapa de perfiles")
                        mp = similitud.mapa_pca(pos_csv, pool, jugador, vec["vector"])
                        if "error" in mp:
                            st.info(mp["error"])
                        else:
                            v_tot = sum(mp["var_explicada"])
                            svg = mapa_perfiles_svg(mp, res["ranking_ojeados"][:3])
                            render_svg(svg, height=470)
                            st.caption(
                                f"Los 2 ejes conservan el {v_tot:.0%} del perfil: el mapa sitúa "
                                f"el barrio, pero en las distancias cortas reordena a los vecinos. "
                                f"Por eso los parecidos de verdad van con línea discontinua "
                                f"(coseno, las 28 métricas). **Si el mapa y las líneas no "
                                f"coinciden, manda la línea.**")

                        cda, cdb = st.columns(2)
                        with cda:
                            st.markdown("**Destaca en** (vs media de la posición):")
                            if res["destaca"]:
                                for f, z in res["destaca"]:
                                    st.markdown(f"<span style='color:{NEON_OK}'>▲ {f}</span> "
                                                f"<span style='color:{TXT_LO_SVG}'>(+{z})</span>",
                                                unsafe_allow_html=True)
                            else:
                                st.caption("Sin rasgos por encima de la media.")
                        with cdb:
                            st.markdown("**Flojea en:**")
                            if res["floja"]:
                                for f, z in res["floja"]:
                                    st.markdown(f"<span style='color:{NEON_BAD}'>▼ {f}</span> "
                                                f"<span style='color:{TXT_LO_SVG}'>({z})</span>",
                                                unsafe_allow_html=True)
                            else:
                                st.caption("Sin rasgos por debajo de la media.")
                        if res.get("features_excluidas"):
                            st.caption("Métricas fuera de la comparación (definición distinta "
                                       "a la de los tops, o sin dato en ellos): "
                                       + ", ".join(res["features_excluidas"]))


def _sugerir_set(posicion, set_keys):
    """Mapea la posición del jugador a uno de los sets del radar.
    Delega en analytics.set_de_posicion (fuente única); POR no tiene set en el
    spider, así que cae en 'MC/MCD' como hasta ahora."""
    k = analytics.set_de_posicion(posicion)
    return "MC/MCD" if k == "POR" else k


# ----------------------------------------------------------------------------
# GRÁFICOS · subapartado de EQUIPOS (solo sesiones de tipo equipo)
# ----------------------------------------------------------------------------
# ============================================================================
# SECCIÓN: PREDICCIONES — tendencias + ML
# ============================================================================
def tabla_expectativa_html(filas):
    """Tabla del resumen de expectativa. HTML propio (NO st.dataframe: pinta
    sobre canvas Glide y el CSS del tema no entra). Mismo idioma que .seq-*."""
    tercio_txt = {0: "1er tercio", 1: "2º tercio", 2: "3er tercio"}
    head = ("<div class='exp-head'>"
            "<span>Acción · Zona</span><span class='h-num'>Suyos</span>"
            "<span class='h-num'>% real</span><span class='h-num'>Predicción</span>"
            "<span class='h-num'>Esperado rol</span><span class='h-num'>Δ</span>"
            "<span>Lectura</span></div>")
    rows = ""
    for f in filas:
        signo = "pos" if f["diff_pts"] > 0 else ("neg" if f["diff_pts"] < 0 else "cero")
        et = {"destaca": "destaca", "en linea": "en línea", "por debajo": "por debajo"}[f["etiqueta"]]
        rows += (
            f"<div class='exp-row' data-et='{f['etiqueta']}'>"
            f"<span class='exp-acc'>{_esc(f['accion'])} <span class='exp-zona'>· {tercio_txt[f['tercio']]}</span></span>"
            f"<span class='exp-num'>{f['n_jugador']}</span>"
            f"<span class='exp-num'>{round(f['pct_real']*100)}%</span>"
            f"<span class='exp-num exp-strong'>{round(f['pred']*100)}%</span>"
            f"<span class='exp-num'>{round(f['expectativa_pos']*100)}% <span class='exp-npos'>({f['n_pos']})</span></span>"
            f"<span class='exp-delta' data-signo='{signo}'>{f['diff_pts']:+d}</span>"
            f"<span class='exp-pill' data-et='{f['etiqueta']}'>{et}</span></div>")
    return f"<div class='exp-tabla'>{head}{rows}</div>"


def render_predicciones():
    st.markdown("<div class='hud-kicker'>Análisis · predicción de acierto</div>", unsafe_allow_html=True)
    st.markdown("# Predicción de acierto")
    st.caption("Estima el % de acierto de un jugador en una acción y zona concretas. "
               "Con poca muestra propia, la predicción se apoya en lo esperado para su "
               "posición (suavizado); nunca inventa un 0% a partir de 3-4 intentos sueltos.")

    if st.button("↻ Recargar datos", key="reload-pred"):
        st.cache_data.clear(); st.rerun()

    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. El módulo necesita datos.")
        return

    agg = analytics.agregados_expectativa(df)
    pm = analytics.player_metrics(df)
    jugadores = pm["jugador"].tolist() if not pm.empty else []
    if not jugadores:
        st.info("No hay jugadores con acciones.")
        return

    # -------- PREDICTOR INTERACTIVO --------
    st.markdown("#### Predictor")
    c1, c2, c3 = st.columns(3)
    jugador = c1.selectbox("Jugador", jugadores, key="exp-jug")
    dju = df[df["jugador"] == jugador]
    acc_opts = sorted(dju[dju["intento"].astype(bool)]["accion"].dropna().unique().tolist())
    if not acc_opts:
        st.warning("Este jugador no tiene acciones con resultado de éxito/fallo.")
        return
    accion = c2.selectbox("Acción", acc_opts, key="exp-acc")
    tercio_lbl = {0: "1er tercio (defensa)", 1: "2º tercio (medio)", 2: "3er tercio (ataque)"}
    tercio = c3.selectbox("Zona", [0, 1, 2], format_func=lambda t: tercio_lbl[t], key="exp-ter")

    # posición más frecuente del jugador (para el set de comparación)
    posmodo = dju["posicion"].replace("", np.nan).dropna()
    posicion = posmodo.mode().iloc[0] if not posmodo.empty else ""
    out = analytics.predecir_acierto(agg, jugador, accion, tercio, posicion)

    pred_pct = round(out["pred"] * 100)
    exp_pct = round(out["expectativa_pos"] * 100)
    color = NEON_OK if pred_pct >= 65 else (NEON_ORANGE if pred_pct >= 40 else NEON_BAD)
    crudo = (f"{round(out['aciertos_jugador'] / out['n_jugador'] * 100)}% ({out['n_jugador']} intentos)"
             if out["n_jugador"] else "sin intentos propios en este combo")
    st.markdown(
        f"<div style='display:flex;gap:28px;align-items:baseline;margin:6px 0 2px'>"
        f"<div style='font-size:44px;font-weight:800;color:{color}'>{pred_pct}%</div>"
        f"<div style='color:{INK};opacity:.85'>predicción de acierto</div></div>",
        unsafe_allow_html=True)
    st.caption(f"Su dato: {crudo}  ·  Expectativa de su posición ({out['set']}): "
               f"{exp_pct}% ({out['n_pos']} casos del grupo).")
    if out["n_jugador"] < 3:
        st.caption("⚠ Muestra propia mínima: la predicción se apoya casi toda en la "
                   "expectativa de su posición. Gana peso a medida que tagees más acciones suyas.")

    st.divider()

    # -------- RESUMEN DEL JUGADOR (cierre de scouting) --------
    st.markdown("#### Dónde destaca o floja respecto a su rol")
    filas = analytics.resumen_expectativa_jugador(df, agg, jugador)
    if not filas:
        st.info("Este jugador no tiene aún combos acción+zona con muestra suficiente "
                f"({analytics._EXP_CFG['min_muestra_resumen']}+ intentos) para el resumen.")
    else:
        st.markdown(tabla_expectativa_html(filas), unsafe_allow_html=True)
        st.caption("Predicción del jugador frente a lo esperado para su posición. La etiqueta "
                   "usa la predicción suavizada, no el % crudo, para no señalar ruido de muestra baja.")


# ============================================================================
# PIZARRA TÁCTICA (dentro de una sesión de equipo abierta)
# ============================================================================
def _pizarra_key(formacion, fase):
    return f"{formacion}__{fase}"


def render_pizarra_sesion():
    """Pizarra de la sesión de equipo ABIERTA (usa st.session_state, sin selector
    de sesión). Arrastre real con un componente HTML/JS embebido; al soltar una
    ficha, el componente sincroniza las posiciones con Python vía un input oculto."""
    st.caption("Coloca las fichas arrastrándolas con el ratón. Cada fase guarda su "
               "propia disposición dentro de esta sesión de equipo.")

    col_fases, col_campo, col_cfg = st.columns([1, 2.6, 1.2])

    with col_fases:
        st.markdown("##### Fases")
        if "piz_fase" not in st.session_state:
            st.session_state.piz_fase = FASES[0]
        for fase in FASES:
            activa = (st.session_state.piz_fase == fase)
            if st.button(fase, key=f"piz-fase-{fase}", use_container_width=True,
                         type=("primary" if activa else "secondary")):
                st.session_state.piz_fase = fase
                st.rerun()

    fase = st.session_state.piz_fase

    with col_cfg:
        st.markdown("##### Configuración")
        formacion = st.selectbox("Formación base", list(FORMACIONES.keys()), key="piz-form")
        clave = _pizarra_key(formacion, fase)
        if st.button("Restablecer formación", use_container_width=True, key="piz-reset"):
            st.session_state.pizarras[clave] = formacion_a_fichas(formacion, fase)
            autosave()
            st.rerun()
        st.markdown(f"<div class='session-sub'>{FASE_DESC[fase]}</div>", unsafe_allow_html=True)

    # Fichas actuales: guardadas o generadas por defecto
    clave = _pizarra_key(formacion, fase)
    fichas = st.session_state.pizarras.get(clave) or formacion_a_fichas(formacion, fase)

    with col_campo:
        st.markdown(f"##### {fase} · {formacion}")
        # Campo para recibir las posiciones desde el componente JS.
        nuevo = st.text_input("posiciones_sync", key=f"piz_sync_{clave}",
                              label_visibility="collapsed", placeholder="")
        if nuevo:
            try:
                import json
                data = json.loads(nuevo)
                if isinstance(data, list) and data:
                    st.session_state.pizarras[clave] = data
                    autosave()
            except Exception:
                pass
        html = _pizarra_drag_html(fichas, clave)
        st_html(html, height=680)
        st.caption("Arriba = portería rival (ataque) · Abajo = portería propia. "
                   "Suelta la ficha para guardar su posición.")

        # Exportar la pizarra como imagen (PNG si hay soporte; si no, SVG).
        svg_export = pizarra_svg(fichas)
        png_bytes = None
        try:
            import cairosvg
            png_bytes = cairosvg.svg2png(bytestring=svg_export.encode("utf-8"),
                                         output_width=600, background_color="white")
        except Exception:
            png_bytes = None
        nombre_base = f"pizarra_{formacion}_{fase}".replace(" ", "_").replace("·", "")
        if png_bytes:
            st.download_button("⬇ Descargar pizarra (PNG)", data=png_bytes,
                               file_name=f"{nombre_base}.png", mime="image/png",
                               use_container_width=True, key="piz-export-png")
        else:
            st.download_button("⬇ Descargar pizarra (SVG)", data=svg_export.encode("utf-8"),
                               file_name=f"{nombre_base}.svg", mime="image/svg+xml",
                               use_container_width=True, key="piz-export-svg")
            st.caption("Se exporta en SVG (se abre en cualquier navegador y se puede "
                       "convertir a PNG). El PNG directo requiere la librería cairosvg.")


def _pizarra_drag_html(fichas, clave, w=440, h=620):
    """Componente HTML/JS: campo SVG con fichas arrastrables. Al soltar, escribe
    el JSON de posiciones en el text_input de Streamlit (input oculto del padre)
    para que Python lo reciba y lo guarde."""
    import json
    fichas_json = json.dumps(fichas)
    grass_a, grass_b = "#16221b", "#101913"
    # campo base (franjas + líneas) en coordenadas del SVG w x h
    stripes = ""
    n = 7
    sh = h / n
    for i in range(n):
        col = grass_a if i % 2 == 0 else grass_b
        stripes += f'<rect x="0" y="{i*sh:.1f}" width="{w}" height="{sh:.1f}" fill="{col}"/>'
    cx, midy, r = w/2, h/2, w*0.18
    lines = (f'<rect x="3" y="3" width="{w-6}" height="{h-6}" fill="none" stroke="#fff" stroke-width="2.5" rx="4"/>'
             f'<line x1="3" y1="{midy}" x2="{w-3}" y2="{midy}" stroke="#fff" stroke-width="2.5"/>'
             f'<circle cx="{cx}" cy="{midy}" r="{r}" fill="none" stroke="#fff" stroke-width="2.5"/>'
             f'<rect x="{cx-w*0.28}" y="3" width="{w*0.56}" height="{h*0.14}" fill="none" stroke="#fff" stroke-width="2"/>'
             f'<rect x="{cx-w*0.28}" y="{h-3-h*0.14}" width="{w*0.56}" height="{h*0.14}" fill="none" stroke="#fff" stroke-width="2"/>')
    return f"""
<div style="font-family:sans-serif">
<svg id="pizfield" viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;display:block;margin:auto;touch-action:none;cursor:grab;">
  <g id="bg">{stripes}{lines}</g>
  <g id="chips"></g>
</svg>
</div>
<script>
(function(){{
  const W={w}, H={h}, RAD=17;
  let fichas = {fichas_json};
  const svg = document.getElementById('pizfield');
  const gChips = document.getElementById('chips');
  function sx(xp){{ return (xp/100)*W; }}
  function sy(yp){{ return H-(yp/100)*H; }}
  function ix(px){{ return Math.max(0, Math.min(100, (px/W)*100)); }}
  function iy(py){{ return Math.max(0, Math.min(100, (1-(py/H))*100)); }}
  function draw(){{
    gChips.innerHTML='';
    fichas.forEach((f,idx)=>{{
      const cx=sx(f.x), cy=sy(f.y);
      const col = f.pos==='POR' ? '#c8a200' : '#0b3d91';
      const g=document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('data-i',idx); g.style.cursor='grab';
      g.innerHTML=`<circle cx="${{cx}}" cy="${{cy}}" r="${{RAD}}" fill="${{col}}" stroke="#fff" stroke-width="2.5"/>`+
        `<text x="${{cx}}" y="${{cy}}" text-anchor="middle" dominant-baseline="central" font-size="15" font-weight="800" fill="#fff">${{f.dorsal}}</text>`+
        `<text x="${{cx}}" y="${{cy+RAD+12}}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" stroke="#000" stroke-width="0.5">${{f.pos||''}}</text>`;
      gChips.appendChild(g);
    }});
  }}
  draw();
  let drag=null;
  function pt(e){{
    const r=svg.getBoundingClientRect();
    const cl = e.touches ? e.touches[0] : e;
    return {{x:(cl.clientX-r.left)*(W/r.width), y:(cl.clientY-r.top)*(H/r.height)}};
  }}
  function start(e){{
    const g=e.target.closest('g[data-i]'); if(!g) return;
    drag=parseInt(g.getAttribute('data-i')); svg.style.cursor='grabbing'; e.preventDefault();
  }}
  function move(e){{
    if(drag===null) return;
    const p=pt(e); fichas[drag].x=ix(p.x); fichas[drag].y=iy(p.y); draw(); e.preventDefault();
  }}
  function end(){{
    if(drag===null) return;
    drag=null; svg.style.cursor='grab'; sync();
  }}
  svg.addEventListener('mousedown',start); svg.addEventListener('touchstart',start,{{passive:false}});
  window.addEventListener('mousemove',move); window.addEventListener('touchmove',move,{{passive:false}});
  window.addEventListener('mouseup',end); window.addEventListener('touchend',end);
  function sync(){{
    // Escribir el JSON en el text_input de Streamlit (input del documento padre).
    try{{
      const doc=window.parent.document;
      const wrap=doc.querySelector('.st-key-piz_sync_{clave} input') ||
                 [...doc.querySelectorAll('input')].find(i=>i.getAttribute('aria-label')==='posiciones_sync');
      if(wrap){{
        const setter=Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype,'value').set;
        setter.call(wrap, JSON.stringify(fichas));
        wrap.dispatchEvent(new Event('input',{{bubbles:true}}));
        wrap.dispatchEvent(new Event('change',{{bubbles:true}}));
      }}
    }}catch(err){{}}
  }}
}})();
</script>
"""


# ============================================================================
# SECCIÓN: INFORME (cuestionario + generación de PDF)
# ============================================================================
# ============================================================================
# SECCIÓN SECUENCIAS (Fase 4)
# ============================================================================
def _mmss(minuto):
    """Minuto decimal -> timecode de vídeo. 21.2 -> '21:12'.
    El tagueo guarda segundos reales en los decimales; esta pantalla existe
    para buscar el clip, así que el dato se da en el idioma del vídeo."""
    try:
        m = float(minuto)
    except (TypeError, ValueError):
        return "—"
    mm = int(m)
    ss = int(round((m - mm) * 60))
    if ss == 60:
        mm, ss = mm + 1, 0
    return f"{mm}:{ss:02d}"


def _esc(s):
    """Escapa el texto que entra en el HTML de las tablas propias."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def kpis_continuidad_html(cont):
    """Cuatro tarjetas de continuidad. Cada acento dice algo: el peligro en
    verde, la pérdida en rojo, el volumen en azul."""
    tarjetas = [
        (f"{cont['secuencias_90']:.1f}", "Secuencias / 90", NEON_SKY),
        (f"{cont['largo_medio']:.1f}", "Acciones por cadena", INK),
        (f"{cont['pct_peligro']:.0f}%", "Acaban en peligro", NEON_OK),
        (f"{cont['pct_perdida']:.0f}%", "Acaban en pérdida", NEON_BAD),
    ]
    cards = "".join(
        f'<div class="seq-kpi" style="--accent:{col}">'
        f'<div class="k-val">{val}</div><div class="k-lab">{lab}</div></div>'
        for val, lab, col in tarjetas
    )
    return f'<div class="seq-kpis">{cards}</div>'


def tabla_secuencias_html(top):
    """Tabla del localizador. HTML propio, NO st.dataframe: ese componente
    pinta sobre un canvas (Glide) y el CSS no entra en las celdas — de ahí el
    fondo verde heredado y la cabecera ilegible.

    El timecode manda: es el punto de entrada al vídeo.
    """
    filas = ""
    for _, r in top.iterrows():
        acciones = list(r["acciones"])
        cadena = ""
        for i, a in enumerate(acciones):
            fin = ' class="fin"' if i == len(acciones) - 1 else ""
            sep = '<span class="sep">›</span>' if i else ""
            cadena += f'{sep}<span{fin}>{_esc(a)}</span>'
        dur = int(round((r["minuto_fin"] - r["minuto_ini"]) * 60))
        signo = "pos" if r["valor"] > 0 else ("neg" if r["valor"] < 0 else "cero")
        filas += (
            f'<div class="seq-row" data-des="{r["desenlace"]}">'
            f'<div><div class="seq-tc">{_mmss(r["minuto_ini"])}</div>'
            f'<div class="seq-meta">{r["n_acciones"]} acc · {dur}s</div></div>'
            f'<div class="seq-cadena">{cadena}'
            f'<div class="seq-meta">{_esc(r["sesion"])}</div></div>'
            f'<div><span class="seq-pill" data-des="{r["desenlace"]}">'
            f'{r["desenlace"]}</span></div>'
            f'<div class="seq-val" data-signo="{signo}">{r["valor"]:+.2f}</div>'
            f'</div>'
        )
    return (
        '<div class="seq-tabla">'
        '<div class="seq-head"><div>Minuto</div><div>Cadena de acciones</div>'
        '<div>Desenlace</div><div class="h-num">Valor</div></div>'
        f'{filas}</div>'
    )


def barras_bigrama_svg(bi, origen, w=720):
    """Qué hace después: barras horizontales. La más frecuente en dorado.
    Muestra veces Y porcentaje: un % sin su n engaña con muestra corta."""
    n = len(bi)
    row_h = 44
    pad_t, pad_l, pad_r = 8, 210, 96
    h = pad_t + row_h * n + 8
    plot_w = w - pad_l - pad_r
    vmax = max(bi["pct"].max(), 1)
    bars = ""
    for i, (_, r) in enumerate(bi.iterrows()):
        y = pad_t + i * row_h
        bw = plot_w * (r["pct"] / vmax)
        col = NEON_GOLD if i == 0 else NEON_SKY
        etiqueta = str(r["siguiente"])[:26]
        bars += (f'<text x="{pad_l-12}" y="{y+row_h/2:.1f}" text-anchor="end" '
                 f'dominant-baseline="central" font-size="13" font-weight="700" '
                 f'fill="{INK}">{etiqueta}</text>')
        bars += (f'<rect x="{pad_l}" y="{y+9:.1f}" width="{max(bw,2):.1f}" '
                 f'height="{row_h-20}" rx="4" fill="{col}" fill-opacity="0.9"/>')
        bars += (f'<text x="{pad_l+max(bw,2)+10:.1f}" y="{y+row_h/2:.1f}" '
                 f'dominant-baseline="central" font-size="13" font-weight="800" '
                 f'fill="{col}">{r["pct"]:.0f}%</text>')
        bars += (f'<text x="{pad_l+max(bw,2)+10+42:.1f}" y="{y+row_h/2:.1f}" '
                 f'dominant-baseline="central" font-size="11" font-weight="600" '
                 f'fill="{TXT_LO_SVG}">{int(r["veces"])}×</text>')
    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMinYMin meet" style="display:block;width:100%;height:{h}px;">
      <g>{bars}</g></svg>'''


def render_secuencias():
    st.markdown("<div class='hud-kicker'>Análisis · continuidad</div>",
                unsafe_allow_html=True)
    st.markdown("# Secuencias")
    st.caption(
        "Una secuencia es lo que el jugador encadena SIN cortes: acciones suyas "
        f"seguidas a menos de {int(secuencias.VENTANA_GAP * 60)}s. Es un eje aparte: "
        "el % de acierto mide fiabilidad, la nota mide impacto, esto mide "
        "continuidad. No modifica a ninguno de los dos."
    )

    if st.button("↻ Recargar datos", key="reload-sec"):
        st.cache_data.clear(); st.rerun()

    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. "
                "Ve a **Registro jugadores**, crea una sesión y registra acciones.")
        return

    jugadores = sorted(df["jugador"].dropna().unique())
    with st.sidebar:
        st.markdown("### Secuencias")
        jugador = st.selectbox("Jugador", jugadores, key="sec-jug")

    d = df[df["jugador"] == jugador]
    secs = secuencias.detectar_secuencias(d)
    if secs.empty:
        st.info(f"No hay acciones de {jugador} para analizar.")
        return

    # ---------- 1. Cabecera de continuidad ----------
    minutos = analytics.minutos_de_jugador(df, jugador)
    cont = secuencias.continuidad(secs, jugador, minutos=minutos)
    st.markdown(kpis_continuidad_html(cont), unsafe_allow_html=True)
    st.caption("La longitud media cuenta también las acciones sueltas: "
               "excluirlas inflaría la media.")

    st.divider()

    # ---------- 2. Localizador de jugadas ----------
    st.markdown("### Localizador de jugadas")
    st.caption("El minuto es el timecode de la primera acción de la cadena: "
               f"búscalo tal cual en el vídeo. Sólo cadenas de "
               f"{secuencias.MIN_ACCIONES}+ acciones — una acción suelta no es "
               "una jugada.")
    lc1, lc2, lc3 = st.columns([1, 1, 1])
    orden = lc1.radio("Ordenar", ["Mejores", "Peores"], horizontal=True,
                      key="sec-orden")
    des_lbl = lc2.selectbox("Desenlace", ["Todos", "peligro", "perdida", "neutro"],
                            key="sec-des")
    cuantas = lc3.slider("Cuántas", 5, 30, 10, key="sec-n")
    top = secuencias.top_secuencias(
        secs, jugador, n=cuantas, ascendente=(orden == "Peores"),
        desenlace=(None if des_lbl == "Todos" else des_lbl),
    )
    if top.empty:
        st.info(f"No hay cadenas de {secuencias.MIN_ACCIONES}+ acciones con ese filtro.")
    else:
        st.markdown(tabla_secuencias_html(top), unsafe_allow_html=True)

    st.divider()

    # ---------- 3. Tras esta acción, ¿qué hace? ----------
    st.markdown("### Tras esta acción, ¿qué hace?")
    accs = sorted(d["accion"].dropna().unique())
    origen = st.selectbox("Acción de origen", accs, key="sec-origen")
    bi, total_bi = secuencias.patrones_bigrama(secs, jugador, origen)
    if total_bi == 0:
        st.info(f"Ninguna cadena de {jugador} continúa tras «{origen}».")
    elif bi.empty:
        st.info(f"{total_bi} cadenas continúan tras «{origen}», pero ninguna "
                f"opción llega al {secuencias.MIN_PCT_BIGRAMA:.0f}%: hace de todo "
                "un poco, sin una salida preferente.")
    else:
        st.caption(f"{total_bi} cadenas continúan tras «{origen}». "
                   f"Sólo se muestran las salidas por encima del "
                   f"{secuencias.MIN_PCT_BIGRAMA:.0f}%.")
        render_svg(barras_bigrama_svg(bi, origen), height=8 + 44 * len(bi) + 8)


# ============================================================================
# ENRUTADO PRINCIPAL
# ============================================================================
render_nav()

section = st.session_state.section
if section == "Registro jugadores":
    if st.session_state.view == "menu":
        render_menu(tipo=TIPO_JUGADORES)
    else:
        render_edit()
elif section == "Gráficos":
    render_graficos()
elif section == "Secuencias":
    render_secuencias()
elif section == "Predicciones":
    render_predicciones()
else:
    # Compatibilidad con estados antiguos guardados en sesión.
    st.session_state.section = "Registro jugadores"
    render_menu(tipo=TIPO_JUGADORES)
