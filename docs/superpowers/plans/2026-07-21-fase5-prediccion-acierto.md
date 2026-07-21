# Predicción de acierto por jugador — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sustituir las 3 pestañas de la sección Predicciones por un motor de suavizado jerárquico de 5 niveles que predice el % de acierto de un jugador por acción y zona sin sobreajustar el ruido de las celdas con poca muestra.

**Architecture:** El motor vive en `analytics.py`: una función de agregados (cuenta aciertos/intentos por 6 niveles de granularidad) y una función de predicción que recorre la cascada `categoría → acción → acción+zona → acción+zona+posición → acción+zona+jugador`, suavizando cada nivel hacia el superior con la fórmula `(aciertos + k·prior)/(intentos + k)`. La UI (`scouting_app.py`) reemplaza `render_predicciones` por una vista única: predictor interactivo + resumen automático del jugador en tabla HTML propia. Se elimina el Random Forest (y scikit-learn), la tendencia lineal y la pestaña de patrones IA.

**Tech Stack:** Python, pandas, numpy, Streamlit. Sin nuevas dependencias (se ELIMINA scikit-learn).

## Global Constraints

- Reutilizar SIEMPRE la clasificación de acierto existente: columnas `intento` (bool) y `peso` (0.0/0.5/1.0) que ya produce `analytics.flatten_events` vía `is_success`/`is_attempt`/`success_weight`. NO reclasificar resultados por cuenta propia.
- "Acierto ponderado" de una celda = `suma de peso` sobre las filas con `intento==True`; "intentos" = número de esas filas. Parcial cuenta 0.5, igual que el % del dashboard.
- Excluir siempre `analytics.EQUIPO_TAG` (`"★ EQUIPO"`).
- Agrupación de posición = los 6 sets del radar (EXT, MP, MC/MCD, DC, DFC, LAT) + POR como grupo propio, vía un único mapeador `analytics.set_de_posicion`.
- Tercio = 0/1/2 desde `zona_x` (fallback al texto de `zona` con `_OLD_ZONE_TO_COL`). Todos los eventos de la BD hoy traen `zona_x` (verificado: 4650/4650).
- Config editable en `diccionario_resultados.json`, bloque nuevo `"expectativa"`: `k` (8.0), `min_muestra_resumen` (3), `umbral_destaca` (15.0). Mismo patrón que `nota`/`similitud`/`secuencias`.
- Tablas de la UI en HTML propio + clases `.exp-*` en `styles.css`, NUNCA `st.dataframe` (pinta sobre canvas Glide y el CSS no entra). Mismo idioma que `.seq-*`.
- Tests: pytest, se ejecutan desde la raíz del repo (`python -m pytest tests/ -q`), sin conftest, importando módulos directamente (`import analytics`). `pytest` NO va en `requirements.txt` (lo instala Streamlit Cloud). Fixtures sintéticas y deterministas, sin red ni Supabase.
- Estilo: español, defensivo (listas vacías → estructuras vacías, sin excepciones), un commit por tarea.

---

### Task 1: Mapeador único de posición a set del radar

Extrae la lógica de posición→set (hoy embebida en `scouting_app._sugerir_set`) a `analytics.py` como fuente única de verdad, añadiendo el grupo `POR`, y hace que `_sugerir_set` delegue sin cambiar su comportamiento actual para el radar.

**Files:**
- Modify: `analytics.py` (añadir `set_de_posicion` cerca de `SETS_POSICION`, ~línea 1570)
- Modify: `scouting_app.py:2465-2478` (`_sugerir_set` delega)
- Test: `tests/test_expectativa.py` (nuevo)

**Interfaces:**
- Produces: `analytics.set_de_posicion(posicion: str) -> str` — devuelve uno de `"EXT"`, `"MP"`, `"DC"`, `"DFC"`, `"LAT"`, `"POR"`, `"MC/MCD"`.

- [ ] **Step 1: Write the failing test**

En `tests/test_expectativa.py`:

```python
"""Tests del motor de expectativa de acierto (Fase 5).

Fixtures SINTÉTICAS y deterministas: no tocan Supabase ni la red. Los valores
esperados del suavizado se calculan a mano con k=8 (ver el plan).
"""
import pandas as pd
import pytest

import analytics


def test_set_de_posicion_mapea_los_6_sets_mas_por():
    assert analytics.set_de_posicion("EXT") == "EXT"
    assert analytics.set_de_posicion("MP") == "MP"
    assert analytics.set_de_posicion("DC") == "DC"
    assert analytics.set_de_posicion("DFC") == "DFC"
    assert analytics.set_de_posicion("LD") == "LAT"
    assert analytics.set_de_posicion("LI") == "LAT"
    assert analytics.set_de_posicion("POR") == "POR"
    assert analytics.set_de_posicion("MED") == "MC/MCD"
    assert analytics.set_de_posicion("MC") == "MC/MCD"
    assert analytics.set_de_posicion("") == "MC/MCD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_expectativa.py::test_set_de_posicion_mapea_los_6_sets_mas_por -v`
Expected: FAIL con `AttributeError: module 'analytics' has no attribute 'set_de_posicion'`

- [ ] **Step 3: Write minimal implementation**

En `analytics.py`, justo después del dict `SETS_POSICION` (~línea 1570):

```python
def set_de_posicion(posicion: str) -> str:
    """Mapea una posición cruda a uno de los 6 sets del radar, con POR aparte.
    Fuente única de verdad; el radar (scouting_app._sugerir_set) delega aquí."""
    p = (posicion or "").upper()
    if "POR" in p:
        return "POR"
    if any(x in p for x in ["EXT", "EI", "ED", "BANDA", "EXTREMO"]):
        return "EXT"
    if any(x in p for x in ["MP", "MEDIAPUNTA", "ENG", "MCO"]):
        return "MP"
    if any(x in p for x in ["DC", "DEL", "9", "PUNTA"]):
        return "DC"
    if any(x in p for x in ["DFC", "CENTRAL", "CB"]):
        return "DFC"
    if any(x in p for x in ["LAT", "LD", "LI", "CARRIL"]):
        return "LAT"
    return "MC/MCD"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_expectativa.py::test_set_de_posicion_mapea_los_6_sets_mas_por -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the radar delegation (behavior unchanged)**

Añade a `tests/test_expectativa.py`:

```python
def test_sugerir_set_mantiene_comportamiento_para_el_radar():
    import scouting_app
    # POR cae en MC/MCD para el radar (no hay set POR en el spider), como antes.
    esperado = {"EXT": "EXT", "MED": "MC/MCD", "LD": "LAT", "MC": "MC/MCD",
                "DFC": "DFC", "DC": "DC", "POR": "MC/MCD", "MP": "MP", "": "MC/MCD"}
    for pos, exp in esperado.items():
        assert scouting_app._sugerir_set(pos, None) == exp
```

- [ ] **Step 6: Run it (may fail on import or on POR)**

Run: `python -m pytest tests/test_expectativa.py::test_sugerir_set_mantiene_comportamiento_para_el_radar -v`
Expected: si `scouting_app` importa limpio, PASA con la implementación actual EXCEPTO que ya queremos delegar; puede FALLAR al importar `scouting_app` fuera de Streamlit. Si el import falla, saltar este test con el motivo y validar la delegación manualmente en el Step 7. (No bloquea: el objetivo real es no cambiar el comportamiento.)

- [ ] **Step 7: Refactor `_sugerir_set` to delegate**

En `scouting_app.py:2465-2478`, reemplaza el cuerpo por:

```python
def _sugerir_set(posicion, set_keys):
    """Mapea la posición del jugador a uno de los sets del radar.
    Delega en analytics.set_de_posicion (fuente única); POR no tiene set en el
    spider, así que cae en 'MC/MCD' como hasta ahora."""
    k = analytics.set_de_posicion(posicion)
    return "MC/MCD" if k == "POR" else k
```

- [ ] **Step 8: Run both Task-1 tests**

Run: `python -m pytest tests/test_expectativa.py -v -k "set_de_posicion or sugerir_set"`
Expected: PASS (o el de delegación saltado si `scouting_app` no importa fuera de Streamlit)

- [ ] **Step 9: Commit**

```bash
git add analytics.py scouting_app.py tests/test_expectativa.py
git commit -m "feat(expectativa): mapeador unico posicion->set del radar (analytics.set_de_posicion)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Config del bloque "expectativa" y helper de tercio

Añade el bloque de configuración al JSON, su cargador en `analytics.py`, y un helper para derivar el tercio (0/1/2) de una fila.

**Files:**
- Modify: `diccionario_resultados.json` (añadir bloque `"expectativa"` en el nivel raíz)
- Modify: `analytics.py` (añadir `_cargar_exp_cfg`, `_EXP_CFG`, `_tercio_de`)
- Test: `tests/test_expectativa.py`

