# Fase 4 — Métricas de secuencia · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un eje de análisis nuevo — la secuencia individual — con un
localizador de jugadas para vídeo y dos niveles de patrones recurrentes, en una
sección propia de la app.

**Architecture:** Módulo nuevo `secuencias.py` que come del DataFrame de
`analytics.flatten_events` y reusa `analytics.nota_evento` para valorar (no
duplica criterio de scout). Config en el bloque `"secuencias"` de
`diccionario_resultados.json`. UI en una sección nueva de `scouting_app.py`.
No toca la NOTA ni el % de acierto.

**Tech Stack:** Python 3, pandas, numpy, Streamlit. Tests con pytest
(**solo en local, NO se añade a `requirements.txt`** — ese fichero lo instala
Streamlit Cloud en el deploy).

**Spec:** `docs/superpowers/specs/2026-07-16-fase4-secuencias-design.md`

## Global Constraints

- **Español** en todo texto de UI, docstrings y comentarios.
- **No tocar `analytics.nota_evento`, `nota_jugador` ni el bloque `"nota"`** del
  JSON. La Fase 4 NO modifica la nota (sería doble conteo).
- **Todo parámetro de scout va al JSON**, no hardcodeado: `ventana_gap` 0.25,
  `min_acciones` 2, `min_repeticiones` 3, `familias`.
- **`ventana_gap` = 0.25 minutos (15s)**: corta la secuencia cuando el gap con la
  acción anterior del mismo jugador **en el mismo partido** es **> 0.25**.
- **Orden estable**: al ordenar por minuto usar `kind="stable"` para que dos
  eventos del mismo minuto conserven el orden de tagueo original (el índice de
  `flatten_events` refleja el orden real de la lista `events`). Los patrones
  dependen de este orden.
- **Minuto crudo** — sin margen de compensación de lag (decisión del usuario).
- No añadir dependencias nuevas a `requirements.txt`.
- Tema neón existente en la UI: INK `#ffffff`, NEON_OK `#15ff66`, NEON_BAD
  `#ff2d55`, NEON_GOLD `#ffcc00`, NEON_SKY `#38bdf8`.

---

## File Structure

| Fichero | Responsabilidad |
|---|---|
| `diccionario_resultados.json` | **Modificar**: añadir bloque `"secuencias"` (config de scout). |
| `secuencias.py` | **Crear**: motor. Detección, valoración, patrones. Sin Streamlit. |
| `tests/test_secuencias.py` | **Crear**: tests unitarios con fixtures sintéticas. |
| `tests/test_secuencias_reales.py` | **Crear**: contraste contra el reparto real medido por SQL. |
| `scouting_app.py` | **Modificar**: `render_secuencias()` + nav + enrutado. |
| `CLAUDE.md` | **Modificar**: estado de la Fase 4. |

---

### Task 1: Config en el JSON + detección de secuencias

**Files:**
- Modify: `diccionario_resultados.json` (añadir bloque `"secuencias"` al nivel raíz, junto a `"nota"` y `"similitud"`)
- Create: `secuencias.py`
- Test: `tests/test_secuencias.py`

**Interfaces:**
- Consumes: `analytics.flatten_events` (DataFrame con columnas `session_id`, `sesion`, `jugador`, `minuto`, `accion`, `resultado`, `zona_x`), `analytics.nota_evento(accion, resultado, zona_x) -> float | None`, `analytics._clase_por_accion(accion, resultado) -> str | None`
- Produces: `secuencias.detectar_secuencias(df) -> pd.DataFrame` con columnas exactas: `session_id`, `sesion`, `jugador`, `seq_id`, `minuto_ini`, `minuto_fin`, `n_acciones`, `acciones` (list[str]), `familias` (list[str]), `cadena` (str, acciones unidas por `" > "`), `valor` (float), `desenlace` (str: `"peligro"` | `"perdida"` | `"neutro"`)

- [ ] **Step 1: Añadir el bloque `"secuencias"` al JSON**

Abrir `diccionario_resultados.json` y añadir esta clave al nivel raíz (hermana de `"nota"`):

