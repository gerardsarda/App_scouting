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
RES_REMATE = [("Puerta", "A puerta", "ok"), ("Gol", "Gol", "gol"), ("Fuera", "Fuera/Interceptado", "bad")]
RES_SIMPLE = [("Registrar", "—", "neutral")]
RES_FALTA = [("Falta", "Falta", "falta")]
RES_AMARILLA = [("Amarilla", "Tarjeta amarilla", "amarilla")]
RES_ROJA = [("Roja", "Tarjeta roja", "roja")]
RES_PENALTI = [("Penalti", "Penalti provocado", "penalti")]
RES_PENALTI_CONTRA = [("Penalti", "Penalti cometido", "penalti-contra")]

PANEL = {
    "Construcción y pase": [
        ("Pase progresivo", RES_OK_FALLO), ("Pase entre líneas", RES_OK_FALLO),
        ("Pase al espacio", RES_OK_FALLO), ("Cambio de orientación", RES_OK_FALLO),
        ("Pase filtrado", RES_OK_FALLO), ("Pase en conducción", RES_OK_FALLO),
        ("Pase de primera", RES_OK_FALLO), ("Pase bajo presión", RES_OK_FALLO),
        ("Pase en largo", RES_OK_FALLO), ("Salida de balón", RES_OK_FALLO),
        ("Asistencia", RES_SIMPLE), ("Pase clave", RES_OK_FALLO),
        ("Centro lateral", RES_OK_FALLO),
    ],
    "Regate y conducción": [
        ("Regate 1v1", RES_OK_FALLO), ("Conducción progresiva", RES_OK_FALLO),
        ("Desborde por banda", RES_OK_FALLO), ("Recorte / cambio ritmo", RES_OK_FALLO),
        ("Protección de balón", RES_OK_FALLO), ("Pared", RES_OK_FALLO),
        ("Recibe entre líneas", RES_OK_FALLO),
    ],
    "Movimiento sin balón": [
        ("Desmarque de ruptura", RES_ENCONTRADO), ("Desmarque de apoyo", RES_ENCONTRADO),
        ("Ataque al palo", RES_ENCONTRADO), ("Desmarque de arrastre", RES_ENCONTRADO),
        ("Amplía el campo", RES_ENCONTRADO), ("Ofrece línea de pase", RES_ENCONTRADO),
    ],
    "Finalización": [
        ("Remate", RES_REMATE), ("Remate de cabeza", RES_REMATE),
        ("Remate desde fuera", RES_REMATE), ("Llegada 2ª línea", RES_REMATE),
        ("Generación de ocasión", RES_SIMPLE),
    ],
    "Defensa": [
        ("Entrada / tackle", RES_OK_FALLO), ("Intercepción", RES_OK_FALLO),
        ("Recuperación", RES_OK_FALLO), ("Despeje", RES_OK_FALLO),
        ("Duelo aéreo def.", RES_OK_FALLO), ("Duelo 1v1 def.", RES_OK_FALLO),
        ("Presión fuerza error", RES_OK_FALLO), ("Cobertura", RES_OK_FALLO),
        ("Marcaje al hombre", RES_OK_FALLO), ("Bloqueo tiro/centro", RES_OK_FALLO),
        ("Repliegue", RES_OK_FALLO), ("Falta táctica", RES_SIMPLE),
        ("Falta", RES_FALTA), ("Tarjeta amarilla", RES_AMARILLA),
        ("Tarjeta roja", RES_ROJA), ("Penalti provocado", RES_PENALTI),
        ("Penalti cometido", RES_PENALTI_CONTRA),
    ],
    "Transiciones y duelos": [
        ("Transición ofensiva", RES_OK_FALLO), ("Transición defensiva", RES_OK_FALLO),
        ("Duelo aéreo of.", RES_OK_FALLO), ("Contrapresión", RES_OK_FALLO),
    ],
    "Balón parado y otros": [
        ("Acción a balón parado", RES_OK_FALLO), ("Error grave / pérdida", RES_SIMPLE),
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

# Etiqueta especial para distinguir eventos de equipo de los de jugador.
EQUIPO_TAG = "★ EQUIPO"

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
        "section": "Sesiones",
        "view": "menu",
        "current_session_id": None,
        "events": [], "players": [], "active_player": None,
        "clock_start": None, "clock_offset": 0.0,
        "match_info": {
            "nombre": "", "equipo_local": "", "equipo_visitante": "",
            "goles_local": 0, "goles_visitante": 0, "posesion_local": 50,
            "competicion": "Mundial", "fecha": datetime.now().strftime("%Y-%m-%d"),
        },
        "final_notes": "",
        "zona_x": 1, "zona_y": 1,
        # Tagging de equipo (sección Equipos): cronómetro y zona propios
        "team_clock_start": None, "team_clock_offset": 0.0,
        "team_zona_x": 1, "team_zona_y": 1,
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
        "events": st.session_state.events,
        "notas": st.session_state.final_notes,
    }


def autosave():
    sid = st.session_state.current_session_id
    if sid:
        storage.save_session(sid, collect_session_data())


def load_into_state(session):
    st.session_state.current_session_id = session["id"]
    st.session_state.events = session.get("events") or []
    st.session_state.players = session.get("jugadores") or []
    st.session_state.active_player = st.session_state.players[0] if st.session_state.players else None
    st.session_state.match_info = {
        "nombre": session.get("nombre", ""),
        "equipo_local": session.get("equipo_local", "") or "",
        "equipo_visitante": session.get("equipo_visitante", "") or "",
        "goles_local": session.get("goles_local", 0) or 0,
        "goles_visitante": session.get("goles_visitante", 0) or 0,
        "posesion_local": session.get("posesion_local", 50) or 50,
        "competicion": session.get("competicion", "Mundial") or "Mundial",
        "fecha": session.get("fecha", datetime.now().strftime("%Y-%m-%d")) or "",
    }
    st.session_state.final_notes = session.get("notas", "") or ""
    st.session_state.clock_start = None
    st.session_state.clock_offset = 0.0
    st.session_state.view = "edit"


# ----------------------------------------------------------------------------
# REGISTRO DE ACCIONES
# ----------------------------------------------------------------------------
def add_event(action, result_code):
    if st.session_state.active_player is None:
        st.toast("Selecciona un jugador primero")
        return
    minute = current_minute()
    zx, zy = st.session_state.zona_x, st.session_state.zona_y
    st.session_state.events.append({
        "jugador": st.session_state.active_player,
        "minuto": round(minute, 2),
        "minuto_fmt": fmt_minute(minute),
        "accion": action,
        "resultado": result_code,
        "zona": zona_label(zx, zy),
        "zona_x": zx, "zona_y": zy,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })
    label = action + (f" · {result_code}" if result_code != "—" else "")
    st.toast(f"{st.session_state.active_player} — {label}")
    autosave()


def undo_last():
    if st.session_state.events:
        removed = st.session_state.events.pop()
        st.toast(f"Deshecho: {removed['accion']}")
        autosave()
    else:
        st.toast("No hay acciones que deshacer")


# ----------------------------------------------------------------------------
# TAGGING DE EQUIPO
# Las acciones de equipo se guardan como eventos normales pero con
# jugador = EQUIPO_TAG, para que entren en timeline y métricas sin mezclarse
# con las individuales. Usan su propio cronómetro y su propia zona.
# ----------------------------------------------------------------------------
def team_minute():
    if st.session_state.team_clock_start is None:
        return st.session_state.team_clock_offset
    elapsed = (datetime.now() - st.session_state.team_clock_start).total_seconds() / 60.0
    return st.session_state.team_clock_offset + elapsed


def add_team_event(action, result_code):
    sid = st.session_state.current_session_id
    if not sid:
        st.toast("Abre o selecciona una sesión antes de registrar")
        return
    minute = team_minute()
    zx, zy = st.session_state.team_zona_x, st.session_state.team_zona_y
    st.session_state.events.append({
        "jugador": EQUIPO_TAG,
        "minuto": round(minute, 2),
        "minuto_fmt": fmt_minute(minute),
        "accion": action,
        "resultado": result_code,
        "zona": zona_label(zx, zy),
        "zona_x": zx, "zona_y": zy,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })
    label = action + (f" · {result_code}" if result_code != "—" else "")
    st.toast(f"EQUIPO — {label}")
    autosave()


def undo_last_team():
    """Deshace la última acción de equipo (no toca las de jugadores)."""
    for i in range(len(st.session_state.events) - 1, -1, -1):
        if st.session_state.events[i].get("jugador") == EQUIPO_TAG:
            removed = st.session_state.events.pop(i)
            st.toast(f"Deshecho: {removed['accion']}")
            autosave()
            return
    st.toast("No hay acciones de equipo que deshacer")


# ============================================================================
# HELPERS DE DIBUJO (SVG) — campo, heatmap, radar, timeline
# Todo SVG puro inyectado con st_html, integrado en el tema césped.
# ============================================================================
GRASS_A = "#2e8b3d"
GRASS_B = "#277a35"
LINE = "#ffffff"
INK = "#14241a"


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
            cells += f'<rect x="{xi*cw:.1f}" y="{yi*ch:.1f}" width="{cw:.1f}" height="{ch:.1f}" fill="#e6a700" opacity="{op:.2f}"/>'
            cells += (f'<text x="{cx:.1f}" y="{ccy:.1f}" text-anchor="middle" '
                      f'dominant-baseline="central" font-size="22" font-weight="800" '
                      f'fill="#ffffff" stroke="{INK}" stroke-width="0.6">{c}</text>')
    # rejilla divisoria
    grid_lines = ""
    for i in (1, 2):
        grid_lines += f'<line x1="{i*cw:.1f}" y1="0" x2="{i*cw:.1f}" y2="{h}" stroke="{LINE}" stroke-width="1" opacity="0.4" stroke-dasharray="5 5"/>'
        grid_lines += f'<line x1="0" y1="{i*ch:.1f}" x2="{w}" y2="{i*ch:.1f}" stroke="{LINE}" stroke-width="1" opacity="0.4" stroke-dasharray="5 5"/>'
    arrow = (f'<defs><marker id="ar" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto">'
             f'<path d="M0,0 L6,3 L0,6 Z" fill="#fff"/></marker></defs>'
             f'<line x1="{w*0.3}" y1="{h+18}" x2="{w*0.7}" y2="{h+18}" stroke="#fff" stroke-width="2" marker-end="url(#ar)"/>'
             f'<text x="{w*0.5}" y="{h+14}" text-anchor="middle" font-size="11" fill="#dff3e4">Sentido del ataque</text>')
    ttl = f'<text x="{w/2}" y="-8" text-anchor="middle" font-size="13" font-weight="800" fill="#14241a">{title}</text>' if title else ""
    return f'''<svg viewBox="-10 -28 {w+20} {h+50}" width="100%" xmlns="http://www.w3.org/2000/svg">
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
                col = "#d83a4e"
            elif intensity > 0.33:
                col = "#e6a700"
            else:
                col = "#9fe5b0"
            blobs += (f'<circle cx="{cx:.1f}" cy="{ccy:.1f}" r="{rad:.1f}" fill="{col}" '
                      f'opacity="{0.25 + 0.5*intensity:.2f}" />')
    flt = ('<defs><filter id="blur"><feGaussianBlur stdDeviation="14"/></filter></defs>')
    return f'''<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg">
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
        rings += f'<polygon points="{" ".join(pts)}" fill="none" stroke="#d3ded5" stroke-width="1"/>'

    spokes, labels = "", ""
    for i, lab in enumerate(axes_labels):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        ex, ey = cx + R * math.cos(ang), cy + R * math.sin(ang)
        spokes += f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#d3ded5" stroke-width="1"/>'
        lx, ly = cx + (R + 26) * math.cos(ang), cy + (R + 26) * math.sin(ang)
        anchor = "middle"
        if math.cos(ang) > 0.3:
            anchor = "start"
        elif math.cos(ang) < -0.3:
            anchor = "end"
        labels += (f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                   f'dominant-baseline="central" font-size="13" font-weight="700" fill="#14241a">{lab}</text>')

    polys = ""
    for s in series:
        pts = [point(i, v) for i, v in enumerate(s["values"])]
        pstr = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        polys += f'<polygon points="{pstr}" fill="{s["color"]}" fill-opacity="0.22" stroke="{s["color"]}" stroke-width="2.5"/>'
        for x, y in pts:
            polys += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{s["color"]}"/>'

    return f'''<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg">
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
        grid += f'<line x1="{x:.1f}" y1="{pad_t-6}" x2="{x:.1f}" y2="{h-18}" stroke="#e8efe9" stroke-width="1"/>'
        grid += f'<text x="{x:.1f}" y="{pad_t-12}" text-anchor="middle" font-size="11" fill="#6c7d72">{fmt_minute(m)}</text>'

    rows = ""
    color_map = {"Correcto": "#1a8f3c", "Encontrado": "#1a8f3c", "A puerta": "#1a8f3c",
                 "Gol": "#e6a700", "Fallo": "#d83a4e", "No encontrado": "#d83a4e",
                 "Fuera/Interceptado": "#d83a4e", "Falta": "#d98300",
                 "Tarjeta amarilla": "#e6c200", "Tarjeta roja": "#d83a4e",
                 "Penalti provocado": "#7d4ad8", "Penalti cometido": "#9e1b2f"}
    for ri, pl in enumerate(players):
        y = pad_t + ri * row_h
        rows += f'<line x1="{pad_l}" y1="{y+row_h/2:.1f}" x2="{w-30}" y2="{y+row_h/2:.1f}" stroke="#eef3ef" stroke-width="1"/>'
        rows += (f'<text x="{pad_l-10}" y="{y+row_h/2:.1f}" text-anchor="end" '
                 f'dominant-baseline="central" font-size="12" font-weight="700" fill="#14241a">{pl[:18]}</text>')
        sub = df[df["jugador"] == pl]
        for _, ev in sub.iterrows():
            x = xpos(ev["minuto"])
            col = color_map.get(ev["resultado"], "#5f7a8a")
            rows += (f'<rect x="{x-7:.1f}" y="{y+6:.1f}" width="14" height="{row_h-12}" rx="3" '
                     f'fill="{col}"><title>{ev["minuto_fmt"]} · {ev["accion"]} · {ev["resultado"]}</title></rect>')

    return f'''<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg"
        style="background:#ffffff;border-radius:12px;border:1px solid #d3ded5">
      <g>{grid}{rows}</g></svg>'''


# ============================================================================
# NAVEGACIÓN PRINCIPAL (barra lateral)
# ============================================================================
def render_nav():
    with st.sidebar:
        st.markdown("<div class='hud-kicker'>Scouting Mundial</div>", unsafe_allow_html=True)
        st.markdown("### Navegación")
        secciones = ["Sesiones", "Gráficos", "Equipos", "Predicciones"]
        for sec in secciones:
            is_active = (st.session_state.section == sec)
            if st.button(sec, key=f"nav-{sec}", use_container_width=True,
                         type=("primary" if is_active else "secondary")):
                if sec == "Sesiones" and st.session_state.section != "Sesiones":
                    st.session_state.view = "menu"
                st.session_state.section = sec
                st.rerun()
        st.divider()


# ============================================================================
# SECCIÓN: SESIONES — menú
# ============================================================================
def render_menu():
    st.markdown("<div class='hud-kicker'>Sesiones · panel de control</div>", unsafe_allow_html=True)
    st.markdown("# Sesiones de análisis")
    st.caption("Cada sesión guarda un partido con sus jugadores y todas las acciones registradas. "
               "Se guarda automáticamente en la nube.")

    with st.container():
        c1, c2, c3 = st.columns([3, 2, 1])
        nombre = c1.text_input("Nombre de la nueva sesión",
                               placeholder="Ej: España vs Brasil — cuartos", key="new_session_name")
        competicion = c2.text_input("Competición", value="Mundial", key="new_session_comp")
        c3.write(""); c3.write("")
        if c3.button("Crear sesión", type="primary", use_container_width=True):
            if nombre.strip():
                sid = storage.create_session(nombre.strip(), competicion.strip() or "Mundial")
                if sid:
                    new_sess = storage.load_session(sid)
                    if new_sess:
                        load_into_state(new_sess)
                        st.rerun()
            else:
                st.warning("Pon un nombre a la sesión antes de crearla.")

    st.divider()
    st.markdown("### Sesiones guardadas")
    sessions = storage.list_sessions()
    if not sessions:
        st.info("Aún no tienes sesiones guardadas. Crea la primera arriba.")
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
        if st.button("← Volver a sesiones", use_container_width=True):
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
            if mi != old:
                autosave()
        st.divider()
        st.subheader("Jugadores")
        new_player = st.text_input("Añadir jugador", placeholder="Ej: 10 - Messi", key="new_player_input")
        if st.button("Añadir jugador", use_container_width=True):
            name = new_player.strip()
            if name and name not in st.session_state.players:
                st.session_state.players.append(name)
                if st.session_state.active_player is None:
                    st.session_state.active_player = name
                autosave()
                st.rerun()
        if st.session_state.players:
            sel = st.radio("Jugador activo", st.session_state.players,
                           index=st.session_state.players.index(st.session_state.active_player)
                           if st.session_state.active_player in st.session_state.players else 0)
            if sel != st.session_state.active_player:
                st.session_state.active_player = sel
        else:
            st.info("Añade al menos un jugador para empezar.")
        st.divider()
        st.subheader("Cronómetro")
        running = st.session_state.clock_start is not None
        estado = "En marcha" if running else "Detenido"
        st.metric("Tiempo de partido", fmt_minute(current_minute()), delta=estado, delta_color="off")
        cc1, cc2 = st.columns(2)
        if cc1.button("Iniciar" if not running else "Pausar", use_container_width=True, key="sc-clock-toggle"):
            if running: clock_pause()
            else: clock_start()
            st.rerun()
        if cc2.button("Reiniciar", use_container_width=True):
            clock_reset(); st.rerun()
        st.divider()
        with st.expander("Atajos de teclado", expanded=False):
            st.markdown("- **Z** — Deshacer\n- **Espacio** — Iniciar/pausar cron\n"
                        "- **← / →** — Jugador anterior/siguiente")

    # --- CABECERA ---
    mi = st.session_state.match_info
    titulo = f"{mi['equipo_local'] or 'Local'} {mi['goles_local']} - {mi['goles_visitante']} {mi['equipo_visitante'] or 'Visitante'}"
    running = st.session_state.clock_start is not None
    rec = ("<span class='rec-dot'></span>Grabando · " if running else "")
    st.markdown(f"<div class='hud-kicker'>{rec}Scouting en vivo · {mi['competicion']}</div>", unsafe_allow_html=True)
    st.markdown(f"# {titulo}")

    # --- CHIPS DE JUGADOR ---
    if st.session_state.players:
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

    bar1, bar2 = st.columns([3, 1])
    with bar1:
        if st.session_state.active_player:
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
    def render_action(action, results):
        n = len(results)
        name_w = 3.0 if n <= 2 else 2.2
        cols = st.columns([name_w] + [1.5] * n)
        cols[0].markdown(f"<div class='action-name'>{action}</div>", unsafe_allow_html=True)
        for i, (label, code, kind) in enumerate(results):
            if cols[i + 1].button(label, key=f"res-{kind}--{action}--{code}", use_container_width=True):
                add_event(action, code); st.rerun()

    def render_block(title, actions):
        st.markdown(f"<div class='block-head'>{title}</div>", unsafe_allow_html=True)
        for action, results in actions:
            render_action(action, results)

    col_izq, col_der = st.columns(2)
    distribucion = {
        "izq": ["Construcción y pase", "Movimiento sin balón", "Transiciones y duelos"],
        "der": ["Regate y conducción", "Finalización", "Defensa", "Balón parado y otros"],
    }
    with col_izq:
        for nombre in distribucion["izq"]:
            render_block(nombre, PANEL[nombre]); st.markdown("")
    with col_der:
        for nombre in distribucion["der"]:
            render_block(nombre, PANEL[nombre]); st.markdown("")

    # --- TIMELINE (sustituye al resumen anterior) ---
    st.divider()
    st.subheader("Timeline del partido")
    if st.session_state.events:
        st.markdown("<div class='session-sub'>Cada barra es una acción, situada en su minuto. "
                    "Verde = éxito · Rojo = fallo · Dorado = gol. Pasa el ratón por una barra para ver el detalle.</div>",
                    unsafe_allow_html=True)
        svg = timeline_svg(st.session_state.events, w=1000)
        n_players = len(set(e["jugador"] for e in st.session_state.events))
        st_html(f"<div style='font-family:sans-serif'>{svg}</div>", height=80 + 30 * max(n_players, 1) + 40, scrolling=True)

        with st.expander("Ver registro cronológico en tabla", expanded=False):
            df = pd.DataFrame(st.session_state.events)
            jugadores_con_eventos = sorted(df["jugador"].unique())
            filtro = st.multiselect("Filtrar por jugador", jugadores_con_eventos, default=jugadores_con_eventos)
            df_f = df[df["jugador"].isin(filtro)] if filtro else df
            st.dataframe(df_f[["minuto_fmt", "jugador", "accion", "resultado", "zona"]].sort_values("minuto_fmt"),
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
def _load_all_flat():
    """Carga todas las sesiones y las aplana. Cacheado 30s para no machacar la BD."""
    sessions = storage.load_all_sessions()
    return sessions, analytics.flatten_events(sessions)


def render_graficos():
    st.markdown("<div class='hud-kicker'>Análisis · gráficos</div>", unsafe_allow_html=True)
    st.markdown("# Gráficos y comparativas")
    st.caption("Agrega los datos de todas tus sesiones guardadas. "
               "Compara jugadores, mira dónde ocurren las acciones y genera mapas de calor.")

    if st.button("↻ Recargar datos", key="reload-graf"):
        st.cache_data.clear(); st.rerun()

    sessions, df = _load_all_flat()
    if df.empty:
        st.info("No hay acciones registradas en ninguna sesión todavía. "
                "Crea una sesión, registra acciones y vuelve aquí.")
        return

    tab_radar, tab_campo, tab_calor = st.tabs(["Radar comparativo", "Campo por tercios", "Mapa de calor"])

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
            series.append({"name": j1, "values": analytics.radar_axes(row1, df), "color": "#1a8f3c"})
            if j2 != "(ninguno)":
                row2 = pm[pm["jugador"] == j2].iloc[0].to_dict()
                series.append({"name": j2, "values": analytics.radar_axes(row2, df), "color": "#d83a4e"})
            cg, cl = st.columns([2, 1])
            with cg:
                svg = radar_svg(analytics.RADAR_DIMENSIONS, series)
                st_html(f"<div style='font-family:sans-serif'>{svg}</div>", height=480)
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
            st_html(f"<div style='font-family:sans-serif'>{svg}</div>", height=430)
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
        st_html(f"<div style='font-family:sans-serif'>{svg}</div>", height=400)
        st.caption("Verde = baja concentración · Dorado = media · Rojo = alta concentración de acciones.")


# ============================================================================
# SECCIÓN: EQUIPOS — métricas agregadas y calculadora de posesión
# ============================================================================
def render_equipos():
    st.markdown("<div class='hud-kicker'>Análisis · equipos</div>", unsafe_allow_html=True)
    st.markdown("# Equipo")
    st.caption("Registra acciones del equipo en vivo con botones generales, "
               "y analiza las métricas globales del conjunto.")

    tab_reg, tab_ana = st.tabs(["Registrar (en vivo)", "Análisis"])
    with tab_reg:
        render_equipo_tagging()
    with tab_ana:
        render_equipo_analisis()


# ----------------------------------------------------------------------------
# EQUIPOS · pestaña de TAGGING en vivo
# ----------------------------------------------------------------------------
def render_equipo_tagging():
    # Elegir sobre qué sesión se registra (debe existir una sesión).
    sessions = storage.list_sessions()
    if not sessions:
        st.info("Primero crea una sesión en el apartado **Sesiones**. "
                "El tagging de equipo se guarda dentro de una sesión, igual que el de jugadores.")
        return

    nombres = [f"{s.get('nombre','(sin nombre)')} · {s.get('fecha','')}" for s in sessions]
    # Preseleccionar la sesión que ya esté abierta, si la hay.
    pre_idx = 0
    if st.session_state.current_session_id:
        for i, s in enumerate(sessions):
            if s["id"] == st.session_state.current_session_id:
                pre_idx = i
                break
    csel = st.selectbox("Sesión donde registrar", nombres, index=pre_idx, key="team-session-pick")
    sel_session = sessions[nombres.index(csel)]

    # Si cambiamos de sesión respecto a la cargada en memoria, la cargamos.
    if sel_session["id"] != st.session_state.current_session_id:
        full = storage.load_session(sel_session["id"])
        if full:
            st.session_state.current_session_id = full["id"]
            st.session_state.events = full.get("events") or []
            st.session_state.players = full.get("jugadores") or []
            st.session_state.match_info = {
                "nombre": full.get("nombre", ""),
                "equipo_local": full.get("equipo_local", "") or "",
                "equipo_visitante": full.get("equipo_visitante", "") or "",
                "goles_local": full.get("goles_local", 0) or 0,
                "goles_visitante": full.get("goles_visitante", 0) or 0,
                "posesion_local": full.get("posesion_local", 50) or 50,
                "competicion": full.get("competicion", "Mundial") or "Mundial",
                "fecha": full.get("fecha", "") or "",
            }
            st.session_state.final_notes = full.get("notas", "") or ""

    mi = st.session_state.match_info
    equipo_nombre = mi.get("equipo_local") or "Equipo"
    st.markdown(f"<div class='hud-kicker'>Registrando acciones de · {equipo_nombre}</div>",
                unsafe_allow_html=True)

    # --- Cronómetro propio del tagging de equipo ---
    running = st.session_state.team_clock_start is not None
    cclk = st.columns([2, 1, 1, 1])
    cclk[0].metric("Tiempo", fmt_minute(team_minute()),
                   delta=("En marcha" if running else "Detenido"), delta_color="off")
    if cclk[1].button("Iniciar" if not running else "Pausar", use_container_width=True, key="team-clock-toggle"):
        if running:
            st.session_state.team_clock_offset = team_minute()
            st.session_state.team_clock_start = None
        else:
            st.session_state.team_clock_start = datetime.now()
        st.rerun()
    if cclk[2].button("Reiniciar", use_container_width=True, key="team-clock-reset"):
        st.session_state.team_clock_start = None
        st.session_state.team_clock_offset = 0.0
        st.rerun()
    if cclk[3].button("Deshacer", use_container_width=True, key="team-undo"):
        undo_last_team(); st.rerun()

    # --- Selector de zona 3x3 (independiente del de jugadores) ---
    st.markdown("<div class='chips-label'>Zona del campo — pulsa la celda donde ocurre la acción</div>",
                unsafe_allow_html=True)
    zf, zh = st.columns([2, 1])
    with zf:
        for yi in range(3):
            row = st.columns(3)
            for xi in range(3):
                is_active = (st.session_state.team_zona_x == xi and st.session_state.team_zona_y == yi)
                lab = f"{ZONA_COLS[xi].split()[0]}·{ZONA_ROWS[yi].split()[-1][:3]}"
                if row[xi].button(lab, key=f"team-zona-{xi}-{yi}", use_container_width=True,
                                  type=("primary" if is_active else "secondary")):
                    st.session_state.team_zona_x = xi
                    st.session_state.team_zona_y = yi
                    st.rerun()
    with zh:
        st.info(f"Zona activa:\n\n**{zona_label(st.session_state.team_zona_x, st.session_state.team_zona_y)}**\n\n"
                "Izquierda = tu defensa · Derecha = ataque")

    # --- Botones de acción de equipo ---
    def render_team_action(action, results):
        n = len(results)
        name_w = 3.0 if n <= 2 else 2.2
        cols = st.columns([name_w] + [1.5] * n)
        cols[0].markdown(f"<div class='action-name'>{action}</div>", unsafe_allow_html=True)
        for i, (label, code, kind) in enumerate(results):
            if cols[i + 1].button(label, key=f"teamres-{kind}--{action}--{code}", use_container_width=True):
                add_team_event(action, code); st.rerun()

    def render_team_block(title, actions):
        st.markdown(f"<div class='block-head'>{title}</div>", unsafe_allow_html=True)
        for action, results in actions:
            render_team_action(action, results)

    col_a, col_b = st.columns(2)
    dist = {"a": ["Pases y posesión", "Ataque"],
            "b": ["Defensa", "Transiciones y balón parado"]}
    with col_a:
        for nombre in dist["a"]:
            render_team_block(nombre, PANEL_EQUIPO[nombre]); st.markdown("")
    with col_b:
        for nombre in dist["b"]:
            render_team_block(nombre, PANEL_EQUIPO[nombre]); st.markdown("")

    # --- Resumen rápido de lo registrado para el equipo en esta sesión ---
    st.divider()
    team_events = [e for e in st.session_state.events if e.get("jugador") == EQUIPO_TAG]
    st.subheader(f"Acciones de equipo registradas: {len(team_events)}")
    if team_events:
        svg = timeline_svg(team_events, w=1000)
        st_html(f"<div style='font-family:sans-serif'>{svg}</div>", height=140, scrolling=True)
        with st.expander("Ver tabla", expanded=False):
            df_t = pd.DataFrame(team_events)
            st.dataframe(df_t[["minuto_fmt", "accion", "resultado", "zona"]].sort_values("minuto_fmt"),
                         use_container_width=True, hide_index=True, height=260)
    else:
        st.caption("Aún no has registrado acciones de equipo en esta sesión.")


# ----------------------------------------------------------------------------
# EQUIPOS · pestaña de ANÁLISIS (métricas agregadas)
# ----------------------------------------------------------------------------
def render_equipo_analisis():
    if st.button("↻ Recargar datos", key="reload-eq"):
        st.cache_data.clear(); st.rerun()

    sessions, df = _load_all_flat()
    if not sessions:
        st.info("No hay sesiones guardadas todavía.")
        return

    nombres = [f"{s.get('nombre','(sin nombre)')} · {s.get('fecha','')}" for s in sessions]
    opciones = ["Todas las sesiones"] + nombres
    sel = st.selectbox("Sesión a analizar", opciones, key="eq-ana-pick")

    if sel == "Todas las sesiones":
        d = df
        mi = None
    else:
        idx = nombres.index(sel)
        s = sessions[idx]
        d = analytics.flatten_events([s])
        mi = {"goles_local": s.get("goles_local", 0), "posesion_local": s.get("posesion_local", 50)}

    # Incluir acciones de equipo (tag) en las métricas
    tm = analytics.team_metrics(d, mi)

    st.markdown("### Indicadores generales")
    r1 = st.columns(4)
    r1[0].metric("Acciones totales", tm["total_acciones"])
    r1[1].metric("Tiros", tm["tiros"], delta=f"{tm['tiros_puerta']} a puerta", delta_color="off")
    r1[2].metric("Goles (tagueados)", tm["goles_accion"])
    r1[3].metric("Pases completados", f"{tm['pct_pase']}%", delta=f"{tm['pases_ok']}/{tm['pases']}", delta_color="off")
    r2 = st.columns(4)
    r2[0].metric("Regates completados", f"{tm['pct_regate']}%", delta=f"{tm['regates_ok']}/{tm['regates']}", delta_color="off")
    r2[1].metric("Recuperaciones", tm["recuperaciones"])
    r2[2].metric("Duelos def. ganados", f"{tm['duelos_def_ok']}/{tm['duelos_def']}")
    r2[3].metric("Tarjetas", f"{tm['amarillas']}A · {tm['rojas']}R", delta=f"{tm['faltas']} faltas", delta_color="off")

    st.divider()
    st.markdown("### Calculadora de posesión")
    st.caption("Estima el % de posesión a partir del tiempo con balón de cada equipo (en segundos o minutos). "
               "Útil para registrar posesión de forma rápida mientras ves el partido.")
    cc = st.columns(3)
    t_local = cc[0].number_input("Tiempo con balón — local", min_value=0.0, value=0.0, step=10.0)
    t_visit = cc[1].number_input("Tiempo con balón — visitante", min_value=0.0, value=0.0, step=10.0)
    total_t = t_local + t_visit
    if total_t > 0:
        pos_local = round(100 * t_local / total_t, 1)
        cc[2].metric("Posesión local", f"{pos_local}%", delta=f"Visitante {round(100-pos_local,1)}%", delta_color="off")
        st.markdown(
            f"<div style='display:flex;height:26px;border-radius:8px;overflow:hidden;border:1px solid #d3ded5'>"
            f"<div style='width:{pos_local}%;background:#1a8f3c;color:#fff;display:flex;align-items:center;"
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

    sessions, df = _load_all_flat()
    if df.empty:
        st.info("No hay acciones registradas todavía. El módulo necesita datos para proyectar.")
        return

    tab_jug, tab_modelo = st.tabs(["Tendencia por jugador", "Modelo ML (acierto de acción)"])

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


# ============================================================================
# ENRUTADO PRINCIPAL
# ============================================================================
render_nav()

section = st.session_state.section
if section == "Sesiones":
    if st.session_state.view == "menu":
        render_menu()
    else:
        render_edit()
elif section == "Gráficos":
    render_graficos()
elif section == "Equipos":
    render_equipos()
elif section == "Predicciones":
    render_predicciones()
