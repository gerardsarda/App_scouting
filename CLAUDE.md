# CLAUDE.md — App de Scouting de Fútbol

Documento de referencia del proyecto para retomar el desarrollo en futuras
sesiones. Resume arquitectura, datos, metodología de scout, decisiones tomadas
y estado del roadmap.

---

## 1. QUÉ ES

Aplicación de scouting de fútbol para registrar y analizar el rendimiento de
jugadores partido a partido. Usada en directo durante el Mundial 2026. El
usuario taguea acciones de jugadores concretos y la app genera análisis
individuales: dashboard con radar, mapas de calor, gráficos de influencia y
evolución, modelo de similitud con jugadores top, y un MCP que conecta la base
de datos con Claude para análisis en lenguaje natural.

La ventaja del proyecto es el OJO del scout: el tagging manual capta matices
(desmarques, presión, calidad de pase bajo presión) que los datos automáticos
no recogen. El código NO opina: agrupa, cuenta y contextualiza; el análisis
cualitativo lo hace el scout o Claude.

---

## 2. ARQUITECTURA Y ARCHIVOS

**Frontend/lógica (Streamlit):**
- `scouting_app.py` (~2480 líneas) — UI principal. Secciones activas: Registro
  de jugadores, Gráficos (dashboard), Predicciones. Contiene también todas las
  funciones de generación de gráficos SVG (radar, mapas, influencia, evolución).
- `analytics.py` — motor de cálculo. Clasificación de acciones, métricas,
  agregaciones, filtros (parte, contexto), datos de todos los gráficos.
- `storage.py` — capa de datos con Supabase. Sesiones, fichas de jugador, y
  URLs de fotos del bucket.
- `similitud.py` — modelo de similitud Nivel 1 (vector por-90 + coseno vs tops).
- `secuencias.py` — Fase 4. Motor de secuencia individual: detección de cadenas,
  localizador de jugadas para vídeo y patrones recurrentes. Reusa
  `analytics.nota_evento` para valorar; NO toca la nota.
- `styles.css` — tema neón.
- `diccionario_resultados.json` — diccionario canónico por acción (ver §4).

**MCP (en el ordenador del usuario, NO en el repo de la app):**
- `server.py` — servidor MCP (FastMCP). Herramientas: listar_tablas,
  describir_tabla, consultar, sql_select, dossier_jugador, vector_jugador,
  clips_jugador. Usa la service_role key y conexión propia a Supabase. Lo
  arranca `claude_desktop_config.json` con el Python313 de
  `AppData\Local\Programs\Python\Python313`, NO el del PATH: verificar contra ESE
  intérprete (el del PATH no tiene `mcp` ni `psycopg`).
- `dossier.py` — construye el dossier analítico completo de un jugador.
- `vector.py` — construye el vector de 28 features por-90 para similitud.
  Sincronizado con `similitud.py` de la app (calibración Fase 3, ver §7):
  verificado idéntico feature a feature sobre la base entera.
- `nota.py` — sistema de nota (Fase 2) en Python puro.
- `secuencias.py` — Fase 4. Port en Python PURO del motor de la app (sin pandas);
  alimenta `clips_jugador`. Reusa `nota.nota_evento`; NO toca la nota.
- `analytics.py` — **CÓDIGO MUERTO**: copia vieja (jun-2026) que no importa nadie.
  Los módulos vivos son los de arriba. No fiarse de él como referencia.
- El MCP tiene su PROPIA copia de la lógica; usa de la ficha solo min_in/min_out
  y posición (que viajan en la sesión), NO las fotos.

**Despliegue:**
- Repo: `github.com/gerardsarda/app_scouting`.
- Streamlit Community Cloud. Deploy vía `git push` desde PowerShell (Windows).
- Tras push, si la nube da error pese a código correcto → CACHÉ → **Reboot app**
  en Manage app (no borra datos, viven en Supabase).

**Entorno de desarrollo de Claude:**
- Trabaja en `/home/claude/app/`, SE REINICIA entre tandas. Recuperar copiando
  desde `/mnt/user-data/outputs/`.
- Dependencias a reinstalar: `pip install pandas numpy streamlit --break-system-packages`.
- Verificar SIEMPRE: sintaxis (`python3 -c "import ast..."`) y arranque de la app
  con AppTest de Streamlit mockeando `storage`.
- Al tocar `analytics.py`, copiar la parte equivalente al MCP.

---

## 3. ESTRUCTURA DE DATOS (Supabase)

**Tabla `sesiones`** — un partido por fila:
- id, nombre, fecha, tipo ('jugadores'), competicion
- equipo_local, equipo_visitante, goles_local, goles_visitante, posesion_local
- minuto_descanso: **NO es una columna** (verificado 2026-07-16 contra
  information_schema). Vive dentro de `meta`; `analytics.flatten_events` lo lee de
  `meta` con fallback a 45. CONSECUENCIA: la lista de columnas de
  `storage.load_all_sessions` la pide igual, la query falla siempre con
  `42703 column does not exist` y cae al `select("*")` del except. Funciona, pero
  hace DOS consultas en cada carga. Ojo si se limpia: es ese fallback el que trae
  `jugadores_info` (que la lista de columnas omite a propósito), y de ahí salen
  el equipo del jugador y los min_in/min_out. Ya no pesa: las fotos viven en
  Storage desde hace tiempo (ver §5).
- jugadores (lista), posiciones (dict jugador→pos)
- events (JSONB): lista de acciones tagueadas
- meta: nivel_propio, nivel_rival (escala Élite/Alto/Medio/Bajo), contexto_partido
- jugadores_info (JSONB): ficha ligera por jugador (pos, equipo, edad, min_in,
  min_out). YA NO contiene fotos (ver §5).

**Cada evento en `events`:**
- jugador, posicion, minuto, minuto_fmt
- accion (ej. "Pase progresivo"), resultado (ej. "Correcto", "Gol", "—")
- zona, zona_x (0=def, 1=medio, 2=ataque), zona_y

**Tabla `jugadores`** — ficha por jugador (separada de las sesiones):
- id, nombre, posicion, equipo, edad, min_in, min_out, updated_at
- (foto/bandera existen como columnas pero van vacías; las fotos viven en Storage)