```json
  "secuencias": {
    "_comment": "Fase 4 — secuencia individual. ventana_gap en MINUTOS: corta la cadena cuando el hueco con la accion anterior del mismo jugador y partido supera este valor. min_acciones: longitud minima para considerar CADENA (el localizador y los patrones la exigen; la cabecera de continuidad cuenta tambien las de largo 1). min_repeticiones: veces minimas para mostrar un patron.",
    "ventana_gap": 0.25,
    "min_acciones": 2,
    "min_repeticiones": 3,
    "desenlace_peligro": [
      "Remate", "Remate de cabeza", "Remate desde fuera", "Llegada 2ª línea",
      "Remate a balón parado", "Falta directa a puerta", "Generación de ocasión",
      "Pase clave", "Asistencia", "Penalti provocado"
    ],
    "familias": {
      "Conducción progresiva": "Progresa con balón",
      "Sprint of. con balón": "Progresa con balón",
      "Regate 1v1": "Encara/regatea",
      "Recorte / cambio ritmo": "Encara/regatea",
      "Centro lateral": "Sirve peligro",
      "Pase clave": "Sirve peligro",
      "Asistencia": "Sirve peligro",
      "Pase al espacio": "Sirve peligro",
      "Pase entre líneas": "Sirve peligro",
      "Generación de ocasión": "Sirve peligro",
      "Remate": "Remata",
      "Remate de cabeza": "Remata",
      "Remate desde fuera": "Remata",
      "Llegada 2ª línea": "Remata",
      "Remate a balón parado": "Remata",
      "Falta directa a puerta": "Remata",
      "Pase lateral": "Circula",
      "Pase atrás": "Circula",
      "Pase de primera": "Circula",
      "Pase progresivo": "Circula",
      "Pase en largo": "Circula",
      "Cambio de orientación": "Circula",
      "Pase bajo presión": "Circula",
      "Recibe entre líneas": "Recibe/protege",
      "Control difícil": "Recibe/protege",
      "Control fácil fallado": "Recibe/protege",
      "Protección de balón": "Recibe/protege",
      "Duelo aéreo of.": "Recibe/protege",
      "Desmarque de ruptura": "Mov. sin balón",
      "Desmarque de apoyo": "Mov. sin balón",
      "Desmarque de arrastre": "Mov. sin balón",
      "Ofrece línea de pase": "Mov. sin balón",
      "Amplía el campo": "Mov. sin balón",
      "Ataque al palo": "Mov. sin balón",
      "Entrada en área rival": "Mov. sin balón",
      "Sprint of. sin balón": "Mov. sin balón",
      "Entrada / tackle": "Defiende",
      "Intercepción": "Defiende",
      "Anticipación": "Defiende",
      "Recuperación": "Defiende",
      "Despeje": "Defiende",
      "Duelo aéreo def.": "Defiende",
      "Duelo 1v1 def.": "Defiende",
      "Presión fuerza error": "Defiende",
      "Cobertura": "Defiende",
      "Bloqueo tiro/centro": "Defiende",
      "Repliegue": "Defiende",
      "Sprint def.": "Defiende",
      "Falta táctica": "Defiende",
      "Despeje en ABP def.": "Defiende",
      "Duelo en ABP def.": "Defiende",
      "Lanzamiento córner": "Balón parado",
      "Lanzamiento falta lateral": "Balón parado",
      "Error grave / pérdida": "Pierde",
      "Falta recibida": "Otros",
      "Falta": "Otros",
      "Tarjeta amarilla": "Otros",
      "Tarjeta roja": "Otros",
      "Penalti cometido": "Otros",
      "Penalti provocado": "Otros",
      "Control fácil": "Otros"
    },
    "familia_default": "Otros"
  },
```

Verificar que sigue siendo JSON válido:

```bash
python -c "import json; d=json.load(open('diccionario_resultados.json',encoding='utf-8')); print(sorted(d.keys())); print(d['secuencias']['ventana_gap'], len(d['secuencias']['familias']))"
```
Expected: la lista de claves incluye `secuencias`, y `0.25 60` aprox (el nº exacto de familias puede variar; lo que importa es que no reviente).

- [ ] **Step 2: Escribir el test que falla**

Crear `tests/test_secuencias.py`:

```python
"""Tests del motor de secuencias (Fase 4).

Fixtures SINTÉTICAS y deterministas: no tocan Supabase ni la red.
"""
import pandas as pd
import pytest

import secuencias


def _df(rows):
    """Construye un DataFrame con las columnas mínimas que usa el motor.
    rows = lista de tuplas (session_id, jugador, minuto, accion, resultado, zona_x).
    """
    return pd.DataFrame(
        [
            {"session_id": s, "sesion": f"partido-{s}", "jugador": j,
             "minuto": m, "accion": a, "resultado": r, "zona_x": z}
            for (s, j, m, a, r, z) in rows
        ]
    )


def test_corta_por_gap_mayor_que_ventana():
    """Dos acciones a 10s (0.17') son la MISMA cadena; a 30s (0.5') son dos."""
    df = _df([
        ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 10.17, "Centro lateral", "Correcto", 2),
        ("s1", "Ana", 10.67, "Despeje", "Correcto", 0),
    ])
    out = secuencias.detectar_secuencias(df)
    assert len(out) == 2
    assert list(out["n_acciones"]) == [2, 1]


def test_no_encadena_entre_partidos_ni_entre_jugadores():
    """Mismo minuto, distinto partido o distinto jugador -> cadenas distintas."""
    df = _df([
        ("s1", "Ana", 10.00, "Pase progresivo", "Correcto", 1),
        ("s2", "Ana", 10.05, "Pase progresivo", "Correcto", 1),
        ("s1", "Leo", 10.05, "Pase progresivo", "Correcto", 1),
    ])
    out = secuencias.detectar_secuencias(df)
    assert len(out) == 3
    assert set(out["n_acciones"]) == {1}


def test_columnas_de_la_cadena():
    """minuto_ini/fin, cadena y familias salen en el orden de tagueo."""
    df = _df([
        ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 10.10, "Recorte / cambio ritmo", "Correcto", 2),
        ("s1", "Ana", 10.20, "Centro lateral", "Correcto", 2),
    ])
    out = secuencias.detectar_secuencias(df)
    assert len(out) == 1
    fila = out.iloc[0]
    assert fila["minuto_ini"] == 10.00
    assert fila["minuto_fin"] == 10.20
    assert fila["n_acciones"] == 3
    assert fila["cadena"] == "Conducción progresiva > Recorte / cambio ritmo > Centro lateral"
    assert fila["familias"] == ["Progresa con balón", "Encara/regatea", "Sirve peligro"]


def test_desenlace_lo_marca_la_ultima_accion():
    """peligro / perdida / neutro segun la ULTIMA accion de la cadena."""
    base = ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1)
    peligro = _df([base, ("s1", "Ana", 10.10, "Pase clave", "Encontrado", 2)])
    perdida = _df([base, ("s1", "Ana", 10.10, "Error grave / pérdida", "—", 0)])
    neutro = _df([base, ("s1", "Ana", 10.10, "Pase atrás", "Correcto", 1)])
    assert secuencias.detectar_secuencias(peligro).iloc[0]["desenlace"] == "peligro"
    assert secuencias.detectar_secuencias(perdida).iloc[0]["desenlace"] == "perdida"
    assert secuencias.detectar_secuencias(neutro).iloc[0]["desenlace"] == "neutro"


def test_valor_es_la_suma_de_nota_evento():
    """El valor reusa analytics.nota_evento; los neutros (None) no rompen."""
    import analytics
    df = _df([
        ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 10.10, "Sprint of. sin balón", "Correcto", 1),
    ])
    out = secuencias.detectar_secuencias(df)
    esperado = sum(
        v for v in [analytics.nota_evento("Conducción progresiva", "Correcto", 1),
                    analytics.nota_evento("Sprint of. sin balón", "Correcto", 1)]
        if v is not None
    )
    assert out.iloc[0]["valor"] == pytest.approx(esperado)


def test_df_vacio_no_revienta():
    out = secuencias.detectar_secuencias(pd.DataFrame())
    assert len(out) == 0
    assert "desenlace" in out.columns
```

