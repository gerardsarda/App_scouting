"""
App de Scouting en Vivo — Scouting Mundial
==========================================
Tagging de acciones de jugadores mientras ves un partido en la TV.
Las sesiones se guardan en Supabase (base de datos en la nube), así que
sobreviven al deploy y son accesibles desde cualquier ordenador.

Cómo ejecutar localmente:
    streamlit run scouting_app.py

Requisitos:
    pip install -r requirements.txt
    Rellenar .streamlit/secrets.toml con SUPABASE_URL y SUPABASE_KEY.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit.components.v1 import html as st_html
import io
import os

import storage

# ----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Scouting Mundial",
    page_icon="◆",
    layout="wide",
)


# ----------------------------------------------------------------------------
# CARGA DEL CSS
# ----------------------------------------------------------------------------
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
RES_ENCONTRADO = [("Encontrado", "Encontrado", "ok"),
                  ("No encontrado", "No encontrado", "bad")]
RES_REMATE = [("Puerta", "A puerta", "ok"),
              ("Gol", "Gol", "gol"),
              ("Fuera", "Fuera/Interceptado", "bad")]
RES_SIMPLE = [("Registrar", "—", "neutral")]

PANEL = {
    "Construcción y pase": [
        ("Pase progresivo", RES_OK_FALLO),
        ("Pase entre líneas", RES_OK_FALLO),
        ("Pase al espacio", RES_OK_FALLO),
        ("Cambio de orientación", RES_OK_FALLO),
        ("Pase filtrado", RES_OK_FALLO),
        ("Pase en conducción", RES_OK_FALLO),
        ("Pase de primera", RES_OK_FALLO),
        ("Pase bajo presión", RES_OK_FALLO),
        ("Pase en largo", RES_OK_FALLO),
        ("Salida de balón", RES_OK_FALLO),
        ("Asistencia", RES_SIMPLE),
        ("Pase clave", RES_OK_FALLO),
        ("Centro lateral", RES_OK_FALLO),
    ],
    "Regate y conducción": [
        ("Regate 1v1", RES_OK_FALLO),
        ("Conducción progresiva", RES_OK_FALLO),
        ("Desborde por banda", RES_OK_FALLO),
        ("Recorte / cambio ritmo", RES_OK_FALLO),
        ("Protección de balón", RES_OK_FALLO),
        ("Pared", RES_OK_FALLO),
        ("Recibe entre líneas", RES_OK_FALLO),
    ],
    "Movimiento sin balón": [
        ("Desmarque de ruptura", RES_ENCONTRADO),
        ("Desmarque de apoyo", RES_ENCONTRADO),
        ("Ataque al palo", RES_ENCONTRADO),
        ("Desmarque de arrastre", RES_ENCONTRADO),
        ("Amplía el campo", RES_ENCONTRADO),
        ("Ofrece línea de pase", RES_ENCONTRADO),
    ],
    "Finalización": [
        ("Remate", RES_REMATE),
        ("Remate de cabeza", RES_REMATE),
        ("Remate desde fuera", RES_REMATE),
        ("Llegada 2ª línea", RES_REMATE),
        ("Generación de ocasión", RES_SIMPLE),
    ],
    "Defensa": [
        ("Entrada / tackle", RES_OK_FALLO),
        ("Intercepción", RES_OK_FALLO),
        ("Recuperación", RES_OK_FALLO),
        ("Despeje", RES_OK_FALLO),
        ("Duelo aéreo def.", RES_OK_FALLO),
        ("Duelo 1v1 def.", RES_OK_FALLO),
        ("Presión fuerza error", RES_OK_FALLO),
        ("Cobertura", RES_OK_FALLO),
        ("Marcaje al hombre", RES_OK_FALLO),
        ("Bloqueo tiro/centro", RES_OK_FALLO),
        ("Repliegue", RES_OK_FALLO),
        ("Falta táctica", RES_SIMPLE),
    ],
    "Transiciones y duelos": [
        ("Transición ofensiva", RES_OK_FALLO),
        ("Transición defensiva", RES_OK_FALLO),
        ("Duelo aéreo of.", RES_OK_FALLO),
        ("Contrapresión", RES_OK_FALLO),
    ],
    "Balón parado y otros": [
        ("Acción a balón parado", RES_OK_FALLO),
        ("Error grave / pérdida", RES_SIMPLE),
    ],
}

ZONAS = ["1er tercio", "2º tercio", "3er tercio"]


# ----------------------------------------------------------------------------
# ESTADO DE LA SESIÓN
# ----------------------------------------------------------------------------
def init_state():
    defaults = {
        # Modo de la app: "menu" (lista de sesiones) o "edit" (panel de tagging)
        "view": "menu",
        "current_session_id": None,
        # Estado del partido en edición
        "events": [],
        "players": [],
        "active_player": None,
        "clock_start": None,
        "clock_offset": 0.0,
        "match_info": {
            "nombre": "",
            "equipo_local": "",
            "equipo_visitante": "",
            "goles_local": 0,
            "goles_visitante": 0,
            "posesion_local": 50,
            "competicion": "Mundial",
            "fecha": datetime.now().strftime("%Y-%m-%d"),
        },
        "final_notes": "",
        "active_zone": "2º tercio",
        # Control de guardado
        "needs_save": False,
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
# GUARDADO AUTOMÁTICO
# ----------------------------------------------------------------------------
def collect_session_data():
    """Empaqueta el estado actual en el formato que espera storage.save_session."""
    mi = st.session_state.match_info
    return {
        "nombre": mi.get("nombre") or f"{mi['equipo_local'] or 'Local'} vs {mi['equipo_visitante'] or 'Visitante'}",
        "competicion": mi["competicion"],
        "fecha": mi["fecha"],
        "equipo_local": mi["equipo_local"],
        "equipo_visitante": mi["equipo_visitante"],
        "goles_local": mi["goles_local"],
        "goles_visitante": mi["goles_visitante"],
        "posesion_local": mi["posesion_local"],
        "jugadores": st.session_state.players,
        "events": st.session_state.events,
        "notas": st.session_state.final_notes,
    }


def autosave():
    """Guarda en Supabase si hay una sesión activa. Llamar tras cada cambio."""
    sid = st.session_state.current_session_id
    if sid:
        storage.save_session(sid, collect_session_data())


def load_into_state(session: dict):
    """Carga una sesión de Supabase en el estado de Streamlit."""
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


def reset_state_for_new():
    """Limpia el estado para una sesión nueva (no toca la base de datos)."""
    st.session_state.current_session_id = None
    st.session_state.events = []
    st.session_state.players = []
    st.session_state.active_player = None
    st.session_state.clock_start = None
    st.session_state.clock_offset = 0.0
    st.session_state.match_info = {
        "nombre": "",
        "equipo_local": "",
        "equipo_visitante": "",
        "goles_local": 0,
        "goles_visitante": 0,
        "posesion_local": 50,
        "competicion": "Mundial",
        "fecha": datetime.now().strftime("%Y-%m-%d"),
    }
    st.session_state.final_notes = ""


# ----------------------------------------------------------------------------
# REGISTRO DE ACCIONES
# ----------------------------------------------------------------------------
def add_event(action, result_code):
    if st.session_state.active_player is None:
        st.toast("Selecciona un jugador primero")
        return
    minute = current_minute()
    st.session_state.events.append({
        "jugador": st.session_state.active_player,
        "minuto": round(minute, 2),
        "minuto_fmt": fmt_minute(minute),
        "accion": action,
        "resultado": result_code,
        "zona": st.session_state.active_zone,
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


# ============================================================================
# VISTA: MENÚ PRINCIPAL — Lista de sesiones
# ============================================================================
def render_menu():
    st.markdown(
        "<div class='hud-kicker'>Scouting Mundial · panel de control</div>",
        unsafe_allow_html=True,
    )
    st.markdown("# Sesiones de análisis")
    st.caption("Cada sesión guarda un partido con sus jugadores y todas las acciones registradas. "
               "Se guarda automáticamente en la nube.")

    # --- Crear nueva sesión ---
    with st.container():
        c1, c2, c3 = st.columns([3, 2, 1])
        nombre = c1.text_input("Nombre de la nueva sesión",
                               placeholder="Ej: España vs Brasil — cuartos",
                               key="new_session_name")
        competicion = c2.text_input("Competición", value="Mundial", key="new_session_comp")
        c3.write(""); c3.write("")
        if c3.button("Crear sesión", type="primary", use_container_width=True):
            if nombre.strip():
                sid = storage.create_session(nombre.strip(), competicion.strip() or "Mundial")
                if sid:
                    # Cargar la recién creada
                    new_sess = storage.load_session(sid)
                    if new_sess:
                        load_into_state(new_sess)
                        st.rerun()
            else:
                st.warning("Pon un nombre a la sesión antes de crearla.")

    st.divider()

    # --- Lista de sesiones existentes ---
    st.markdown("### Sesiones guardadas")
    sessions = storage.list_sessions()
    if not sessions:
        st.info("Aún no tienes sesiones guardadas. Crea la primera arriba.")
        return

    for s in sessions:
        with st.container():
            cols = st.columns([3.5, 1.5, 1.2, 1.2, 1, 1])
            # Nombre + subtítulo (equipos / marcador)
            local = s.get("equipo_local") or ""
            visit = s.get("equipo_visitante") or ""
            if local or visit:
                marcador = f"{local or 'Local'} {s.get('goles_local',0)}–{s.get('goles_visitante',0)} {visit or 'Visitante'}"
            else:
                marcador = "(sin equipos definidos)"
            cols[0].markdown(
                f"**{s['nombre']}**  \n"
                f"<span class='session-sub'>{marcador} · {s.get('competicion','')} · {s.get('fecha','')}</span>",
                unsafe_allow_html=True,
            )
            cols[1].metric("Acciones", s.get("num_events", 0))
            cols[2].metric("Jugadores", s.get("num_jugadores", 0))
            # Última edición
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
                # Confirmación con dos clics: marca el id para borrar
                if st.session_state.get("confirm_delete") == s["id"]:
                    if storage.delete_session(s["id"]):
                        st.session_state.pop("confirm_delete", None)
                        st.rerun()
                else:
                    st.session_state["confirm_delete"] = s["id"]
                    st.warning(f"Pulsa Borrar otra vez para confirmar el borrado de «{s['nombre']}».")
            st.markdown("<hr class='session-sep'>", unsafe_allow_html=True)


# ============================================================================
# VISTA: PANEL DE EDICIÓN (tagging en vivo)
# ============================================================================
def render_edit():
    # --- ATAJOS DE TECLADO (vía JS inyectado) ---
    # Z: deshacer · Espacio: iniciar/pausar cron · 1/2/3: cambiar zona ·
    # Tab o flechas izq/der: cambiar de jugador
    shortcuts_js = """
    <script>
    (function() {
        if (window._scouting_shortcuts_installed) return;
        window._scouting_shortcuts_installed = true;

        const clickByText = (selector, text) => {
            const btns = window.parent.document.querySelectorAll(selector);
            for (const b of btns) {
                if (b.innerText.trim() === text) { b.click(); return true; }
            }
            return false;
        };
        const clickByKeyPrefix = (prefix) => {
            // Pulsa el primer botón del documento cuyo contenedor tiene una clase
            // que empieza por st-key-<prefix>
            const doc = window.parent.document;
            const el = doc.querySelector('[class*="st-key-' + prefix + '"]');
            if (el) {
                const b = el.querySelector('button');
                if (b) { b.click(); return true; }
            }
            return false;
        };

        window.parent.document.addEventListener('keydown', function(e) {
            // Si estás escribiendo en un input/textarea, no interceptar
            const tag = (e.target && e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;

            // Z / z: deshacer
            if (e.key === 'z' || e.key === 'Z') {
                if (clickByKeyPrefix('sc-undo')) e.preventDefault();
                return;
            }
            // Espacio: alternar cronómetro
            if (e.code === 'Space') {
                if (clickByKeyPrefix('sc-clock-toggle')) e.preventDefault();
                return;
            }
            // 1 / 2 / 3: cambiar zona
            if (e.key === '1' || e.key === '2' || e.key === '3') {
                if (clickByKeyPrefix('sc-zone-' + e.key)) e.preventDefault();
                return;
            }
            // Flechas izquierda / derecha: jugador anterior / siguiente
            if (e.key === 'ArrowLeft') {
                if (clickByKeyPrefix('sc-player-prev')) e.preventDefault();
                return;
            }
            if (e.key === 'ArrowRight') {
                if (clickByKeyPrefix('sc-player-next')) e.preventDefault();
                return;
            }
        }, true);
    })();
    </script>
    """
    st_html(shortcuts_js, height=0)

    # --- SIDEBAR ---
    with st.sidebar:
        if st.button("← Volver al menú", use_container_width=True):
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
            # Si cambió algo, guarda
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
            sel = st.radio(
                "Jugador activo",
                st.session_state.players,
                index=st.session_state.players.index(st.session_state.active_player)
                if st.session_state.active_player in st.session_state.players else 0,
            )
            if sel != st.session_state.active_player:
                st.session_state.active_player = sel
        else:
            st.info("Añade al menos un jugador para empezar.")

        st.divider()
        st.subheader("Cronómetro")
        running = st.session_state.clock_start is not None
        estado = "En marcha" if running else "Detenido"
        st.metric("Tiempo de partido", fmt_minute(current_minute()),
                  delta=estado, delta_color="off")
        cc1, cc2 = st.columns(2)
        # Botón único de Iniciar/Pausar para que el atajo Espacio sea inequívoco
        if cc1.button("Iniciar" if not running else "Pausar",
                      use_container_width=True, key="sc-clock-toggle"):
            if running: clock_pause()
            else: clock_start()
            st.rerun()
        if cc2.button("Reiniciar", use_container_width=True):
            clock_reset(); st.rerun()

        st.divider()
        with st.expander("Atajos de teclado", expanded=False):
            st.markdown(
                "- **Z** — Deshacer última acción\n"
                "- **Espacio** — Iniciar / pausar cronómetro\n"
                "- **1 / 2 / 3** — Cambiar zona del campo\n"
                "- **← / →** — Jugador anterior / siguiente"
            )

    # --- CABECERA ---
    mi = st.session_state.match_info
    titulo = f"{mi['equipo_local'] or 'Local'} {mi['goles_local']} - {mi['goles_visitante']} {mi['equipo_visitante'] or 'Visitante'}"
    running = st.session_state.clock_start is not None
    rec = ("<span class='rec-dot'></span>Grabando · " if running else "")
    st.markdown(
        f"<div class='hud-kicker'>{rec}Scouting en vivo · {mi['competicion']}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"# {titulo}")

    # --- CHIPS DE JUGADOR + ZONA + DESHACER ---
    if st.session_state.players:
        st.markdown("<div class='chips-label'>Jugador activo</div>", unsafe_allow_html=True)
        chip_cols = st.columns(min(len(st.session_state.players), 6) + 1)
        # Jugador anterior (atajo flecha izquierda)
        idx_actual = (st.session_state.players.index(st.session_state.active_player)
                      if st.session_state.active_player in st.session_state.players else 0)
        for i, jugador in enumerate(st.session_state.players[:6]):
            is_active = (jugador == st.session_state.active_player)
            kind = "chip-active" if is_active else "chip"
            with chip_cols[i]:
                key = f"sc-player-pick-{i}--{jugador}"
                if st.button(jugador, key=key, use_container_width=True,
                             type=("primary" if is_active else "secondary")):
                    st.session_state.active_player = jugador
                    st.rerun()
        # Botones invisibles para los atajos ←/→
        # Los pintamos en una columna oculta al final para que existan en el DOM
        nav = chip_cols[-1]
        with nav:
            sub_a, sub_b = st.columns(2)
            if sub_a.button("‹", key="sc-player-prev", use_container_width=True,
                            help="Jugador anterior (flecha izquierda)"):
                if st.session_state.players:
                    new_idx = (idx_actual - 1) % len(st.session_state.players)
                    st.session_state.active_player = st.session_state.players[new_idx]
                    st.rerun()
            if sub_b.button("›", key="sc-player-next", use_container_width=True,
                            help="Jugador siguiente (flecha derecha)"):
                if st.session_state.players:
                    new_idx = (idx_actual + 1) % len(st.session_state.players)
                    st.session_state.active_player = st.session_state.players[new_idx]
                    st.rerun()

    bar1, bar2, bar3 = st.columns([2.2, 2, 1])
    with bar1:
        if st.session_state.active_player:
            st.success(f"Jugador: {st.session_state.active_player}  ·  minuto {fmt_minute(current_minute())}")
        else:
            st.warning("Sin jugador asignado — añádelo en el panel lateral.")
    with bar2:
        # Selector de zona como 3 botones que se mapean a atajos 1/2/3
        zc = st.columns(3)
        for i, z in enumerate(ZONAS):
            is_active = (z == st.session_state.active_zone)
            if zc[i].button(z, key=f"sc-zone-{i+1}--{z}", use_container_width=True,
                            type=("primary" if is_active else "secondary")):
                st.session_state.active_zone = z
                st.rerun()
    with bar3:
        if st.button("Deshacer (Z)", use_container_width=True, key="sc-undo"):
            undo_last(); st.rerun()

    st.caption("Zona activa: " + st.session_state.active_zone +
               "  ·  el minuto se sella al pulsar cada acción")

    # --- PANEL DE ACCIONES ---
    def render_action(action, results):
        n = len(results)
        name_w = 3.0 if n <= 2 else 2.2
        cols = st.columns([name_w] + [1.5] * n)
        cols[0].markdown(f"<div class='action-name'>{action}</div>", unsafe_allow_html=True)
        for i, (label, code, kind) in enumerate(results):
            key = f"res-{kind}--{action}--{code}"
            if cols[i + 1].button(label, key=key, use_container_width=True):
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
            render_block(nombre, PANEL[nombre])
            st.markdown("")
    with col_der:
        for nombre in distribucion["der"]:
            render_block(nombre, PANEL[nombre])
            st.markdown("")

    # --- RESUMEN EN VIVO ---
    st.divider()
    st.subheader("Resumen en vivo")
    if st.session_state.events:
        df = pd.DataFrame(st.session_state.events)
        jugadores_con_eventos = sorted(df["jugador"].unique())
        filtro = st.multiselect("Filtrar por jugador", jugadores_con_eventos,
                                default=jugadores_con_eventos)
        df_f = df[df["jugador"].isin(filtro)] if filtro else df
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Conteo por acción y resultado**")
            if not df_f.empty:
                resumen = (df_f.groupby(["accion", "resultado"])
                           .size().reset_index(name="conteo")
                           .sort_values("conteo", ascending=False))
                st.dataframe(resumen, use_container_width=True, hide_index=True, height=280)
        with col_b:
            st.markdown("**Totales por jugador**")
            tot = df_f.groupby("jugador").size().reset_index(name="acciones")
            st.dataframe(tot, use_container_width=True, hide_index=True, height=280)
        st.markdown("**Registro cronológico**")
        st.dataframe(
            df_f[["minuto_fmt", "jugador", "accion", "resultado", "zona"]]
            .sort_values("minuto_fmt"),
            use_container_width=True, hide_index=True, height=260,
        )
    else:
        st.info("Todavía no has registrado ninguna acción. Pulsa los botones del panel para empezar.")

    # --- NOTAS + EXPORTACIÓN ---
    st.divider()
    st.subheader("Notas y exportación")
    notas_old = st.session_state.final_notes
    st.session_state.final_notes = st.text_area(
        "Notas finales del partido", st.session_state.final_notes,
        placeholder="Ej: El 10 baja mucho a recibir, buen primer toque, le falta ritmo en transición defensiva...",
        height=110,
    )
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
        col_order = list(match_cols.keys()) + [
            "minuto", "minuto_decimal", "jugador",
            "accion", "resultado", "zona", "hora_real",
        ]
        if st.session_state.events:
            df = pd.DataFrame(st.session_state.events)
            df = df.rename(columns={"minuto_fmt": "minuto",
                                    "minuto": "minuto_decimal",
                                    "timestamp": "hora_real"})
            for col, val in match_cols.items():
                df[col] = val
            df = df[col_order]
            df.to_csv(output, index=False)
        else:
            df = pd.DataFrame([{**match_cols,
                                "minuto": "", "minuto_decimal": "", "jugador": "",
                                "accion": "", "resultado": "", "zona": "",
                                "hora_real": ""}])[col_order]
            df.to_csv(output, index=False)
        return output.getvalue().encode("utf-8-sig")

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
    nombre_archivo = f"scouting_{mi['equipo_local'] or 'partido'}_{fecha_str}.csv".replace(" ", "_")
    st.download_button(
        "Exportar datos a CSV",
        data=build_csv(),
        file_name=nombre_archivo,
        mime="text/csv",
        use_container_width=True,
        type="primary",
    )
    st.caption(f"Se exportarán {len(st.session_state.events)} acciones. "
               "Cada fila incluye la acción y los datos del partido como columnas.")


# ============================================================================
# ENRUTADO PRINCIPAL
# ============================================================================
if st.session_state.view == "menu":
    render_menu()
else:
    render_edit()