**Bucket `fotos`** (Supabase Storage, PÚBLICO):
- Fotos y banderas sueltas (sin subcarpetas). Nombres normalizados + extensión.
- Ver §5 para el detalle.

**MULTI-EQUIPO (2026-07-20).** Terminado el Mundial se taguean partidos previos
del jugador con su club o categorías inferiores (Gilberto Mora → México,
México U20, Tijuana). El dashboard SIEMPRE agregó por NOMBRE de jugador, así que
los datos ya salían unidos; lo que había que arreglar era que `equipo` fuese un
solo campo global.
- **`jugadores.equipo`** (tabla global) = **equipo PRINCIPAL**. Único que alimenta
  la **bandera** del hero. Sin migración: ya contenía el país.
- **`jugadores_info[jug]["equipo"]`** de cada sesión = **equipo EN ESE PARTIDO**.
  Es la fuente de verdad. Ya existía y ya estaba poblado.
- `analytics.flatten_events` expone la columna **`equipo_jugador`** (sesión →
  fallback al principal vía el 2º parámetro `equipos_principales`, que
  `_load_all_flat` rellena con `storage.list_jugadores()`).
- **`_rival_partido` bebe de `equipo_jugador`**, no de `jugador_info`. Sin esto,
  en un partido de club el equipo de la ficha ("México") no casaba con ningún
  lado y el rival caía al visitante — que podía ser el PROPIO equipo del jugador.
- **Verificado contra la BD entera:** 78 pares jugador-partido, **0 sin equipo**
  y el equipo **casa siempre** con local o visitante → el fallback no se dispara
  hoy y el cambio es de comportamiento IDÉNTICO sobre los datos actuales.
- **Registro**: dos campos separados, "Equipo principal (bandera)" (→ ficha
  global) y "Equipo en este partido" (→ solo la sesión). Antes eran uno, y
  editarlo para un partido de club **pisaba el histórico entero**.
- **Dashboard**: selector "Equipo" en el sidebar (`Todos` + equipos con nº de
  partidos). Filtra por `session_id` y va el PRIMERO, antes que partido y
  contexto, así que arrastra a todo (tarjetas, radar, mapas, nota, influencia,
  evolución, similitud).
- **Hero**: bandera = equipo principal SIEMPRE. **Equipos y posiciones se pintan
  TODOS con filtro o sin él** (`analytics.equipos_de_jugador` /
  `posiciones_de_jugador`, calculadas sobre el df SIN filtrar): el hero es la
  identidad del jugador, no la selección de datos. El **set de métricas** sí sigue
  sugiriéndose desde la posición más frecuente, que necesita una sola.
- **MCP**: `dossier_jugador(jugador, equipo="")` y `clips_jugador(..., equipo="")`.
  `dossier.ficha` pasa de `equipo` (que salía de la PRIMERA sesión encontrada, o
  sea arbitrario) a **`equipos`** (lista con nº de partidos) + `equipo` = el más
  frecuente + `equipo_filtrado`. Cada `contextos_partidos` gana `equipo`.
  **Reiniciar el MCP.**
- **`vector_jugador` NO gana filtro de equipo, a propósito**: con la muestra por
  club que habrá, un vector de 4 partidos es ruido y el filtro invitaría a leerlo
  como si fuese sólido. La similitud del dashboard sí lo respeta, por coherencia.
- Diseño completo en `docs/superpowers/specs/2026-07-20-multi-equipo-jugador-design.md`.

---

## 4. METODOLOGÍA DE SCOUT — clasificación de acciones

**Diccionario canónico POR ACCIÓN** (`diccionario_resultados.json`, _version 2,
60 acciones): para cada acción, clasifica sus resultados posibles en
exito / parcial / fallo / fallo_parcial / fallo_medio / fallo_grave / neutro.

Idea clave (del usuario): el MISMO resultado puede significar cosas distintas
según la acción. Ej.: "—" es FALLO en "Error grave / pérdida" pero NEUTRO en
"Generación de ocasión". `analytics` clasifica cada evento (viejo o nuevo)
mirando la tabla de SU acción, sin necesidad de re-taguear.

**Decisiones de scout tomadas:**
- Remates: "Gol"=éxito(1.0), "A puerta"=parcial(0.5), "Fuera"/"Bloqueado"/"Barrera"=fallo.
- Duelo 1v1 def.: "Correcto"=éxito, "Retrasó/aguantó"=parcial, "Regateado"/"Fallo"=fallo.
- Presión fuerza error: "Correcto"=éxito, "Fallo"=NEUTRO (presionar vale aunque
  no robes).
- Penalti provocado y Generación de ocasión = ÉXITO (generan ocasión de gol).
- Penalti cometido y Tarjeta roja = fallo_grave. Error grave/pérdida = fallo_medio.
  Falta, Tarjeta amarilla, Falta táctica = fallo_parcial.

**Pesos negativos (fallo_grave -1.0, fallo_medio -0.7, fallo_parcial -0.15):**
definidos en el JSON (`pesos._pesos_nota_fase2`) pero NO activos. Hoy, en el %
de acierto (que es una división, no admite negativos), todas las variantes de
fallo cuentan como intento fallado (peso 0, bajan la media sin restar). Los
negativos se activarán en el sistema de NOTA (Fase 2). AVISO: al meter faltas/
amarillas en el % de acierto, el % defensivo puede ensuciarse; revisar con datos
reales y, si molesta, devolverlas a neutro dejando la penalización solo en la nota.

**Equivalencias de pase** (en el código, no en el diccionario): Pase entre líneas
/ al espacio / largo / cambio de orientación cuentan como Pase progresivo; Pase
de primera como Pase atrás; Pase clave / bajo presión / Asistencia NO suman como
pase nuevo (son complemento informativo, PASE_COMPLEMENTO).

**Sets de posición** (`analytics.SETS_POSICION`, 8 métricas por posición para el
radar/tarjetas): EXT, MP, MC/MCD, DC, DFC, LAT. Cada uno con sus métricas
combinadas (pase_prog, def_combinada, duelos_aereos, ofrece_apoyo, goles).

El diccionario de variables completo (definición de cada acción y cuándo usarla)
lo mantiene el usuario aparte.

---

## 5. FOTOS (Supabase Storage)

Historia: empezaron en base64 dentro de la BD → causaba statement timeout
(código 57014) y se perdían al crear otra sesión. Migradas a Storage.