- [ ] **Step 3: Instalar pytest (solo local) y ver el test fallar**

```bash
pip install pytest
python -m pytest tests/test_secuencias.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'secuencias'`

- [ ] **Step 4: Implementar `secuencias.py` (mínimo para pasar)**

Crear `secuencias.py`:

```python
"""Fase 4 — Métricas de secuencia INDIVIDUAL.

Una secuencia es una cadena de acciones consecutivas del MISMO jugador en el
MISMO partido, separadas por menos de `ventana_gap` minutos. No reconstruye la
jugada colectiva (la base sólo tiene 1-3 jugadores tagueados por partido: la
cadena de equipo tendría 19 eslabones invisibles).

Es un eje de análisis aparte: NO toca la nota ni el % de acierto. El % mide
fiabilidad, la nota mide impacto, la secuencia mide CONTINUIDAD.

El valor de cada acción NO se define aquí: se reusa `analytics.nota_evento`,
que ya tiene el criterio de scout calibrado (Fase 2).
"""
from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd

import analytics

# ----------------------------------------------------------------------------
# CONFIG (bloque "secuencias" del diccionario canónico)
# ----------------------------------------------------------------------------
_DIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "diccionario_resultados.json")


def _cargar_cfg() -> dict[str, Any]:
    try:
        with open(_DIC_PATH, "r", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("secuencias", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


_CFG = _cargar_cfg()
VENTANA_GAP = float(_CFG.get("ventana_gap", 0.25))
MIN_ACCIONES = int(_CFG.get("min_acciones", 2))
MIN_REPETICIONES = int(_CFG.get("min_repeticiones", 3))
_FAMILIAS = _CFG.get("familias", {}) or {}
_FAMILIA_DEF = _CFG.get("familia_default", "Otros")
_PELIGRO = set(_CFG.get("desenlace_peligro", []) or [])

_COLS = ["session_id", "sesion", "jugador", "seq_id", "minuto_ini", "minuto_fin",
         "n_acciones", "acciones", "familias", "cadena", "valor", "desenlace"]


def familia(accion: str) -> str:
    """Familia de la acción (para los patrones de trigrama)."""
    return _FAMILIAS.get(accion, _FAMILIA_DEF)


def _desenlace(accion: str, resultado: str) -> str:
    """Desenlace de la cadena, marcado por su ÚLTIMA acción."""
    if accion in _PELIGRO:
        return "peligro"
    clase = analytics._clase_por_accion(accion, resultado)
    if clase in {"fallo", "fallo_parcial", "fallo_medio", "fallo_grave"}:
        return "perdida"
    return "neutro"


def detectar_secuencias(df: pd.DataFrame) -> pd.DataFrame:
    """Cadenas de acciones consecutivas del mismo jugador y partido.

    Corta cuando el hueco con la acción anterior supera `ventana_gap` minutos.
    Devuelve TODAS las secuencias, incluidas las de una sola acción (la cabecera
    de continuidad las necesita para que la longitud media no mienta); los
    consumidores que exigen cadena filtran por `min_acciones`.
    """
    if df is None or len(df) == 0 or "minuto" not in df.columns:
        return pd.DataFrame(columns=_COLS)

    d = df.copy()
    d["minuto"] = pd.to_numeric(d["minuto"], errors="coerce")
    d = d[d["minuto"].notna()]
    if len(d) == 0:
        return pd.DataFrame(columns=_COLS)

    # Orden ESTABLE: dos eventos del mismo minuto conservan el orden de tagueo
    # (el índice original refleja el orden real de la lista `events`).
    d = d.sort_values(["session_id", "jugador", "minuto"], kind="stable")

    gap = d.groupby(["session_id", "jugador"], sort=False)["minuto"].diff()
    corte = (gap.isna()) | (gap > VENTANA_GAP)
    d["seq_id"] = corte.cumsum()

    filas = []
    for seq_id, g in d.groupby("seq_id", sort=True):
        acciones = list(g["accion"])
        ult = g.iloc[-1]
        valor = 0.0
        for _, ev in g.iterrows():
            v = analytics.nota_evento(ev["accion"], ev.get("resultado", ""),
                                      ev.get("zona_x"))
            if v is not None:
                valor += v
        filas.append({
            "session_id": g.iloc[0]["session_id"],
            "sesion": g.iloc[0].get("sesion", ""),
            "jugador": g.iloc[0]["jugador"],
            "seq_id": int(seq_id),
            "minuto_ini": float(g["minuto"].iloc[0]),
            "minuto_fin": float(g["minuto"].iloc[-1]),
            "n_acciones": len(g),
            "acciones": acciones,
            "familias": [familia(a) for a in acciones],
            "cadena": " > ".join(acciones),
            "valor": round(valor, 3),
            "desenlace": _desenlace(ult["accion"], ult.get("resultado", "")),
        })
    return pd.DataFrame(filas, columns=_COLS)
```

