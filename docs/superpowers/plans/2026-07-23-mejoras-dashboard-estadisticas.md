# Mejoras dashboard + sección Estadísticas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar las 6 mejoras aprobadas: nueva sección Estadísticas (1), "TODOS" en el radar + rename (2), mapas sensibles a Aciertos (3), filtro por nivel absoluto de rival + fix de la nota (4), franjas de prórroga (5) y evolución por-90 (6).

**Architecture:** El motor vive en `analytics.py` (funciones puras, testeadas con pytest contra DataFrames); la UI en `scouting_app.py` (Streamlit, HTML propio con tema neón, NUNCA `st.dataframe`). El punto 4 se corrige en un solo sitio (`flatten_events` pasa el nivel a perspectiva del jugador) y de ahí beben el filtro nuevo y la nota. El MCP (`../scouting-mcp/dossier.py`) replica el fix del punto 4.

**Tech Stack:** Python, pandas, numpy, Streamlit; pytest para tests; SVG/HTML inline para gráficos.

## Global Constraints

- **NUNCA `st.dataframe`** en secciones con tema: pinta sobre canvas Glide y el CSS del tema no entra (Fase 4/5). Tablas = HTML propio con clases prefijadas.
- **pytest NO está en `requirements.txt`** a propósito. Local: `pip install pytest`; correr con `python -m pytest tests/ -q`.
- **Verificar SIEMPRE**: sintaxis (`python -c "import ast, sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" <archivo>`) y, en cambios de UI, arranque manual de la app.
- **Al tocar `analytics.py`**, sincronizar la parte equivalente del MCP (aquí, solo el punto 4 → `dossier.py`).
- Colores neón (ya definidos en `scouting_app.py`): `NEON_OK=#15ff66`, `NEON_BAD=#ff2d55`, `NEON_GOLD=#ffcc00`, `NEON_ORANGE=#ff7a1a`, `NEON_SKY=#38bdf8`, `TXT_LO_SVG=#8b93a1`, `PANEL_SVG=#15171c`, `INK=#ffffff`.
- Español en toda la UI y los comentarios.
- El % de acierto sigue sin admitir negativos (no se toca la clasificación).
- **Antes de empezar**: estamos en `main` (rama por defecto). Crear rama `feat/mejoras-dashboard-estadisticas` y trabajar ahí. NO hacer `git push` hasta que el usuario lo pida (push despliega en Streamlit Cloud).

**Nota sobre tests nuevos:** todos van en un archivo nuevo `tests/test_mejoras_2026_07_23.py` con estos dos helpers al principio (se usan en varias tareas):

```python
# -*- coding: utf-8 -*-
"""Tests de las mejoras del 2026-07-23 (dashboard + sección Estadísticas)."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


def _df(filas, **cols):
    """(jugador, accion, resultado) -> df con las columnas que usa el motor.
    cols permite fijar columnas extra (zona_x, minuto...) para todas las filas."""
    base = []
    for j, a, r in filas:
        fila = {"session_id": "s1", "sesion": "S1", "fecha": "2026-01-01",
                "jugador": j, "posicion": "MC", "accion": a, "resultado": r,
                "zona_x": 1, "zona_y": 1, "minuto": 10.0}
        fila.update(cols)
        base.append(fila)
    df = pd.DataFrame(base)
    df["exito"] = df.apply(lambda x: analytics.is_success(x["resultado"], x["accion"]), axis=1)
    df["intento"] = df.apply(lambda x: analytics.is_attempt(x["resultado"], x["accion"]), axis=1)
    df["peso"] = df.apply(lambda x: analytics.success_weight(x["resultado"], x["accion"]), axis=1)
    return df


def _sesion(jug, equipo, local, visit, nivel_propio, nivel_rival, eventos,
            sid=None, min_in=0, min_out=90):
    """Sesión mínima para flatten_events. nivel_propio/nivel_rival se guardan
    tal cual en meta (= niveles de LOCAL/VISITANTE, como en la BD real)."""
    return {"id": sid or f"{local}-{visit}", "nombre": f"{local} vs {visit}",
            "fecha": "2026-01-01", "equipo_local": local, "equipo_visitante": visit,
            "meta": {"nivel_propio": nivel_propio, "nivel_rival": nivel_rival},
            "jugadores_info": {jug: {"equipo": equipo, "min_in": min_in, "min_out": min_out}},
            "events": eventos}
```

---

## Task 1: P4 — flatten_events en perspectiva del jugador + helpers de filtro

**Files:**
- Modify: `analytics.py` (`flatten_events`, ~280-370; añadir 2 helpers tras `filtrar_sesiones_por_contexto`, ~1866)
- Test: `tests/test_mejoras_2026_07_23.py`

**Interfaces:**
- Produces:
  - `flatten_events(sessions, equipos_principales=None) -> DataFrame` (mismo interfaz; las columnas `nivel_propio`/`nivel_rival` pasan a estar en **perspectiva del jugador**).
  - `niveles_rival_de_jugador(df, jugador) -> dict[str, str]` (`{session_id: nivel_rival}`).
  - `filtrar_por_nivel_rival(df, jugador, nivel) -> DataFrame`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_mejoras_2026_07_23.py` (tras los helpers):

```python
# --- P4: nivel de rival en perspectiva del jugador --------------------------

def test_nivel_rival_visitante_se_intercambia():
    # Nusa juega en Noruega, de VISITANTE en Irak vs Noruega. meta guarda
    # nivel_propio=Bajo (Irak, local) y nivel_rival=Alto (Noruega, visitante).
    s = _sesion("Nusa", "Noruega", "Irak", "Noruega", "Bajo", "Alto",
                [{"jugador": "Nusa", "accion": "Regate 1v1", "resultado": "Correcto",
                  "minuto": 10, "zona_x": 2, "zona_y": 1}])
    df = analytics.flatten_events([s])
    assert df.iloc[0]["nivel_propio"] == "Alto"   # su equipo (Noruega)
    assert df.iloc[0]["nivel_rival"] == "Bajo"    # el rival (Irak)


def test_nivel_rival_local_no_se_toca():
    s = _sesion("Irankunda", "Australia", "Australia", "Turquia", "Medio", "Alto",
                [{"jugador": "Irankunda", "accion": "Regate 1v1", "resultado": "Correcto",
                  "minuto": 10, "zona_x": 2, "zona_y": 1}])
    df = analytics.flatten_events([s])
    assert df.iloc[0]["nivel_propio"] == "Medio"
    assert df.iloc[0]["nivel_rival"] == "Alto"