**Cómo funciona ahora:**
- Bucket público `fotos`, archivos sueltos (sin subcarpetas).
- La app NO sube fotos; se suben a MANO en el panel de Supabase.
- La app construye la URL desde el nombre del jugador (foto) y el equipo/país
  (bandera), normalizado con `_slug()` (minúsculas, sin tildes, espacios→"_").
- Prueba varias extensiones (.PNG, .png, .jpg...) y usa la que exista de verdad
  (comprobación HEAD en el servidor, cacheada 1h en `_primera_url_existente`).
- URL base: `https://xcqlxeyfdmenulbkkrhn.supabase.co/storage/v1/object/public/fotos/`
  (en `storage.py`, o vía st.secrets FOTOS_BASE_URL).
- La foto es del JUGADOR (vive en el bucket, una vez), no del partido → nunca se
  borra al crear otra sesión.

**Reglas de nombres al subir:** "Gilberto Mora"→`gilberto_mora.PNG`,
"Costa de Marfil"→`costa_de_marfil.PNG`.

**Si una foto no sale:** casi siempre es (a) caché de 1h → Reboot, o (b) nombre
del archivo no coincide con el slug del jugador. Comprobar abriendo la URL
pública en el navegador.

---

## 6. DASHBOARD (sección Gráficos)

Controles en el SIDEBAR: selector jugador, set de posición (autodetectado),
modo (Total / Aciertos / Total 90 / Aciertos 90), parte del partido, y filtro
de contexto de rival.

- **Cabecera (hero):** bandera de fondo + foto + nombre/posición/equipo/edad/minutos.
- **8 tarjetas** de métricas según el set de posición.
- **Radar** (ancho completo): ejes por categorías o acciones, comparar 1 jugador.
- **Mapa de calor:** escala de color CONTINUA verde→amarillo→rojo (normalizada
  entre min y max reales con realce, para distinguir volúmenes).
- **Mapa de acciones por tercios.**
- **Influencia por minuto:** barras de volumen + línea de eficiencia por franjas
  de 15', con símbolos de peligro (★ gol, ▲ tiro a puerta, ◆ pase clave). Hasta
  3 jugadores. Símbolos DEBAJO del gráfico.
- **Evolución partido a partido:** rival en el eje X, hasta 3 jugadores con
  color distinto, puntos del color de la línea pero más oscuros.
- **Similitud con jugadores top** (Nivel 1).

**Filtro de contexto (Fase 1, punto 3):** compara nivel_propio vs nivel_rival
de cada partido → clasifica en superior/similar/inferior. Cuenta los partidos
DEL JUGADOR seleccionado (no del total). Filosofía: mostrar el contexto para
que el scout haga el cruce con su ojo, no calcular medias con submuestras
pequeñas que engañan.

**Parte del partido:** usa el minuto_descanso PROPIO de cada partido (columna en
cada evento vía flatten_events), no un valor global.

**Colores neón:** INK=#ffffff, NEON_OK=#15ff66, NEON_BAD=#ff2d55,
NEON_GOLD=#ffcc00, NEON_SKY=#38bdf8, violeta=#a855f7, TXT_LO_SVG=#8b93a1,
GRID_SVG=#2a2e38, PANEL_SVG=#15171c.

---

## 7. MODELO DE SIMILITUD (Nivel 1)

`similitud.py`: construye un vector de 28 features por-90 del jugador, lo
estandariza (z-score) contra los tops de su posición y compara por coseno.
- CSV de referencia: 59 jugadores top FotMob, 6 posiciones (~10 c/u).
- El coseno mide FORMA (perfil), no nivel. Valores absolutos bajos son normales;
  importa el orden y el perfil "destaca/floja".
- Métricas NEGATIVAS (Pérdidas, Faltas, Regateado, Tarjetas) se invierten en
  destaca/floja (destacar = tener pocas).
- Fiabilidad según nº de partidos (baja <5).

**CALIBRACIÓN tagueo-manual vs FotMob (2026-07-16, Fase 3).** Al medir contra
datos reales se detectó que los vectores de los ojeados estaban a **norma 18.84**
del centro de los tops (los tops entre sí: 5.05) y con **coseno medio +0.61 entre
ellos** (tops: −0.11): o sea, todos empujados en la MISMA dirección ≈3.6σ. No era
fútbol, era **desajuste de definiciones** en 2 métricas concretas (el resto
encajaba; `Toques` daba 69.3 vs 68.5 → el volumen de tagueo es correcto):
1. **`Posesion ganada en 3r Tercio`** (2.18 vs 0.91): incluía `Presión fuerza
   error`, que FotMob NO cuenta como posesión ganada (solo el robo efectivo).
   **Sacado de `POSESION_3T`** → 0.98 vs 0.91, clavado. La presión sigue contando
   en el % de acierto y en la nota; el cambio es SOLO del vector de similitud.
2. **`Pérdidas de balón`** (4.47 vs 1.25): la nuestra suma regate fallado (2.05,
   que además es DOBLE CONTEO — ese evento ya vive en `Regates realizados %`),
   protección fallada, control difícil, conducción y error grave. Decisión del
   usuario: **conservar la definición amplia** (es la buena para el scout y para
   la nota) y **excluir la métrica del vector de comparación**, vía
   `similitud.features_excluidas` en el JSON.
- **Resultado:** norma 18.84 → **9.94**, coseno entre ojeados +0.61 → **+0.19**.
  El 2x de norma que queda es diferencia real sub-20 vs élite. Ya aparecen
  similitudes NEGATIVAS (perfiles opuestos), señal de que el modelo discrimina.
- **Cambia respuestas ya en producción:** el top más parecido a Diomande pasó de
  Nico Williams a Saka; el ojeado más parecido, de Rayan a Alajbegovic.
