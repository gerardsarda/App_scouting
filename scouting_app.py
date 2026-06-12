"""
App de Scouting en Vivo — Scouting Mundial
==========================================
Tagging de acciones de jugadores mientras ves un partido + módulos de análisis.

Secciones (navegación en la barra lateral):
    · Sesiones      -> lista, crear/abrir/borrar y panel de tagging en vivo
    · Gráficos      -> radar comparativo, campo por tercios y mapa de calor
    · Equipos       -> métricas agregadas de equipo y calculadora de posesión
    · Predicciones  -> tendencias + modelo ML (scikit-learn) cuando hay datos

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
import report
import ai_analysis

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
RES_ENCONTRADO = [("Encontrado", "Encontrado", "ok"), ("No encontrado", "No encontrado", "bad")]
# Remate: ahora separa "fuera" de "bloqueado" (B) para no perder info de selección de tiro.
RES_REMATE = [("Puerta", "A puerta", "ok"), ("Gol", "Gol", "gol"),
              ("Fuera", "Fuera", "bad"), ("B", "Bloqueado", "falta")]
# Duelo defensivo 1v1: éxito (recuperó), parcial naranja "R" (aguantó/retrasó), fallo (le regatearon).
RES_DUELO_DEF = [("OK", "Correcto", "ok"), ("R", "Retrasó/aguantó", "falta"), ("Fallo", "Regateado", "bad")]
# Falta directa a puerta: puerta / gol / fuera / barrera (blocked).
RES_FALTA_DIRECTA = [("Puerta", "A puerta", "ok"), ("Gol", "Gol", "gol"),
                     ("Fuera", "Fuera", "bad"), ("Barrera", "Barrera", "falta")]
RES_SIMPLE = [("Registrar", "—", "neutral")]
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
        ("Protección de balón", RES_OK_FALLO), ("Pared", RES_OK_FALLO),
        ("Recibe entre líneas", RES_OK_FALLO),
        ("Falta recibida", RES_SIMPLE), ("Penalti provocado", RES_PENALTI),
    ],
    "Movimiento sin balón": [
        ("Desmarque de ruptura", RES_ENCONTRADO), ("Desmarque de apoyo", RES_ENCONTRADO),
        ("Ataque al palo", RES_ENCONTRADO), ("Desmarque de arrastre", RES_ENCONTRADO),
        ("Amplía el campo", RES_ENCONTRADO), ("Ofrece línea de pase", RES_ENCONTRADO),
        ("Entrada en área rival", RES_ENCONTRADO),
    ],
    "Finalización": [
        ("Remate", RES_REMATE), ("Remate de cabeza", RES_REMATE),
        ("Remate desde fuera", RES_REMATE), ("Llegada 2ª línea", RES_REMATE),
        ("Ocasión clara fallada", RES_SIMPLE),
        ("Generación de ocasión", RES_OK_FALLO),
    ],
    "Defensa": [
        ("Entrada / tackle", RES_OK_FALLO), ("Intercepción", RES_OK_FALLO),
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
    "Transiciones y duelos": [
        ("Transición ofensiva", RES_OK_FALLO), ("Transición defensiva", RES_OK_FALLO),
        ("Duelo aéreo of.", RES_OK_FALLO), ("Contrapresión", RES_OK_FALLO),
    ],
    "Balón parado y otros": [
        ("Lanzamiento córner", RES_OK_FALLO),
        ("Lanzamiento falta lateral", RES_OK_FALLO),
        ("Falta directa a puerta", RES_FALTA_DIRECTA),
        ("Remate a balón parado", RES_REMATE),
        ("Despeje en córner def.", RES_OK_FALLO),
        ("Duelo en córner def.", RES_OK_FALLO),
        ("Acción a balón parado", RES_OK_FALLO),
        ("Error grave / pérdida", RES_SIMPLE),
    ],
}

# ----------------------------------------------------------------------------
# PANEL DE ACCIONES DE EQUIPO (tagging colectivo, más general que el individual)
# Resultados mixtos: éxito/fallo donde aplica, registro simple donde no.
# ----------------------------------------------------------------------------
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
        "izq": ["Construcción y pase", "Movimiento sin balón", "Transiciones y duelos"],
        "der": ["Regate y conducción", "Finalización", "Defensa", "Balón parado y otros"],
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
NEON_SKY = "#38bdf8"      # azul cielo
TXT_LO_SVG = "#8b93a1"    # labels tenues
GRID_SVG = "#2a2e38"      # rejillas
PANEL_SVG = "#15171c"     # fondo de paneles SVG



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
    """Mapa de calor suave sobre el campo (degradado por intensidad)."""
    base = _pitch_base_svg(w, h)
    cw, ch = w / 3, h / 3
    mx = grid.max() or 1
    blobs = ""
    for yi in range(3):
        for xi in range(3):
            c = int(grid[yi, xi])
            if c == 0:
                continue
            cx = xi * cw + cw / 2
            ccy = yi * ch + ch / 2
            intensity = c / mx
            rad = (cw if cw < ch else ch) * (0.55 + 0.45 * intensity)
            # color de frío (verde) a caliente (rojo) según intensidad
            if intensity > 0.66:
                col = NEON_BAD
            elif intensity > 0.33:
                col = NEON_GOLD
            else:
                col = NEON_OK
            blobs += (f'<circle cx="{cx:.1f}" cy="{ccy:.1f}" r="{rad:.1f}" fill="{col}" '
                      f'opacity="{0.25 + 0.5*intensity:.2f}" />')
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
        polys += f'<polygon points="{pstr}" fill="{s["color"]}" fill-opacity="0.22" stroke="{s["color"]}" stroke-width="2.5"/>'
        for x, y in pts:
            polys += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{s["color"]}"/>'

    # viewBox con margen para que las etiquetas laterales no se corten.
    m = 64
    return f'''<svg viewBox="{-m} {-m} {w + 2*m} {h + 2*m}" xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%">
      <g>{rings}{spokes}{polys}{labels}</g></svg>'''


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
        secciones = ["Registro jugadores", "Registro equipos", "Gráficos", "Informe", "Predicciones"]
        for sec in secciones:
            is_active = (st.session_state.section == sec)
            if st.button(sec, key=f"nav-{sec}", use_container_width=True,
                         type=("primary" if is_active else "secondary")):
                # Al cambiar de sección de registro, volvemos al menú de esa sección.
                if sec in ("Registro jugadores", "Registro equipos") and st.session_state.section != sec:
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
            cols[1].metric("Acciones", s.get("num_events", 0))
            if es_equipo:
                cols[2].metric("Tipo", "Equipo")
            else:
                cols[2].metric("Jugadores", s.get("num_jugadores", 0))
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
                "Minuto de descanso (separa 1ª/2ª parte)", min_value=1, max_value=120,
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
                new_equipo = st.text_input("Equipo del jugador", key="new_player_equipo",
                                           placeholder="Ej: FC Barcelona")
                cme, cms = st.columns(2)
                new_min_in = cme.number_input("Minuto de entrada", 0, 120, 0, key="new_player_min_in",
                                              help="0 si es titular. Para un suplente, el minuto en que entró.")
                new_min_out = cms.number_input("Minuto de salida", 0, 120, 90, key="new_player_min_out",
                                               help="Minuto en que fue sustituido. Déjalo en el final si jugó hasta el pitido.")
                new_foto = st.file_uploader("Foto (opcional)", type=["png", "jpg", "jpeg"],
                                            key="new_player_foto")
                if st.button("Guardar jugador", use_container_width=True, type="primary"):
                    name = new_player.strip()
                    if name and name not in st.session_state.players:
                        st.session_state.players.append(name)
                        st.session_state.posiciones[name] = new_pos
                        foto_b64 = ""
                        if new_foto is not None:
                            import base64
                            foto_b64 = base64.b64encode(new_foto.getvalue()).decode("ascii")
                        st.session_state.jugadores_info[name] = {
                            "pos": new_pos, "equipo": new_equipo.strip(),
                            "edad": int(new_edad), "foto": foto_b64,
                            "min_in": int(new_min_in), "min_out": int(new_min_out),
                        }
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
                    info = st.session_state.jugadores_info.get(sel, {})
                    cur_pos = st.session_state.posiciones.get(sel) or info.get("pos")
                    idx_pos = POSICION_CODIGOS.index(cur_pos) if cur_pos in POSICION_CODIGOS else 0
                    e1, e2 = st.columns(2)
                    edit_pos = e1.selectbox("Posición", POSICION_CODIGOS, index=idx_pos,
                                            format_func=lambda c: f"{c} · {POSICIONES[c]}", key=f"editpos_{sel}")
                    edit_edad = e2.number_input("Edad", 14, 50, int(info.get("edad", 23)), key=f"editedad_{sel}")
                    edit_equipo = st.text_input("Equipo", info.get("equipo", ""), key=f"editeq_{sel}")
                    em1, em2 = st.columns(2)
                    edit_min_in = em1.number_input("Minuto de entrada", 0, 120,
                                                   int(info.get("min_in", 0)), key=f"editmin_in_{sel}",
                                                   help="0 si es titular.")
                    edit_min_out = em2.number_input("Minuto de salida", 0, 120,
                                                    int(info.get("min_out", 90)), key=f"editmin_out_{sel}")
                    edit_foto = st.file_uploader("Cambiar foto", type=["png", "jpg", "jpeg"], key=f"editfoto_{sel}")
                    if st.button("Guardar cambios", key=f"savej_{sel}", use_container_width=True):
                        st.session_state.posiciones[sel] = edit_pos
                        nueva = dict(info)
                        nueva.update({"pos": edit_pos, "edad": int(edit_edad), "equipo": edit_equipo.strip(),
                                      "min_in": int(edit_min_in), "min_out": int(edit_min_out)})
                        if edit_foto is not None:
                            import base64
                            nueva["foto"] = base64.b64encode(edit_foto.getvalue()).decode("ascii")
                        st.session_state.jugadores_info[sel] = nueva
                        autosave()
                        st.rerun()
            else:
                st.info("Añade al menos un jugador para empezar.")
            st.divider()
        st.subheader("Cronómetro")

        @st.fragment(run_every="1s")
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
            min_obj = aj1.number_input("Minuto", min_value=0, max_value=130,
                                       value=int(current_minute()), step=1, key="set-min")
            seg_obj = aj2.number_input("Seg", min_value=0, max_value=59, value=0, step=1, key="set-seg")
            if st.button("Fijar minuto", use_container_width=True, key="set-min-btn"):
                clock_set_minute(min_obj + seg_obj / 60.0)
                st.rerun()
        st.divider()
        with st.expander("Atajos de teclado", expanded=False):
            atajos = "- **Z** — Deshacer\n- **Espacio** — Iniciar/pausar cron\n"
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
            @st.fragment(run_every="1s")
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
    ICONO_RES = {"ok": "✓", "bad": "✕", "gol": "GOL"}

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
            tip = label
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

    # --- TIMELINE (sustituye al resumen anterior) ---
    st.divider()
    st.subheader("Timeline del partido")
    if st.session_state.events:
        st.markdown("<div class='session-sub'>Cada barra es una acción, situada en su minuto. "
                    "Verde = éxito · Rojo = fallo · Dorado = gol. Pasa el ratón por una barra para ver el detalle.</div>",
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
            # Ordenar por el minuto NUMÉRICO (no por el texto "mm:ss", que pone 100 entre 09 y 13).
            orden = "minuto" if "minuto" in df_f.columns else "minuto_fmt"
            df_f = df_f.sort_values(orden)
            st.dataframe(df_f[["minuto_fmt", "jugador", "accion", "resultado", "zona"]],
                         use_container_width=True, hide_index=True, height=300)
    else:
        st.info("Todavía no has registrado ninguna acción. Pulsa los botones del panel para empezar.")

    # --- RESUMEN DE EQUIPO DE ESTA SESIÓN ---
    st.divider()
    st.subheader("Resumen de equipo (este partido)")
    if st.session_state.events:
        df_sess = analytics.flatten_events([{**collect_session_data(), "id": st.session_state.current_session_id}])
        tm = analytics.team_metrics(df_sess, st.session_state.match_info)
        m = st.columns(5)
        m[0].metric("Acciones", tm["total_acciones"])
        m[1].metric("Tiros (a puerta)", f"{tm['tiros']} ({tm['tiros_puerta']})")
        m[2].metric("Goles (tagueados)", tm["goles_accion"])
        m[3].metric("Pases OK", f"{tm['pct_pase']}%")
        m[4].metric("Regates OK", f"{tm['pct_regate']}%")
    else:
        st.caption("Registra acciones para ver el resumen de equipo.")

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
@st.cache_data(ttl=30)
def _load_all_flat(tipo=None):
    """Carga las sesiones (del tipo indicado) y las aplana.
    Cacheado 30s para no machacar la BD."""
    sessions = storage.load_all_sessions(tipo=tipo)
    return sessions, analytics.flatten_events(sessions)


def render_graficos():
    st.markdown("<div class='hud-kicker'>Análisis · gráficos</div>", unsafe_allow_html=True)
    st.markdown("# Gráficos y comparativas")
    st.caption("Analiza por separado los datos de jugadores y los de equipo. "
               "Cada subapartado usa solo sus propias sesiones.")

    if st.button("↻ Recargar datos", key="reload-graf"):
        st.cache_data.clear(); st.rerun()

    sub_jug, sub_eq = st.tabs(["Gráficos de jugadores", "Gráficos de equipos"])
    with sub_jug:
        _graficos_jugadores()
    with sub_eq:
        _graficos_equipos()


def _graficos_jugadores():
    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. "
                "Ve a **Registro jugadores**, crea una sesión y registra acciones.")
        return

    # Filtro por parte del partido (común a todas las pestañas).
    fp1, fp2 = st.columns([2, 1])
    parte_lbl = fp1.radio("Parte del partido", ["Todo el partido", "1ª parte", "2ª parte"],
                          horizontal=True, key="graf-parte")
    md_default = 45
    if sessions:
        mds = [s.get("minuto_descanso") for s in sessions if s.get("minuto_descanso")]
        if mds:
            md_default = int(max(set(mds), key=mds.count))
    minuto_desc = fp2.number_input("Min. descanso", 1, 120, md_default, key="graf-md")
    parte = {"Todo el partido": "todo", "1ª parte": "1", "2ª parte": "2"}[parte_lbl]
    df = analytics.filter_by_parte(df, parte, minuto_desc)
    if df.empty:
        st.warning("No hay acciones en esa parte del partido.")
        return

    tab_radar, tab_campo, tab_calor, tab_rank = st.tabs(
        ["Radar comparativo", "Campo por tercios", "Mapa de calor", "Rankings y comparativas"])

    # ---- RADAR ----
    with tab_radar:
        st.markdown("#### Comparar dos jugadores")
        st.caption("El radar muestra % de acierto por faceta + volumen relativo de acciones. "
                   "Útil para comparar p. ej. regates efectivos de dos jugadores.")
        pm = analytics.player_metrics(df)
        jugadores = pm["jugador"].tolist()
        if len(jugadores) < 1:
            st.info("Necesitas al menos un jugador con acciones.")
        else:
            c1, c2 = st.columns(2)
            j1 = c1.selectbox("Jugador A", jugadores, index=0)
            j2 = c2.selectbox("Jugador B", ["(ninguno)"] + jugadores,
                              index=(2 if len(jugadores) > 1 else 0))
            series = []
            row1 = pm[pm["jugador"] == j1].iloc[0].to_dict()
            series.append({"name": j1, "values": analytics.radar_axes(row1, df), "color": NEON_SKY})
            if j2 != "(ninguno)":
                row2 = pm[pm["jugador"] == j2].iloc[0].to_dict()
                series.append({"name": j2, "values": analytics.radar_axes(row2, df), "color": NEON_GOLD})
            cg, cl = st.columns([2, 1])
            with cg:
                svg = radar_svg(analytics.RADAR_DIMENSIONS, series)
                render_svg(svg, height=520)
            with cl:
                for s in series:
                    st.markdown(f"<span style='color:{s['color']};font-weight:800'>● {s['name']}</span>",
                                unsafe_allow_html=True)
                st.markdown("**Detalle**")
                cols_show = ["jugador", "acciones", "pct_pase", "pct_regate",
                             "pct_finalizacion", "pct_defensa", "pct_mov"]
                sel = pm[pm["jugador"].isin([s["name"] for s in series])][cols_show]
                sel = sel.rename(columns={"pct_pase": "Pase%", "pct_regate": "Regate%",
                                          "pct_finalizacion": "Final%", "pct_defensa": "Def%", "pct_mov": "Mov%"})
                st.dataframe(sel, use_container_width=True, hide_index=True)

    # ---- CAMPO POR TERCIOS ----
    with tab_campo:
        st.markdown("#### Acciones por zona del campo")
        c1, c2 = st.columns(2)
        jugs = ["(todos)"] + analytics.player_metrics(df)["jugador"].tolist()
        jf = c1.selectbox("Jugador", jugs, key="campo-jug")
        accs = ["(todas)"] + sorted(df["accion"].unique().tolist())
        af = c2.selectbox("Acción", accs, key="campo-acc")
        d = df.copy()
        if jf != "(todos)":
            d = d[d["jugador"] == jf]
        if af != "(todas)":
            d = d[d["accion"] == af]
        grid = analytics.zone_grid_counts(d)
        cg, cl = st.columns([2, 1])
        with cg:
            svg = pitch_thirds_svg(grid, title="Conteo de acciones por celda")
            render_svg(svg, height=380)
        with cl:
            st.metric("Acciones mostradas", int(grid.sum()))
            # Reparto por tercio (suma de columnas)
            por_tercio = grid.sum(axis=0)
            st.markdown("**Reparto por tercio**")
            for i, name in enumerate(ZONA_COLS):
                tot = int(grid.sum()) or 1
                st.markdown(f"{name}: **{int(por_tercio[i])}** ({100*por_tercio[i]/tot:.0f}%)")
            st.caption("Los datos en formato antiguo (solo 3 tercios) se colocan en la banda central.")

    # ---- MAPA DE CALOR ----
    with tab_calor:
        st.markdown("#### Mapa de calor")
        c1, c2 = st.columns(2)
        jf2 = c1.selectbox("Jugador", jugs, key="calor-jug")
        solo_exito = c2.checkbox("Solo acciones con éxito", value=False)
        d = df.copy()
        if jf2 != "(todos)":
            d = d[d["jugador"] == jf2]
        if solo_exito:
            d = d[d["exito"]]
        grid = analytics.zone_grid_counts(d)
        svg = heatmap_svg(grid)
        render_svg(svg, height=360)
        st.caption("Verde = baja concentración · Dorado = media · Rojo = alta concentración de acciones.")

    # ---- RANKINGS Y COMPARATIVAS ----
    with tab_rank:
        st.markdown("#### Rankings filtrables")
        st.caption("Ejemplo: top 5 delanteros centro (DC) en remates a puerta. "
                   "Combina variable, posición, resultado, métrica y rango de minutos.")

        acciones_disp = ["(todas)"] + sorted(df["accion"].unique().tolist())
        posiciones_presentes = (set(df["posicion"].dropna().unique())
                                if "posicion" in df.columns else set())
        pos_disp = ["(todas)"] + [c for c in POSICION_CODIGOS if c in posiciones_presentes]

        f1, f2, f3 = st.columns(3)
        r_accion = f1.selectbox("Variable / acción", acciones_disp, key="rk-accion")
        r_pos = f2.selectbox("Posición", pos_disp,
                             format_func=lambda c: c if c == "(todas)" else f"{c} · {POSICIONES.get(c,c)}",
                             key="rk-pos")
        r_res = f3.selectbox("Resultado", ["todos", "acierto", "fallo"], key="rk-res")
        f4, f5 = st.columns(2)
        r_metrica = f4.selectbox(
            "Métrica", ["conteo", "pct", "aciertos"],
            format_func=lambda m: {"conteo": "Nº de acciones (volumen)",
                                   "pct": "% de acierto (eficacia)",
                                   "aciertos": "Aciertos absolutos"}[m], key="rk-met")
        r_topn = f5.slider("Top N jugadores", 3, 15, 5, key="rk-topn")
        r_min = st.slider("Rango de minutos", 0, 120, (0, 120), key="rk-min")

        rk = analytics.player_ranking(df, accion=r_accion, posicion=r_pos,
                                      resultado=r_res, metrica=r_metrica,
                                      min_lo=r_min[0], min_hi=r_min[1], top_n=r_topn)
        if rk.empty:
            st.info("No hay datos para esos filtros. Prueba a ampliar el rango o quitar algún filtro.")
        else:
            unidad = {"conteo": "acciones", "pct": "% acierto", "aciertos": "aciertos"}[r_metrica]
            svg = barras_ranking_svg(rk, unidad)
            render_svg(svg, height=max(160, 52 * len(rk) + 60))

        st.divider()
        st.markdown("#### Tabla de clasificación ordenable")
        st.caption("Pulsa una cabecera de columna para reordenar.")
        rk_full = analytics.player_ranking(df, accion=r_accion, posicion=r_pos,
                                           resultado=r_res, metrica=r_metrica,
                                           min_lo=r_min[0], min_hi=r_min[1], top_n=999)
        if not rk_full.empty:
            tabla = rk_full.rename(columns={"jugador": "Jugador", "posicion": "Pos",
                                            "acciones": "Acciones", "aciertos": "Aciertos",
                                            "pct": "% acierto"})[
                ["Jugador", "Pos", "Acciones", "Aciertos", "% acierto"]]
            st.dataframe(tabla, use_container_width=True, hide_index=True, height=320)

        st.divider()
        st.markdown("#### Medias por posición")
        st.caption("Compara el rendimiento medio de cada posición en la variable elegida.")
        pa = analytics.position_averages(df, accion=r_accion, metrica=r_metrica,
                                         min_lo=r_min[0], min_hi=r_min[1])
        if pa.empty:
            st.info("Sin datos de posición para esos filtros.")
        else:
            pa_show = pa.copy()
            pa_show["posicion"] = pa_show["posicion"].apply(
                lambda c: f"{c} · {POSICIONES.get(c, c)}")
            st.bar_chart(pa_show.set_index("posicion")["valor"], height=300)

        st.divider()
        st.markdown("#### Dispersión: volumen vs acierto")
        st.caption("Cada punto es un jugador. Eje X = nº de acciones, eje Y = % de acierto. "
                   "Arriba a la derecha = mucho volumen y buena eficacia.")
        sc = analytics.scatter_volume_accuracy(df, accion=r_accion, posicion=r_pos,
                                               min_lo=r_min[0], min_hi=r_min[1])
        if sc.empty or len(sc) < 1:
            st.info("Sin datos para la dispersión con esos filtros.")
        else:
            svg = dispersion_svg(sc)
            render_svg(svg, height=420)


# ----------------------------------------------------------------------------
# GRÁFICOS · subapartado de EQUIPOS (solo sesiones de tipo equipo)
# ----------------------------------------------------------------------------
def _graficos_equipos():
    sessions, df = _load_all_flat(tipo=TIPO_EQUIPO)
    if not sessions:
        st.info("No hay sesiones de equipo todavía. "
                "Ve a **Registro equipos**, crea una sesión y registra acciones del conjunto.")
        return

    nombres = [f"{s.get('nombre','(sin nombre)')} · {s.get('fecha','')}" for s in sessions]
    opciones = ["Todas las sesiones"] + nombres
    sel = st.selectbox("Sesión a analizar", opciones, key="eq-graf-pick")

    if sel == "Todas las sesiones":
        d = df
        mi = None
    else:
        idx = nombres.index(sel)
        s = sessions[idx]
        d = analytics.flatten_events([s])
        mi = {"goles_local": s.get("goles_local", 0), "posesion_local": s.get("posesion_local", 50)}

    tm = analytics.team_metrics(d, mi)

    st.markdown("### Indicadores generales")
    r1 = st.columns(4)
    r1[0].metric("Acciones totales", tm["total_acciones"])
    r1[1].metric("Tiros", tm["tiros"], delta=f"{tm['tiros_puerta']} a puerta", delta_color="off")
    r1[2].metric("Goles (tagueados)", tm["goles_accion"])
    r1[3].metric("Pases completados", f"{tm['pct_pase']}%", delta=f"{tm['pases_ok']}/{tm['pases']}", delta_color="off")
    r2 = st.columns(4)
    r2[0].metric("Progresiones OK", f"{tm['pct_regate']}%", delta=f"{tm['regates_ok']}/{tm['regates']}", delta_color="off")
    r2[1].metric("Recuperaciones", tm["recuperaciones"])
    r2[2].metric("Duelos def. ganados", f"{tm['duelos_def_ok']}/{tm['duelos_def']}")
    r2[3].metric("Tarjetas", f"{tm['amarillas']}A · {tm['rojas']}R", delta=f"{tm['faltas']} faltas", delta_color="off")

    st.divider()
    cizq, cder = st.columns(2)
    with cizq:
        st.markdown("#### Zonas del campo")
        grid = analytics.zone_grid_counts(d)
        svg = pitch_thirds_svg(grid, title="Acciones de equipo por celda")
        render_svg(svg, height=360)
    with cder:
        st.markdown("#### Mapa de calor")
        grid2 = analytics.zone_grid_counts(d)
        svg2 = heatmap_svg(grid2)
        render_svg(svg2, height=360)

    st.divider()
    st.markdown("### Calculadora de posesión")
    st.caption("Estima el % de posesión a partir del tiempo con balón de cada equipo (en segundos o minutos).")
    cc = st.columns(3)
    t_local = cc[0].number_input("Tiempo con balón — local", min_value=0.0, value=0.0, step=10.0, key="eq-pos-l")
    t_visit = cc[1].number_input("Tiempo con balón — visitante", min_value=0.0, value=0.0, step=10.0, key="eq-pos-v")
    total_t = t_local + t_visit
    if total_t > 0:
        pos_local = round(100 * t_local / total_t, 1)
        cc[2].metric("Posesión local", f"{pos_local}%", delta=f"Visitante {round(100-pos_local,1)}%", delta_color="off")
        st.markdown(
            f"<div style='display:flex;height:26px;border-radius:8px;overflow:hidden;border:1px solid #d3ded5'>"
            f"<div style='width:{pos_local}%;background:#15ff66;color:#04210f;display:flex;align-items:center;"
            f"justify-content:center;font-weight:800;font-size:0.8rem'>{pos_local}%</div>"
            f"<div style='width:{100-pos_local}%;background:#5f7a8a;color:#fff;display:flex;align-items:center;"
            f"justify-content:center;font-weight:800;font-size:0.8rem'>{round(100-pos_local,1)}%</div></div>",
            unsafe_allow_html=True)
    else:
        cc[2].metric("Posesión local", "—")

    st.divider()
    st.markdown("### Distribución de acciones por tipo")
    if not d.empty:
        by_acc = d.groupby("accion").size().reset_index(name="conteo").sort_values("conteo", ascending=False)
        st.bar_chart(by_acc.set_index("accion")["conteo"], height=320)
    else:
        st.caption("Sin acciones en la selección.")


# ============================================================================
# SECCIÓN: PREDICCIONES — tendencias + ML
# ============================================================================
def render_predicciones():
    st.markdown("<div class='hud-kicker'>Análisis · predicciones (IA)</div>", unsafe_allow_html=True)
    st.markdown("# Predicción de rendimiento")
    st.caption("Combina dos enfoques: tendencias (siempre disponibles) y un modelo de "
               "machine learning que se entrena cuando hay datos suficientes. "
               "La fiabilidad se muestra de forma honesta: con pocos datos, las predicciones son orientativas.")

    if st.button("↻ Recargar datos", key="reload-pred"):
        st.cache_data.clear(); st.rerun()

    st.caption("De momento, las predicciones cubren solo jugadores.")
    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. El módulo necesita datos para proyectar.")
        return

    tab_jug, tab_modelo, tab_patrones = st.tabs(
        ["Tendencia por jugador", "Modelo ML (acierto de acción)", "Patrones tácticos (IA)"])

    # ---- TENDENCIA POR JUGADOR ----
    with tab_jug:
        pm = analytics.player_metrics(df)
        jugadores = pm["jugador"].tolist()
        jugador = st.selectbox("Jugador", jugadores)
        dpj = df[df["jugador"] == jugador]
        pred = analytics.predict_player_trend(dpj)

        if pred["n_sesiones"] == 0:
            st.warning("Este jugador no tiene acciones de éxito/fallo suficientes para proyectar.")
        else:
            c1, c2, c3 = st.columns(3)
            ult = pred["historico"][-1]["pct"] if pred["historico"] else 0
            c1.metric("% acierto último partido", f"{ult}%")
            c2.metric("Proyección próximo partido", f"{pred['proyeccion']}%")
            flecha = {"al alza": "↗", "a la baja": "↘", "estable": "→"}[pred["tendencia"]]
            c3.metric("Tendencia", f"{flecha} {pred['tendencia']}")

            if pred["n_sesiones"] == 1:
                st.info("Solo hay 1 partido de este jugador: la proyección es simplemente su valor actual. "
                        "Registra más partidos para detectar una tendencia real.")
            else:
                hist = pd.DataFrame(pred["historico"])
                hist_idx = hist.set_index("fecha")["pct"]
                st.markdown("**Evolución del % de acierto por partido**")
                st.line_chart(hist_idx, height=260)
                st.caption(f"Basado en {pred['n_sesiones']} partidos. La proyección usa una regresión lineal simple; "
                           "es orientativa y mejora con más datos.")

    # ---- MODELO ML ----
    with tab_modelo:
        st.markdown("#### Modelo: probabilidad de éxito de una acción")
        st.caption("Random Forest entrenado con tus datos. Predice si una acción saldrá bien "
                   "según el tipo de acción, la zona y el minuto.")
        model_info = analytics.train_outcome_model(df)

        if not model_info["trained"]:
            st.warning(f"Modelo no entrenado. {model_info['reason']}")
            st.caption("El modelo se activa automáticamente cuando acumules suficientes acciones con resultado.")
        else:
            acc = model_info["accuracy"]
            c1, c2 = st.columns(2)
            c1.metric("Acciones de entrenamiento", model_info["n"])
            if acc is not None:
                fiab = "alta" if acc >= 0.7 else "media" if acc >= 0.6 else "baja"
                c2.metric("Fiabilidad (validación cruzada)", f"{acc*100:.0f}%", delta=fiab, delta_color="off")
            if acc is not None and acc < 0.6:
                st.info("La fiabilidad es baja todavía: trata estas predicciones como una guía, no como certeza. "
                        "Mejorará conforme registres más partidos.")

            st.markdown("**Qué factores pesan más en el modelo**")
            fi = model_info["feature_importance"]
            fi_df = pd.DataFrame(fi, columns=["factor", "importancia"])
            fi_df["factor"] = fi_df["factor"].str.replace("accion_", "Acción: ").str.replace("zona_str_", "Zona: ")
            st.bar_chart(fi_df.set_index("factor")["importancia"], height=300)

            st.divider()
            st.markdown("**Simular una acción**")
            sc1, sc2, sc3 = st.columns(3)
            acc_opts = sorted(df[df["intento"]]["accion"].unique().tolist())
            sim_acc = sc1.selectbox("Acción", acc_opts)
            zona_opts = sorted(df["zona"].dropna().unique().tolist())
            sim_zona = sc2.selectbox("Zona", zona_opts) if zona_opts else ""
            sim_min = sc3.slider("Minuto", 0, 120, 45)
            if st.button("Calcular probabilidad de éxito", type="primary"):
                enc = model_info["encoder"]
                clf = model_info["model"]
                X_in = pd.DataFrame([{"accion": sim_acc, "zona_str": str(sim_zona)}])
                X_cat = enc.transform(X_in)
                X = np.hstack([X_cat, [[float(sim_min)]]])
                proba = clf.predict_proba(X)[0]
                # índice de la clase "éxito" (1)
                classes = list(clf.classes_)
                p_exito = proba[classes.index(1)] if 1 in classes else 0.0
                st.metric("Probabilidad estimada de éxito", f"{p_exito*100:.0f}%")
                st.caption("Estimación del modelo según tus datos históricos. Orientativa.")

    # ---- PATRONES TÁCTICOS (IA) ----
    with tab_patrones:
        st.markdown("#### Detección de patrones tácticos con IA")
        st.caption("La IA busca tendencias en los datos (zonas de pérdida, tramos de "
                   "bajón, diferencias entre partes), no solo cifras. El análisis avisa "
                   "de su fiabilidad según cuántos datos haya.")
        pm2 = analytics.player_metrics(df)
        jugadores2 = pm2["jugador"].tolist()
        if not jugadores2:
            st.info("No hay jugadores con acciones.")
        else:
            jug_p = st.selectbox("Jugador", jugadores2, key="pat-jug")
            # ficha del jugador (para entrada/salida si es suplente)
            info_p = {}
            for s in sessions:
                ji = s.get("jugadores_info") or {}
                if jug_p in ji:
                    info_p = ji[jug_p]; break
            # fiabilidad previa (sin llamar a la IA)
            pd_datos = analytics.patrones_tacticos_datos(df, jug_p, info_jugador=info_p)
            if pd_datos:
                nivel = pd_datos["fiabilidad"]
                etiqueta = {"baja": "🔴 Fiabilidad baja", "media": "🟡 Fiabilidad media",
                            "alta": "🟢 Fiabilidad alta"}[nivel]
                extra = ""
                if pd_datos.get("es_suplente"):
                    extra = f" · suplente ({pd_datos['ventana']}, {pd_datos['minutos_jugados']} min)"
                st.markdown(f"**{etiqueta}** — {pd_datos['n_partidos']} partido(s), "
                            f"{pd_datos['n_acciones']} acciones{extra}.")
                if nivel == "baja":
                    st.warning("Con tan pocos datos, los patrones serán preliminares. "
                               "Gana fiabilidad acumulando más partidos del jugador.")
            if not ai_analysis.hay_api_key():
                st.info("Configura GEMINI_KEY en los secrets para activar esta función.")
            elif st.button("Detectar patrones", type="primary", key="pat-gen"):
                with st.spinner("Analizando patrones..."):
                    texto, msg = ai_analysis.detectar_patrones(pd_datos)
                if texto:
                    st.markdown(texto)
                else:
                    st.warning(msg)


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
def render_informe():
    st.markdown("<div class='hud-kicker'>Informe · jugador</div>", unsafe_allow_html=True)
    st.markdown("# Informe del jugador")
    st.caption("Rellena el cuestionario y genera un PDF. El radar, mapa de calor, "
               "acciones por tercio, fortalezas/debilidades y notas se calculan solos "
               "desde las sesiones.")

    if st.button("↻ Recargar datos", key="reload-inf"):
        st.cache_data.clear(); st.rerun()

    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía.")
        return

    pm = analytics.player_metrics(df)
    jugadores = pm["jugador"].tolist()
    if not jugadores:
        st.info("No hay jugadores con acciones.")
        return

    st.markdown("### Cuestionario")

    # Reunir la ficha del jugador (pos/equipo/edad/foto) desde las sesiones.
    def info_de_jugador(nombre):
        for s in sessions:
            ji = s.get("jugadores_info") or {}
            if nombre in ji:
                return ji[nombre]
        # compat: solo posición si existe en 'posiciones'
        for s in sessions:
            pos_map = s.get("posiciones") or {}
            if nombre in pos_map:
                return {"pos": pos_map[nombre]}
        return {}

    c1, c2 = st.columns(2)
    jugador = c1.selectbox("Jugador del informe", jugadores, key="inf-jug")
    info_j = info_de_jugador(jugador)
    # posición real del jugador (de su ficha, o de sus datos)
    dpj = df[df["jugador"] == jugador]
    pos = info_j.get("pos") or (dpj["posicion"].mode().iloc[0] if not dpj["posicion"].mode().empty else "")
    pos_larga = POSICIONES.get(pos, pos) if pos else "sin posición"
    extra_info = []
    if info_j.get("equipo"): extra_info.append(info_j["equipo"])
    if info_j.get("edad"): extra_info.append(f"{info_j['edad']} años")
    c2.text_input("Ficha del jugador", value=" · ".join([pos_larga] + extra_info),
                  disabled=True, key="inf-pos")

    # Fuente de datos: total o una sesión
    fuente_op = c1.radio("Datos a usar", ["Todas las sesiones (total)", "Una sesión concreta"],
                         key="inf-fuente")
    session_id = None
    if fuente_op == "Una sesión concreta":
        sess_jug = [s for s in sessions if jugador in (s.get("jugadores") or [])]
        if sess_jug:
            nombres = [f"{s.get('nombre','(s/n)')} · {s.get('fecha','')}" for s in sess_jug]
            idx = c2.selectbox("Sesión", range(len(nombres)), format_func=lambda i: nombres[i], key="inf-sess")
            session_id = sess_jug[idx]["id"]
        else:
            c2.warning("Ese jugador no aparece en ninguna sesión concreta.")

    # Métricas de volumen: cualquier acción, con variantes ✓ y por tercio
    opciones_vol = analytics.opciones_volumen(dpj)
    defaults_vol = [o for o in ["Pase progresivo", "Regate 1v1 ✓", "Recuperación @ 3er tercio",
                                "Remate", "Error grave / pérdida"] if o in opciones_vol]
    vol_keys = st.multiselect(
        "Métricas en 'Volumen de acciones' (cualquier acción; ✓ = solo exitosas; @ = por tercio)",
        opciones_vol, default=defaults_vol, key="inf-vol")
    if len(vol_keys) > 6:
        st.caption("Se usarán las primeras 6.")

    # Comparación con otro jugador de su posición
    comparar = st.checkbox("Comparar con otro jugador de su posición", value=True, key="inf-cmp")
    jugador_b, estad_cmp = None, []
    if comparar:
        cc1, cc2 = st.columns(2)
        candidatos = [j for j in analytics.players_in_position(df, pos) if j != jugador]
        if candidatos:
            jugador_b = cc1.selectbox("Comparar con", candidatos, key="inf-jugb")
            estad_cmp = cc2.multiselect(
                "Estadísticas a comparar",
                ["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón"],
                default=["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón"],
                key="inf-estad")
        else:
            cc1.warning(f"No hay otros jugadores en la posición {pos or '—'}.")
            comparar = False

    # Análisis con IA (Gemini)
    usar_ia = st.checkbox("Incluir análisis con IA (Gemini)", value=ai_analysis.hay_api_key(),
                          key="inf-ia")
    if usar_ia and not ai_analysis.hay_api_key():
        st.info("Para el análisis con IA, configura GEMINI_KEY en los secrets de Streamlit. "
                "Sin ella, el informe se generará igualmente pero sin esa sección.")

    st.divider()
    if st.button("Generar informe PDF", type="primary", key="inf-gen"):
        with st.spinner("Generando informe..."):
            fuente = "sesion" if session_id else "total"
            datos = analytics.player_report_data(df, jugador, vol_keys[:6],
                                                 fuente=fuente, session_id=session_id,
                                                 info_jugador=info_j)
            datos["posicion"] = pos
            datos["posicion_larga"] = POSICIONES.get(pos, pos)
            # Contexto de nivel: si es una sesión concreta, el nivel de ese partido;
            # si son todas, un resumen de los rivales enfrentados.
            if session_id:
                s = next((s for s in sessions if s["id"] == session_id), None)
                meta = (s or {}).get("meta") or {}
                datos["contexto_nivel"] = (
                    f"Rival: nivel {meta.get('nivel_rival','Medio').lower()} · "
                    f"Equipo propio: nivel {meta.get('nivel_propio','Medio').lower()}")
            else:
                sess_jug = [s for s in sessions if jugador in (s.get("jugadores") or [])]
                rivales = [((s.get("meta") or {}).get("nivel_rival", "Medio")) for s in sess_jug]
                if rivales:
                    from collections import Counter
                    resumen = ", ".join(f"{n}×{c}" for n, c in Counter(rivales).items())
                    datos["contexto_nivel"] = f"Rivales enfrentados ({len(rivales)} part.): {resumen}"
            comparacion = None
            if comparar and jugador_b and estad_cmp:
                comparacion = analytics.player_comparison(df, jugador, jugador_b, estad_cmp)

            # Notas: de la sesión elegida, o de la más reciente del jugador
            notas_txt = ""
            if session_id:
                s = next((s for s in sessions if s["id"] == session_id), None)
                notas_txt = (s or {}).get("notas", "") or ""
            else:
                con_notas = [s for s in sessions
                             if jugador in (s.get("jugadores") or []) and (s.get("notas") or "").strip()]
                if con_notas:
                    notas_txt = con_notas[-1].get("notas", "")
            notas_list = [n.strip() for n in notas_txt.replace("\n", ". ").split(". ") if n.strip()]

            # Foto del jugador: de su ficha (base64) -> archivo temporal
            foto_path = None
            if info_j.get("foto"):
                try:
                    import base64, tempfile as _tf
                    raw = base64.b64decode(info_j["foto"])
                    ftmp = _tf.NamedTemporaryFile(delete=False, suffix=".png")
                    ftmp.write(raw); ftmp.close()
                    foto_path = ftmp.name
                except Exception:
                    foto_path = None

            # Análisis con IA (si está activado y hay key)
            analisis_ia = None
            ia_msg = ""
            if usar_ia:
                analisis_ia, ia_msg = ai_analysis.analizar_jugador(
                    datos, comparacion=comparacion, nombre_b=jugador_b,
                    posicion_larga=datos.get("posicion_larga", ""))

            import tempfile
            out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            out.close()
            report.generar_informe(out.name, datos, comparacion=comparacion,
                                   notas=notas_list or None, foto_path=foto_path,
                                   nombre_b=jugador_b, analisis_ia=analisis_ia)
            with open(out.name, "rb") as f:
                pdf_bytes = f.read()

        st.success("Informe generado.")
        # Mostrar el análisis IA en pantalla
        if usar_ia:
            if analisis_ia:
                st.markdown("### Análisis con IA")
                st.markdown(analisis_ia)
            elif ia_msg and ia_msg != "ok":
                st.warning(ia_msg)
        st.download_button("Descargar PDF", data=pdf_bytes,
                           file_name=f"informe_{jugador.replace(' ', '_')}.pdf",
                           mime="application/pdf", key="inf-dl")


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
elif section == "Registro equipos":
    if st.session_state.view == "menu":
        render_menu(tipo=TIPO_EQUIPO)
    else:
        render_edit()
elif section == "Gráficos":
    render_graficos()
elif section == "Informe":
    render_informe()
elif section == "Predicciones":
    render_predicciones()
else:
    # Compatibilidad con estados antiguos guardados en sesión.
    st.session_state.section = "Registro jugadores"
    render_menu(tipo=TIPO_JUGADORES)
