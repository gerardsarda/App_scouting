"""
storage.py — Capa de almacenamiento contra Supabase
====================================================
Toda la lógica de "hablar con la base de datos" vive aquí, separada de la app.
Si en el futuro cambias de Supabase a otra cosa, solo se toca este archivo.

Funciones públicas:
    get_client()            -> cliente de Supabase (cacheado)
    list_sessions()         -> lista de sesiones {id, nombre, fecha, ...}
    load_session(id)        -> dict completo de la sesión
    create_session(...)     -> crea una sesión vacía y devuelve su id
    save_session(id, data)  -> guarda el estado completo
    delete_session(id)      -> borra una sesión

La tabla `sesiones` debe existir en Supabase con la estructura:
    id uuid primary key, nombre text, competicion text, fecha text,
    equipo_local text, equipo_visitante text, goles_local int,
    goles_visitante int, posesion_local int, jugadores jsonb,
    events jsonb, notas text, created_at timestamptz, updated_at timestamptz
"""

from __future__ import annotations
import streamlit as st
from datetime import datetime, timezone
from typing import Any


@st.cache_resource
def get_client():
    """Crea (una sola vez) y cachea el cliente de Supabase."""
    from supabase import create_client
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL y/o SUPABASE_KEY en .streamlit/secrets.toml. "
            "Rellena las dos claves antes de usar la app."
        )
    return create_client(url, key)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_sessions(tipo: str = "jugadores") -> list[dict[str, Any]]:
    """Devuelve la lista de sesiones del tipo indicado, más recientes primero.
    `tipo` puede ser 'jugadores' o 'equipo'. Solo trae campos resumen.
    Las sesiones antiguas sin columna 'tipo' se consideran 'jugadores'.

    Usa select('*') a propósito: así la app no se rompe si la columna 'tipo'
    aún no se ha creado en la base de datos (se trataría todo como 'jugadores')."""
    try:
        client = get_client()
        res = (client.table("sesiones")
               .select("*")
               .order("updated_at", desc=True)
               .execute())
        rows = res.data or []
        out = []
        for r in rows:
            # Sesiones sin tipo (columna inexistente o vacía) cuentan como 'jugadores'.
            r_tipo = r.get("tipo") or "jugadores"
            if r_tipo != tipo:
                continue
            r["num_events"] = len(r.get("events") or [])
            r["num_jugadores"] = len(r.get("jugadores") or [])
            r.pop("events", None)
            out.append(r)
        return out
    except Exception as e:
        st.error(f"Error al listar sesiones: {e}")
        return []


def load_all_sessions(tipo: str | None = None) -> list[dict[str, Any]]:
    """Trae TODAS las sesiones completas (con events y jugadores).
    Si se indica `tipo` ('jugadores' o 'equipo'), filtra por ese tipo.
    Usado por Gráficos y Predicciones, que agregan datos entre partidos."""
    try:
        client = get_client()
        res = (client.table("sesiones")
               .select("*")
               .order("fecha", desc=False)
               .execute())
        rows = res.data or []
        if tipo is None:
            return rows
        return [r for r in rows if (r.get("tipo") or "jugadores") == tipo]
    except Exception as e:
        st.error(f"Error al cargar todas las sesiones: {e}")
        return []


def load_session(session_id: str) -> dict[str, Any] | None:
    """Carga una sesión completa por id."""
    try:
        client = get_client()
        res = (client.table("sesiones")
               .select("*")
               .eq("id", session_id)
               .single()
               .execute())
        return res.data
    except Exception as e:
        st.error(f"Error al cargar la sesión: {e}")
        return None


def create_session(nombre: str, competicion: str = "Mundial",
                   fecha: str | None = None, tipo: str = "jugadores") -> str | None:
    """Crea una sesión nueva vacía y devuelve su id.
    `tipo` marca si es de 'jugadores' o de 'equipo'.
    Si la columna 'tipo' aún no existe en la tabla, reintenta sin ella."""
    try:
        client = get_client()
        payload = {
            "nombre": nombre,
            "competicion": competicion,
            "fecha": fecha or datetime.now().strftime("%Y-%m-%d"),
            "tipo": tipo,
            "equipo_local": "",
            "equipo_visitante": "",
            "goles_local": 0,
            "goles_visitante": 0,
            "posesion_local": 50,
            "jugadores": [],
            "events": [],
            "notas": "",
            "updated_at": _now_iso(),
        }
        try:
            res = client.table("sesiones").insert(payload).execute()
        except Exception:
            # Posible columna 'tipo' inexistente: reintentar sin ella.
            payload.pop("tipo", None)
            res = client.table("sesiones").insert(payload).execute()
        if res.data:
            return res.data[0]["id"]
        return None
    except Exception as e:
        st.error(f"Error al crear la sesión: {e}")
        return None


def save_session(session_id: str, data: dict[str, Any]) -> bool:
    """Guarda el estado completo de una sesión.
    `data` debe contener las claves: nombre, competicion, fecha, equipo_local,
    equipo_visitante, goles_local, goles_visitante, posesion_local,
    jugadores (list), events (list), notas (str).
    """
    try:
        client = get_client()
        payload = {
            "nombre": data.get("nombre", "Sin nombre"),
            "competicion": data.get("competicion", ""),
            "fecha": data.get("fecha", ""),
            "equipo_local": data.get("equipo_local", ""),
            "equipo_visitante": data.get("equipo_visitante", ""),
            "goles_local": int(data.get("goles_local", 0)),
            "goles_visitante": int(data.get("goles_visitante", 0)),
            "posesion_local": int(data.get("posesion_local", 50)),
            "jugadores": data.get("jugadores", []),
            "events": data.get("events", []),
            "notas": data.get("notas", ""),
            "updated_at": _now_iso(),
        }
        # Posiciones de los jugadores (dict nombre->código). Va dentro de un
        # campo jsonb; si la columna no existe, se reintenta sin él más abajo.
        if data.get("posiciones") is not None:
            payload["posiciones"] = data["posiciones"]
        if data.get("jugadores_info") is not None:
            payload["jugadores_info"] = data["jugadores_info"]
        # Pizarras tácticas (dict formacion__fase -> lista de fichas).
        if data.get("pizarras") is not None:
            payload["pizarras"] = data["pizarras"]
        # Preservar el tipo solo si se proporciona (no pisar con vacío).
        if data.get("tipo"):
            payload["tipo"] = data["tipo"]
        try:
            client.table("sesiones").update(payload).eq("id", session_id).execute()
        except Exception:
            # Alguna columna opcional ('tipo', 'posiciones', 'pizarras') puede no
            # existir todavía en la tabla. Reintentamos quitándolas.
            payload.pop("tipo", None)
            payload.pop("posiciones", None)
            payload.pop("pizarras", None)
            payload.pop("jugadores_info", None)
            client.table("sesiones").update(payload).eq("id", session_id).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar la sesión: {e}")
        return False


def delete_session(session_id: str) -> bool:
    """Borra una sesión."""
    try:
        client = get_client()
        client.table("sesiones").delete().eq("id", session_id).execute()
        return True
    except Exception as e:
        st.error(f"Error al borrar la sesión: {e}")
        return False