- **MCP SINCRONIZADO (2026-07-17).** `scouting-mcp/vector.py` ya replica la
  calibración; era el último pendiente de Fase 3.
  - **Cambio 1 aplicado:** `Presión fuerza error` fuera de `POSESION_3T`. El sesgo
    era grande y medido contra la BD: Diomande 18 vs 8, Maza 16 vs 9, Nusa 3 vs 0.
  - **Cambio 2 aplicado como METADATO, no borrando el dato** (decisión del
    usuario, mismo criterio que la app): `vector_jugador` sigue devolviendo las 28
    columnas —"Pérdidas de balón" incluida, porque el número amplio es el bueno
    para el scout— y añade `features_excluidas` + `columnas_comparacion` (27),
    leídos del bloque `"similitud"` del JSON vía `vector._cargar_sim_cfg()`, misma
    fuente que `similitud.FEATURES_EXCLUIDAS`. La docstring dice explícitamente
    que para z-score/coseno se use `columnas_comparacion`, NO `columnas_orden`.
  - **DERIVA EXTRA encontrada al contrastar** (no era de Fase 3, era copia vieja),
    ya sincronizada: al MCP le faltaba `Duelo en ABP def.` en `DUELOS_TOTALES` y
    en `AEREOS`, y `Despejes` no sumaba `Despeje en ABP def.`. Poco volumen (4
    eventos en toda la base) pero movía el "Duelos ganados %" de Manzambi 2 puntos
    (38.1 vs 40.0). OJO al matiz que se replicó tal cual: la app cuenta `Duelo en
    córner def.` en los duelos pero NO `Despeje en córner def.` en los despejes.
  - **Verificado sobre la BD ENTERA**, no sobre una muestra: los dos
    `construir_vector` (app y MCP) sobre los mismos datos → **21 jugadores × 28
    features = 588 comparaciones, 0 discrepancias**.
  - Falso amigo descartado de paso: la app decide el tercio por `zona_x==2` y el
    MCP parsea el texto con `dossier._tercio`, que mira `"2" in z` ANTES que el 3.
    Con los 9 valores reales de `zona` ("3er tercio · Centro"…) coinciden, así que
    no es un bug hoy; sí lo sería si alguien mete un "2" en el nombre de una zona
    del 3er tercio.
  - **Reiniciar el MCP** para tomar los cambios.

---

## 8. ESTADO DEL ROADMAP

**Fase 0 (datos) — COMPLETA.**
1. Vocabulario cerrado (vía diccionario por acción).
2. Éxito+detalle (derivado del diccionario, sin retaguear).
3. Diccionario canónico JSON versionado.
4. Auditoría de datos: botón en Registro→Mantenimiento que detecta combinaciones
   acción+resultado sin clasificar (huérfanas por nombres viejos).

**Fase 1 (MCP) — COMPLETA (2026-07-13).**
- Punto 2 (percentiles): DESCARTADO (mal de raíz con tagging manual, poca población).
- Punto 3 (contexto): HECHO como filtro en el dashboard.
- Punto 4 (fiabilidad): YA EXISTÍA en el dossier.
- **Punto 1 (sql_select con rol de solo lectura): HECHO.** Se sustituyó el
  filtro por texto "select" por un rol Postgres real (`scouting_ro`) con
  permiso único de SELECT + timeout de 15s, conectado vía connection string
  propia (session pooler) desde `server.py` con `psycopg` y transacción
  READ ONLY. Desbloquea WITH, CASE, ventanas y casts. `jugadores` tiene RLS
  activado → se añadió policy `scouting_ro_read` para que el rol pueda leerla
  (si se crean tablas nuevas con RLS, replicar la policy). Verificado:
  lectura OK (WITH/CASE) y escritura bloqueada (`cannot execute UPDATE in a
  read-only transaction`). El RPC antiguo `ejecutar_select` queda obsoleto.
  Detalle completo en `scouting-mcp/INSTRUCCIONES_FASE1.md` y
  `scouting-mcp/fase1_setup.sql`.

**Fase 2 (sistema de nota) — REDISEÑADA a VALOR ACUMULADO (2026-07-14); predictor aplazado.**
- **Modelo de VALOR ACUMULADO** (tipo rating de analista real; sustituye a la
  media ponderada anterior, que medía fiabilidad y sesgaba hacia defensas):
  `nota = clip( baseline + k · Σ(valor_outcome · factor_zona), 0, 10)`.
  Cada `(acción, clase)` tiene un **valor propio y ASIMÉTRICO**: premio si sale
  bien, castigo si sale mal, independientes. Un gol SUMA mucho (+3.0, el ancla),
  un pase atrás casi nada (+0.02), una pérdida en tu área RESTA mucho (−1.5·zona).
  Premia el **impacto acumulado** (goles, ocasiones, duelos ganados), no el % de
  acierto → los goles ya no se diluyen y disparar/regatear no penaliza como antes.
  El `%` de acierto del dashboard se queda como eje de **fiabilidad**; la NOTA es
  el eje de **impacto**. Se leen juntas.
- **Por qué el cambio:** la media ponderada tenía techo 1.0 por acción (era un
  "% de acierto ponderado"), así que premiaba la fiabilidad (defensas, pases
  simples) y castigaba la ambición (remates/regates fallados = ceros pesados).
  Manzambi marcó 2 goles y sacaba 5.8. Con el modelo nuevo (ya con las palancas
  de abajo) saca 8.2 de media; su partido de 2 goles, 9.0.
- **Config en `diccionario_resultados.json` → bloque `"nota"`** (editable a mano):
  `modelo: "valor_acumulado"`, `baseline` (5.0), `k` (0.30, el usuario los da por
  ajustados — NO tocar sin datos), `valores` (dict por acción con `{exito, parcial,
  fallo, fallo_parcial, fallo_medio, fallo_grave}` según use), `valores_default`,
  `excluir_clases` (neutro) y los tres pesos de zona. El gol es el ancla +3.0;
  todo lo demás es relativo a eso.
