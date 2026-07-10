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

**Fase 1 (MCP) — casi completa.** Tras análisis crítico se recortó:
- Punto 2 (percentiles): DESCARTADO (mal de raíz con tagging manual, poca población).
- Punto 3 (contexto): HECHO como filtro en el dashboard.
- Punto 4 (fiabilidad): YA EXISTÍA en el dossier.
- **Punto 1 (sql_select con rol de solo lectura): PENDIENTE.** Único que queda.
  Cambiar el filtro por texto "select" por un rol de solo lectura real en
  Postgres. Toca seguridad de Supabase + MCP local del usuario.

**Fase 2 (sistema de nota) — PENDIENTE.** Activar los pesos negativos del
diccionario. Nota = valor_base(acción) × factor_zona × signo_resultado.
PESO_ZONA={0:0.8, 1:1.0, 2:1.3} ya existe en analytics. Tabla valor_base
preparada. Predictor a rehacer (acción+zona+posición, sin minuto).

**Fase 3+ — exploratorias:** descubrimiento/visualización, contrafactual de
scouting, detección automática de momentos.

**Pendientes sueltos:**
- Quitar Predicciones (probable; "sirve para poco", requiere escala tipo StatsBomb).
- Migrar nombres viejos tras ver la auditoría.
- Limpieza de código muerto de equipo (informe y registro de equipos ya fuera
  de la UI; constantes inertes).
- Rescatar `acierto_ponderado_zona` al dashboard (calculado pero huérfano).

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
