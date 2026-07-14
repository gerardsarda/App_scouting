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
- `styles.css` — tema neón.
- `diccionario_resultados.json` — diccionario canónico por acción (ver §4).

**MCP (en el ordenador del usuario, NO en el repo de la app):**
- `scouting_mcp.py` / `server.py` — servidor MCP (FastMCP). Herramientas:
  listar_tablas, describir_tabla, consultar, sql_select, dossier_jugador,
  vector_jugador. Usa la service_role key y conexión propia a Supabase.
- `dossier.py` — construye el dossier analítico completo de un jugador.
- `vector.py` — construye el vector de 28 features por-90 para similitud.
- El MCP tiene su PROPIA copia de la lógica; usa de la ficha solo min_in/min_out
  y posición (que viajan en la sesión), NO las fotos.

**Despliegue:**
- Repo: `github.com/gerardsarda/app_scouting`.
- Streamlit Community Cloud. Deploy vía `git push` desde PowerShell (Windows).
- Tras push, si la nube da error pese a código correcto → CACHÉ → **Reboot app**
  en Manage app (no borra datos, viven en Supabase).
- NO subir cambios en mitad de un partido en vivo (reinicia la app). Hacer en
  el descanso.

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
- minuto_descanso (propio de cada partido; separa 1ª/2ª parte)
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
- **MCP: DESINCRONIZADO tras las 3 palancas (PENDIENTE).** El motor `scouting-mcp/
  nota.py` implementa el modelo de suma pura ANTERIOR (sin freno de circulación,
  sin roja=−8, sin ajuste de rival). Aunque lee el mismo diccionario canónico (y
  por tanto ya tomaría roja=−8 y los params nuevos del JSON si la carpeta hermana
  es accesible), su función `nota_de_eventos` NO aplica la compresión de
  circulación ni el factor de rival → dará notas distintas a la app. **Falta
  replicar en `nota.py` la lógica nueva de `analytics.nota_jugador` (palancas 1 y
  3) y que `dossier.py` pase el nivel propio/rival por partido.** El usuario pidió
  tocar SOLO la app en esta tanda; el MCP se sincroniza después.
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
- Pendiente: sincronizar el MCP con las 3 palancas (solo se tocó la app).
- Aplazado: perfiles de peso por estilo de juego (dominador vs bloque bajo),
  necesarios para el contrafactual de Fase 6.

**Fase 3 — Similitud coseno + proyección PCA 2D.**
- Ampliar `similitud.py` para comparar también contra jugadores de la propia
  base (hoy solo compara contra el CSV de 59 tops), y proyectar los vectores
  de 28 features a 2D (PCA) para un mapa visual de perfiles parecidos.
- Descartado de esta fase (2026-07-14): generador de dossier en PDF (ya existió
  y se quitó; el MCP se construyó principalmente para sustituirlo), dashboard
  comparativo (rejillas 3×3), motor de shortlisting con umbral de muestra.

**Fase 4 — Métricas de secuencia.**
- Usar el minuto de cada evento para detectar cadenas de jugadas relacionadas
  (recuperación → progresión → ocasión) y valorar la contribución a la
  secuencia completa, no la acción suelta. Base de la detección automática de
  momentos (Fase 6).
- Descartado de esta fase (2026-07-14): esquema ampliado más allá de
  `sesiones` (tabla de jugador con pie/club/valor de mercado).

**Fase 5 — Mejorar la sección Predicciones.**
Estado actual de `render_predicciones()` (`scouting_app.py:2254`), 3 pestañas:
1. *Tendencia por jugador*: regresión lineal simple sobre % de acierto por
   partido. Simple y ya avisa de su límite con poca muestra. Se mantiene.
2. *Modelo ML (Random Forest)*: predice éxito de una acción con
   `accion + zona + minuto`. Es el predictor que en Fase 2 se dejó aplazado
   por usar el minuto (aporta poco, necesita mucha muestra). **Sustituir** por
   el predictor de `acción + zona + posición` ya diseñado en Fase 2 — comparte
   lógica con el motor de nota (dificultad contextual de la acción), en vez de
   ser un modelo estadístico aparte sobreajustado a muestra pequeña.
3. *Patrones tácticos (IA/Gemini)*: usa contexto real (marcador, nivel propio/
   rival, posesión, si es suplente) y un LLM para detectar patrones en
   lenguaje natural, con aviso de fiabilidad. Es el enfoque más honesto de los
   tres porque no finge precisión estadística con pocos datos — se mantiene y
   es la vía a potenciar.
- **Criterio de scout senior:** con el volumen real de datos (pocos partidos
  por jugador, tagueo manual en directo), un Random Forest genérico es
  sobreingeniería — capta ruido, no fútbol. Lo que aporta valor real es (a) el
  predictor determinista acción+zona+posición, que codifica TU criterio de
  dificultad en vez de aprenderlo de una muestra minúscula, y (b) el patrón
  táctico vía LLM, que usa contexto cualitativo en vez de solo números.
- **Opciones realistas a debatir/añadir:**
  - Alertas de tendencia en directo: avisar si un jugador lleva 2+ partidos
    seguidos a la baja en % de acierto o en nota — útil para decisiones en
    tiempo real durante el Mundial, no solo post-análisis.
  - Extender "Patrones tácticos" para comparar explícitamente 1ª vs 2ª parte
    del propio jugador (ya se menciona en el caption pero no se ve explotado).
  - Descartar el simulador "Calcular probabilidad de éxito" del Random Forest
    actual junto con el propio modelo — da falsa sensación de precisión.

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
