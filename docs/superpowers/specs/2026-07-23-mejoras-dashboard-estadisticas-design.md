# Diseño — Mejoras dashboard + nueva sección Estadísticas (2026-07-23)

Seis mejoras pedidas por el usuario. Dos son features nuevas (1 y 2), cuatro son
correcciones de comportamiento (3, 4, 5, 6). El punto 4 destapó un **bug real**
verificado contra la base entera que afecta también a la NOTA.

Numeración = la del usuario. Orden de lectura recomendado: **4 primero** (su
corrección es el cimiento del filtro y de la nota), luego el resto.

---

## Punto 4 — Filtro de nivel de rival (BUG confirmado + rediseño)

### Qué pide
"Revisa lo de rival inferior/similar/superior. ¿Sería mejor filtrar por Rival
élite/alto/medio/bajo? Revisa que lo calcule bien, no por local y visitante como
parece que hace ahora."

### Diagnóstico (verificado contra la BD, 51 partidos)
`meta.nivel_propio` guarda SIEMPRE el nivel del equipo **LOCAL** y
`meta.nivel_rival` el del **VISITANTE**, NO el del jugador scouteado. Pruebas
decisivas:
- *Irak (Bajo) vs Noruega (Alto)* con **Nusa en Noruega** → `propio=Bajo,
  rival=Alto`. Describe a Irak como "propio" aunque Nusa juega en Noruega.
- *Escocia vs Brasil* con **Rayan en Brasil** → `propio=Medio, rival=Élite`.
- Sesiones con **dos ojeados en equipos contrarios** (Brasil vs Noruega:
  Rayan + Nusa; USA vs Bélgica: Freeman + Ngoy) → "propio" no puede ser de los
  dos a la vez. Cero contraejemplos: los campos son local/visitante.

Consecuencias:
1. `comparacion_rival` (`analytics.py:1841`) calcula superior/similar/inferior
   como **visitante-vs-local** → **invertido para ~la mitad** de los
   partidos-jugador (los que el ojeado juega de visitante).
2. La **NOTA, palanca 3** (`analytics.py:940`) usa `nivel_rival`/`nivel_propio`
   propagados por `flatten_events` → a un ojeado visitante le premia/castiga por
   dificultad de rival **al revés**.

### Decisión (confirmada con el usuario)
- Cambiar el filtro a **nivel ABSOLUTO del rival** (Élite/Alto/Medio/Bajo).
- **Arreglar también la nota** (palanca 3), app y MCP.

### Diseño — corrección en UN solo sitio
`flatten_events` ya calcula por evento `equipo_jugador`, `equipo_local`,
`equipo_visitante`, `nivel_propio` (=local) y `nivel_rival` (=visitante). Se
añade justo después una **corrección a perspectiva del jugador**:

```
lado = _norm_equipo(equipo_jugador)
if lado == _norm_equipo(equipo_local):      # juega de local: ya correcto
    nivel_propio_real, nivel_rival_real = nivel_propio, nivel_rival
elif lado == _norm_equipo(equipo_visitante):# juega de visitante: SWAP
    nivel_propio_real, nivel_rival_real = nivel_rival, nivel_propio
else:                                        # no se puede determinar: sin tocar
    nivel_propio_real, nivel_rival_real = nivel_propio, nivel_rival
```

Se **sobrescriben** las columnas `nivel_propio`/`nivel_rival` con los valores en
perspectiva del jugador (sus nombres pasan por fin a significar lo que dicen). En
sesiones con dos ojeados, la corrección es **por fila/evento**, así que cada uno
sale bien. Con esto:
- La **nota** (único consumidor de esas columnas vía `_nivel_partido`) queda
  correcta sin tocar `nota_jugador`.
- El **filtro** sale directo del DataFrame: para un jugador, el nivel de rival de
  cada partido es su `nivel_rival` (ya en perspectiva).

Nueva función `analytics.niveles_rival_de_jugador(df, jugador)` → dict
`{session_id: nivel_rival}`, y `filtrar_por_nivel_rival(df, jugador, nivel)`.