def test_niveles_rival_de_jugador_y_filtro():
    s1 = _sesion("Nusa", "Noruega", "Irak", "Noruega", "Bajo", "Alto",
                 [{"jugador": "Nusa", "accion": "Regate 1v1", "resultado": "Correcto",
                   "minuto": 10, "zona_x": 2, "zona_y": 1}], sid="p1")
    s2 = _sesion("Nusa", "Noruega", "Noruega", "Francia", "Alto", "Élite",
                 [{"jugador": "Nusa", "accion": "Regate 1v1", "resultado": "Fallo",
                   "minuto": 20, "zona_x": 2, "zona_y": 1}], sid="p2")
    df = analytics.flatten_events([s1, s2])
    niveles = analytics.niveles_rival_de_jugador(df, "Nusa")
    assert niveles == {"p1": "Bajo", "p2": "Élite"}
    d = analytics.filtrar_por_nivel_rival(df, "Nusa", "Élite")
    assert set(d["session_id"].unique()) == {"p2"}
    # 'Todos' o vacío no filtra
    assert len(analytics.filtrar_por_nivel_rival(df, "Nusa", "Todos")) == 2
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -q`
Expected: FAIL (`AttributeError: module 'analytics' has no attribute 'niveles_rival_de_jugador'`, y las aserciones de swap fallan porque hoy no corrige).

- [ ] **Step 3: Corregir `flatten_events`**

En `analytics.py`, dentro del bucle `for ev in events:`, DESPUÉS de calcular `equipo_jug` (línea ~333) y ANTES de `row.update({...})`, insertar:

```python
            # NIVEL EN PERSPECTIVA DEL JUGADOR. meta guarda nivel_propio=LOCAL y
            # nivel_rival=VISITANTE (verificado 2026-07-23 contra la BD entera).
            # Para un ojeado que juega de VISITANTE hay que INTERCAMBIARLOS, o el
            # filtro de rival y la palanca 3 de la nota salen invertidos. En
            # sesiones con dos ojeados en equipos contrarios la corrección es por
            # evento, así que cada uno sale bien.
            _niv_local = sess_meta["nivel_propio"]
            _niv_visit = sess_meta["nivel_rival"]
            _ej = _norm_equipo(equipo_jug)
            if _ej and _ej == _norm_equipo(sess_meta["equipo_visitante"]):
                _niv_propio_jug, _niv_rival_jug = _niv_visit, _niv_local
            else:  # local o indeterminado: se deja como está
                _niv_propio_jug, _niv_rival_jug = _niv_local, _niv_visit
```

Y en el `row.update({...})` que sigue, AÑADIR estas dos claves (sobrescriben las que venían de `sess_meta`):

```python
                "nivel_propio": _niv_propio_jug,
                "nivel_rival": _niv_rival_jug,
```

- [ ] **Step 4: Añadir los dos helpers**

En `analytics.py`, justo después de `filtrar_sesiones_por_contexto` (~1866), añadir:

```python
def niveles_rival_de_jugador(df, jugador):
    """{session_id: nivel_rival} del jugador, en SU perspectiva (la columna
    nivel_rival ya viene corregida local<->visitante por flatten_events). Un
    valor por partido."""
    d = df[df["jugador"] == jugador]
    out = {}
    for sid, g in d.groupby("session_id"):
        out[sid] = _nivel_partido(g, "nivel_rival")
    return out


def filtrar_por_nivel_rival(df, jugador, nivel):
    """Deja las sesiones donde el rival del jugador tuvo ese nivel ABSOLUTO
    (Élite/Alto/Medio/Bajo). nivel vacío o 'Todos' no filtra."""
    if not nivel or nivel == "Todos":
        return df
    sids = {sid for sid, nr in niveles_rival_de_jugador(df, jugador).items()
            if nr == nivel}
    return df[df["session_id"].isin(sids)]
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -q`
Expected: PASS.

- [ ] **Step 6: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('analytics.py', encoding='utf-8').read())"`
Expected: sin salida (OK).

- [ ] **Step 7: Commit**

```bash
git add analytics.py tests/test_mejoras_2026_07_23.py
git commit -m "fix(nivel-rival): perspectiva del jugador en flatten_events + helpers de filtro"
```

---

## Task 2: P4 — filtro por nivel absoluto del rival en el dashboard

**Files:**
- Modify: `scouting_app.py` (sidebar ~2107-2118; bloque de filtro ~2133-2148)

**Interfaces:**
- Consumes: `analytics.niveles_rival_de_jugador`, `analytics.filtrar_por_nivel_rival` (Task 1).

- [ ] **Step 1: Sustituir el control del sidebar**

En `scouting_app.py`, reemplazar el `st.radio` de contexto (`~2108-2112`):

```python
        ctx_lbl = st.radio("Nivel del rival (vs tu equipo)",
                           ["Todos", "Rival superior", "Rival similar", "Rival inferior"],
                           key="dash-ctx",
                           help="Filtra los partidos según si el rival era de nivel "
                                "superior, similar o inferior al equipo propio.")
```

por:

```python
        # Filtro por nivel ABSOLUTO del rival (en perspectiva del jugador; los
        # niveles ya vienen corregidos local<->visitante por flatten_events).
        _niv_presentes = set(analytics.niveles_rival_de_jugador(d_jug, jugador).values())
        _orden_niv = ["Élite", "Alto", "Medio", "Bajo"]
        niv_opts = ["Todos"] + [n for n in _orden_niv if n in _niv_presentes]
        niv_lbl = st.radio("Nivel del rival", niv_opts, key="dash-ctx",
                           help="Filtra los partidos por el nivel absoluto del rival "
                                "en cada partido (élite/alto/medio/bajo).")
```

- [ ] **Step 2: Sustituir el mapeo y el bloque de filtro**

Borrar la línea del mapeo antiguo (`~2117-2118`):

```python
    ctx = {"Todos": "todos", "Rival superior": "superior",
           "Rival similar": "similar", "Rival inferior": "inferior"}[ctx_lbl]
```

Y reemplazar el bloque de filtro por contexto (`~2133-2148`, desde `if ctx != "todos":` hasta el `return` de ese bloque) por:

```python
    # Filtrar por nivel absoluto del rival. El conteo es de los partidos DEL
    # JUGADOR seleccionado con ese nivel de rival, no del total de la base.
    if niv_lbl != "Todos":
        sids_niv = {sid for sid, nr in analytics.niveles_rival_de_jugador(df, jugador).items()
                    if nr == niv_lbl}
        n_part = len(sids_niv)
        st.info(f"Nivel del rival: **{niv_lbl}** → {jugador} jugó {n_part} partido(s) así. "
                + ("Muestra muy pequeña, resultado orientativo." if 0 < n_part <= 2 else ""))
        df = df[df["session_id"].isin(sids_niv)]
        if df[df["jugador"] == jugador].empty:
            st.warning(f"{jugador} no tiene partidos con rival de nivel {niv_lbl}.")
            return
```