- [ ] **Step 5: Ver los tests pasar**

```bash
python -m pytest tests/test_secuencias.py -v
```
Expected: PASS — 6 passed.

- [ ] **Step 6: Commit**

```bash
git add secuencias.py tests/test_secuencias.py diccionario_resultados.json
git commit -m "feat(fase4): deteccion de secuencias individuales + config en el JSON"
```

---

### Task 2: Contraste contra los datos reales

El único test que demuestra que el motor mide lo que se midió por SQL en el
diseño. Sin esto, el resto es fe.

**Files:**
- Create: `tests/fixtures/eventos_reales.json` (exportado de la BD, sólo los campos que usa el motor)
- Create: `tests/test_secuencias_reales.py`

**Interfaces:**
- Consumes: `secuencias.detectar_secuencias`
- Produces: nada (test de verificación)

- [ ] **Step 1: Exportar la fixture desde la BD**

Usar la herramienta MCP `mcp__scouting-db__sql_select` con esta consulta, y
guardar el resultado como `tests/fixtures/eventos_reales.json`:

```sql
SELECT json_agg(json_build_object(
         'session_id', sid, 'sesion', nombre, 'jugador', jugador,
         'minuto', minuto, 'accion', accion, 'resultado', resultado,
         'zona_x', zona_x))::text
FROM (
  SELECT s.id::text AS sid, s.nombre AS nombre, e->>'jugador' AS jugador,
         (e->>'minuto')::numeric AS minuto, e->>'accion' AS accion,
         e->>'resultado' AS resultado, (e->>'zona_x') AS zona_x
  FROM sesiones s, jsonb_array_elements(s.events) e
) t;
```

Si la salida viene truncada por tamaño, exportarla en dos mitades con
`OFFSET`/`LIMIT` sobre `t` y concatenar las listas a mano en el fichero.

Comprobar el volumen:

```bash
python -c "import json; d=json.load(open('tests/fixtures/eventos_reales.json',encoding='utf-8')); print(len(d))"
```
Expected: `4491`

- [ ] **Step 2: Escribir el test de contraste**

Crear `tests/test_secuencias_reales.py`:

```python
"""Contraste del motor contra el reparto REAL medido por SQL en el diseño.

Los números vienen de la consulta de la fase de brainstorming sobre la base
completa (47 partidos, 4.491 eventos) con ventana de 15s. Si este test falla,
el motor NO reproduce lo que se midió: está mal el motor, no el test.

Ver docs/superpowers/specs/2026-07-16-fase4-secuencias-design.md §8.
"""
import json
import os

import pandas as pd
import pytest

import secuencias

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "eventos_reales.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_FIX),
    reason="falta tests/fixtures/eventos_reales.json (exportar de la BD)",
)


@pytest.fixture(scope="module")
def secs():
    with open(_FIX, "r", encoding="utf-8") as fh:
        df = pd.DataFrame(json.load(fh))
    return secuencias.detectar_secuencias(df)


def test_total_de_secuencias(secs):
    assert len(secs) == 2476


def test_reparto_por_longitud(secs):
    reparto = secs["n_acciones"].value_counts().to_dict()
    assert reparto[1] == 1298
    assert reparto[2] == 709
    assert reparto[3] == 264
    assert reparto[4] == 116
    assert reparto[5] == 56


def test_ninguna_cadena_cruza_partido_o_jugador(secs):
    """Cada seq_id pertenece a un solo (partido, jugador)."""
    assert secs.groupby("seq_id").size().max() == 1
```

- [ ] **Step 3: Ejecutar el contraste**

```bash
python -m pytest tests/test_secuencias_reales.py -v
```
Expected: PASS — 3 passed.