- **TRES PALANCAS de calibración de scout (2026-07-14, sobre datos reales).** El
  modelo de suma pura inflaba a los defensas por VOLUMEN: Ngoy se iba EXPULSADO y
  sacaba 9.4 (26 pases progresivos + conducciones aportaban +4 pts de nota; la
  roja −0.9 quedaba sepultada). Diagnóstico verificado con sus 3 partidos reales.
  Se añadieron al bloque `"nota"` del JSON y a `nota_jugador`:
  1. **Freno de volumen (circulación de bajo riesgo).** El aporte POSITIVO de las
     acciones de `circulacion_bajo_riesgo` (`Pase progresivo`, `Conducción
     progresiva`, `Pase atrás`, `Pase lateral`) NO suma lineal: se comprime por
     partido con `techo_circulacion·tanh(Σ/techo_circulacion)` (`techo_circulacion`
     2.5). Así 26 pases correctos no inflan; regate, duelos, remates, pase clave y
     TODA la defensa siguen lineales (decisión del usuario: un partidazo a base de
     regates o de defensa de mérito debe sumar 100%). Los FALLOS de esas acciones
     (negativos) sí restan completo. NOTA: se detectó que la defensa de volumen
     (despeje ×8, etc.) también infla, pero el usuario decidió NO tocar la defensa.
  2. **Roja/penalti cometido restan fuerte** (sin techo de nota): `Tarjeta roja` y
     `Penalti cometido` pasan de −3.0 a **−8.0**. Un expulsado cae al 3-4 (Ngoy vs
     Irán: 9.4 → 3.8). Decisión del usuario: restar mucho, no poner tope duro.
  3. **Ajuste por nivel de rival** (difícil = más mérito y más perdón). `delta =
     nivel_valor[rival] − nivel_valor[propio]` (Élite 4/Alto 3/Medio 2/Bajo 1);
     el premio se multiplica por `1 + rival_sensibilidad_premio·delta` y el castigo
     por `1 − rival_sensibilidad_castigo·delta` (ambas 0.08/escalón). Contra rival
     superior el acierto vale más y el fallo pesa menos; contra inferior al revés.
     `flatten_events` ahora propaga `nivel_propio`/`nivel_rival` a cada evento.
  Fórmula final: `nota = clip(baseline + k·[(circ_comp + resto_pos)·f_premio +
  neg·f_castigo], 0, 10)`. Todo por PARTIDO (`nota_jugador` asume un partido).
- **DOS regímenes de zona** (decisión de scout): el **premio** (valor≥0) usa zona
  direccional — ofensivas premian arriba `peso_zona_premio_of {0:0.8,1:1,2:1.3}`,
  defensivas cerca de tu área `peso_zona_premio_def {0:1.3,1:1,2:0.8}`. El
  **castigo** (valor<0) usa `peso_zona_perdida {0:1.3,1:1,2:0.7}`: perder balón/
  duelo duele más cerca de tu portería, en CUALQUIER acción (un mal regate en
  campo rival ≈ gratis; una pérdida en tu tercio, cara). `Error grave / pérdida`
  salió de `acciones_sin_zona` para usar el factor pérdida. Disciplina fija
  (roja, penalti cometido, tarjetas, faltas) y sprints siguen sin zona (1.0).
- **Neutros** (sprints, falta recibida, presión que no roba) se EXCLUYEN.
- **Motor en `analytics.py`:** `nota_evento` (→ contribución float o None),
  `nota_jugador` (→ {nota, suma, n}), `serie_nota_por_partido`,
  `_valor_outcome_nota`, `_factor_zona_nota`, `_cargar_nota_cfg`. `suma` = valor
  acumulado bruto (antes de baseline/k).
- **Dashboard:** badge de NOTA en el hero dentro de un **círculo** con borde/glow
  del color de banda (ya no se funde con el panel), solo el número (sin label
  "Nota" ni contador de acciones; el aviso de muestra baja va en `title`/tooltip)
  + gráfico **"Evolución de la nota" en BARRAS** (`barras_nota_svg`, hasta 3
  jugadores agrupados) coloreadas por banda. Ambos respetan parte y contexto.
- **Bandas de color** (helper `_color_nota`, mismo criterio en badge y barras):
  `[1,5)`→rojo `NEON_BAD`, `[5,7)`→naranja `NEON_ORANGE`, `[7,9)`→amarillo
  `NEON_GOLD`, `≥9`→verde `NEON_OK`.
- PASE_COMPLEMENTO (Pase clave / bajo presión / Asistencia) **sí puntúan** aparte
  en la nota (suman impacto extra: Asistencia +2.0, Pase clave +0.8).
- **MCP: SINCRONIZADO con las 3 palancas (2026-07-14).** `scouting-mcp/nota.py`
  replica la lógica nueva: `nota_de_eventos(eventos, nivel_propio, nivel_rival)`
  aplica el freno de circulación (palanca 1) y el ajuste de rival (palanca 3), y
  la roja=−8 (palanca 2) llega vía el diccionario. `dossier.py` pasa el nivel de
  cada partido y guarda la nota por partido. **CAMBIO de semántica:** el campo
  `nota` global del dossier ya NO es la suma acumulada sobre el pool, sino la
  **MEDIA de las notas por partido** (nueva `nota.nota_media`, mismo criterio que
  el badge del dashboard); devuelve `{nota, n_partidos, n_acciones}`. Verificado:
  MISMAS notas que la app (Ngoy 6.5 media / partido de la roja 3.8; Manzambi 8.2).
  El JSON se copió a `scouting-mcp/` (copia local sincronizada). Reiniciar el MCP
  para tomar cambios.
- **Predictor** (acción+zona+posición, sin minuto): APLAZADO por decisión del
  usuario.
- **`k` (0.30) y `baseline` (5.0):** el usuario los da por ajustados. NO tocar
  sin una nueva tanda de datos que lo justifique.
- **Ajuste por dificultad de rival: HECHO** (palanca 3, ver arriba). Ya no es
  pendiente.
- **PENDIENTE — sincronizar el MCP** con las 3 palancas (ver bloque MCP arriba).
- **Verificación de las palancas (2026-07-14):** sobre datos reales. Ngoy (central
  expulsado) 9.1 → 6.5 de media (partido de la roja 9.4 → 3.8). Manzambi (goleador)
  8.2 de media, goles sin diluir, rival correcto (gris vs Qatar/Bajo → 5.9;
  partidazo vs Canadá/Alto → 9.7). Falta ver el arranque visual del dashboard en
  Streamlit (los cambios no tocan UI; interfaces de `nota_media_jugador` y
  `serie_nota_por_partido` intactas).

---

## 8bis. ROADMAP PENDIENTE (renumerado 2026-07-14)

Reordenado sobre lo que queda por hacer, tras revisar el roadmap completo
guardado en Drive ("Roadmap_Scouting") y recortar según decisión del usuario.
Fase 0 (datos) y la Fase 1 histórica (MCP) están completas — ver arriba.