- [ ] **Step 3: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('scouting_app.py', encoding='utf-8').read())"`
Expected: sin salida (OK).

- [ ] **Step 4: Smoke manual**

Arrancar la app (`streamlit run scouting_app.py` o skill `run`), ir a Gráficos, elegir Nusa, comprobar que el selector "Nivel del rival" ofrece niveles absolutos y que al elegir uno el conteo y los gráficos cambian. Verificar un jugador visitante (Nusa/Maza) y uno local.

- [ ] **Step 5: Commit**

```bash
git add scouting_app.py
git commit -m "feat(dashboard): filtro por nivel absoluto del rival (sustituye superior/similar/inferior)"
```

---

## Task 3: P4 — sincronizar el MCP (dossier.py) con la perspectiva del jugador

**Files:**
- Modify: `../scouting-mcp/dossier.py` (`construir_dossier`, ~187-199)

**Interfaces:**
- Consumes: `nota.nota_de_eventos(eventos, nivel_propio, nivel_rival)` (ya existe; recibe los niveles ya corregidos).

- [ ] **Step 1: Corregir el nivel antes de la nota y del contexto**

En `../scouting-mcp/dossier.py`, dentro de `construir_dossier`, reemplazar el bloque (`~187-192`):

```python
        meta = s.get("meta") or {}
        # Nota del partido con las 3 palancas (el nivel de rival es por partido).
        nota_part = nota.nota_de_eventos(evs_jug,
                                         meta.get("nivel_propio") or "Medio",
                                         meta.get("nivel_rival") or "Medio")
```

por:

```python
        meta = s.get("meta") or {}
        # NIVEL EN PERSPECTIVA DEL JUGADOR. meta guarda nivel_propio=LOCAL y
        # nivel_rival=VISITANTE; si el jugador juega de visitante hay que
        # intercambiarlos, o la palanca 3 de la nota sale invertida (mismo fix
        # que analytics.flatten_events en la app, 2026-07-23).
        _niv_local = meta.get("nivel_propio") or "Medio"
        _niv_visit = meta.get("nivel_rival") or "Medio"
        if eq_part and eq_part.strip().lower() == str(s.get("equipo_visitante", "")).strip().lower():
            _niv_propio_jug, _niv_rival_jug = _niv_visit, _niv_local
        else:
            _niv_propio_jug, _niv_rival_jug = _niv_local, _niv_visit
        # Nota del partido con las 3 palancas (el nivel de rival es por partido).
        nota_part = nota.nota_de_eventos(evs_jug, _niv_propio_jug, _niv_rival_jug)
```

Y en el dict `contextos.append({...})`, cambiar (`~198-199`):

```python
            "nivel_rival": meta.get("nivel_rival", ""),
            "nivel_propio": meta.get("nivel_propio", ""),
```

por:

```python
            "nivel_rival": _niv_rival_jug,
            "nivel_propio": _niv_propio_jug,
```

- [ ] **Step 2: Verificar sintaxis con el intérprete REAL del servidor**

Run (ajustar la ruta del Python313 del `claude_desktop_config.json`):
`& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -c "import ast; ast.parse(open('../scouting-mcp/dossier.py', encoding='utf-8').read())"`
Expected: sin salida (OK).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "fix(mcp): dossier pasa el nivel de rival en perspectiva del jugador"
```

Nota: el MCP no está en este repo; el commit registra solo el spec/plan. Recordar al usuario **reiniciar el MCP** para tomar el cambio.

---

## Task 4: P3 — mapas de calor y de acciones sensibles a "Aciertos"

**Files:**
- Modify: `analytics.py` (`zone_grid_counts`, ~582)
- Modify: `scouting_app.py` (llamadas ~2295 y ~2302)
- Test: `tests/test_mejoras_2026_07_23.py`

**Interfaces:**
- Produces: `zone_grid_counts(df, solo_exito=False) -> np.ndarray`.

- [ ] **Step 1: Test que falla**

Añadir a `tests/test_mejoras_2026_07_23.py`:

```python
# --- P3: mapas sensibles a aciertos -----------------------------------------

def test_zone_grid_solo_exito_cuenta_solo_aciertos():
    df = _df([("Ana", "Regate 1v1", "Correcto"), ("Ana", "Regate 1v1", "Fallo")],
             zona_x=2, zona_y=1)
    assert int(analytics.zone_grid_counts(df).sum()) == 2
    assert int(analytics.zone_grid_counts(df, solo_exito=True).sum()) == 1
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py::test_zone_grid_solo_exito_cuenta_solo_aciertos -q`
Expected: FAIL (`zone_grid_counts() got an unexpected keyword argument 'solo_exito'`).

- [ ] **Step 3: Añadir el parámetro**

En `analytics.py`, cambiar la firma y el arranque de `zone_grid_counts`:

```python
def zone_grid_counts(df: pd.DataFrame, solo_exito: bool = False) -> np.ndarray:
    """Devuelve una matriz 3x3 (filas = bandas, cols = tercios) con conteos.

    solo_exito=True cuenta SOLO las acciones con éxito (para el modo Aciertos del
    dashboard); si no, cuenta todas.

    Soporta dos formatos de zona:
      - Nuevo: columnas zona_x (0-2) y zona_y (0-2) en cada evento.
      - Antiguo: solo 'zona' con "1er/2º/3er tercio" -> se coloca en la fila central.
    """
    grid = np.zeros((3, 3), dtype=int)
    if df.empty:
        return grid
    if solo_exito and "exito" in df.columns:
        df = df[df["exito"]]
```

(El resto de la función se queda igual.)

- [ ] **Step 4: Correr y verificar que pasa**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py::test_zone_grid_solo_exito_cuenta_solo_aciertos -q`
Expected: PASS.

- [ ] **Step 5: Cablear las dos llamadas del dashboard**

En `scouting_app.py`, en el mapa de calor (`~2295`) y en el mapa de acciones (`~2302`), cambiar:

```python
        grid = analytics.zone_grid_counts(df[df["jugador"] == jugador])
```

por (idéntico en ambos sitios):

```python
        grid = analytics.zone_grid_counts(
            df[df["jugador"] == jugador],
            solo_exito=modo in ("aciertos", "aciertos90"))
```

