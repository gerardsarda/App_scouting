# Totales de Conducción / Despeje / Remates + exclusión de meta-tags en mapas

**Fecha:** 2026-07-28
**Rama:** `feat/totales-conduccion-despeje-remates`
**Alcance:** dashboard + sección Estadísticas. NO toca la NOTA ni el MCP.

## Contexto

Tras el tagging de decisión y bajo presión (§8quater), quedan tres huecos de
contabilización que Gerard quiere cerrar y sincronizar entre el dashboard (cards
/ radar) y la sección Estadísticas:

1. Los meta-tags de presión/decisión inflan el volumen de los gráficos espaciales.
2. Las variantes "bajo presión" de conducción y despeje no se pliegan en su total,
   como sí hace `Pase progresivo` con `Pase entre líneas`, `Pase en largo`, etc.
3. `Remate bajo presión` necesita contar por sí mismo pero fuera del total de
   remates, y falta un agregado "Remates totales".

Idea rectora consensuada: **replicar el patrón de `Pase progresivo`** — la
variante cuenta como fila propia **y además** suma al total. La lista de
equivalencias es la **fuente única** que consumen a la vez la card/radar del
dashboard y la fila-total de Estadísticas, de modo que los números coinciden
entre secciones.

## Estado actual (verificado en código)

- `PASE_PROG_EQUIV` = `[Pase progresivo, Pase entre líneas, Pase al espacio,
  Pase en largo, Cambio de orientación]` (5). Lo usan `METRICAS_DASH["pase_prog"]`
  (card/radar) y la fila "Pase progresivo (total)" de `estadisticas_por_seccion`
  (se inserta cuando hay ≥2 variantes presentes). Es EXACTAMENTE lo que se
  replica.
- `zone_grid_counts(df, solo_exito)` cuenta TODOS los eventos del df que recibe.
  Los dos call sites del dashboard (Mapa de calor, Mapa de acciones,
  `scouting_app.py` ~2324 y ~2333) le pasan el df crudo del jugador → hoy suman
  `Decisión bajo presión`, `Tras pérdida`, `Pase BP` y `Remate BP`. Hay un tercer
  consumidor interno (`analytics.py:1073`, resumen por tercios) que NO debe
  cambiar.
- `influencia_por_minuto(df, jugador)` cuenta `volumen = len(fr)` por franja →
  también suma esos meta-tags. Único caller: el dashboard.
- `METRICAS_DASH["conduccion"]` = `["Conducción progresiva"]` (sin BP).
- `METRICAS_DASH["despeje"]` = `["Despeje", "Despeje en ABP def."]` (sin BP).
- `METRICAS_DASH["remates"]` = `list(SHOT_ACTIONS)` → ya excluye `Remate BP`
  (que no está en `SHOT_ACTIONS`). No cambia.
- Despejes existentes en el diccionario: `Despeje`, `Despeje bajo presión`,
  `Despeje en ABP def.` (no existe "en córner").

## Diseño

### 1. Exclusión de meta-tags en Mapa de calor / Mapa de acciones / Influencia

Nuevo conjunto en `analytics.py`:

```python
# Meta-tags que NO representan un evento con balón "nuevo" y ubicable: juicios
# (Decisión/Tras pérdida) y complementos aditivos (Pase/Remate BP, cuyo pase o
# remate tipado ya está en el mapa). No deben sumar al volumen de los gráficos
# espaciales (mapa de calor, mapa de acciones, influencia por minuto).
META_NO_VOLUMEN = {"Decisión bajo presión", "Tras pérdida",
                   "Pase bajo presión", "Remate bajo presión"}
```

- `zone_grid_counts` gana un parámetro opcional `excluir=None` (conjunto de
  acciones a descartar antes de contar). Default `None` → comportamiento idéntico
  → el consumidor interno de `analytics.py:1073` no cambia. Los dos call sites del
  dashboard pasan `excluir=META_NO_VOLUMEN`.
- `influencia_por_minuto` aplica `META_NO_VOLUMEN` internamente (su único caller
  es el dashboard; semánticamente el volumen de influencia no debe contar
  meta-tags). El símbolo de peligro `Pase clave` NO está en el set, así que sigue
  pintándose.
- **SÍ siguen contando** `Conducción BP`, `Despeje BP` y `Pérdida BP`: son
  acciones de reemplazo reales con ubicación propia.
- **Fuera de alcance:** no se toca el eje "Volumen" del radar ni ningún otro
  conteo global. Solo esos tres gráficos.

### 2. Conducción progresiva incluye su variante BP (patrón Pase progresivo)

```python
CONDUCCION_EQUIV = ["Conducción progresiva", "Conducción bajo presión"]
```

- `METRICAS_DASH["conduccion"]["acciones"]` = `CONDUCCION_EQUIV`.
- Estadísticas: cada variante presente sale como **fila propia** (ya ocurre, vía
  la iteración de `presentes`) **+** fila **"Conducción progresiva (total)"** en
  la sección **Ataque**, insertada cuando hay ≥2 variantes presentes (idéntico
  criterio que Pase progresivo).