**Interfaces:**
- Produces: `analytics._EXP_CFG` (dict con `k`, `min_muestra_resumen`, `umbral_destaca`).
- Produces: `analytics._tercio_de(zona_x, zona_texto) -> int | None`.

- [ ] **Step 1: Add the config block to the JSON**

En `diccionario_resultados.json`, en el objeto raíz (junto a `"secuencias"`), añade:

```json
"expectativa": {
  "_comment": "Fase 5 — prediccion de acierto por jugador. Cascada de suavizado de 5 niveles (categoria -> accion -> accion+zona -> accion+zona+posicion -> accion+zona+jugador). k = intentos virtuales del prior en cada nivel (cuanto mas alto, mas se fia del grupo amplio frente a la celda fina). min_muestra_resumen = intentos propios minimos para que un combo del jugador salga en el resumen. umbral_destaca = puntos de diferencia prediccion-vs-expectativa para etiquetar destaca/por debajo.",
  "k": 8.0,
  "min_muestra_resumen": 3,
  "umbral_destaca": 15.0
}
```

Verifica que el JSON sigue siendo válido:

Run: `python -c "import json; json.load(open('diccionario_resultados.json', encoding='utf-8')); print('ok')"`
Expected: `ok`

- [ ] **Step 2: Write the failing test**

Añade a `tests/test_expectativa.py`:

```python
def test_cfg_expectativa_tiene_defaults():
    cfg = analytics._EXP_CFG
    assert cfg["k"] == 8.0
    assert cfg["min_muestra_resumen"] == 3
    assert cfg["umbral_destaca"] == 15.0


def test_tercio_de_prioriza_zona_x_y_cae_al_texto():
    assert analytics._tercio_de(0, "lo que sea") == 0
    assert analytics._tercio_de(2, "") == 2
    assert analytics._tercio_de(None, "1er tercio · Centro") == 0
    assert analytics._tercio_de(None, "2º tercio · Banda der.") == 1
    assert analytics._tercio_de(None, "3er tercio · Centro") == 2
    assert analytics._tercio_de(None, "zona rara") is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_expectativa.py -v -k "cfg_expectativa or tercio_de"`
Expected: FAIL (`_EXP_CFG` / `_tercio_de` no existen)

- [ ] **Step 4: Write minimal implementation**

En `analytics.py`, tras `_cargar_nota_cfg`/`_NOTA_CFG` (~línea 168):

```python
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
```

Y cerca de `_OLD_ZONE_TO_COL` (línea 514), tras su definición:

```python
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
```

Nota: `_tercio_de` usa `_OLD_ZONE_TO_COL`, que se define en la línea 514; colócalo DESPUÉS de esa línea (o mueve `_OLD_ZONE_TO_COL` arriba si prefieres agrupar). Si lo pones antes, fallará por NameError en tiempo de llamada — verifícalo con el test.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_expectativa.py -v -k "cfg_expectativa or tercio_de"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add diccionario_resultados.json analytics.py tests/test_expectativa.py
git commit -m "feat(expectativa): bloque de config en el JSON + helper de tercio

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Agregados de la cascada

Construye la función que cuenta `(aciertos_ponderados, intentos)` por los 6 niveles de granularidad a partir del df aplanado.

**Files:**
- Modify: `analytics.py` (añadir `agregados_expectativa`, tras `set_de_posicion`)
- Test: `tests/test_expectativa.py`

**Interfaces:**
- Consumes: columnas `jugador`, `accion`, `zona_x`, `zona`, `posicion`, `intento`, `peso` del df de `flatten_events`; `set_de_posicion`, `_tercio_de`, `_action_category`, `EQUIPO_TAG`.
- Produces: `analytics.agregados_expectativa(df) -> dict` con las claves:
  - `"global"`: `(A, N)`
  - `"categoria"`: `{cat: (A, N)}`
  - `"accion"`: `{accion: (A, N)}`
  - `"accion_tercio"`: `{(accion, tercio): (A, N)}`
  - `"accion_tercio_pos"`: `{(accion, tercio, set): (A, N)}`
  - `"accion_tercio_jug"`: `{(accion, tercio, jugador): (A, N)}`

  donde `A` = suma de `peso` sobre filas con `intento==True`, `N` = nº de esas filas.

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_expectativa.py` un helper y el test. La fixture: todos "Pase progresivo" (categoría "Pase"), tercio 1; tres jugadores con posiciones DFC/LD/DC.

```python
def _df_pp(rows):
    """rows = lista de (jugador, posicion, zona_x, intento, peso).
    Construye el df mínimo que consume el motor de expectativa."""
    return pd.DataFrame(
        [{"jugador": j, "posicion": p, "accion": "Pase progresivo",
          "zona": "2º tercio · Centro", "zona_x": zx, "intento": i, "peso": w}
         for (j, p, zx, i, w) in rows]
    )