- [ ] **Step 6: Sintaxis**

Run: `python -c "import ast; ast.parse(open('analytics.py', encoding='utf-8').read())"` y lo mismo con `scouting_app.py`.
Expected: sin salida.

- [ ] **Step 7: Commit**

```bash
git add analytics.py scouting_app.py tests/test_mejoras_2026_07_23.py
git commit -m "fix(mapas): contar solo aciertos en modo Aciertos (mapa de calor y de acciones)"
```

---

## Task 5: P5 — franjas de prórroga en influencia por minuto (90-105 y 105+)

**Files:**
- Modify: `analytics.py` (`FRANJAS_15`/`FRANJA_LABELS` ~1871-1872; `influencia_por_minuto` caso vacío ~1888)
- Test: `tests/test_mejoras_2026_07_23.py`

- [ ] **Step 1: Test que falla**

```python
# --- P5: franjas de prórroga ------------------------------------------------

def test_franjas_incluyen_prorroga():
    assert (90, 105) in analytics.FRANJAS_15
    assert (105, 200) in analytics.FRANJAS_15
    assert analytics.FRANJA_LABELS[-2:] == ["90-105", "105+"]


def test_influencia_separa_105():
    df = _df([("Ana", "Regate 1v1", "Correcto"), ("Ana", "Regate 1v1", "Correcto")])
    df.loc[0, "minuto"] = 95.0
    df.loc[1, "minuto"] = 110.0
    r = analytics.influencia_por_minuto(df, "Ana")
    i1 = analytics.FRANJA_LABELS.index("90-105")
    i2 = analytics.FRANJA_LABELS.index("105+")
    assert r["volumen"][i1] == 1
    assert r["volumen"][i2] == 1
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -k franja -q` y `-k influencia_separa`.
Expected: FAIL.

- [ ] **Step 3: Partir la franja**

En `analytics.py` (~1871-1872):

```python
FRANJAS_15 = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90),
              (90, 105), (105, 200)]
FRANJA_LABELS = ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90",
                 "90-105", "105+"]
```

En el caso vacío de `influencia_por_minuto` (~1888), sustituir los `7` hardcodeados:

```python
        return {"labels": FRANJA_LABELS, "volumen": [0] * len(FRANJAS_15),
                "eficiencia": [None] * len(FRANJAS_15),
                "peligro": [[] for _ in range(len(FRANJAS_15))]}
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -k "franja or influencia_separa" -q`
Expected: PASS.

- [ ] **Step 5: Sintaxis + commit**

Run: `python -c "import ast; ast.parse(open('analytics.py', encoding='utf-8').read())"`

```bash
git add analytics.py tests/test_mejoras_2026_07_23.py
git commit -m "feat(influencia): franjas 90-105 y 105+ para prórroga/descuento"
```

---

## Task 6: P6 — evolución partido a partido compatible con Por-90

**Files:**
- Modify: `analytics.py` (`serie_temporal` ~1341; nuevo helper `_minutos_en_grupo`)
- Modify: `scouting_app.py` (`linea_temporal_svg` ~1074-1080 y ~1116; mapeo de modo ~2339-2345)
- Test: `tests/test_mejoras_2026_07_23.py`

**Interfaces:**
- Produces: `serie_temporal(df, jugador, acciones, modo, clases=None)` acepta `modo` ∈ `{"totales","aciertos","totales90","aciertos90"}`.

- [ ] **Step 1: Test que falla**

```python
# --- P6: evolución por-90 ---------------------------------------------------

def test_serie_temporal_por90_usa_minutos_del_partido():
    df = _df([("Ana", "Pase progresivo", "Correcto"),
              ("Ana", "Pase progresivo", "Fallo")])
    # 2 acciones en 45 min de ese partido -> 4.0 por 90
    df["jugador_info"] = [{"min_in": 0, "min_out": 45}, {"min_in": 0, "min_out": 45}]
    serie = analytics.serie_temporal(df, "Ana", ["Pase progresivo"], "totales90")
    assert len(serie) == 1
    assert serie[0]["valor"] == 4.0
    # aciertos90: 1 acierto en 45 min -> 2.0
    serie_ac = analytics.serie_temporal(df, "Ana", ["Pase progresivo"], "aciertos90")
    assert serie_ac[0]["valor"] == 2.0
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -k serie_temporal_por90 -q`
Expected: FAIL (hoy `modo="totales90"` cae al `else` y da el conteo crudo 2.0, no 4.0).

- [ ] **Step 3: Helper de minutos por grupo**

En `analytics.py`, justo antes de `serie_temporal` (~1341), añadir:

```python
def _minutos_en_grupo(g):
    """Minutos del jugador en el partido del grupo g (un session_id). De
    jugador_info (min_in/min_out) si está; si no, el último minuto con acción."""
    if "jugador_info" in g.columns and len(g):
        info = g["jugador_info"].iloc[0]
        if isinstance(info, dict) and (info.get("min_in") is not None
                                       or info.get("min_out") is not None):
            mi = int(info.get("min_in", 0))
            mo = int(info.get("min_out", 90))
            return max(0, mo - mi)
    return int(g["minuto"].max()) if not g.empty else 0
```

- [ ] **Step 4: Extender `serie_temporal`**

En `serie_temporal`, reemplazar el cálculo del valor (el bloque `if modo == "totales": ... else: ...`, ~1357-1361) por:

```python
        if modo == "totales":
            val = float(len(g))
        elif modo in ("totales90", "aciertos90"):
            mins = _minutos_en_grupo(g)
            base = len(g) if modo == "totales90" else int(g["exito"].sum())
            val = round(base * 90.0 / mins, 1) if mins > 0 else 0.0
        else:  # aciertos (% ponderado)
            inten = g[g["intento"]]
            val = round(100 * g["peso"].sum() / len(inten), 1) if len(inten) else 0.0
```

Actualizar el docstring para mencionar los modos `totales90`/`aciertos90`.

- [ ] **Step 5: Correr y verificar que pasa**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -k serie_temporal_por90 -q`
Expected: PASS.

- [ ] **Step 6: `linea_temporal_svg` — escala y etiquetas del /90**

En `scouting_app.py`, en `linea_temporal_svg`, el cálculo de `vmax` (~1075-1080) ya cae al `else` (max*1.15) para los modos `*90` porque no son `"aciertos"` ni `"nota"`: no hay que tocarlo. Solo cambiar la etiqueta de cada punto (~1116) para que los modos por-90 lleven 1 decimal:

```python
            etq_val = (f'{p["valor"]:.1f}'
                       if modo in ("nota", "totales90", "aciertos90")
                       else f'{round(p["valor"])}')