**Fase 1 — Filtro por partido en el dashboard (NUEVA).**
- Añadir selector de partido concreto en el sidebar del dashboard, para ver la
  performance del jugador en ESE partido (no agregada).
- Eliminar el filtro de 1ª/2ª parte (se sustituye por el filtro de partido).

**Fase 2 — Sistema de nota (en curso).**
- HECHO (2026-07-14): 3 palancas de calibración de scout (freno de volumen en
  circulación, roja=−8, ajuste por nivel de rival). Ver §8, Fase 2.
- `k` y `baseline` dados por ajustados por el usuario; no tocar sin datos nuevos.
- HECHO (2026-07-14): MCP sincronizado con las 3 palancas (ver §8, bloque MCP).
- Aplazado: perfiles de peso por estilo de juego (dominador vs bloque bajo),
  necesarios para el contrafactual de Fase 6.

**Fase 3 — Similitud coseno + proyección PCA 2D. COMPLETA (2026-07-16).**
- **`_z_space()` es la FUENTE ÚNICA del espacio**: ranking y mapa beben de ahí.
  Población de referencia = SOLO los tops de la posición (fijan media y
  desviación); los ojeados se PROYECTAN, no la definen (con ~6 ojeados la
  desviación sería ruido y un outlier deformaría la escala de todos).
- **`vectores_ojeados(sesiones)`**: pool de la propia base con umbral de muestra
  (`min_minutos` 90 para entrar; por debajo de `minutos_solido` 270 entra pero
  marcado `atenuado`). Config en el bloque `"similitud"` del JSON. De 21
  jugadores tagueados, entran 16.
- **Ranking en DOS listas separadas** (decisión del usuario): tops (a qué
  referencia se parece) y ojeados (qué alternativa de la lista cubre el perfil).
  Comparten z-space → los % son comparables.
- **`mapa_pca()`**: PCA por SVD de numpy (sin sklearn, mismo idioma que el resto
  del archivo). **Se ajusta SOLO con los tops** y los ojeados se proyectan: así
  los ejes NO se mueven al taguear un jugador nuevo y el mapa es estable entre
  sesiones. Devuelve `var_explicada` y las cargas para nombrar los ejes.
- **`_norm_filas()`**: normaliza antes del PCA para que `|a-b|² = 2-2·cos`, o sea
  que la distancia del mapa sea función del coseno del ranking. Verificado: 0
  pares violan la identidad. NO altera el ranking (el coseno es invariante a
  escala).
- **LÍMITE MEDIDO, no opinado.** Aplastar 28 dims a 2 conserva el **47-52%**.
  A lo grande el mapa es bueno (**Spearman 0.62-0.80** entre distancia 2D y real),
  pero en las distancias cortas **reordena a los vecinos** (solo 7/15 aciertan el
  vecino más cercano). Es inherente al PCA, no un bug. Por eso el mapa **dibuja
  los 3 parecidos REALES por coseno** con líneas discontinuas desde el jugador en
  foco: la posición la pone el PCA, la verdad la pinta el coseno encima. La UI lo
  dice explícitamente ("si el mapa y las líneas no coinciden, manda la línea").
- **`mapa_perfiles_svg()`** en `scouting_app.py` (tema neón, tops huecos, ojeados
  en `NEON_SKY`, foco en `NEON_GOLD` con glow, atenuados punteados). Tiene
  anticolisión de etiquetas: reserva hueco en orden de importancia (foco →
  ojeados → tops) y pinta en orden de capas (tops al fondo → foco arriba).
- Arreglado de paso: `MAPA_POS_CSV` no tenía `"MED"` (Gilberto Mora, Maza, Nico
  Paz caían en la primera posición de la lista). Ahora `MED` y `MP` van al bloque
  `"MC organizador"` junto con los `MC`, por decisión del usuario.
- **Ver §7** para la calibración tagueo-vs-FotMob, que salió de esta fase y era
  el bug de fondo.
- Descartado de esta fase (2026-07-14): generador de dossier en PDF (ya existió
  y se quitó; el MCP se construyó principalmente para sustituirlo), dashboard
  comparativo (rejillas 3×3), motor de shortlisting con umbral de muestra.
- Descartado (2026-07-16): comparar contra la propia base como POBLACIÓN de
  referencia (z-score sobre los ojeados) y el PCA global de todas las posiciones.

**Fase 4 — Métricas de secuencia. COMPLETA (app 2026-07-16; MCP 2026-07-17).**
- **Alcance corregido: secuencia INDIVIDUAL, no colectiva.** El roadmap pedía
  cadenas recuperación→progresión→ocasión, pero eso es cadena de EQUIPO y la
  base no la sostiene: **29 de 47 partidos tienen un solo jugador tagueado**
  (12 dos, 6 tres). Reconstruirla con 1-3 de los 22 del campo mediría a quién se
  decidió taguear ese día, no fútbol. Sí hay datos para la individual: de 4.420
  pares consecutivos del mismo jugador, **2.015 (46%) a ≤15s**, mediana 20s, y
  el minuto tiene resolución de segundos (4.437 de 4.491 eventos con decimales).
- **`secuencias.py`**: `detectar_secuencias` (corta por `ventana_gap` 15s
  agrupando por partido+jugador; orden estable para respetar el orden de
  tagueo en empates de minuto), `continuidad`, `top_secuencias` (localizador de
  vídeo), `patrones_bigrama`, `patrones_familia`. Config en el bloque
  `"secuencias"` del JSON (`ventana_gap`, `min_acciones` 2, `min_repeticiones`
  3, `familias`, `desenlace_peligro`).
- **HALLAZGO que condicionó el diseño (medido, no opinado):** el patrón del
  ejemplo del usuario `Conducción progresiva > Recorte > Centro lateral` es el
  nº1 de la base — 7 veces, pero **repartidas entre 5 jugadores**. Es un patrón
  del fútbol, no de un jugador. Máximo que UN jugador repite un patrón:
  **3 acciones exactas → 3 veces (1 solo par jugador-patrón con ≥3 en TODA la
  base)**; 3 familias → 10 (38 pares con ≥3); 2 acciones exactas → 18 (121
  pares). **Por eso NO existen los trigramas de acción exacta**: sólo el bigrama
  de acción exacta. No es una carencia por hacer: es una decisión. Reevaluar
  sólo con mucha más muestra.