### UI (dashboard, `scouting_app.py:2108`)
Sustituir el `st.radio` "Nivel del rival (vs tu equipo)" por:
`st.radio("Nivel del rival", ["Todos"] + [niveles presentes para ese jugador,
ordenados Élite→Bajo])`. El texto de ayuda explica que es el nivel absoluto del
rival en cada partido. El `st.info` de conteo se mantiene (nº de partidos del
jugador con ese nivel de rival).

### Limpieza
`comparacion_rival` y `filtrar_sesiones_por_contexto` dejan de usarse en la app.
Se **eliminan** si ningún test/módulo vivo los usa (verificar con grep); si algún
test los cubre, se adaptan.

### MCP
`scouting-mcp/dossier.py` construye la nota por partido pasando el nivel a
`nota.nota_de_eventos`. Debe pasar los niveles **en perspectiva del jugador**
(mismo SWAP local↔visitante). Igual que en la app, el dato de rival de
`contextos_partidos` pasa a ser absoluto y correcto. **Reiniciar el MCP.**

### Archivos
`analytics.py` (flatten_events + 2 helpers), `scouting_app.py` (filtro),
`scouting-mcp/dossier.py`. Tests nuevos en `tests/`.

---

## Punto 1 — Nueva sección "Estadísticas" (feature)

### Qué pide
Apartado nuevo "Estadísticas" con estadísticas **totales, aciertos y por-90
(total y acierto)** de cada jugador, divididas en secciones (pase, ABP, ataque,
defensa…), con **opción de comparar** con otros jugadores e incluyendo las
**medidas agregadas**. El **pase progresivo incluye siempre** sus equivalentes.
Inspirado en FotMob.

### Decisiones (confirmadas con el usuario)
- **Formato estilo FotMob**: toggle `Total / Por 90` arriba que cambia todos los
  números; secciones apiladas.
- **Visual = barra de composición (Opción B)**: por métrica, una barra cuyo
  **largo = volumen** (relativo a la métrica mayor de su sección) **partida en
  verde (aciertos) y apagado (fallos)**. Autocontenida: no inventa percentil de
  población (no hay muestra para ello). Junto a la barra, los números
  `valor · %`.
- Comparar hasta **2 jugadores más**, con **escala de volumen común** por
  sección (barras comparables). Colores foco/comparados: `NEON_SKY`,
  `NEON_GOLD`, violeta `#a855f7` (mismos que el resto del dashboard).

### Secciones (reusa `_action_category`, con dos recortes)
Orden: **Pase · Ataque · Defensa · ABP · Mov. sin balón · Disciplina · Otros**,
y al final **Agregadas**. Regla de asignación de cada acción:
- **ABP** (recorte explícito): `Duelo en ABP def.`, `Despeje en ABP def.`,
  `Duelo en córner def.`, `Remate a balón parado`, `Falta directa a puerta`.
- **Disciplina** (recorte explícito, solo eventos NEGATIVOS de indisciplina):
  `Falta`, `Falta táctica`, `Tarjeta amarilla`, `Tarjeta roja`, `Penalti cometido`.
  Los eventos POSITIVOS que se "provocan" (`Penalti provocado`, `Falta recibida`)
  NO van aquí: se quedan en su sección natural (Ataque/Otros) — provocarlos es
  mérito, no indisciplina.
- El resto por `_action_category`: `Pase`→Pase; `Finalización`+`Regate`→**Ataque**
  (todo lo ofensivo con balón); `Defensa`→Defensa (sin las de ABP);
  `Mov. sin balón`→Mov. sin balón; `Otros`→Otros.
- **Agregadas** = las 5 de `ACCIONES_AGREGADAS` (Pérdidas, Progresión, Peligro
  generado, Duelos totales, Disciplina), con su `clases`/`solo_conteo`.

Dentro de **Pase**, los 5 equivalentes de `PASE_PROG_EQUIV` se pliegan en una
sola fila **"Pase progresivo"** (vía `expandir_pase_prog`); no se listan sueltos.
Complementos (`Pase clave`, `Asistencia`, `Pase bajo presión`) sí aparecen como
filas propias (informativas; no suman volumen de pase).

### Motor (`analytics.py`)
`estadisticas_por_seccion(df_all, jugador)` → dict ordenado
`{seccion: [fila, …]}` con cada fila:
`{label, acciones, total, aciertos, pct, tiene_pct, total90, aciertos90}`.
- `total` = nº eventos; `aciertos` = nº con éxito; `pct` = % ponderado
  (reusa `metrica_jugador(..., 'aciertos')`); `tiene_pct` = hay algún intento.
