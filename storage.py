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

    IMPORTANTE: selecciona solo columnas ligeras (NO 'events' ni 'jugadores_info',
    que pueden pesar mucho por las fotos en base64). Traer todo con select('*')
    disparaba un statement timeout en Supabase al crecer los datos."""
    try:
        client = get_client()
        # Columnas ligeras para el listado. Si alguna no existe en una BD antigua,
        # el except de abajo captura el fallo y se reintenta con '*'.
        cols = "id,nombre,fecha,tipo,competicion,equipo_local,equipo_visitante,jugadores,updated_at"
        try:
            res = (client.table("sesiones")
                   .select(cols)
                   .order("updated_at", desc=True)
                   .execute())
        except Exception:
            # Fallback para BD antiguas sin alguna de esas columnas.
            res = (client.table("sesiones")
                   .select("id,nombre,fecha,tipo")
                   .order("fecha", desc=True)
                   .execute())
        rows = res.data or []
        out = []
        for r in rows:
            r_tipo = r.get("tipo") or "jugadores"
            if r_tipo != tipo:
                continue
            r["num_jugadores"] = len(r.get("jugadores") or [])
            out.append(r)
        return out
    except Exception as e:
        st.error(f"Error al listar sesiones: {e}")
        return []


def load_all_sessions(tipo: str | None = None) -> list[dict[str, Any]]:
    """Trae TODAS las sesiones con sus events, pero SIN 'jugadores_info'
    (donde viven las fotos en base64 que disparaban el statement timeout).
    Las fichas se resuelven aparte con resolver_ficha() desde la tabla 'jugadores'.
    Si se indica `tipo`, filtra por ese tipo.
    Usado por Gráficos y Predicciones, que agregan datos entre partidos."""
    try:
        client = get_client()
        # Todas las columnas MENOS jugadores_info (pesada por las fotos).
        cols = ("id,nombre,fecha,tipo,competicion,equipo_local,equipo_visitante,"
                "goles_local,goles_visitante,posesion_local,minuto_descanso,"
                "jugadores,posiciones,events,notas,meta,updated_at")
        try:
            res = (client.table("sesiones").select(cols)
                   .order("fecha", desc=False).execute())
        except Exception:
            # Fallback para BD antiguas con distinto esquema de columnas.
            res = (client.table("sesiones").select("*")
                   .order("fecha", desc=False).execute())
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
        # Meta de la sesión: minuto de descanso y niveles propio/rival.
        if data.get("meta") is not None:
            payload["meta"] = data["meta"]
        # Preservar el tipo solo si se proporciona (no pisar con vacío).
        if data.get("tipo"):
            payload["tipo"] = data["tipo"]
        try:
            client.table("sesiones").update(payload).eq("id", session_id).execute()
        except Exception:
            # Alguna columna opcional puede no existir todavía. Reintentamos quitándolas.
            payload.pop("tipo", None)
            payload.pop("posiciones", None)
            payload.pop("pizarras", None)
            payload.pop("jugadores_info", None)
            payload.pop("meta", None)
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


# ============================================================================
# TABLA jugadores — fichas separadas de las sesiones (foto, bandera, datos)
# ============================================================================
# Las fichas viven aquí, no dentro de cada sesión, para no engordar las
# consultas de partidos con las fotos en base64.

def list_jugadores() -> list[dict[str, Any]]:
    """Devuelve todas las fichas de jugador de la tabla 'jugadores'.
    Si la tabla no existe todavía, devuelve lista vacía (compatibilidad)."""
    try:
        client = get_client()
        res = client.table("jugadores").select("*").order("nombre").execute()
        return res.data or []
    except Exception:
        return []


def get_ficha_jugador(nombre: str) -> dict[str, Any] | None:
    """Devuelve la ficha de un jugador por nombre desde la tabla 'jugadores'.
    None si no existe (o si la tabla aún no está creada)."""
    try:
        client = get_client()
        res = (client.table("jugadores").select("*")
               .eq("nombre", nombre).limit(1).execute())
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:
        return None


def upsert_ficha_jugador(nombre: str, ficha: dict[str, Any]) -> bool:
    """Crea o actualiza la ficha de un jugador en la tabla 'jugadores'.
    Enlaza por nombre. Devuelve True si fue bien."""
    try:
        client = get_client()
        payload = {
            "nombre": nombre,
            "posicion": ficha.get("pos", "") or ficha.get("posicion", ""),
            "equipo": ficha.get("equipo", ""),
            "edad": int(ficha["edad"]) if ficha.get("edad") not in (None, "") else None,
            "foto": ficha.get("foto", ""),
            "bandera": ficha.get("bandera", ""),
            "min_in": int(ficha.get("min_in", 0) or 0),
            "min_out": int(ficha.get("min_out", 90) or 90),
            "updated_at": _now_iso(),
        }
        existente = get_ficha_jugador(nombre)
        if existente:
            client.table("jugadores").update(payload).eq("nombre", nombre).execute()
        else:
            client.table("jugadores").insert(payload).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar la ficha de {nombre}: {e}")
        return False


def resolver_ficha(nombre: str, sesiones: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Devuelve la ficha de un jugador con COMPATIBILIDAD:
      1) primero busca en la tabla nueva 'jugadores'
      2) si no está, la busca en las sesiones (formato antiguo)
    Así lo viejo sigue funcionando durante la transición.
    Devuelve dict (posiblemente vacío) con las claves de ficha."""
    ficha = get_ficha_jugador(nombre)
    if ficha:
        # normalizar a las claves que usa la app (pos, no posicion)
        return {
            "pos": ficha.get("posicion", ""), "equipo": ficha.get("equipo", ""),
            "edad": ficha.get("edad"), "foto": ficha.get("foto", ""),
            "bandera": ficha.get("bandera", ""),
            "min_in": ficha.get("min_in", 0), "min_out": ficha.get("min_out", 90),
        }
    # fallback: buscar la más completa en las sesiones viejas
    if sesiones:
        candidatas = []
        for s in sesiones:
            ji = s.get("jugadores_info") or {}
            if nombre in ji:
                candidatas.append(ji[nombre])
        for c in candidatas:
            if c.get("foto"):
                return c
        for c in candidatas:
            if c.get("bandera"):
                return c
        if candidatas:
            return max(candidatas, key=lambda c: len([v for v in c.values() if v]))
    return {}


