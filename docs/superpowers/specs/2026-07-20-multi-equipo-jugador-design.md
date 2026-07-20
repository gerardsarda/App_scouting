# Multi-equipo por jugador — diseño

Fecha: 2026-07-20
Estado: aprobado por el usuario, pendiente de plan de implementación.

## Contexto

Terminado el Mundial 2026, se van a taguear partidos **previos** de los mismos
jugadores con su club o con categorías inferiores. Un jugador pasa a tener
varios equipos: Gilberto Mora → `México`, `México U20`, `Tijuana`.

Requisito del usuario: **los datos tienen que salir unidos en el dashboard**
independientemente del equipo, más un **filtro de equipo** en el dashboard.

## Lo que ya funciona (no se toca)

El dashboard agrega **por nombre de jugador**, no por equipo. La foto también se
resuelve por nombre (`storage.url_foto_jugador(nombre)`). Por tanto los partidos
de México, México U20 y Tijuana **ya** se unen hoy sin cambiar nada.

## El problema real

`equipo` es UN solo campo global del jugador (tabla `jugadores`) y editarlo pisa
el histórico. Eso rompe dos cosas:

1. `analytics._rival_partido` (`analytics.py:38`) deduce el rival comparando el
   equipo de la ficha con `equipo_local`/`equipo_visitante`. Con la ficha en
   "México" y un partido Tijuana–América **no casa con ninguno y cae al
   visitante** → rival mal etiquetado en el filtro de partido y en la evolución.
2. La bandera del hero se construye desde `equipo` → con "Tijuana" buscaría
   `tijuana.PNG`, que no existe en el bucket.

## Decisiones

### 1. Modelo de datos — sin cambios de esquema

- **`jugadores.equipo`** (tabla global) se reinterpreta como **equipo
  principal**. Es el ÚNICO que alimenta la bandera del hero. Para Mora: `México`.
  **No hay migración**: hoy ya contiene el país.
- **`jugadores_info[jugador]["equipo"]`** de cada sesión es la fuente de verdad
  del **equipo en ESE partido**. Ya existe, es per-sesión y ya está poblado en
  los partidos del Mundial.
- **Fallback**: si una sesión no trae equipo del jugador, se usa el principal de
  la ficha. Nunca se muestra "(sin equipo)".

Se descartó deducir el equipo de `equipo_local`/`equipo_visitante` (no dice en
qué lado juega el jugador, que es justo lo que `_rival_partido` necesita) y
guardar una lista de equipos en la ficha (sirve para el filtro pero no dice qué
equipo en qué partido, así que no arregla el rival).

### 2. Registro (`scouting_app.py`)

Se separan los dos campos, hoy fusionados en uno solo:

- **"Equipo principal (bandera)"** → va a `storage.upsert_ficha_jugador`.
- **"Equipo en este partido"** → va SOLO a
  `st.session_state.jugadores_info[jug]`, **sin tocar la ficha global**.
  Prerrellenado con el principal.

Aplica a los dos sitios: el formulario "➕ Añadir jugador" y el expander
"Editar datos de {sel}".

Esto arregla el bug de fondo: hoy, editar el equipo para un partido de Tijuana
pisaría el "México" de todo el histórico.

### 3. `analytics.flatten_events` — nueva columna `equipo_jugador`

Cada evento gana `equipo_jugador` = `jugadores_info[jugador]["equipo"]` de su
sesión, con fallback al equipo principal de la ficha. Es la columna de la que
bebe el filtro del dashboard y el rival.

`analytics._rival_partido` pasa a usar `equipo_jugador` en vez de
`jugador_info["equipo"]`. Mismo dato, pero explícito y con fallback — y así los
partidos de club etiquetan bien el rival en lugar de caer al visitante.

### 4. Dashboard — filtro de equipo

- **Nuevo selector "Equipo" en el sidebar**, justo bajo "Jugador":
  `Todos` + los equipos con partidos tagueados de ese jugador, con el nº de
  partidos entre paréntesis (`Tijuana (7)`). Por defecto **Todos** → datos
  unidos.
- Filtra `df` por `session_id` **antes** que el filtro de partido y el de
  contexto, así que arrastra a **todo**: tarjetas, radar, mapas de calor y de
  tercios, nota (badge y barras), influencia por minuto, evolución y
  **similitud**.
- El filtro de **Partido** se recalcula sobre el equipo elegido: no ofrece
  partidos de otro equipo.

### 5. Dashboard — hero

El hero muestra la **identidad** del jugador, no la selección de datos. Por eso
sus listas se calculan sobre el `df` **SIN filtrar**:

- **Bandera**: siempre la del **equipo principal** de la ficha. Nunca la del
  filtro. No hay que subir escudos de club al bucket.
- **Equipos**: SIEMPRE todos (`México · México U20 · Tijuana`), da igual el
  filtro. Ordenados por nº de partidos desc.
- **Posiciones**: hoy pinta `pos_jug`, que es la **moda** (una sola). Pasa a
  pintar TODAS las posiciones distintas del jugador según las fichas por partido
  (`MP · EXT · MED`), ordenadas por nº de partidos desc.
- El **set de métricas** sigue sugiriéndose desde la posición **más frecuente**
  (necesita una sola para elegir radar y tarjetas) y es editable a mano como
  ahora.

### 6. MCP (`scouting-mcp/`)

- `dossier_jugador(jugador, equipo=None)` → filtro opcional ("cómo rinde Mora en
  Tijuana"). Si `equipo` no casa con ninguno, el error lista los disponibles,
  mismo criterio que el parámetro `partido` de `clips_jugador`.
- `dossier.py` hoy coge `info_jugador` de la PRIMERA sesión donde aparece el
  jugador (`dossier.py:165`), así que con varios equipos devolvería uno
  arbitrario. Pasa a devolver:
  - `ficha.equipos`: lista `[{equipo, partidos}]` ordenada desc.
  - `ficha.equipo`: el más frecuente (compatibilidad con consumidores actuales).
- Cada entrada de `contextos_partidos` gana el campo `equipo` (el del jugador en
  ese partido).
- `clips_jugador` gana también `equipo=None`.
- Reiniciar el MCP para tomar los cambios.

### 7. Similitud / vector

- **Dashboard**: la similitud respeta el filtro de equipo, por coherencia con
  "el filtro arrastra a todo".
- **MCP**: `vector_jugador` NO gana filtro de equipo. Con la muestra por club que
  habrá, un vector de 4 partidos es ruido; añadirlo invitaría a leerlo como si
  fuese sólido.

## Fuera de alcance

- Escudos de club en el bucket `fotos` (la bandera es siempre la del equipo
  principal).
- Cambios de esquema en Supabase.
- Perfiles de similitud separados por equipo en el MCP.

## Verificación

- Sintaxis (`python -c "import ast..."`) y arranque de la app con AppTest de
  Streamlit mockeando `storage`.
- `python -m pytest tests/ -q` sigue en verde (el motor de secuencias no se toca,
  pero `flatten_events` sí).
- Comprobar con datos reales que un jugador con un solo equipo (todos los del
  Mundial hoy) se comporta EXACTAMENTE igual que antes: mismo rival por partido,
  misma nota, mismo vector.