```

- [ ] **Step 7: Cablear el modo en el dashboard**

En `scouting_app.py` (~2339), reemplazar:

```python
        modo_ev = "totales" if modo in ("total", "total90") else "aciertos"
```

por:

```python
        modo_ev = {"total": "totales", "aciertos": "aciertos",
                   "total90": "totales90", "aciertos90": "aciertos90"}[modo]
```

Y el guardarraíl de `solo_conteo` justo debajo (~2342-2345), reemplazar por (cubre también el modo por-90):

```python
        if spec_ev["solo_conteo"] and modo_ev == "aciertos":
            modo_ev = "totales"
            st.caption(f"«{etq}» se cuenta siempre en total: un % de acierto no "
                       "significa nada para esta métrica.")
        elif spec_ev["solo_conteo"] and modo_ev == "aciertos90":
            modo_ev = "totales90"
            st.caption(f"«{etq}» se cuenta siempre (por 90): un % de acierto no "
                       "significa nada para esta métrica.")
```

- [ ] **Step 8: Sintaxis + smoke + commit**

Run: `python -c "import ast; ast.parse(open('analytics.py', encoding='utf-8').read())"` y lo mismo con `scouting_app.py`.
Smoke: en la app, con un suplente (p. ej. un jugador con partidos de pocos minutos), alternar Total ↔ Total /90 y ver que la línea de evolución CAMBIA.

```bash
git add analytics.py scouting_app.py tests/test_mejoras_2026_07_23.py
git commit -m "feat(evolucion): serie por-90 con minutos de cada partido"
```

---

## Task 7: P2 — "TODOS" en el radar + renombrar "Acciones concretas" → "Acciones"

**Files:**
- Modify: `scouting_app.py` (radar ~2251-2269; `_selector_cat_accion` ~2007; comentarios)
- Modify: `analytics.py` (comentarios ~129, ~1200)

**Interfaces:**
- Consumes: `analytics.radar_ejes_seleccion(df, jugador, ejes, modo)` (ya resuelve ejes mixtos por prioridad categoría→agregado→acción).

- [ ] **Step 1: Renombrar en `_selector_cat_accion`**

En `scouting_app.py` (~2007), cambiar:

```python
    base = ["Categoría"] + (["Agregada"] if aggs else []) + ["Acción concreta"]
```

por:

```python
    base = ["Categoría"] + (["Agregada"] if aggs else []) + ["Acción"]
```

(El `else` de dispatch más abajo no comprueba el literal, así que sigue funcionando.)

- [ ] **Step 2: Radar — renombrar y añadir "Todos"**

En `scouting_app.py`, reemplazar el bloque de selección de ejes del radar (~2250-2269, desde `eje_opts = ...` hasta el cierre del `else:` de acciones) por:

```python
    eje_opts = (["Categorías"] + (["Agregadas"] if aggs_radar else [])
                + ["Acciones", "Todos"])
    eje_modo = st.radio("Ejes del radar", eje_opts,
                        horizontal=True, key="dash-radar-ejemodo")
    mapa = analytics.acciones_por_categoria(df)
    todas_accs = sorted({a for accs in mapa.values() for a in accs})
    if eje_modo == "Categorías":
        disp = [c for c in analytics.CATEGORIAS if c in mapa and c != "Otros"]
        ejes = st.multiselect("Categorías a mostrar (3-8)", disp,
                              default=disp[:6], key="dash-radar-ejes-cat")
    elif eje_modo == "Agregadas":
        ejes = st.multiselect("Métricas agregadas a mostrar (3-8)", aggs_radar,
                              default=aggs_radar[:6], key="dash-radar-ejes-agg")
        st.caption("Los agregados se comparan siempre por volumen (normalizado al "
                   "máximo entre los ejes): mezclar Pérdidas con un % de acierto "
                   "en el mismo radar no se leería.")
    elif eje_modo == "Todos":
        _opc = ([f"Categoría · {c}" for c in analytics.CATEGORIAS if c in mapa]
                + [f"Agregada · {a}" for a in aggs_radar]
                + [f"Acción · {a}" for a in todas_accs])
        _def = [o for o in _opc if o.startswith("Categoría")][:6]
        _sel = st.multiselect("Ejes: categorías + agregadas + acciones (3-8)", _opc,
                              default=_def, key="dash-radar-ejes-todos")
        ejes = [s.split(" · ", 1)[1] for s in _sel]
        st.caption("Modo mixto: se comparan por volumen (normalizado al máximo). "
                   "Mezclar % de acierto con volumen en un mismo radar no se leería.")
    else:  # Acciones
        ejes = st.multiselect("Acciones a mostrar (3-8)", todas_accs,
                              default=todas_accs[:6], key="dash-radar-ejes-acc")
```

Y en el bloque que decide `modo_radar` (~2274-2277), cambiar para que "Todos" fuerce volumen:

```python
        if eje_modo in ("Agregadas", "Todos"):
            modo_radar = "totales"
        else:
            modo_radar = "totales" if modo in ("total", "total90") else "aciertos"
```

- [ ] **Step 3: Renombrar comentarios en analytics.py**

En `analytics.py`, cambiar los comentarios que dicen «Acción concreta» por «Acción» (líneas ~129 y ~1200). No afecta al comportamiento; es coherencia.

- [ ] **Step 4: Sintaxis + smoke**

Run: `python -c "import ast; ast.parse(open('scouting_app.py', encoding='utf-8').read())"` y `analytics.py`.
Smoke: en el radar, comprobar que aparece el modo "Todos" y que se pueden mezclar una categoría + un agregado + una acción como ejes, y que el radar pinta.

- [ ] **Step 5: Commit**

```bash
git add scouting_app.py analytics.py
git commit -m "feat(radar): modo Todos (mezcla ejes) y rename Acciones concretas->Acciones"
```

---

## Task 8: P1 — motor de la sección Estadísticas

**Files:**
- Modify: `analytics.py` (nuevas `_ABP_ACCIONES`, `_DISCIPLINA_ACCIONES`, `ORDEN_SECCIONES`, `_seccion_stats`, `_fila_stats`, `estadisticas_por_seccion`; ubicar cerca de `ACCIONES_AGREGADAS`/`metrica_jugador`, ~1264)
- Test: `tests/test_mejoras_2026_07_23.py`

**Interfaces:**
- Produces:
  - `_seccion_stats(accion) -> str` (una de ORDEN_SECCIONES).
  - `estadisticas_por_seccion(df_all, jugador) -> dict[str, list[dict]]`; cada fila `{label, acciones, total, aciertos, pct, tiene_pct, total90, aciertos90}`. Incluye la clave `"Agregadas"` al final si hay datos.

- [ ] **Step 1: Tests que fallan**

```python
# --- P1: motor de Estadísticas ----------------------------------------------