def migrar_fichas_desde_sesiones(sesiones: list[dict[str, Any]]) -> dict[str, int]:
    """PASO 5: recorre las sesiones, extrae las fichas más completas de cada
    jugador (con foto/bandera/datos) y las vuelca a la tabla 'jugadores'.
    No borra nada de las sesiones. Devuelve un resumen {migrados, saltados}."""
    mejor_ficha: dict[str, dict] = {}
    for s in sesiones:
        ji = s.get("jugadores_info") or {}
        for nombre, ficha in ji.items():
            if not isinstance(ficha, dict):
                continue
            actual = mejor_ficha.get(nombre)
            # nos quedamos con la ficha que tenga más datos rellenos
            if actual is None or len([v for v in ficha.values() if v]) > len([v for v in actual.values() if v]):
                mejor_ficha[nombre] = ficha
    migrados, saltados = 0, 0
    for nombre, ficha in mejor_ficha.items():
        # no pisar si ya existe en la tabla nueva
        if get_ficha_jugador(nombre):
            saltados += 1
            continue
        if upsert_ficha_jugador(nombre, ficha):
            migrados += 1
    return {"migrados": migrados, "saltados": saltados, "total": len(mejor_ficha)}


def load_fichas_para_migrar() -> list[dict[str, Any]]:
    """Trae SOLO id + jugadores_info de todas las sesiones (sin events), para
    la migración de fichas. Ligero por no traer events; complementa a
    load_all_sessions (que trae events sin jugadores_info)."""
    try:
        client = get_client()
        res = (client.table("sesiones").select("id,jugadores_info")
               .order("fecha", desc=False).execute())
        return res.data or []
    except Exception as e:
        st.error(f"Error al cargar fichas para migrar: {e}")
        return []


# ============================================================================
# FOTOS EN SUPABASE STORAGE — URLs construidas desde nombre/país
# ============================================================================
# Las fotos NO se guardan en la base de datos. Viven en el bucket público
# 'fotos' de Supabase Storage, en subcarpetas jugadores/ y banderas/.
# La app construye la URL a partir del nombre del jugador (foto) y del equipo/
# país (bandera), normalizados. Se suben a mano en el panel de Supabase.

# URL base del bucket público. Ej:
#   https://XXXXX.supabase.co/storage/v1/object/public/fotos/
# Se puede sobreescribir con st.secrets["FOTOS_BASE_URL"] si se prefiere.
_FOTOS_BASE_URL_DEFAULT = "https://xcqlxeyfdmenulbkkrhn.supabase.co/storage/v1/object/public/fotos/"


def _fotos_base_url() -> str:
    try:
        u = st.secrets.get("FOTOS_BASE_URL", "")
        if u:
            return u.rstrip("/") + "/"
    except Exception:
        pass
    return _FOTOS_BASE_URL_DEFAULT.rstrip("/") + "/"


def _slug(texto: str) -> str:
    """Normaliza un texto para nombre de archivo: minúsculas, sin tildes,
    espacios y guiones a '_'. 'Costa de Marfil' -> 'costa_de_marfil'."""
    import unicodedata, re
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = t.lower().strip()
    t = re.sub(r"[\s\-]+", "_", t)
    t = re.sub(r"[^a-z0-9_]", "", t)
    return t


def _variantes_ext(base_sin_ext: str) -> list[str]:
    """Devuelve las URLs candidatas probando varias extensiones, empezando por
    .PNG (mayúsculas, como las sube Supabase) y cayendo a otras variantes."""
    exts = [".PNG", ".png", ".JPG", ".jpg", ".JPEG", ".jpeg"]
    return [base_sin_ext + e for e in exts]


def url_foto_jugador(nombre: str) -> dict:
    """URLs candidatas de la foto de un jugador (bucket 'fotos', sin subcarpetas).
    Prueba varias extensiones. Nombre normalizado (sin tildes, minúsculas)."""
    base = _fotos_base_url()
    slug = _slug(nombre)
    if not slug:
        return {"cands": []}
    return {"cands": _variantes_ext(f"{base}{slug}")}


def url_bandera(pais: str) -> dict:
    """URLs candidatas de la bandera (bucket 'fotos', sin subcarpetas)."""
    base = _fotos_base_url()
    slug = _slug(pais)
    if not slug:
        return {"cands": []}
    return {"cands": _variantes_ext(f"{base}{slug}")}