**Si el total no da 2.476:** NO ajustar el test para que cuadre. Comparar la
lógica de corte con el SQL del diseño (`minuto - lag(minuto) <= 0.25` agrupando
por `(id, jugador)` y ordenando por `minuto`); la causa más probable es el
`groupby` sin `sort=False`, un `minuto` leído como texto (comparación
lexicográfica) o el orden no estable.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/eventos_reales.json tests/test_secuencias_reales.py
git commit -m "test(fase4): contraste del motor contra el reparto real (2476 secuencias)"
```

---

### Task 3: Continuidad, localizador y patrones

**Files:**
- Modify: `secuencias.py` (añadir cuatro funciones al final)
- Test: `tests/test_secuencias.py` (añadir tests)

**Interfaces:**
- Consumes: `secuencias.detectar_secuencias`
- Produces:
  - `continuidad(secs, jugador, minutos=None) -> dict` con claves `n_secuencias`, `largo_medio`, `pct_peligro`, `pct_perdida`, `secuencias_90`
  - `top_secuencias(secs, jugador, n=10, ascendente=False, desenlace=None) -> pd.DataFrame`
  - `patrones_bigrama(secs, jugador, accion_origen) -> pd.DataFrame` con columnas `siguiente`, `veces`, `pct`
  - `patrones_familia(secs, jugador, min_repes=None) -> pd.DataFrame` con columnas `patron`, `veces`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_secuencias.py`:

```python
def _df_patrones():
    """Ana conduce->recorta->centra dos veces; una vez conduce->pierde."""
    rows = []
    for i, base in enumerate([10.0, 20.0]):
        rows += [
            ("s1", "Ana", base + 0.00, "Conducción progresiva", "Correcto", 1),
            ("s1", "Ana", base + 0.10, "Recorte / cambio ritmo", "Correcto", 2),
            ("s1", "Ana", base + 0.20, "Centro lateral", "Correcto", 2),
        ]
    rows += [
        ("s1", "Ana", 30.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 30.10, "Error grave / pérdida", "—", 0),
    ]
    return _df(rows)


def test_continuidad():
    secs = secuencias.detectar_secuencias(_df_patrones())
    cont = secuencias.continuidad(secs, "Ana", minutos=180)
    assert cont["n_secuencias"] == 3
    assert cont["largo_medio"] == pytest.approx(8 / 3, abs=0.01)
    assert cont["pct_peligro"] == pytest.approx(0.0)      # centro lateral no es peligro
    assert cont["pct_perdida"] == pytest.approx(100 / 3, abs=0.1)
    assert cont["secuencias_90"] == pytest.approx(1.5)    # 3 en 180'


def test_top_secuencias_ordena_por_valor_y_exige_min_acciones():
    secs = secuencias.detectar_secuencias(_df_patrones())
    top = secuencias.top_secuencias(secs, "Ana", n=5)
    assert len(top) == 3
    assert list(top["valor"]) == sorted(top["valor"], reverse=True)
    assert top["n_acciones"].min() >= secuencias.MIN_ACCIONES
    peor = secuencias.top_secuencias(secs, "Ana", n=1, ascendente=True)
    assert peor.iloc[0]["desenlace"] == "perdida"


def test_top_secuencias_filtra_por_desenlace():
    secs = secuencias.detectar_secuencias(_df_patrones())
    out = secuencias.top_secuencias(secs, "Ana", desenlace="perdida")
    assert len(out) == 1
    assert out.iloc[0]["desenlace"] == "perdida"


def test_patrones_bigrama():
    """Tras conducir: 2 de 3 veces recorta, 1 de 3 pierde."""
    secs = secuencias.detectar_secuencias(_df_patrones())
    out = secuencias.patrones_bigrama(secs, "Ana", "Conducción progresiva")
    fila = out[out["siguiente"] == "Recorte / cambio ritmo"].iloc[0]
    assert fila["veces"] == 2
    assert fila["pct"] == pytest.approx(200 / 3, abs=0.1)
    assert out["veces"].sum() == 3


def test_patrones_familia_respeta_el_umbral():
    secs = secuencias.detectar_secuencias(_df_patrones())
    # con umbral 2 aparece el patron repetido dos veces
    out = secuencias.patrones_familia(secs, "Ana", min_repes=2)
    assert list(out["patron"]) == ["Progresa con balón > Encara/regatea > Sirve peligro"]
    assert list(out["veces"]) == [2]
    # con umbral 3 no hay nada que ensenar
    assert len(secuencias.patrones_familia(secs, "Ana", min_repes=3)) == 0
```

- [ ] **Step 2: Ver fallar**

```bash
python -m pytest tests/test_secuencias.py -v
```
Expected: FAIL — `AttributeError: module 'secuencias' has no attribute 'continuidad'`

- [ ] **Step 3: Implementar las cuatro funciones**

Añadir al final de `secuencias.py`:

```python
# ----------------------------------------------------------------------------
# CONSUMIDORES
# ----------------------------------------------------------------------------
def _del_jugador(secs: pd.DataFrame, jugador: str) -> pd.DataFrame:
    if secs is None or len(secs) == 0:
        return pd.DataFrame(columns=_COLS)
    return secs[secs["jugador"] == jugador]


def continuidad(secs: pd.DataFrame, jugador: str,
                minutos: float | None = None) -> dict[str, float]:
    """Eje descriptivo: ¿aparece y se va, o sostiene la jugada?

    Cuenta TODAS las secuencias (también las de una acción): si se excluyeran,
    el largo medio y los % saldrían inflados. `minutos` = minutos jugados, para
    el por-90 (None -> secuencias_90 = 0.0).
    """
    d = _del_jugador(secs, jugador)
    n = len(d)
    if n == 0:
        return {"n_secuencias": 0, "largo_medio": 0.0, "pct_peligro": 0.0,
                "pct_perdida": 0.0, "secuencias_90": 0.0}
    return {
        "n_secuencias": n,
        "largo_medio": float(d["n_acciones"].mean()),
        "pct_peligro": 100.0 * (d["desenlace"] == "peligro").sum() / n,
        "pct_perdida": 100.0 * (d["desenlace"] == "perdida").sum() / n,
        "secuencias_90": (90.0 * n / minutos) if minutos else 0.0,
    }


def top_secuencias(secs: pd.DataFrame, jugador: str, n: int = 10,
                   ascendente: bool = False,
                   desenlace: str | None = None) -> pd.DataFrame:
    """Localizador de jugadas para vídeo: las cadenas de más (o menos) valor,
    con su minuto de entrada. Exige `min_acciones`: una acción suelta no es una
    jugada que se pueda recortar."""
    d = _del_jugador(secs, jugador)
    d = d[d["n_acciones"] >= MIN_ACCIONES]
    if desenlace:
        d = d[d["desenlace"] == desenlace]
    return d.sort_values("valor", ascending=ascendente).head(n)


def patrones_bigrama(secs: pd.DataFrame, jugador: str,
                     accion_origen: str) -> pd.DataFrame:
    """Tras `accion_origen`, ¿qué hace? Distribución de la acción siguiente
    dentro de la misma cadena, con veces y %."""
    d = _del_jugador(secs, jugador)
    siguientes: list[str] = []
    for acciones in d["acciones"]:
        for i, a in enumerate(acciones[:-1]):
            if a == accion_origen:
                siguientes.append(acciones[i + 1])
    if not siguientes:
        return pd.DataFrame(columns=["siguiente", "veces", "pct"])
    out = (pd.Series(siguientes).value_counts()
           .rename_axis("siguiente").reset_index(name="veces"))
    out["pct"] = 100.0 * out["veces"] / out["veces"].sum()
    return out


def patrones_familia(secs: pd.DataFrame, jugador: str,
                     min_repes: int | None = None) -> pd.DataFrame:
    """Trigramas por FAMILIA de acción (ej. Progresa con balón > Encara >
    Sirve peligro), con el nº de veces.

    Por familia y no por acción exacta a propósito: medido sobre la base real,
    los trigramas de acción exacta no se repiten por jugador (1 solo caso en
    4.491 eventos). Ver el diseño de la Fase 4, §3.
    """
    umbral = MIN_REPETICIONES if min_repes is None else int(min_repes)
    d = _del_jugador(secs, jugador)
    patrones: list[str] = []
    for fams in d["familias"]:
        for i in range(len(fams) - 2):
            patrones.append(" > ".join(fams[i:i + 3]))
    if not patrones:
        return pd.DataFrame(columns=["patron", "veces"])
    out = (pd.Series(patrones).value_counts()
           .rename_axis("patron").reset_index(name="veces"))
    out = out[out["veces"] >= umbral]
    return out.reset_index(drop=True)
```

- [ ] **Step 4: Ver pasar**

```bash
python -m pytest tests/ -v
```
Expected: PASS — todos.

- [ ] **Step 5: Commit**

```bash
git add secuencias.py tests/test_secuencias.py
git commit -m "feat(fase4): continuidad, localizador de jugadas y patrones"
```

---

### Task 4: Sección "Secuencias" en la app

**Files:**
- Modify: `scouting_app.py:1380` (añadir la sección al nav)
- Modify: `scouting_app.py` (añadir `render_secuencias()` antes del enrutado, ~línea 2750)
- Modify: `scouting_app.py:2759-2772` (enrutado)

**Interfaces:**
- Consumes: `secuencias.detectar_secuencias`, `continuidad`, `top_secuencias`, `patrones_bigrama`, `patrones_familia`, `MIN_REPETICIONES`; `analytics.flatten_events`; los helpers de la app `_carga_sesiones()` / patrón de `render_graficos()`
- Produces: sección navegable "Secuencias"

**Helpers YA EXISTENTES que se reusan (no reinventar):**
- `_load_all_flat(tipo=TIPO_JUGADORES) -> (sessions, df)` (`scouting_app.py:1949`) — carga y aplana.
- `analytics.minutos_de_jugador(df_all, jugador) -> int` (`analytics.py:1418`) — minutos jugados, sumando partidos.
- `analytics._rival_partido(g) -> str` (`analytics.py:37`) — etiqueta de rival para el selector de partido.

- [ ] **Step 1: Añadir la sección al nav**

En `scouting_app.py:1380`:

```python
        secciones = ["Registro jugadores", "Gráficos", "Secuencias", "Predicciones"]
```

- [ ] **Step 2: Escribir `render_secuencias()`**

Insertar antes del bloque `# ENRUTADO PRINCIPAL` (~línea 2755). Adaptar la carga
de sesiones y los filtros al patrón leído en el Step 1:

```python
# ============================================================================
# SECCIÓN SECUENCIAS (Fase 4)
# ============================================================================
def render_secuencias():
    st.markdown("<div class='hud-kicker'>Continuidad · cadenas de acciones</div>",
                unsafe_allow_html=True)
    st.markdown("# Secuencias")
    st.caption(
        "Una secuencia es lo que el jugador encadena SIN cortes: acciones suyas "
        f"seguidas a menos de {int(secuencias.VENTANA_GAP * 60)}s. Es un eje aparte: "
        "el % de acierto mide fiabilidad, la nota mide impacto, esto mide "
        "continuidad. No modifica ninguno de los dos."
    )

    sessions, df = _load_all_flat(tipo=TIPO_JUGADORES)
    if df.empty:
        st.info("No hay acciones de jugadores registradas todavía. "
                "Ve a **Registro jugadores**, crea una sesión y registra acciones.")
        return

    jugadores = sorted(df["jugador"].dropna().unique())
    with st.sidebar:
        jugador = st.selectbox("Jugador", jugadores, key="sec-jug")

    d = df[df["jugador"] == jugador]
    secs = secuencias.detectar_secuencias(d)

    # --- 1. Cabecera de continuidad -----------------------------------------
    minutos = analytics.minutos_de_jugador(df, jugador)
    cont = secuencias.continuidad(secs, jugador, minutos=minutos)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Secuencias / 90", f"{cont['secuencias_90']:.1f}")
    c2.metric("Longitud media", f"{cont['largo_medio']:.1f}")
    c3.metric("Acaban en peligro", f"{cont['pct_peligro']:.0f}%")
    c4.metric("Acaban en pérdida", f"{cont['pct_perdida']:.0f}%")

    st.divider()

    # --- 2. Localizador de jugadas ------------------------------------------
    st.markdown("### Localizador de jugadas")
    st.caption("Para recortar vídeo: el minuto es el del tagueo de la primera "
               "acción de la cadena.")
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
    if len(top) == 0:
        st.info("No hay cadenas de "
                f"{secuencias.MIN_ACCIONES}+ acciones con ese filtro.")
    else:
        vista = top[["sesion", "minuto_ini", "minuto_fin", "n_acciones",
                     "cadena", "desenlace", "valor"]].rename(columns={
            "sesion": "Partido", "minuto_ini": "Min. inicio",
            "minuto_fin": "Min. fin", "n_acciones": "Acciones",
            "cadena": "Cadena", "desenlace": "Desenlace", "valor": "Valor"})
        st.dataframe(vista, use_container_width=True, hide_index=True)

    st.divider()

    # --- 3. Tras esta acción, ¿qué hace? ------------------------------------
    st.markdown("### Tras esta acción, ¿qué hace?")
    accs = sorted(d["accion"].dropna().unique())
    origen = st.selectbox("Acción de origen", accs, key="sec-origen")
    bi = secuencias.patrones_bigrama(secs, jugador, origen)
    if len(bi) == 0:
        st.info("No hay ninguna cadena que continúe tras esa acción.")
    else:
        st.caption(f"{int(bi['veces'].sum())} cadenas continúan tras «{origen}».")
        vista_bi = bi.rename(columns={"siguiente": "Después hace",
                                      "veces": "Veces", "pct": "%"})
        vista_bi["%"] = vista_bi["%"].map(lambda v: f"{v:.0f}%")
        st.dataframe(vista_bi, use_container_width=True, hide_index=True)

    st.divider()

    # --- 4. Patrones de familia ---------------------------------------------
    st.markdown("### Patrones recurrentes")
    st.caption(
        "Por FAMILIA de acción, no por acción exacta: medido sobre la base real, "
        "los patrones de 3 acciones exactas no se repiten por jugador (1 solo "
        "caso en 4.491 eventos). Mira siempre el nº de veces antes de leer un "
        "patrón como una tendencia."
    )
    fam = secuencias.patrones_familia(secs, jugador)
    if len(fam) == 0:
        st.info(f"Ningún patrón se repite {secuencias.MIN_REPETICIONES}+ veces. "
                "Con pocos partidos es lo normal — y es más honesto que enseñar "
                "ruido.")
    else:
        for _, r in fam.iterrows():
            aviso = " ⚠️ muestra baja" if r["veces"] < 5 else ""
            st.markdown(f"**{r['patron']}** — {int(r['veces'])} veces{aviso}")
```

**Filtro de partido y contexto:** el dashboard los construye inline en
`_graficos_jugadores` (`scouting_app.py:2025-2046`), no como helper. **No
copiar y pegar ese bloque aquí.** Esta sección sale sin ellos: el localizador ya
muestra la columna Partido y se puede ordenar por ella, que cubre el caso de uso
(buscar clips). Si Gerard los pide después, se extrae el bloque a un helper
compartido y se usa en las dos secciones.

- [ ] **Step 3: Añadir el import y el enrutado**

Import junto a los de `analytics` / `similitud` (cabecera del fichero):

```python
import secuencias
```

Enrutado en `scouting_app.py` (~línea 2766):

```python
elif section == "Gráficos":
    render_graficos()
elif section == "Secuencias":
    render_secuencias()
elif section == "Predicciones":
    render_predicciones()
```

- [ ] **Step 4: Verificar sintaxis y arranque**

