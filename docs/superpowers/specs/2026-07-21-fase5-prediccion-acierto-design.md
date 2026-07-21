# Fase 5 — Predicción de acierto por jugador (rediseño de Predicciones)

Fecha: 2026-07-21
Estado: aprobado por el usuario, pendiente de plan de implementación.

---

## 1. Punto de partida y decisión

La sección **Predicciones** (`scouting_app.py:render_predicciones`) tiene hoy
3 pestañas:

1. *Tendencia por jugador* — regresión lineal simple del % de acierto por
   partido (`analytics.predict_player_trend`).
2. *Modelo ML (Random Forest)* — predice éxito de una acción con
   `accion + zona + minuto` (`analytics.train_outcome_model`, scikit-learn) +
   un simulador manual "Calcular probabilidad de éxito".
3. *Patrones tácticos (IA/Gemini)* — LLM sobre datos de zonas/tramos/partes.

El roadmap (Fase 5) proponía sustituir el RF por un predictor determinista
acción+zona+posición y potenciar Patrones tácticos. Al reabrir la discusión, el
usuario decidió **reconsiderar el apartado desde cero**.

**Objetivo real (usuario):** predecir el **% de acierto que puede tener un
jugador por acción y zona**, entrenado con sus propios datos. Momento de uso:
**cierre de scouting** de un jugador ("¿lo recomiendo o no?"), no en directo.

**Decisión final:**
- Se **retiran las 3 pestañas** actuales y toda su lógica.
- Se **elimina la dependencia de scikit-learn** (solo la usaba el RF).
- La sección conserva el nombre **"Predicciones"** (sigue prediciendo el
  acierto esperado; lo que cambia es el motor).
- Motor nuevo: **cascada de suavizado jerárquico de 5 niveles** (partial
  pooling), NO un Random Forest.

## 2. Por qué NO un Random Forest (medido, no opinado)

La dispersión de la muestra real hace que un RF sobreajuste ruido justo en las
celdas finas, que es donde más importa la transparencia. Contra la BD entera
(4.650 eventos, todos con resultado):

- **acción × tercio × posición-cruda:** 637 combinaciones existentes, media 7.3
  eventos/combo, **389 (61%) con <5 eventos**.
- **acción × tercio × set-de-posición** (los 6 del radar): 542 combinaciones,
  media 8.6, **307 (57%) con <5**.
- **jugador × acción × tercio** (el grano que el usuario quiere predecir):
  1.219 combinaciones, media 3.8, **903 (74%) con <5 eventos**.

Ejemplo real del daño: "Pase progresivo" de un **DC en el tercio medio → 4
intentos, los 4 fallados → 0% crudo**. No es fútbol, es ruido; un RF se lo
comería como probabilidad con aparente confianza y su accuracy de validación
cruzada fluctuaría celda a celda. Con este reparto, un RF no aprende nada que
una tabla de frecuencias no diga ya, y añade opacidad.

**El modelo correcto para "muchos grupos, pocos datos por grupo"** (muchos
jugadores/celdas, poca muestra en cada una) es el **partial pooling / modelo
jerárquico**: cada celda fina se mezcla con el grupo más amplio del que sí hay
datos, con un peso que depende de cuánta muestra propia tenga. Es un modelo
estadístico entrenado con los datos del usuario, y aquí le gana a un RF por la
estructura del problema, no porque "ML" esté descartado en general.

## 3. Motor: cascada de suavizado de 5 niveles

### 3.1 Agrupaciones (reutilizan taxonomía existente)

- **Acción:** las 62 tal cual vienen tagueadas.
- **Zona:** tercio 0/1/2 (`zona_x`), igual que el resto del dashboard.
- **Posición:** los **6 sets del radar** (`analytics.SETS_POSICION`: EXT, MP,
  MC/MCD, DC, DFC, LAT), vía el mismo mapeo que `_sugerir_set`. POR es su
  propio grupo. Consistente con similitud (MED/MP/MC → "MC organizador").
- **Categoría:** la de `analytics.CATEGORIAS` (Pase/Regate/Finalización/
  Defensa/Mov. sin balón/Otros) vía `_action_category`.

### 3.2 Definición de acierto

**Se reutilizan `analytics.is_success` e `is_attempt`** (diccionario canónico
por acción). NO se inventa una clasificación nueva. "Acierto" = éxito (parcial
cuenta 0.5 vía `success_weight`, coherente con el % del dashboard); "intento" =
lo que `is_attempt` considera intento. Los neutros no entran.

### 3.3 La cascada (partial pooling encadenado)

Cinco niveles, de más general a más específico. Cada nivel se **suaviza hacia
el nivel inmediatamente superior** (su "prior"):

0. **Categoría** de la acción (todas zonas/posiciones/jugadores) — ancla más
   amplia. Su prior es la tasa global de todos los intentos.
1. **Acción** (todas zonas/posiciones/jugadores), suavizada hacia el nivel 0.
2. **Acción + zona**, suavizada hacia el nivel 1.
3. **Acción + zona + posición** (set del radar), suavizada hacia el nivel 2.
4. **Acción + zona + jugador**, suavizada hacia el nivel 3.

Fórmula en cada nivel:

```
tasa_nivel = (aciertos_nivel + k · prior) / (intentos_nivel + k)
```

donde `prior` es la `tasa_nivel` ya calculada del nivel superior y `k` es el
peso del suavizado (cuántos "intentos virtuales" del prior se añaden). Un único
`k` global controla toda la cascada. Mismo patrón de tunable editable que
`nota` (`k`, `baseline`) o `similitud`.

