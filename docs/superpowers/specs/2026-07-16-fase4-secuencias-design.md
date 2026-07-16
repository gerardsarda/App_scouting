# Fase 4 — Métricas de secuencia (diseño)

Fecha: 2026-07-16
Estado: aprobado por el usuario, pendiente de plan de implementación.

---

## 1. Punto de partida y corrección del roadmap

El roadmap original define la Fase 4 como "detectar cadenas de jugadas
relacionadas (recuperación → progresión → ocasión)". Eso es una cadena de
EQUIPO y **no es medible con los datos de esta base**:

- 47 partidos, 4.491 eventos, 21 jugadores.
- **29 de los 47 partidos tienen un solo jugador tagueado** (12 tienen dos,
  6 tienen tres).
- Ritmo real ~1 evento por minuto de partido.

Reconstruir una cadena colectiva con 1-3 de los 22 jugadores del campo mide
"cuántas veces coincidieron dos ojeados", que depende de a quién se decidió
taguear ese día, no de fútbol.

**Decisión (usuario, 2026-07-16): la Fase 4 es de secuencia INDIVIDUAL** —
cadenas del propio jugador. Los datos la sostienen: de 4.420 pares de acciones
consecutivas del mismo jugador, **2.015 (46%) ocurren a ≤15s**, mediana 20s. El
minuto tiene resolución de segundos (4.437 de 4.491 eventos con decimales).

## 2. Objetivos del usuario