- `total90`/`aciertos90` = valor · 90 / `minutos_de_jugador`.
- Agregados: acciones+clases del spec; `solo_conteo` → `tiene_pct=False`.
- **NO reclasifica**: reusa `is_success`/`is_attempt`/`peso`/`filtrar_clases`.
- La barra de composición se dibuja con `aciertos/total` (fracción verde); las
  filas `tiene_pct=False` (Pérdidas, Disciplina, faltas…) usan una barra única
  ámbar de solo-volumen.

### UI (`scouting_app.py`)
- Nueva entrada de nav "Estadísticas" (`secciones`, `scouting_app.py:1380`) +
  dispatch `render_estadisticas()` (`:3024`-área).
- Controles: jugador, filtro de equipo (multi-equipo, como el dashboard), toggle
  `Total / Por 90`, comparar (≤2). (Sin filtro de partido/contexto aquí: son
  totales de temporada. Decisión abierta abajo.)
- Render en **HTML propio** con clases `.stats-*` en `styles.css` (bloque
  ESTADISTICAS). Barras = `<div>` como en el mockup aprobado. **NUNCA
  `st.dataframe`** (Fase 4/5: pinta sobre canvas Glide y el CSS del tema no
  entra). Tema neón: aciertos `NEON_OK`, fallos gris apagado, solo-volumen
  `NEON_GOLD`/ámbar.

### Archivos
`analytics.py` (motor), `scouting_app.py` (`render_estadisticas` + nav +
helpers de barra), `styles.css` (bloque `.stats-*`). Tests del motor.
**Sin cambios en el MCP** (esto es solo dashboard).

---

## Punto 2 — "TODOS" en el radar + renombrar "Acciones concretas"→"Acciones"

### Qué pide
En el dashboard, permitir **mezclar** categorías, agregadas y acciones creando
una categoría nueva "TODOS". Renombrar "Acciones concretas" → "Acciones" en
todas partes.

### Diagnóstico
El motor del radar `radar_ejes_seleccion` (`analytics.py:1407`) **ya resuelve
ejes mixtos** por prioridad (categoría → agregado → acción). Es solo UI.

### Diseño
- Radar (`scouting_app.py:2251`): el `st.radio` de modo de ejes gana la opción
  **"Todos"**. Con "Todos", un único `multiselect` ofrece categorías +
  agregadas + acciones juntas, con etiqueta prefijada para distinguirlas
  (`Categoría · Pase`, `Agregada · Pérdidas`, `Acción · Pase atrás`); se
  desprefija antes de pasar a `radar_ejes_seleccion`. El `modo_radar`
  (totales/aciertos) se decide igual que hoy según el modo del dashboard.
- **Renombrar**: `scouting_app.py:2252` "Acciones concretas"→"Acciones";
  `scouting_app.py:2007` y el `selectbox` de `:2028` "Acción concreta"→"Acción".
  Actualizar comentarios en `analytics.py:129,1200`. (No tocar `NOTA_FASE2.md:234`:
  ahí "acción concreta" es prosa, no etiqueta de UI.)
- El selector de evolución (`_selector_cat_accion`) NO gana "Todos" (ahí se
  elige UNA métrica para la serie temporal; mezclar no aplica). Solo el rename.

### Archivos
`scouting_app.py`, `analytics.py` (comentarios).

---

## Punto 3 — Mapa de calor y de acciones no cambian Total→Aciertos

### Diagnóstico
`zone_grid_counts` (`analytics.py:582`) cuenta SIEMPRE todos los eventos, ignora
el éxito. El mapa de calor (`scouting_app.py:2295`) y el de acciones (`:2302`)
lo llaman igual en cualquier modo → Total y Aciertos dan lo mismo. El mapa de
calor además no aplica el /90 (solo el de acciones), pero eso es secundario: se
normaliza por min/max, así que un factor constante no cambia el patrón.

### Diseño
- `zone_grid_counts(df, solo_exito=False)`: si `solo_exito`, cuenta solo filas
  con `exito=True`.