**Nivel 4 es la predicción final del jugador:** si el jugador tiene mucho tape
propio en esa acción+zona, su predicción se acerca a su dato real; si tiene
poco, se acerca a la expectativa de su posición (nivel 3). Nunca devuelve el
"0% sobre 4 intentos".

### 3.4 Transparencia obligatoria

Toda predicción va acompañada de:
- La **muestra real** de la celda del jugador (nivel 4): "N intentos propios".
- La **expectativa de su posición** (nivel 3): "P% (n casos del grupo)".
- La predicción combinada final.

El número se suaviza; **la finura del dato nunca se esconde** — mismo criterio
de honestidad que nota, similitud y patrones tácticos.

### 3.5 Configuración

Bloque nuevo `"expectativa"` en `diccionario_resultados.json`, junto a `nota`,
`similitud`, `secuencias`:

- `k` — peso del suavizado en cada nivel (propuesta inicial: **8**). Editable a
  mano; el usuario lo calibrará con datos si hace falta.
- `min_muestra_resumen` — intentos propios mínimos para que un combo del
  jugador aparezca en el resumen automático (propuesta: **3**).
- `umbral_destaca` — puntos de diferencia jugador-vs-expectativa para etiquetar
  destaca/por debajo (propuesta: **15**).

## 4. Interfaz (una sola vista, sin pestañas)

Título: **"Predicción de acierto"** (la sección sigue llamándose Predicciones
en el nav).

### 4.1 Predictor interactivo

Tres selectores: **Jugador · Acción · Zona (tercio)**. El resultado se actualiza
al vuelo (no hay que entrenar: es consulta a la tabla ya calculada). Muestra:
- Predicción final (%), coloreada por banda verde/ámbar/rojo.
- Desglose: *"Su dato: N intentos, M% real"* + *"Expectativa de su posición:
  P% (n casos)"*.
- Aviso de fiabilidad según cuánto pesa su dato propio frente al del grupo.

### 4.2 Resumen automático del jugador (cierre de scouting)

Debajo, sin ir combo a combo: tabla de las acciones+zona más repetidas del
jugador (con `min_muestra_resumen`+ intentos propios), **ordenada por dónde su
predicción más se aleja de la expectativa de su posición**. Cada fila:
- Acción · Zona (tercio)
- Sus intentos y su % real
- % esperado para su grupo de posición + muestra de esa celda
- Diferencia (pts) + etiqueta **destaca ↑ / en línea → / por debajo ↓**
  (umbral `umbral_destaca`), con colores neón (verde/rojo).

Aviso de fiabilidad global 🔴🟡🟢 según el volumen total del jugador, mismo
patrón que Patrones tácticos.

### 4.3 Tablas en HTML propio, NO st.dataframe

Igual que la sección Secuencias: `st.dataframe` pinta sobre canvas (Glide) y el
CSS del tema no entra (fondo verde heredado, cabecera ilegible). La tabla del
resumen se hace con HTML propio + clases prefijadas en `styles.css`, mismo
idioma que `.seq-*`.

## 5. Limpieza y alcance técnico

- **Eliminar de `analytics.py`:** `train_outcome_model` y `predict_player_trend`
  (y los imports de sklearn que quedan dentro de `train_outcome_model`).
- **Eliminar de `scouting_app.py`:** las 3 pestañas de `render_predicciones`
  (Tendencia, Modelo ML + simulador, Patrones tácticos), reemplazadas por la
  vista única.
- **Eliminar de `requirements.txt`:** `scikit-learn`.
- **Motor nuevo en `analytics.py`:** `expectativa_acierto(...)` (nombre
  propuesto) — construye la tabla en cascada y devuelve la predicción de un
  `(jugador, accion, tercio)` con su desglose; y un helper para el resumen del
  jugador. Reutiliza `is_success`/`is_attempt`/`_action_category`/`SETS_POSICION`.
- **`ai_analysis.py`:** solo se **desconecta** de esta sección; NO se borra el
  módulo (puede reutilizarse en otra parte). Si el usuario confirma que no se
  usa en ningún otro sitio, se puede eliminar en un paso aparte.
- **MCP:** sin cambios. No hay tool de predicción en el MCP; esta sección es
  solo dashboard.

## 6. Verificación prevista

- Sintaxis (`ast`) + arranque de la app con AppTest de Streamlit mockeando
  `storage`, como en cambios anteriores.
- Contraste del motor contra la BD: para un puñado de celdas conocidas (ej.
  "Pase progresivo", DFC, tercio 1) el nivel 3 debe casar con el % crudo cuando
  hay muestra alta, y suavizarse hacia el prior cuando es baja. El caso del
  "DC 0% sobre 4" debe devolver un valor entre su dato y la expectativa de su
  posición, no 0%.
- Confirmar que al quitar sklearn la app sigue arrancando (ninguna otra parte
  lo importa: verificado, único uso en `train_outcome_model`).

## 7. Decisiones registradas

- Reconsiderar desde cero en vez de seguir el plan del CLAUDE.md. **(usuario)**
- Momento de uso: cierre de scouting de un jugador. **(usuario)**
- Modelo: cascada de suavizado jerárquico, NO Random Forest, tras ver la
  dispersión real de la muestra. **(usuario, convencido por el ejemplo del DC)**
- Extender la cascada hasta nivel jugador (predicción por jugador+acción+zona),
  que era el objetivo original del usuario. **(usuario)**
- Agrupar posición por los 6 sets del radar, no posición cruda. **(usuario)**
- Mantener el nombre "Predicciones". **(usuario)**
- Conservar tanto el predictor interactivo como el resumen automático. **(usuario)**