1. **Localizar acciones para vídeos cortos de análisis** (objetivo principal).
2. **Ver tendencias** de comportamiento repetido (ej. "conduce, recorta y busca
   el centro o disparo").

## 3. Hallazgo que condiciona el diseño (medido, no opinado)

El patrón del ejemplo del usuario existe y es el nº1 de la base:
`Conducción progresiva > Recorte / cambio ritmo > Centro lateral`, **7 veces**
— pero **repartidas entre 5 jugadores**. Es un patrón del fútbol, no de un
jugador.

Repeticiones máximas de un mismo patrón POR JUGADOR (ventana de 15s):

| Patrón | Máx. repes por jugador | Pares (jugador, patrón) con ≥3 |
|---|---|---|
| 3 acciones exactas | 3 | **1** |
| 3 familias de acción | 10 | 38 (9 con ≥5) |
| 2 acciones exactas | 18 | 121 |

**Consecuencia: las tendencias de 3 acciones exactas no existen en estos datos**
(un solo caso en toda la base) y NO se construyen. Presentarlas sería vender
ruido con forma de hábito.

## 4. Alcance

Se construye:
- Continuidad como **eje descriptivo** nuevo.
- **Localizador** de secuencias (objetivo de vídeo).
- Tendencia por **bigrama de acción exacta** (121 casos con ≥3).
- Tendencia por **trigrama de familia** (38 casos con ≥3), con contador de
  veces siempre visible.

NO se construye:
- Trigramas de acción exacta (sin datos).
- Cadenas colectivas / entre jugadores (sin datos).
- **Ninguna modificación de la NOTA.** La cadena que acaba en ocasión NO
  reparte valor hacia atrás: sería doble conteo (la nota ya paga Pase clave
  +0.8, Generación de ocasión y Gol +3.0) y obligaría a recalibrar `k` y las
  tres palancas de la Fase 2, ya ajustadas contra datos reales.

**Tres ejes separados, se leen juntos:** % de acierto = fiabilidad; NOTA =
impacto; secuencia = **continuidad**.

## 5. Decisiones de scout tomadas

- **Ventana de corte: 15s** (`0.25` min) de gap entre acciones consecutivas del
  mismo jugador y partido. Configurable.
- **Minuto crudo, sin margen de compensación** (decisión del usuario): cada
  acción tiene su minuto tagueado y se usa tal cual como punto de entrada al
  vídeo.
- Alcance de UI: **sección propia** ahora; herramienta MCP después (fuera de
  esta fase).

## 6. Arquitectura

**Módulo nuevo `secuencias.py`** — no dentro de `analytics.py` (~1400 líneas ya,
y esto es un eje propio; mismo criterio que `similitud.py`). Depende de
`analytics` para el valor de cada acción: **reusa `nota_evento`, no duplica
criterio de scout**.

**Config en `diccionario_resultados.json`, bloque `"secuencias"`** (editable a
mano, como el resto del proyecto):
- `ventana_gap`: 0.25 (minutos)
- `min_acciones`: 2 — longitud mínima para considerar CADENA
- `familias`: mapeo acción → familia
- `min_repeticiones`: 3 — umbral de aparición para mostrar un patrón

**Secuencias de una sola acción (1.298 de 2.476):** `detectar_secuencias`
las devuelve todas (una acción aislada es una secuencia de largo 1 y hace falta
para que "longitud media" y "% de secuencias que acaban en peligro" no mientan).
Los consumidores filtran: **localizador y patrones exigen `min_acciones` (2)**
— una acción suelta no es una jugada que se pueda recortar en vídeo ni una
tendencia; **la cabecera de continuidad las cuenta todas**.

**`desenlace`** se asigna por la ÚLTIMA acción de la secuencia:
`peligro` (remates, Generación de ocasión, Pase clave, Asistencia, Penalti
provocado), `perdida` (clase de fallo según el diccionario canónico de esa
acción), `neutro` (el resto).

**Familias** (agrupación para trigramas): Progresa con balón, Encara/regatea,
Sirve peligro, Remata, Circula, Recibe/protege, Mov. sin balón, Defiende, Otros.

**Funciones públicas:**

| Función | Devuelve |
|---|---|
| `detectar_secuencias(df)` | Núcleo. Una fila por secuencia: jugador, partido, `minuto_ini`, `minuto_fin`, acciones, familias, `valor` (suma de `nota_evento`), `desenlace` (peligro / perdida / neutro) |
| `continuidad(secs, jugador, minutos)` | Los 4 números de la cabecera: nº secuencias, largo medio, % peligro, % pérdida, secuencias/90 |
| `top_secuencias(secs, jugador, n)` | Localizador de vídeo: mejores/peores jugadas con su minuto |
| `patrones_bigrama(secs, jugador, accion_origen)` | Distribución "tras acción X, qué hace" con % y n |
| `patrones_familia(secs, jugador)` | Trigramas de familia con contador de veces |

Todo come del `df` de `flatten_events`, el mismo que ya usa el dashboard.

**Filtros de partido y contexto: NO en esta fase.** El dashboard los construye
inline dentro de `_graficos_jugadores` (`scouting_app.py:2025-2046`), no como
helper reutilizable, y copiarlos sería duplicar. El localizador ya muestra la
columna Partido y es ordenable, que cubre el caso de uso (buscar clips). Si
hacen falta después, se extrae el bloque a un helper y lo comparten las dos
secciones.

## 7. UI — sección nueva "Secuencias"

Al nivel de Registro / Gráficos / Predicciones. Selector de jugador propio en el
sidebar. Cuatro bloques, ordenados de más sólido a más frágil:

1. **Cabecera de continuidad** — 4 números por 90: secuencias, longitud media,
   % que acaba en peligro, % que acaba en pérdida.
2. **Localizador de jugadas** (bloque principal) — tabla ordenable: partido,
   minuto inicio–fin, cadena de acciones, desenlace, valor. Orden descendente =
   clips de "lo mejor"; ascendente = "lo que corregir". Filtro por desenlace.
3. **"Tras esta acción, ¿qué hace?"** — se elige acción de origen y se ve la
   distribución de lo que viene después, con % y n.
4. **Patrones de familia** — trigramas con nº de veces pegado al patrón y aviso
   de muestra baja por debajo de 5. Va último a propósito.

## 8. Verificación (obligatoria antes de dar nada por bueno)

- Sintaxis (`python -c "import ast..."`).
- Arranque de la app con AppTest de Streamlit mockeando `storage`.
- **Contraste contra números medidos por SQL**, no por el propio código.

**Nota de implementación (2026-07-16):** el contraste se hace sobre un
SUBCONJUNTO real — 241 eventos de 3 partidos con varios jugadores tagueados
(Bélgica-Egipto J1, Croacia-Ghana J3, Canadá-Bosnia J1) → **153 secuencias;
largo 1→99, 2→36, 3→9, 4→5, 5→2, 6→1, 7→1**. Se descartó exportar la base entera
(4.491 eventos → 2.476 secuencias, reparto 1→1.298, 2→709, 3→264, 4→116, 5→56)
para no meter ~700 KB de datos de scouting en el repo. El algoritmo es el mismo:
si reproduce el reparto de esos 3 partidos, reproduce el global. Se eligieron
partidos multi-jugador a propósito, para que el test cubra también que una
cadena nunca cruza de un jugador a otro. Si el test falla, el sospechoso es el
motor, no el test.

## 9. Fuera de esta fase

- Herramienta MCP para pedir clips en lenguaje natural ("dame las mejores
  jugadas de Diomande"). El usuario la quiere **después** de esta sección.
- Fase 6 (detección automática de momentos) se apoyará en `detectar_secuencias`.