def test_seccion_stats_reparte_bien():
    assert analytics._seccion_stats("Duelo en ABP def.") == "ABP"
    assert analytics._seccion_stats("Remate a balón parado") == "ABP"
    assert analytics._seccion_stats("Tarjeta amarilla") == "Disciplina"
    assert analytics._seccion_stats("Penalti cometido") == "Disciplina"
    # positivos que se "provocan" NO son disciplina
    assert analytics._seccion_stats("Penalti provocado") != "Disciplina"
    assert analytics._seccion_stats("Remate") == "Ataque"
    assert analytics._seccion_stats("Regate 1v1") == "Ataque"
    assert analytics._seccion_stats("Pase atrás") == "Pase"
    assert analytics._seccion_stats("Despeje") == "Defensa"


def test_estadisticas_pliega_pase_progresivo():
    df = _df([("Ana", "Pase progresivo", "Correcto"),
              ("Ana", "Pase entre líneas", "Correcto"),
              ("Ana", "Pase atrás", "Fallo")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    labels = [f["label"] for f in out["Pase"]]
    assert "Pase progresivo" in labels
    assert "Pase entre líneas" not in labels  # plegado dentro de progresivo
    fila = next(f for f in out["Pase"] if f["label"] == "Pase progresivo")
    assert fila["total"] == 2  # progresivo + entre líneas
    assert fila["aciertos"] == 2
    assert fila["tiene_pct"] is True


def test_estadisticas_incluye_agregadas():
    df = _df([("Ana", "Pase progresivo", "Fallo"), ("Ana", "Regate 1v1", "Fallo")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    assert "Agregadas" in out
    perd = next(f for f in out["Agregadas"] if f["label"] == "Pérdidas")
    assert perd["total"] == 2 and perd["tiene_pct"] is False
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -k "seccion_stats or estadisticas" -q`
Expected: FAIL (`module 'analytics' has no attribute '_seccion_stats'`).

- [ ] **Step 3: Implementar el motor**

En `analytics.py`, tras el bloque de `ACCIONES_AGREGADAS`/`spec_agregado` (~1264-1269), añadir:

```python
# ============================================================================
# SECCIÓN ESTADÍSTICAS — stats del jugador agrupadas por área (Fase mejoras 2026-07-23)
# ============================================================================
# Reusa _action_category y saca ABP y Disciplina a cajones propios (decisión de
# scout, ver docs/superpowers/specs/2026-07-23-...). NO reclasifica resultados.
_ABP_ACCIONES = {"Duelo en ABP def.", "Despeje en ABP def.", "Duelo en córner def.",
                 "Remate a balón parado", "Falta directa a puerta"}
# Solo indisciplina NEGATIVA. Penalti provocado / Falta recibida son positivos
# (se provocan): se quedan en su sección natural.
_DISCIPLINA_ACCIONES = {"Falta", "Falta táctica", "Tarjeta amarilla",
                        "Tarjeta roja", "Penalti cometido"}
ORDEN_SECCIONES = ["Pase", "Ataque", "Defensa", "ABP", "Mov. sin balón",
                   "Disciplina", "Otros"]


def _seccion_stats(accion):
    """Sección de la pantalla Estadísticas a la que pertenece una acción."""
    if accion in _ABP_ACCIONES:
        return "ABP"
    if accion in _DISCIPLINA_ACCIONES:
        return "Disciplina"
    cat = _action_category(accion)
    if cat in ("Finalización", "Regate"):
        return "Ataque"
    if cat in ("Pase", "Defensa", "Mov. sin balón"):
        return cat
    return "Otros"


def _fila_stats(df_all, jugador, label, acciones, f90):
    """Una fila de estadística: {label, acciones, total, aciertos, pct,
    tiene_pct, total90, aciertos90}. pct = % ponderado (parcial=0.5); None si no
    hay intentos evaluables. f90 = factor 90/minutos (0 si no hay minutos)."""
    d = df_all[(df_all["jugador"] == jugador) & (df_all["accion"].isin(acciones))]
    total = int(len(d))
    aciertos = int(d["exito"].sum()) if "exito" in d.columns else 0
    n_int = int(d["intento"].sum()) if "intento" in d.columns else 0
    tiene_pct = n_int > 0
    pct = round(100 * d["peso"].sum() / n_int, 1) if tiene_pct else None
    return {"label": label, "acciones": list(acciones), "total": total,
            "aciertos": aciertos, "pct": pct, "tiene_pct": tiene_pct,
            "total90": round(total * f90, 1), "aciertos90": round(aciertos * f90, 1)}


def estadisticas_por_seccion(df_all, jugador):
    """Stats del jugador agrupadas por sección para la pantalla Estadísticas.
    Devuelve dict ordenado {seccion: [fila, ...]} + clave 'Agregadas' al final.
    'Pase progresivo' se pliega en una fila (sus 5 equivalentes no van sueltos).
    NO reclasifica: reusa is_success/is_attempt/peso/metrica_jugador."""
    d = df_all[(df_all["jugador"] == jugador) & (df_all["accion"] != "")]
    minutos = minutos_de_jugador(df_all, jugador)
    f90 = (90.0 / minutos) if minutos and minutos > 0 else 0.0

    tmp = {s: [] for s in ORDEN_SECCIONES}
    presentes = sorted(d["accion"].dropna().unique())
    prog = set(PASE_PROG_EQUIV)
    hay_prog = bool(prog & set(presentes))
    for acc in presentes:
        if acc in prog:
            continue  # se agrega como bloque 'Pase progresivo'
        tmp[_seccion_stats(acc)].append(_fila_stats(df_all, jugador, acc, [acc], f90))
    if hay_prog:
        tmp["Pase"].insert(0, _fila_stats(df_all, jugador, "Pase progresivo",
                                          list(PASE_PROG_EQUIV), f90))

    salida = {}
    for s in ORDEN_SECCIONES:
        filas = sorted(tmp[s], key=lambda r: r["total"], reverse=True)
        if filas:
            salida[s] = filas

    # Agregadas (Pérdidas, Progresión, Peligro generado, Duelos totales, Disciplina)
    aggs = []
    for nombre, spec in ACCIONES_AGREGADAS.items():
        total = int(metrica_jugador(df_all, jugador, spec["acciones"], "totales",
                                    clases=spec["clases"]))
        if total <= 0:
            continue
        tiene_pct = not spec["solo_conteo"]
        d_agg = filtrar_clases(
            df_all[(df_all["jugador"] == jugador)
                   & (df_all["accion"].isin(spec["acciones"]))], spec["clases"])
        aciertos = int(d_agg["exito"].sum()) if (tiene_pct and "exito" in d_agg.columns) else 0
        pct = (metrica_jugador(df_all, jugador, spec["acciones"], "aciertos",
                               clases=spec["clases"]) if tiene_pct else None)
        aggs.append({"label": nombre, "acciones": list(spec["acciones"]),
                     "total": total, "aciertos": aciertos, "pct": pct,
                     "tiene_pct": tiene_pct, "total90": round(total * f90, 1),
                     "aciertos90": round(aciertos * f90, 1)})
    if aggs:
        salida["Agregadas"] = aggs
    return salida
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `python -m pytest tests/test_mejoras_2026_07_23.py -k "seccion_stats or estadisticas" -q`
Expected: PASS.

- [ ] **Step 5: Toda la suite (no romper nada)**

Run: `python -m pytest tests/ -q`
Expected: PASS (los tests viejos siguen verdes).

- [ ] **Step 6: Sintaxis + commit**

Run: `python -c "import ast; ast.parse(open('analytics.py', encoding='utf-8').read())"`

```bash
git add analytics.py tests/test_mejoras_2026_07_23.py
git commit -m "feat(estadisticas): motor de stats por sección (Pase/Ataque/Defensa/ABP/...) + agregadas"
```

---

## Task 9: P1 — UI de la sección Estadísticas (nav + tabla + barras + CSS)

**Files:**
- Modify: `scouting_app.py` (nav `secciones` ~1380; nuevo `render_estadisticas` + `tabla_stats_html` cerca de `render_secuencias` ~2930; dispatch ~3016-3031)
- Modify: `styles.css` (bloque nuevo `ESTADISTICAS`, clases `.stats-*`)

**Interfaces:**
- Consumes: `analytics.estadisticas_por_seccion` (Task 8), `analytics.niveles_rival_de_jugador` (Task 1, no imprescindible aquí), `_load_all_flat`, `analytics.equipos_de_jugador`.

- [ ] **Step 1: Registrar la sección en el nav**

En `scouting_app.py` (~1380), cambiar:

```python
        secciones = ["Registro jugadores", "Gráficos", "Secuencias", "Predicciones"]
```

por:

```python
        secciones = ["Registro jugadores", "Gráficos", "Estadísticas",
                     "Secuencias", "Predicciones"]
```

- [ ] **Step 2: Helper de tabla (HTML propio, barras de composición)**

En `scouting_app.py`, antes de `render_secuencias` (~2930), añadir la tabla. El relleno verde de la barra ya codifica el % de acierto; el número va en el color del jugador (identidad, importante al comparar), así que no hace falta helper de banda:

```python
def tabla_stats_html(secciones, jugadores, colores, modo):
    """Tabla de estadísticas por sección con barra de composición (Opción B).
    - secciones: {seccion: [fila, ...]} del jugador FOCO (define el orden y las
      filas); cada fila trae total/aciertos/pct/total90/aciertos90/tiene_pct.
    - jugadores: [nombre, ...] (foco primero); para comparar.
    - colores: {jugador: color}.
    - modo: 'total' o 'por90' (qué número manda y escala las barras).
    stats_de: {jugador: {label: fila}} lo calcula render_estadisticas y lo pasa
    embebido en cada fila del foco como fila['comp'][jugador] = fila_de_ese_jug.
    """
    val_key = "total90" if modo == "por90" else "total"
    ac_key = "aciertos90" if modo == "por90" else "aciertos"
    html = ["<div class='stats-wrap'>"]
    for seccion, filas in secciones.items():
        html.append(f"<div class='stats-sec'>{seccion}</div>")
        # escala común de la sección = máximo valor entre TODAS las filas y jugadores
        maxv = 1.0
        for f in filas:
            for j in jugadores:
                fj = f["comp"].get(j)
                if fj:
                    maxv = max(maxv, fj[val_key])
        for f in filas:
            html.append("<div class='stats-row'>")
            html.append(f"<div class='stats-lbl'>{f['label']}</div>")
            html.append("<div class='stats-bars'>")
            for j in jugadores:
                fj = f["comp"].get(j)
                if not fj or fj["total"] == 0:
                    html.append("<div class='stats-bar-line stats-empty'>—</div>")
                    continue
                v = fj[val_key]
                w = max(2.0, 100.0 * v / maxv)  # % del ancho de la pista
                col = colores.get(j, NEON_SKY)
                if fj["tiene_pct"] and fj["pct"] is not None:
                    green = max(0.0, min(100.0, fj["pct"]))  # relleno verde = % acierto
                    barra = (f"<span class='stats-fill' style='width:{green:.0f}%;"
                             f"background:{NEON_OK};'></span>")
                    num = (f"{v:.1f}" if modo == 'por90' else f"{fj['total']}") \
                        + f" · {fj['pct']:.0f}%"
                else:  # solo-volumen (Pérdidas, Disciplina, faltas...)
                    barra = (f"<span class='stats-fill' style='width:100%;"
                             f"background:{NEON_GOLD};opacity:.85;'></span>")
                    num = f"{v:.1f}" if modo == 'por90' else f"{fj['total']}"
                html.append(
                    f"<div class='stats-bar-line'>"
                    f"<span class='stats-track' style='width:{w:.0f}%;"
                    f"box-shadow:inset 0 0 0 1px {col}55;'>{barra}</span>"
                    f"<span class='stats-num' style='color:{col};'>{num}</span>"
                    f"</div>")
            html.append("</div></div>")
    html.append("</div>")
    return "".join(html)
```

- [ ] **Step 3: `render_estadisticas`**

En `scouting_app.py`, añadir (después de `tabla_stats_html`):

```python
def render_estadisticas():
    st.markdown("<div class='hud-kicker'>Análisis · datos</div>", unsafe_allow_html=True)
    st.markdown("# Estadísticas")
    st.caption("Totales y por-90 del jugador, por área. La barra: largo = volumen "
               "(escala común de la sección), relleno verde = % de acierto. Sin "
               "percentil de población (no hay muestra): compara eligiendo jugadores.")

    if st.button("↻ Recargar datos", key="reload-stats"):
        st.cache_data.clear(); st.rerun()

    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. "
                "Ve a **Registro jugadores**, crea una sesión y registra acciones.")
        return

    jugadores = sorted(df["jugador"].dropna().unique())
    with st.sidebar:
        st.markdown("### Estadísticas")
        jugador = st.selectbox("Jugador", jugadores, key="stats-jug")
        equipos_jug = analytics.equipos_de_jugador(df, jugador)
        eq_opts = {"Todos los equipos": None}
        for _eq, _n in equipos_jug:
            eq_opts[f"{_eq} ({_n})"] = _eq
        equipo_lbl = st.selectbox("Equipo", list(eq_opts.keys()), key="stats-equipo")
        equipo_sel = eq_opts.get(equipo_lbl)
        modo_lbl = st.radio("Valores", ["Total", "Por 90"], horizontal=True,
                            key="stats-modo")
        comp = st.multiselect("Comparar con (hasta 2)",
                              [j for j in jugadores if j != jugador],
                              max_selections=2, key="stats-comp")
    modo = "por90" if modo_lbl == "Por 90" else "total"

    # Filtro de equipo (por session_id, para no partir sesiones).
    if equipo_sel is not None:
        sids_eq = set(df[(df["jugador"] == jugador)
                         & (df["equipo_jugador"] == equipo_sel)]["session_id"].unique())
        df = df[df["session_id"].isin(sids_eq)]
        if df.empty:
            st.warning(f"No hay acciones de {jugador} con {equipo_sel}.")
            return

    jugs = [jugador] + comp
    colores = {j: c for j, c in zip(jugs, [NEON_SKY, NEON_GOLD, "#a855f7"])}
    # Foco define las secciones/filas; los comparados aportan su fila por label.
    foco = analytics.estadisticas_por_seccion(df, jugador)
    if not foco:
        st.info(f"{jugador} no tiene acciones que resumir con este filtro.")
        return
    stats_comp = {j: analytics.estadisticas_por_seccion(df, j) for j in comp}

    def _index(secciones_dict):
        return {f["label"]: f for filas in secciones_dict.values() for f in filas}
    idx_foco = _index(foco)
    idx_comp = {j: _index(s) for j, s in stats_comp.items()}
    # Adjuntar a cada fila del foco el dict comp {jugador: fila}
    for filas in foco.values():
        for f in filas:
            f["comp"] = {jugador: f}
            for j in comp:
                fj = idx_comp[j].get(f["label"])
                if fj:
                    f["comp"][j] = fj

    st.markdown(tabla_stats_html(foco, jugs, colores, modo), unsafe_allow_html=True)
    for j in jugs:
        st.markdown(f"<span style='color:{colores[j]};font-weight:800'>● {j}</span>",
                    unsafe_allow_html=True)
```

- [ ] **Step 4: Dispatch de la sección**

En `scouting_app.py` (~3022-3027), añadir la rama. Tras:

```python
elif section == "Gráficos":
    render_graficos()
```

insertar:

```python
elif section == "Estadísticas":
    render_estadisticas()
```

- [ ] **Step 5: CSS**

Añadir al final de `styles.css`:

```css
/* ===================== ESTADISTICAS ===================== */
.stats-wrap { display:flex; flex-direction:column; gap:4px; margin-top:6px; }
.stats-sec {
  font-size:13px; font-weight:800; letter-spacing:.04em; text-transform:uppercase;
  color:#38bdf8; margin:14px 0 4px; padding-bottom:3px;
  border-bottom:1px solid #2a2e38;
}
.stats-row {
  display:flex; align-items:center; gap:12px; padding:5px 6px; border-radius:8px;
}
.stats-row:hover { background:#1a1d24; }
.stats-lbl { flex:0 0 190px; font-size:13.5px; color:#e8ecf2; }
.stats-bars { flex:1; display:flex; flex-direction:column; gap:3px; }
.stats-bar-line { display:flex; align-items:center; gap:10px; }
.stats-track {
  height:12px; background:#15171c; border-radius:6px; overflow:hidden;
  display:inline-block; min-width:8px;
}
.stats-fill { display:block; height:100%; border-radius:6px; }
.stats-num { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12.5px;
  font-weight:700; white-space:nowrap; }
.stats-empty { color:#5b6472; font-size:12px; }
```

- [ ] **Step 6: Sintaxis + smoke manual**

Run: `python -c "import ast; ast.parse(open('scouting_app.py', encoding='utf-8').read())"`
Smoke: arrancar la app, entrar en "Estadísticas". Verificar: (a) secciones Pase/Ataque/Defensa/ABP/... + Agregadas; (b) toggle Total↔Por 90 cambia números y escala de barras; (c) Pase progresivo aparece plegado; (d) elegir 1-2 comparados apila una barra por jugador con escala común; (e) Pérdidas/Disciplina salen con barra ámbar sin %.

- [ ] **Step 7: Commit**

```bash
git add scouting_app.py styles.css
git commit -m "feat(estadisticas): sección nueva con barras de composición y comparación"
```

---

## Verificación final (antes de dar por completo)

- [ ] `python -m pytest tests/ -q` — toda la suite verde.
- [ ] Sintaxis de `analytics.py` y `scouting_app.py` (ast).
- [ ] Arranque manual de la app: recorrer Gráficos (filtro de rival nuevo, mapas cambian con Aciertos, evolución cambia con /90, radar "Todos"), Estadísticas y Secuencias sin excepción.
- [ ] Contrastar el punto 4 contra la BD: para Nusa/Maza/Rayan (visitantes) el nivel de rival y la nota salen ahora en su perspectiva (nota del partido de visitante ya no invertida).
- [ ] MCP: verificar `dossier.py` con el intérprete Python313 real del `claude_desktop_config.json` y **reiniciar el MCP**.
- [ ] NO hacer `git push` hasta que el usuario lo pida (despliega en Streamlit Cloud).

## Self-review del plan (hecho)

- **Cobertura del spec:** los 6 puntos tienen tarea (P4→Tasks 1-3, P1→Tasks 8-9, P2→7, P3→4, P5→5, P6→6). Decisiones abiertas resueltas con los defaults aprobados.
- **Sin placeholders:** todo el código va explícito.
- **Consistencia de tipos:** `estadisticas_por_seccion` produce filas con las claves que consume `tabla_stats_html` (`total/aciertos/pct/tiene_pct/total90/aciertos90` + `comp` que añade la UI); `niveles_rival_de_jugador`/`filtrar_por_nivel_rival` con la misma firma en Task 1 y su uso en Task 2; `zone_grid_counts(df, solo_exito=False)` igual en Task 4.