- **Trigramas de FAMILIA: RETIRADOS (2026-07-16), decisión del usuario** — "no
  aporta nada". Aunque había datos (38 pares con ≥3), lo que salía era del tipo
  `Circula > Circula > Circula`: cierto pero inútil para el scout. Se quitó el
  bloque de UI y, con él, `patrones_familia`, `familia()`, la columna `familias`
  y el mapeo `familias` del JSON (61 entradas) — sin consumidor era código
  muerto. Si algún día se quiere para el MCP, está en el historial de git
  (commit `36945d1`).
- **`min_pct_bigrama` (10%)**: "Tras esta acción, ¿qué hace?" corta la cola
  larga y sólo muestra las salidas por encima de ese %. `patrones_bigrama`
  devuelve `(tabla, total)`: el % se calcula sobre el TOTAL real y la UI lo
  enseña siempre — un 100% de 2 veces no es una tendencia.
- **NO toca la NOTA a propósito.** Repartir el valor de la cadena hacia atrás
  sería doble conteo (la nota ya paga Pase clave +0.8, Generación de ocasión y
  Gol +3.0) y obligaría a recalibrar `k` y las 3 palancas de la Fase 2, ya
  ajustadas contra datos reales. **Tres ejes separados que se leen juntos:**
  % de acierto = fiabilidad, NOTA = impacto, secuencia = **continuidad**.
- **Minuto crudo** para el vídeo, sin margen de compensación de lag de tagueo
  (decisión del usuario).
- **Desenlace** de la cadena = lo que marca su ÚLTIMA acción: `peligro`
  (remates, generación de ocasión, pase clave, asistencia, penalti provocado),
  `perdida` (clase de fallo según el diccionario de esa acción) o `neutro`. Las
  secuencias de 1 acción se devuelven siempre, pero el localizador y los
  patrones exigen `min_acciones`; la cabecera de continuidad las cuenta todas
  (excluirlas inflaría el largo medio y los %).
- **UI**: sección propia "Secuencias" en el nav. Sin filtros de partido/contexto
  a propósito — el dashboard los tiene inline en `_graficos_jugadores`, no como
  helper; copiarlos sería duplicar.