```bash
python -c "import ast; ast.parse(open('scouting_app.py',encoding='utf-8').read()); ast.parse(open('secuencias.py',encoding='utf-8').read()); print('sintaxis OK')"
```
Expected: `sintaxis OK`

Arranque con AppTest mockeando `storage` (patrón obligatorio del proyecto, ver
`CLAUDE.md` §2):

```bash
python -c "
import sys, types
from unittest.mock import MagicMock
sys.modules['storage'] = MagicMock()
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('scouting_app.py', default_timeout=60).run()
print('EXCEPCIONES:', at.exception)
assert not at.exception, at.exception
print('arranque OK')
"
```
Expected: `arranque OK`

Navegar a la sección y comprobar que renderiza:

```bash
python -c "
import sys
from unittest.mock import MagicMock
sys.modules['storage'] = MagicMock()
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('scouting_app.py', default_timeout=60).run()
at.session_state['section'] = 'Secuencias'
at.run()
print('EXCEPCIONES:', at.exception)
assert not at.exception, at.exception
print('seccion Secuencias OK')
"
```
Expected: `seccion Secuencias OK`

- [ ] **Step 5: Commit**

```bash
git add scouting_app.py
git commit -m "feat(fase4): seccion Secuencias en el dashboard"
```

---

### Task 5: Actualizar CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (§2 lista de archivos, §8bis Fase 4)

**Interfaces:**
- Consumes: nada
- Produces: nada

- [ ] **Step 1: Añadir `secuencias.py` a la lista de archivos (§2)**

Tras la línea de `similitud.py`:

```markdown
- `secuencias.py` — Fase 4. Motor de secuencia individual: detección de cadenas,
  localizador de jugadas para vídeo y patrones recurrentes. Reusa
  `analytics.nota_evento` para valorar; NO toca la nota.
```

- [ ] **Step 2: Reescribir el bloque "Fase 4" de §8bis**

Sustituir el bloque actual por:

```markdown
**Fase 4 — Métricas de secuencia. COMPLETA (2026-07-16).**
- **Alcance corregido: secuencia INDIVIDUAL, no colectiva.** El roadmap pedía
  cadenas recuperación→progresión→ocasión, pero eso es cadena de EQUIPO y la
  base no la sostiene: **29 de 47 partidos tienen un solo jugador tagueado**
  (12 dos, 6 tres). Reconstruirla con 1-3 de los 22 del campo mediría a quién
  se decidió taguear ese día, no fútbol. Sí hay datos para la individual: de
  4.420 pares consecutivos del mismo jugador, **2.015 (46%) a ≤15s**, mediana
  20s, y el minuto tiene resolución de segundos.
- **`secuencias.py`**: `detectar_secuencias` (corta por `ventana_gap` 15s,
  agrupando por partido+jugador, orden estable para respetar el tagueo),
  `continuidad`, `top_secuencias` (localizador de vídeo), `patrones_bigrama`,
  `patrones_familia`. Config en el bloque `"secuencias"` del JSON.
- **HALLAZGO que condicionó el diseño (medido, no opinado):** el patrón del
  ejemplo del usuario `Conducción progresiva > Recorte > Centro lateral` es el
  nº1 de la base — 7 veces, pero **repartidas entre 5 jugadores**. Es un patrón
  del fútbol, no de un jugador. Máximo que UN jugador repite un patrón:
  **3 acciones exactas → 3 veces (1 solo par jugador-patrón con ≥3 en toda la
  base)**; 3 familias → 10 (38 pares con ≥3); 2 acciones exactas → 18 (121
  pares). **Por eso NO existen los trigramas de acción exacta**: sólo bigramas
  de acción exacta y trigramas de FAMILIA, con el contador de veces siempre
  visible. Si algún día hay mucha más muestra, reevaluar.
- **NO toca la NOTA a propósito.** Repartir el valor de la cadena hacia atrás
  sería doble conteo (la nota ya paga Pase clave +0.8, Generación de ocasión y
  Gol +3.0) y obligaría a recalibrar `k` y las 3 palancas. Tres ejes separados:
  % de acierto = fiabilidad, NOTA = impacto, secuencia = **continuidad**.
- **Minuto crudo** para el vídeo, sin margen de lag (decisión del usuario).
- Verificado contra los datos reales: `tests/test_secuencias_reales.py` exige el
  reparto medido por SQL (**2.476 secuencias**; largo 1→1.298, 2→709, 3→264,
  4→116, 5→56). **Primeros tests del repo** (`pytest`, NO en `requirements.txt`
  porque ese fichero lo instala Streamlit Cloud; `pip install pytest` en local).
- **PENDIENTE:** herramienta MCP para pedir clips en lenguaje natural ("dame las
  mejores jugadas de Diomande") — el usuario la quiere después. Fase 6
  (detección de momentos) se apoyará en `detectar_secuencias`.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: Fase 4 completa (secuencia individual)"
```

---

## Notas para quien ejecute

- **No hay cultura de tests en el repo**: `tests/` se crea aquí. `pytest` NO va
  a `requirements.txt` (Streamlit Cloud lo instalaría en el deploy sin motivo).
- **El deploy es por `git push`** a `github.com/gerardsarda/app_scouting`, y va a
  producción. **No pushear sin que Gerard lo pida.**
- Si un test contra datos reales falla, **el sospechoso es el código, no el
  test**: los números salieron de SQL contra la base real.