- Ambas variantes caen ya en categoría `Regate` → sección `Ataque`: mismo cajón,
  sin cruce de secciones.

### 3. Despeje incluye BP + ABP (patrón Pase progresivo)

```python
DESPEJE_EQUIV = ["Despeje", "Despeje bajo presión", "Despeje en ABP def."]
```

- `METRICAS_DASH["despeje"]["acciones"]` = `DESPEJE_EQUIV` (hoy ya lleva Despeje +
  ABP; se le añade la variante BP).
- Estadísticas: cada variante sale como **fila propia en su sección natural**
  (`Despeje` y `Despeje bajo presión` en **Defensa**; `Despeje en ABP def.` sigue
  en la sección **ABP**) **+** fila **"Despeje (total)"** anclada en **Defensa**,
  cuando hay ≥2 variantes presentes.
- **Consecuencia aceptada:** la fila-total de Despeje (en Defensa) suma también el
  despeje de ABP, cuyo renglón individual vive en la sección ABP. Es el precio de
  "cuando sale despeje, salen todos"; el renglón de ABP se mantiene por su cuenta
  (no desaparece).

### 4. Remate BP fuera del total + agregado "Remates totales"

- `Remate BP` ya está fuera de `SHOT_ACTIONS` → cuenta como **fila propia** en
  Estadísticas (cae en Finalización → sección Ataque) con su volumen y %, y queda
  **fuera** del total de remates. Sin cambios de clasificación.
- Nuevo agregado en `ACCIONES_AGREGADAS`:

```python
"Remates totales": {
    "acciones": list(SHOT_ACTIONS),   # excluye Remate BP por definición
    "clases": None,
    "solo_conteo": False,             # los remates tienen éxito (Gol/A puerta)
    "ayuda": "Todos los remates (incl. cabeza, desde fuera, ABP, 2ª línea). "
             "NO incluye el Remate bajo presión, que cuenta aparte.",
},
```

  Aparece en el bloque **"Agregadas"** de Estadísticas. La card `remates` del
  dashboard ya usa `SHOT_ACTIONS`, así que ya está sincronizada.

### 5. Sincronización dashboard ↔ estadísticas

Las listas `PASE_PROG_EQUIV` / `CONDUCCION_EQUIV` / `DESPEJE_EQUIV` y
`SHOT_ACTIONS` son la **fuente única** de cada total. Card/radar (`METRICAS_DASH`)
y las filas-total de `estadisticas_por_seccion` beben de las mismas listas → el
número coincide entre secciones.

Para no repetir la lógica del total ad-hoc (hoy hardcodeada solo para pase en
`estadisticas_por_seccion`), se generaliza a una pequeña tabla de grupos:

```python
# (label de la fila-total, lista de equivalencias, sección donde se ancla)
GRUPOS_TOTAL = [
    ("Pase progresivo (total)", PASE_PROG_EQUIV, "Pase"),
    ("Conducción progresiva (total)", CONDUCCION_EQUIV, "Ataque"),
    ("Despeje (total)", DESPEJE_EQUIV, "Defensa"),
]
```

`estadisticas_por_seccion` itera `GRUPOS_TOTAL`: para cada grupo, si hay ≥2 de sus
equivalencias presentes en los datos del jugador, inserta la fila-total al
principio de la sección ancla. Las variantes individuales se siguen listando por
la iteración normal de `presentes` (no se ocultan).

## Fuera de alcance (explícito)

- **La NOTA**: los valores de nota de estas acciones no cambian. Este trabajo es
  solo contabilización/visualización.
- **El agregado "Bajo presión"**: se queda igual. Incluye a propósito Pase BP y
  Remate BP (mide compostura), distinto del volumen de los mapas.
- **El MCP**: sigue pendiente de sincronizar (ya anotado en §8quater). Esto es
  solo dashboard/estadísticas.
- **Pase progresivo**: no se cambia; ya funciona así y es el patrón que se copia.

## Verificación

Tests nuevos en `tests/` (pytest):
- `META_NO_VOLUMEN` excluye los 4 meta-tags del conteo de `zone_grid_counts`
  (con `excluir`) y de `influencia_por_minuto`; Conducción/Despeje/Pérdida BP
  siguen contando.
- `METRICAS_DASH["conduccion"]` suma Conducción prog. + BP; `["despeje"]` suma
  Despeje + BP + ABP.
- `estadisticas_por_seccion` inserta "Conducción progresiva (total)" y
  "Despeje (total)" con el criterio ≥2 variantes, y sus totales cuadran con la
  card correspondiente.
- Agregado "Remates totales" = suma de `SHOT_ACTIONS`, no incluye `Remate BP`;
  `Remate BP` sale como fila propia.

Además: `python -m pytest tests/ -q` completo verde + smoke AppTest de las
secciones (mockeando `storage`), igual que en mejoras anteriores.

Al cerrar: actualizar `CLAUDE.md` (§8quater o nuevo §8quinquies) con estas
reglas y marcar el MCP como pendiente.