def _fixture_pp():
    # Central (DFC): 20 intentos, 19 aciertos (peso 1) + 1 fallo (peso 0)
    # Lateral (LD):  10 intentos, 10 aciertos
    # Punta (DC):     4 intentos,  0 aciertos
    rows = []
    rows += [("Central", "DFC", 1, True, 1.0)] * 19 + [("Central", "DFC", 1, True, 0.0)]
    rows += [("Lateral", "LD", 1, True, 1.0)] * 10
    rows += [("Punta", "DC", 1, True, 0.0)] * 4
    return _df_pp(rows)


def test_agregados_cuenta_por_nivel():
    agg = analytics.agregados_expectativa(_fixture_pp())
    assert agg["global"] == (29.0, 34)
    assert agg["categoria"]["Pase"] == (29.0, 34)
    assert agg["accion"]["Pase progresivo"] == (29.0, 34)
    assert agg["accion_tercio"][("Pase progresivo", 1)] == (29.0, 34)
    assert agg["accion_tercio_pos"][("Pase progresivo", 1, "DFC")] == (19.0, 20)
    assert agg["accion_tercio_pos"][("Pase progresivo", 1, "DC")] == (0.0, 4)
    assert agg["accion_tercio_jug"][("Pase progresivo", 1, "Punta")] == (0.0, 4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_expectativa.py::test_agregados_cuenta_por_nivel -v`
Expected: FAIL (`agregados_expectativa` no existe)

- [ ] **Step 3: Write minimal implementation**

En `analytics.py`, tras `set_de_posicion`:

```python
def agregados_expectativa(df):
    """Agrega (aciertos_ponderados, intentos) por los 6 niveles de la cascada
    de la Fase 5. Solo cuenta filas con intento==True; A = suma de 'peso',
    N = nº de filas. Excluye acciones de equipo. Ver el plan/spec para el detalle.
    """
    niveles = {"global": [0.0, 0], "categoria": {}, "accion": {},
               "accion_tercio": {}, "accion_tercio_pos": {}, "accion_tercio_jug": {}}
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
        tercio = _tercio_de(r.get("zona_x"), r.get("zona", ""))
        if tercio is None:
            continue
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
        _bump(niveles["accion_tercio_jug"], (accion, tercio, jug), w)

    niveles["global"] = (niveles["global"][0], niveles["global"][1])
    return niveles
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_expectativa.py::test_agregados_cuenta_por_nivel -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analytics.py tests/test_expectativa.py
git commit -m "feat(expectativa): agregados por los 6 niveles de la cascada

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Predicción por cascada de suavizado

La función que recorre la cascada y devuelve la predicción de un `(jugador, acción, tercio)` con su desglose de transparencia. Aquí se verifica el caso clave del DC (0% crudo → ~37.9% predicho).

**Files:**
- Modify: `analytics.py` (añadir `predecir_acierto`, tras `agregados_expectativa`)
- Test: `tests/test_expectativa.py`

**Interfaces:**
- Consumes: la salida de `agregados_expectativa`, `set_de_posicion`, `_action_category`, `_EXP_CFG`.
- Produces: `analytics.predecir_acierto(agg, jugador, accion, tercio, posicion, k=None) -> dict` con:
  `pred` (float 0-1), `expectativa_pos` (float 0-1), `n_jugador` (int), `aciertos_jugador` (float), `n_pos` (int), `set` (str), `categoria` (str).

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_expectativa.py`:

```python
def test_predecir_suaviza_el_caso_ruidoso_del_dc():
    agg = analytics.agregados_expectativa(_fixture_pp())
    # Punta: 4 intentos, 0 aciertos crudos -> NO debe salir 0%.
    out = analytics.predecir_acierto(agg, "Punta", "Pase progresivo", 1, "DC", k=8.0)
    assert out["n_jugador"] == 4
    assert out["aciertos_jugador"] == 0.0
    # Expectativa de su posición (nivel 3, set DC) y predicción (nivel 4).
    assert out["expectativa_pos"] == pytest.approx(0.5686274510, abs=1e-6)
    assert out["pred"] == pytest.approx(0.3790849673, abs=1e-6)
    assert out["set"] == "DC"


def test_predecir_alto_tape_se_queda_cerca_del_crudo():
    agg = analytics.agregados_expectativa(_fixture_pp())
    # Central: 20 intentos, 19 aciertos (95% crudo) -> predicción alta.
    out = analytics.predecir_acierto(agg, "Central", "Pase progresivo", 1, "DFC", k=8.0)
    assert out["pred"] == pytest.approx(0.9420768, abs=1e-5)
    assert out["expectativa_pos"] == pytest.approx(0.9222689, abs=1e-5)


def test_predecir_sin_datos_del_jugador_cae_a_la_expectativa():
    agg = analytics.agregados_expectativa(_fixture_pp())
    # Jugador inexistente en ese combo: pred == expectativa_pos (prior puro).
    out = analytics.predecir_acierto(agg, "Nadie", "Pase progresivo", 1, "DC", k=8.0)
    assert out["n_jugador"] == 0
    assert out["pred"] == pytest.approx(out["expectativa_pos"], abs=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_expectativa.py -v -k predecir`
Expected: FAIL (`predecir_acierto` no existe)

- [ ] **Step 3: Write minimal implementation**

En `analytics.py`, tras `agregados_expectativa`:

```python
def predecir_acierto(agg, jugador, accion, tercio, posicion, k=None):
    """Recorre la cascada de 5 niveles y devuelve la predicción de acierto de
    (jugador, accion, tercio) suavizada hacia la expectativa de su posición.
    `agg` es la salida de agregados_expectativa. Ver spec §3.3."""
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
    par_pos = agg["accion_tercio_pos"].get((accion, tercio, setpos))
    rate_azp = _smooth(par_pos, rate_az)
    par_jug = agg["accion_tercio_jug"].get((accion, tercio, jugador))
    rate_azj = _smooth(par_jug, rate_azp)

    aj, nj = par_jug if par_jug else (0.0, 0)
    _, npos = par_pos if par_pos else (0.0, 0)
    return {
        "pred": rate_azj,
        "expectativa_pos": rate_azp,
        "n_jugador": nj,
        "aciertos_jugador": aj,
        "n_pos": npos,
        "set": setpos,
        "categoria": cat,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_expectativa.py -v -k predecir`
Expected: PASS (los 3 tests)

- [ ] **Step 5: Commit**

```bash
git add analytics.py tests/test_expectativa.py
git commit -m "feat(expectativa): prediccion por cascada de suavizado (partial pooling)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Resumen automático del jugador

Para el cierre de scouting: recorre los combos `(acción, tercio)` más repetidos del jugador, calcula predicción vs expectativa de su rol y los etiqueta destaca/en línea/por debajo, ordenados por la desviación más llamativa.

**Files:**
- Modify: `analytics.py` (añadir `resumen_expectativa_jugador`, tras `predecir_acierto`)
- Test: `tests/test_expectativa.py`

**Interfaces:**
- Consumes: df aplanado, salida de `agregados_expectativa`, `predecir_acierto`, `_tercio_de`, `_EXP_CFG`, `EQUIPO_TAG`.
- Produces: `analytics.resumen_expectativa_jugador(df, agg, jugador, k=None, min_muestra=None, umbral=None) -> list[dict]`. Cada dict: `accion` (str), `tercio` (int), `n_jugador` (int), `pct_real` (float 0-1), `pred` (float 0-1), `expectativa_pos` (float 0-1), `n_pos` (int), `diff_pts` (int), `etiqueta` (str: `"destaca"`|`"en linea"`|`"por debajo"`). Ordenada por `abs(diff_pts)` descendente.

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_expectativa.py`:

```python
def test_resumen_incluye_combos_por_encima_del_minimo_y_etiqueta():
    df = _fixture_pp()
    agg = analytics.agregados_expectativa(df)
    filas = analytics.resumen_expectativa_jugador(
        df, agg, "Punta", k=8.0, min_muestra=3, umbral=15.0)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["accion"] == "Pase progresivo"
    assert fila["tercio"] == 1
    assert fila["n_jugador"] == 4
    assert fila["pct_real"] == pytest.approx(0.0, abs=1e-9)
    assert fila["pred"] == pytest.approx(0.3790849673, abs=1e-6)
    assert fila["expectativa_pos"] == pytest.approx(0.5686274510, abs=1e-6)
    # diff = round((0.37908 - 0.56863) * 100) = -19 -> |19| >= 15 -> "por debajo"
    assert fila["diff_pts"] == -19
    assert fila["etiqueta"] == "por debajo"


def test_resumen_descarta_combos_con_muestra_insuficiente():
    df = _df_pp([("Solo", "MC", 1, True, 1.0)] * 2)  # 2 intentos < min_muestra 3
    agg = analytics.agregados_expectativa(df)
    filas = analytics.resumen_expectativa_jugador(
        df, agg, "Solo", k=8.0, min_muestra=3, umbral=15.0)
    assert filas == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_expectativa.py -v -k resumen`
Expected: FAIL (`resumen_expectativa_jugador` no existe)

- [ ] **Step 3: Write minimal implementation**

En `analytics.py`, tras `predecir_acierto`:

```python
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
            "accion": accion, "tercio": tercio, "n_jugador": n_prop,
            "pct_real": (a_prop / n_prop) if n_prop else 0.0,
            "pred": out["pred"], "expectativa_pos": out["expectativa_pos"],
            "n_pos": out["n_pos"], "diff_pts": diff_pts, "etiqueta": etiqueta,
        })
    filas.sort(key=lambda f: abs(f["diff_pts"]), reverse=True)
    return filas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_expectativa.py -v -k resumen`
Expected: PASS

- [ ] **Step 5: Run the whole engine test file**

Run: `python -m pytest tests/test_expectativa.py -q`
Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
git add analytics.py tests/test_expectativa.py
git commit -m "feat(expectativa): resumen del jugador vs expectativa de su rol

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Reescribir la UI (sección Predicciones)

Reemplaza el cuerpo de `render_predicciones` por la vista única (predictor interactivo + resumen en tabla HTML), añade el CSS `.exp-*`, y desconecta `ai_analysis` de esta sección. Tras esta tarea la app deja de llamar a las funciones viejas (que se borran en la Task 7).

**Files:**
- Modify: `scouting_app.py` (`render_predicciones` completo, ~2487-2649; quitar `import ai_analysis` línea 31; nueva función `tabla_expectativa_html`; actualizar docstring de cabecera línea 10)
- Modify: `styles.css` (añadir bloque `EXPECTATIVA` con clases `.exp-*`)

**Interfaces:**
- Consumes: `analytics.agregados_expectativa`, `analytics.predecir_acierto`, `analytics.resumen_expectativa_jugador`, `_load_all_flat`, `player_metrics`, constantes `NEON_*`/`INK`, `_esc`.

- [ ] **Step 1: Replace `render_predicciones` body**

Sustituye TODO el cuerpo de `render_predicciones` (`scouting_app.py:2487` hasta justo antes de `# ===...PIZARRA...` en 2652) por:

```python
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
```

- [ ] **Step 2: Add the `tabla_expectativa_html` helper**

En `scouting_app.py`, justo ANTES de `def render_predicciones():`, añade:

```python
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
```

- [ ] **Step 3: Remove the now-unused `import ai_analysis`**

En `scouting_app.py:31`, borra la línea `import ai_analysis` (ya no se usa en la app tras quitar la pestaña de patrones; el módulo `ai_analysis.py` se conserva en el repo).

Verifica que no quedan otras referencias:

Run: `grep -n "ai_analysis" scouting_app.py`
Expected: sin resultados.

- [ ] **Step 4: Update the file header docstring**

En `scouting_app.py:10`, cambia la línea:

```
    · Predicciones  -> tendencias + modelo ML (scikit-learn) cuando hay datos
```

por:

```
    · Predicciones  -> predicción de acierto por jugador (suavizado jerárquico)
```

- [ ] **Step 5: Add the `.exp-*` CSS block**

En `styles.css`, al final del bloque SECUENCIAS (tras la última regla `.seq-*`, ~línea 731+), añade:

```css
/* ============================================================
   EXPECTATIVA (Fase 5) — tabla propia, NO st.dataframe.
   ============================================================ */
.exp-tabla { border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden; background: var(--card); margin-top: 4px; }
.exp-head, .exp-row {
  display: grid; grid-template-columns: 2.4fr 0.7fr 0.8fr 0.9fr 1.1fr 0.7fr 1fr;
  align-items: center; gap: 8px; padding: 9px 14px;
}
.exp-head { background: var(--card-2); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--txt-lo); font-weight: 700; }
.exp-head .h-num { text-align: right; }
.exp-row { border-bottom: 1px solid var(--hair); border-left: 3px solid transparent; transition: background 120ms ease; }
.exp-row:last-child { border-bottom: none; }
.exp-row:hover { background: var(--card-2); }
.exp-row[data-et="destaca"] { border-left-color: var(--ok); }
.exp-row[data-et="por debajo"] { border-left-color: var(--bad); }
.exp-row[data-et="en linea"] { border-left-color: var(--hair); }
.exp-acc { font-size: 13px; color: var(--txt-hi); font-weight: 600; }
.exp-zona { color: var(--txt-lo); font-weight: 400; }
.exp-num { font-family: var(--mono); font-size: 13px; text-align: right; color: var(--txt-mid); }
.exp-num.exp-strong { color: var(--txt-hi); font-weight: 800; }
.exp-npos { color: var(--txt-lo); font-size: 10px; }
.exp-delta { font-family: var(--mono); font-size: 14px; font-weight: 800; text-align: right; }
.exp-delta[data-signo="pos"] { color: var(--ok); }
.exp-delta[data-signo="neg"] { color: var(--bad); }
.exp-delta[data-signo="cero"] { color: var(--txt-lo); }
.exp-pill { justify-self: start; font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; }
.exp-pill[data-et="destaca"] { color: var(--ok); background: var(--ok-dim); }
.exp-pill[data-et="por debajo"] { color: var(--bad); background: var(--bad-dim); }
.exp-pill[data-et="en linea"] { color: var(--txt-lo); background: rgba(139,147,161,0.12); }
@media (max-width: 760px) {
  .exp-head, .exp-row { grid-template-columns: 1.8fr 0.6fr 0.9fr 0.7fr 0.9fr; }
  .exp-head span:nth-child(3), .exp-row span:nth-child(3),
  .exp-head span:nth-child(7), .exp-row span:nth-child(7) { display: none; }
}
```

Nota: las variables `--ok`, `--ok-dim`, `--bad`, `--bad-dim`, `--card`, `--card-2`, `--hair`, `--mono`, `--radius`, `--txt-hi`, `--txt-mid`, `--txt-lo` YA existen en `styles.css` (verificado: las usa el bloque `.seq-*`). No hay que definir ninguna variable nueva.

- [ ] **Step 6: Syntax check**

Run: `python -c "import ast; ast.parse(open('scouting_app.py', encoding='utf-8').read()); ast.parse(open('analytics.py', encoding='utf-8').read()); print('sintaxis ok')"`
Expected: `sintaxis ok`

- [ ] **Step 7: App boot check with AppTest (mock storage)**

Crea un script temporal en el scratchpad y ejecútalo (NO lo commitees):

```python
# scratch_apptest.py — arranque de la app mockeando storage
import sys, types
from unittest.mock import MagicMock

fake = types.ModuleType("storage")
fake.load_all_sessions = lambda tipo=None: []
fake.list_jugadores = lambda: []
fake.load_session = lambda *a, **k: {}
for extra in ("save_session", "delete_session", "foto_url", "bandera_url",
              "upsert_jugador", "get_jugador"):
    setattr(fake, extra, MagicMock(return_value=None))
sys.modules["storage"] = fake

from streamlit.testing.v1 import AppTest
at = AppTest.from_file("scouting_app.py", default_timeout=30)
at.run()
assert not at.exception, at.exception
print("APP OK — sin excepciones al arrancar")
```

Run: `python "$SCRATCH/scratch_apptest.py"` (sustituye `$SCRATCH` por el directorio de scratchpad)
Expected: `APP OK — sin excepciones al arrancar`. Si `storage` necesita más atributos, añádelos al mock hasta que arranque (la app no debe tocar la red).

- [ ] **Step 8: Commit**

```bash
git add scouting_app.py styles.css
git commit -m "feat(expectativa): nueva seccion Predicciones (predictor + resumen del jugador)

Reemplaza las 3 pestanas (tendencia, RF, patrones IA) por la vista unica de
prediccion de acierto. Desconecta ai_analysis de la app (el modulo se conserva).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Eliminar el código muerto (RF, tendencia, patrones) y scikit-learn

Con la app ya migrada, se borran las funciones que nadie llama y la dependencia de scikit-learn.

**Files:**
- Modify: `analytics.py` (borrar `predict_player_trend`, `train_outcome_model`, `patrones_tacticos_datos`; actualizar docstring de cabecera líneas 14-15)
- Modify: `requirements.txt` (quitar `scikit-learn>=1.3`)
- Test: `tests/test_expectativa.py`

**Interfaces:**
- Produces: nada nuevo. Elimina símbolos públicos ya sin consumidores en la app.

- [ ] **Step 1: Confirm no remaining callers**

Run: `grep -rn "predict_player_trend\|train_outcome_model\|patrones_tacticos_datos" --include=*.py .`
Expected: solo las DEFINICIONES en `analytics.py` (y su docstring de cabecera). Ningún `analytics.<func>(` en `scouting_app.py`. Si aparece alguna llamada viva, PARA y resuélvela antes de borrar.

- [ ] **Step 2: Write the failing test**

Añade a `tests/test_expectativa.py`:

```python
def test_no_queda_codigo_muerto_de_prediccion_vieja():
    assert not hasattr(analytics, "predict_player_trend")
    assert not hasattr(analytics, "train_outcome_model")
    assert not hasattr(analytics, "patrones_tacticos_datos")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_expectativa.py::test_no_queda_codigo_muerto_de_prediccion_vieja -v`
Expected: FAIL (las funciones aún existen)

- [ ] **Step 4: Delete the three functions**

En `analytics.py`, borra completas:
- `predict_player_trend` (línea ~542 hasta antes de `train_outcome_model`)
- `train_outcome_model` (línea ~586 hasta antes del comentario `# RANKING PARAMETRIZABLE`)
- `patrones_tacticos_datos` (línea ~1230 hasta antes del comentario `# SELECTOR CATEGORÍA/ACCIÓN`)

Los imports de sklearn viven DENTRO de `train_outcome_model` (líneas 603-605), así que se van con ella; no hay import de sklearn a nivel de módulo. Verifícalo:

Run: `grep -n "sklearn" analytics.py`
Expected: sin resultados.

- [ ] **Step 5: Update the module header docstring**

En `analytics.py:14-15`, borra las dos líneas:

```
    - predict_player_trend()  -> proyección por tendencia (siempre disponible).
    - train_outcome_model()   -> modelo scikit-learn (cuando hay datos suficientes).
```

y en su lugar (misma sección de la lista) pon:

```
    - agregados_expectativa() / predecir_acierto() -> predicción de acierto
      por jugador con suavizado jerárquico (Fase 5).
```

- [ ] **Step 6: Remove scikit-learn from requirements**

En `requirements.txt`, borra la línea `scikit-learn>=1.3`.

- [ ] **Step 7: Run test to verify it passes + full suite**

Run: `python -m pytest tests/ -q`
Expected: todos PASS (incluido `test_no_queda_codigo_muerto...`). Los tests de secuencias siguen verdes.

- [ ] **Step 8: Re-run the app boot check**

Run: `python "$SCRATCH/scratch_apptest.py"`
Expected: `APP OK — sin excepciones al arrancar` (confirma que borrar las funciones no rompió imports).

- [ ] **Step 9: Syntax check**

Run: `python -c "import ast; ast.parse(open('analytics.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 10: Commit**

```bash
git add analytics.py requirements.txt tests/test_expectativa.py
git commit -m "chore(expectativa): elimina RF/tendencia/patrones muertos y scikit-learn

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificación final (tras todas las tareas)

- [ ] `python -m pytest tests/ -q` → todo verde.
- [ ] `python "$SCRATCH/scratch_apptest.py"` → app arranca sin excepciones.
- [ ] Contraste manual contra la BD (opcional, con el MCP): para `("Pase progresivo", tercio 1, DFC)` el nivel 3 debe rondar el % crudo real (muestra alta); para un jugador con 3-4 intentos en un combo, la predicción debe caer ENTRE su crudo y la expectativa de su posición, nunca en 0%.
- [ ] El MCP no se toca (no hay tool de predicción; esta sección es solo dashboard).

## Notas de decisión registradas en el diseño

- Cascada de suavizado (partial pooling), NO Random Forest: la muestra real (74% de combos jugador+acción+zona con <5 eventos) hace que un RF sobreajuste ruido. Ver spec §2.
- La etiqueta destaca/por debajo usa la predicción suavizada, no el % crudo, para no señalar ruido. La tabla muestra AMBOS (crudo + predicción) por transparencia.
- La expectativa de posición (nivel 3) incluye las propias acciones del jugador; en datos reales con varios jugadores por set el efecto se diluye. Leave-one-out queda como posible refinamiento futuro, fuera de alcance (YAGNI).
- `ai_analysis.py` se conserva (solo se desconecta de esta sección).