- Ambos mapas pasan `solo_exito = modo in ("aciertos", "aciertos90")`.
- El mapa de acciones mantiene el factor /90 (ya lo tiene). El mapa de calor
  puede aplicarlo también por coherencia, aunque sea invisible por la
  normalización.

### Archivos
`analytics.py` (firma), `scouting_app.py` (2 llamadas).

---

## Punto 5 — Influencia por minuto: partir "90+" en "90-105" y "105+"

### Qué pide
Con prórrogas y descuentos largos, el "+90" debe ser 90-105 y una columna aparte
para +105.

### Diagnóstico
`FRANJAS_15` (`analytics.py:1871`) tiene la última franja `(90, 200)` como "90+".
El SVG `influencia_svg` (`scouting_app.py:1191`) ya escala con `n = len(labels)`,
así que solo hay que partir la franja. El único hardcode de 7 está en el caso
vacío de `influencia_por_minuto`.

### Diseño
- `FRANJAS_15`: `…, (75, 90), (90, 105), (105, 200)`.
- `FRANJA_LABELS`: `…, "75-90", "90-105", "105+"`.
- Caso vacío de `influencia_por_minuto`: `[0]*len(FRANJAS_15)` etc. (quitar el 7).

### Archivos
`analytics.py`. **Sin cambios en el MCP** (no usa influencia).

---

## Punto 6 — Evolución partido a partido compatible con Por-90

### Qué pide
Que el gráfico de evolución respete el /90: de suplente baja mucho el total y hoy
cambiar el filtro a /90 no cambia el gráfico.

### Diagnóstico
La evolución llama a `serie_temporal` (`analytics.py:1341`) con modo
`totales`/`aciertos`; cuando el dashboard está en `total90`/`aciertos90` cae a
`totales`/`aciertos` (`scouting_app.py:2339`). Nunca normaliza por minutos.

### Diseño
- `serie_temporal(..., modo)` acepta `totales90` y `aciertos90`. Por cada partido
  (grupo `session_id`), calcula los **minutos del jugador EN ESE partido** (de
  `jugador_info.min_in/min_out` del grupo, con fallback al último minuto con
  acción) y devuelve `valor = conteo · 90 / minutos_partido` (o solo aciertos).
  Helper `_minutos_en_grupo(g)`.
- Dashboard: mapear `total90→totales90`, `aciertos90→aciertos90`.
- `linea_temporal_svg` (`scouting_app.py:1055`): los modos `*90` escalan por el
  máximo (como `totales`) pero las etiquetas van con **1 decimal** (un 2.3/90 no
  se puede redondear a 2). El título indica "por 90".
- Los agregados `solo_conteo` en /90 siguen contando (sin %), solo divididos.
- La evolución de la NOTA (barras) no cambia (la nota ya es 0-10).

### Archivos
`analytics.py` (`serie_temporal`), `scouting_app.py` (mapeo + `linea_temporal_svg`).

---

## Verificación (obligatoria antes de dar por bueno)
- Sintaxis (`python -c "import ast; ast.parse(open(f).read())"`) de cada archivo.
- Arranque de la app con AppTest de Streamlit mockeando `storage`.
- `python -m pytest tests/ -q` (los tests existentes + los nuevos).
- Punto 4: contrastar con la BD que para ≥1 jugador visitante (Nusa, Maza,
  Rayan) el nivel de rival y la nota salen ahora en su perspectiva.
- Al tocar `flatten_events`/nota, sincronizar el MCP (`dossier.py`) y verificar
  con el intérprete REAL del servidor.

## Decisiones abiertas (a confirmar en la revisión del spec)
1. **Estadísticas — filtros**: ¿solo jugador + equipo + toggle + comparar, o
   añadir también el filtro de nivel de rival (punto 4) aquí? Propuesta: NO, para
   mantenerlo como "totales de temporada".
2. **Etiquetas de franja**: "90-105" y "105+" (vs tu "+105"). Propuesta: "105+".
3. **Sección "Otros"** en Estadísticas: ¿mostrar el cajón de acciones sueltas
   (sprints, etc.) o esconderlo? Propuesta: mostrarlo al final para no perder nada.
4. **`comparacion_rival`/`filtrar_sesiones_por_contexto`**: ¿eliminar del todo si
   quedan sin uso, o dejarlas marcadas? Propuesta: eliminar si ningún test vivo
   las usa.