- **NO se usa `st.dataframe` en esta sección, y es a propósito.** Ese componente
  es Glide: **pinta las celdas sobre un `<canvas>`**, así que el CSS del tema no
  entra — heredaba un fondo verde saturado y la cabecera se volvía ilegible (ya
  había un intento fallido de domarlo en `styles.css`, "Anular cualquier fondo
  verde heredado"). Las tablas de la sección son HTML propio
  (`tabla_secuencias_html`, `kpis_continuidad_html`) + SVG (`barras_bigrama_svg`),
  el mismo idioma que el resto del dashboard. Estilos en `styles.css`, bloque
  `SECUENCIAS`, con clases prefijadas `.seq-*`. **Si vuelve a aparecer una tabla
  con fondo verde y cabecera invisible en otra sección, la causa es ésta.**
- **El minuto se pinta como timecode `mm:ss`** (`_mmss`), no como decimal: la
  pantalla existe para buscar el clip en el vídeo, y `21:12` es el idioma del
  vídeo, `21.20` no. Va en monoespaciada y es el elemento dominante de cada fila.
- **PRIMEROS TESTS DEL REPO** (`tests/`, pytest). **`pytest` NO está en
  `requirements.txt`** a propósito: ese fichero lo instala Streamlit Cloud en el
  deploy. En local: `pip install pytest`; correr con `python -m pytest tests/ -q`.
  `tests/test_secuencias_reales.py` contrasta el motor contra DATOS REALES
  (fixture de 241 eventos de 3 partidos con varios jugadores): **153 secuencias;
  largo 1→99, 2→36, 3→9, 4→5, 5→2, 6→1, 7→1**, números calculados por SQL contra
  la BD, no por el propio código. Se usa un subconjunto y no la base entera
  (4.491 eventos → 2.476 secuencias) para no meter 700 KB de datos en el repo.
  Si ese test falla, el sospechoso es el motor, no el test.
- **MCP: HECHO (2026-07-17).** `scouting-mcp/secuencias.py` + tool
  `clips_jugador(jugador, n, peores, desenlace, partido)` en `server.py`: pide
  clips en lenguaje natural ("dame las mejores jugadas de Diomande", "sus peores
  acciones", "jugadas que acabaron en remate", "qué hizo contra Irán"). Devuelve
  cada cadena con **timecode `mm:ss`** (mismo `_mmss` que la UI: el minuto crudo,
  sin compensar lag), la cadena de acciones, su `valor` y su `desenlace`.
  - **Portado a Python PURO, sin pandas**, a propósito: los módulos vivos del MCP
    (`dossier`, `nota`, `vector`) no lo usan. Reusa `nota.nota_evento` igual que
    la app reusa `analytics.nota_evento` → **NO toca la nota**, solo la lee.
  - `_CLASES_FALLO` se redefine aquí (4 clases) porque el `analytics.py` de la
    carpeta del MCP es **código muerto** (nadie lo importa) y no se quiso revivir.
  - `min_acciones` se aplica siempre (una acción suelta no es un clip); `partido`
    busca por subcadena en la etiqueta del partido y, si no casa, el error lista
    los partidos disponibles.
  - **Verificado contra el motor de la app** sobre el fixture real de 241 eventos
    (3 partidos, varios jugadores): **153 secuencias, reparto 1→99, 2→36, 3→9,
    4→5, 5→2, 6→1, 7→1** — los números de SQL — e **idénticas una a una** a las
    de la app, incluidos `valor` y `desenlace`. O sea: `nota.nota_evento` (MCP) y
    `analytics.nota_evento` (app) coinciden. Registro de la tool comprobado con el
    intérprete REAL del servidor (Python313 del `claude_desktop_config.json`, no
    el del PATH).
  - **Reiniciar el MCP** para que aparezca la tool.
- **`diccionario_resultados.json` del MCP resincronizado (2026-07-17):** su copia
  se quedó en Fase 2 (sin los bloques `similitud` ni `secuencias`). Hoy no daba la
  cara porque `nota._cargar_cfg` lee PRIMERO el JSON de la app (`../Scounting_
  Mundial/`) y solo cae a la copia local si falta; `secuencias.py` del MCP usa el
  mismo orden de candidatos. Si el MCP se mueve de carpeta, el fallback local ya
  está completo.
- Fase 6 (detección de momentos) se apoyará en `detectar_secuencias`.
- Descartado de esta fase (2026-07-14): esquema ampliado más allá de
  `sesiones` (tabla de jugador con pie/club/valor de mercado).

**Fase 5 — Predicción de acierto por jugador. COMPLETA (2026-07-21).**
La sección Predicciones se rehízo entera. Se **eliminaron las 3 pestañas**
(tendencia por regresión lineal, Random Forest + simulador, y patrones tácticos
IA/Gemini) y con ellas `predict_player_trend`, `train_outcome_model`,
`patrones_tacticos_datos`, el módulo `ai_analysis.py` y las dependencias
`scikit-learn` y `google-genai`. El nombre "Predicciones" se mantiene.
- **Por qué NO Random Forest (medido, no opinado):** al grano que interesa
  (jugador × acción × zona) **el 74% de los combos tiene menos de 5 eventos**
  (1.219 combos, media 3.8). Un RF sobreajusta ese ruido: un DC con 4 pases
  progresivos fallados daría "0% de acierto" con aparente confianza. El modelo
  correcto para "muchos grupos, pocos datos por grupo" es el **partial pooling**.
- **Motor: cascada de suavizado de 5 pasos** en `analytics.py`
  (`agregados_expectativa`, `predecir_acierto`, `resumen_expectativa_jugador`):
  `global → categoría → acción → acción+zona → acción+zona+posición →
  acción+zona+jugador`, suavizando cada nivel hacia el superior con
  `(A + k·prior)/(N + k)`. Config en el bloque `"expectativa"` del JSON
  (`k` 8.0, `min_muestra_resumen` 3, `umbral_destaca` 15.0, `top_resumen` 12).
  Reutiliza `is_success`/`is_attempt`/`peso` — NO reclasifica resultados.
  Ejemplo real: el 0% crudo de 4 intentos pasa a **56.9% predicho**.
- **LEAVE-ONE-OUT (importante):** la expectativa del puesto **excluye las
  acciones del propio jugador**. Sin esto se le comparaba consigo mismo: **el
  36% de las celdas (acción,zona,puesto) tienen UN SOLO jugador**, y la UI
  presentaba su propio dato como "casos del grupo". `n_pos` cuenta COMPAÑEROS;
  si no hay, la referencia cae al nivel acción+zona y la UI lo dice.
- **Acciones sin éxito posible FUERA del predictor** (`analytics.predecible`,
  derivado del diccionario, no listado a mano): faltas, tarjetas, penalti
  cometido, error grave... Entraban como intento con 0% garantizado, ofrecían
  predecir el "% de acierto de una falta" y **envenenaban el prior de la
  categoría `Otros` en 21 puntos** (50.3% vs 71.2% real), a peor cada vez que se
  tagueaba una falta.
- **UI (una sola vista, sin pestañas):** predictor interactivo (jugador+acción+
  zona, con su dato crudo y la referencia del puesto al lado) + resumen
  automático "dónde destaca o floja respecto a su rol", con badge de fiabilidad
  🔴🟡🟢. La etiqueta destaca/en línea/por debajo usa la predicción **suavizada**,
  no el % crudo, para no señalar ruido de muestra baja; la tabla enseña ambos.
  Tabla en HTML propio (`.exp-*`), **NUNCA `st.dataframe`** (ver Fase 4: pinta
  sobre canvas Glide y el CSS del tema no entra).
- `agregados_expectativa` va **cacheada** (`_agg_expectativa`): Streamlit
  re-ejecuta el script en cada clic y re-agregar la base costaba ~250 ms.
- 34 tests en `tests/`. Spec y plan en `docs/superpowers/`.
- **Sin cambios en el MCP** (no hay tool de predicción; esto es solo dashboard).
- Descartado por el camino: alertas de tendencia en directo y comparación
  explícita 1ª vs 2ª parte (iban con las pestañas eliminadas).

**Fase 6 — Ideas exploratorias (se mantiene).**
- **Contrafactual de scouting:** proyectar la nota de un jugador bajo el perfil
  de peso de un club destino distinto al suyo (depende de los perfiles de peso
  por estilo de juego, aplazados en Fase 2). Responde "cómo encajaría" en vez
  de "cómo rinde ahora".
- **Detección automática de momentos:** aplicación práctica de las métricas de
  secuencia de Fase 4 — detectar tramos de cadenas de acciones de valor para
  generar clips/momentos clave sin revisar el partido entero.
- Ambas requieren más muestra de partidos tagueados para no ser ruido.

(La Fase 5 "mejoras de visualización del dashboard" del roadmap original en
Drive ya está implementada íntegramente: influencia por minuto, evolución en
barras/neón, comparar hasta 3 jugadores. Por eso el número 5 queda libre y se
reutiliza aquí para Predicciones.)

**Pendientes sueltos — TODOS DESCARTADOS (2026-07-14).**
- ~~Quitar Predicciones~~: descartado, se mejora en Fase 5 en vez de eliminarse.
- ~~Migrar nombres viejos tras la auditoría~~: descartado.
- ~~Limpieza de código muerto de equipo~~: descartado.
- ~~Rescatar `acierto_ponderado_zona` al dashboard~~: descartado, no va al dashboard.
- Se eliminó también del código el bloque de mantenimiento "migrar fichas
  antiguas a la tabla de jugadores" + "auditar datos" en Registro de jugadores
  (`scouting_app.py`, sección Registro→Sesiones guardadas): era una migración
  puntual ya completada, obsoleta.

---

## 9. ESTILO DE TRABAJO (crítico)

El usuario (Gerard) es scout/analista/desarrollador exigente. Espera:
- Criterio SENIOR independiente, no complacencia. Decir lo que piensa, no lo que
  quiere oír. Cuestionar ideas malas aunque estén en el roadmap.
- NO construir nada sin que se pida explícitamente.
- Verificar de verdad (sintaxis + arranque), no dar por bueno sin comprobar.
- Asumir los errores propios sin echar balones fuera ni dudar del usuario.
- Respuestas concisas, un paso a la vez, en español.
- Confirmar decisiones de diseño/scout antes de implementarlas.
