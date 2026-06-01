# Diccionario de variables — App de Scouting Mundial

Documento de referencia con **todas** las acciones registrables, su definición,
cuándo usarlas y cómo se contabilizan. El objetivo es que cualquier analista
tague igual la misma jugada: solo así las estadísticas, el radar, los mapas de
calor y las predicciones resultan fiables.

**Cómo leer cada ficha.** Para cada acción se indica el *resultado* que ofrece
el botón:

- **Correcto / Fallo:** la acción se ejecuta bien o mal; cuenta para el % de acierto.
- **Encontrado / No encontrado:** el movimiento es premiado con un pase o no; cuenta para el % de acierto.
- **A puerta / Gol / Fuera:** específico de remates.
- **—** (registro simple): evento puntual que solo se cuenta, sin éxito/fallo.
- **Falta / Tarjeta / Penalti:** eventos disciplinarios con su propio recuento.

Todas las acciones guardan además, automáticamente, el **minuto** y la **zona**
(rejilla 3×3: columna izquierda = defensa propia, derecha = ataque). No hace
falta indicar la zona en el nombre de la acción.

---

# PARTE 1 · REGISTRO DE JUGADORES

Se taguea la acción de un jugador concreto (el jugador activo). Sirve para el
análisis individual: radar comparativo, % de acierto por faceta y mapas de calor.

## Construcción y pase
*Faceta del radar: Pase.*

- **Pase progresivo** — *(Correcto / Fallo)*. Pase que hace avanzar el balón con
  claridad hacia la portería rival, superando líneas o ganando metros. Correcto
  si llega a un compañero y mantiene la progresión.
- **Pase entre líneas** — *(Correcto / Fallo)*. Pase que rompe una línea de
  presión rival (normalmente entre medios y defensas) y encuentra a un compañero
  entre ellas. Correcto si el receptor controla.
- **Pase al espacio** — *(Correcto / Fallo)*. Pase a una zona libre para que el
  compañero corra hacia ella, no a sus pies. Correcto si el compañero llega y
  conserva el balón.
- **Cambio de orientación** — *(Correcto / Fallo)*. Pase largo que traslada el
  juego de un costado al otro para aprovechar el lado débil. Correcto si llega al
  destinatario en el otro carril.
- **Pase en conducción** — *(Correcto / Fallo)*. Pase ejecutado mientras se
  conduce el balón, sin pararlo. Mide la capacidad de combinar avance y
  distribución.
- **Pase de primera** — *(Correcto / Fallo)*. Pase a un toque, sin control
  previo. Indicador de velocidad de circulación.
- **Pase bajo presión** — *(Correcto / Fallo)*. Pase ejecutado con un rival
  encima. Mide la solvencia técnica en situaciones de agobio.
- **Pase en largo** — *(Correcto / Fallo)*. Envío de larga distancia (saltando
  líneas o cambiando de zona del campo). Correcto si encuentra destinatario.
- **Asistencia** — *(registro simple)*. Último pase que termina en gol. Se
  registra como evento puntual; no tiene "fallo" porque por definición es
  exitoso.
- **Pase clave** — *(Correcto / Fallo)*. Pase que genera una ocasión clara de
  remate (aunque no acabe en gol). Correcto si el compañero llega a rematar.
- **Centro lateral** — *(Correcto / Fallo)*. Envío desde banda al área. Correcto
  si conecta con un compañero dentro.

## Regate y conducción
*Faceta del radar: Regate.*

- **Regate 1v1** — *(Correcto / Fallo)*. Encarar y superar a un defensor en duelo
  individual. Correcto si lo supera manteniendo el balón.
- **Conducción progresiva** — *(Correcto / Fallo)*. Avanzar conduciendo el balón
  ganando metros sin oponente directo que le frene. Correcto si progresa sin
  perderlo.
- **Recorte / cambio ritmo** — *(Correcto / Fallo)*. Cambio de dirección o de
  velocidad para desequilibrar sin necesariamente encarar a un rival concreto.
- **Protección de balón** — *(Correcto / Fallo)*. Resguardar el balón con el
  cuerpo ante la presión, ganando una falta, manteniendo posesión o esperando
  apoyo. Correcto si conserva el balón.
- **Pared** — *(Correcto / Fallo)*. Combinación de un-dos con un compañero para
  superar a un rival. Correcto si la pared sale y supera al oponente.
- **Recibe entre líneas** — *(Correcto / Fallo)*. El jugador recibe el balón
  situado entre las líneas rivales. Correcto si controla y mantiene.
- **Falta recibida** — *(registro simple)*. El jugador sufre una falta del rival.
  Indicador de valor ofensivo: a quien frenan ilegalmente con frecuencia. No
  registrar si la falta es penalti (usar "Penalti provocado").
- **Penalti provocado** — *(Penalti)*. El jugador fuerza una pena máxima a su
  favor. Conserva su recuento específico de penalti.

## Movimiento sin balón
*Faceta del radar: Mov. sin balón. Resultado encontrado/no encontrado = si el
movimiento es premiado con un pase.*

- **Desmarque de ruptura** — *(Encontrado / No encontrado)*. Movimiento a la
  espalda de la defensa buscando recibir en carrera. Encontrado si le sirven.
- **Desmarque de apoyo** — *(Encontrado / No encontrado)*. Movimiento hacia el
  balón para ofrecerse como opción de pase corto. Encontrado si recibe.
- **Ataque al palo** — *(Encontrado / No encontrado)*. Movimiento de remate hacia
  el primer o segundo palo en jugada de centro. Encontrado si le llega el balón.
- **Desmarque de arrastre** — *(Encontrado / No encontrado)*. Movimiento que
  arrastra a un defensor para liberar espacio a un compañero. Encontrado si la
  jugada aprovecha ese espacio.
- **Amplía el campo** — *(Encontrado / No encontrado)*. Abrirse a la banda para
  dar amplitud y estirar a la defensa rival.
- **Ofrece línea de pase** — *(Encontrado / No encontrado)*. Colocarse en
  posición para ser opción de pase al poseedor.
- **Entrada en área rival** — *(Encontrado / No encontrado)*. Entrar en el área
  buscando recibir o rematar. Encontrado si le sirven. No registrar si la entrada
  acaba en remate (usar el "Remate" correspondiente).

## Finalización
*Faceta del radar: Finalización.*

- **Remate** — *(A puerta / Gol / Fuera)*. Disparo a portería con el pie en
  jugada. A puerta si va entre los tres palos, Gol si entra, Fuera si se marcha
  o lo interceptan.
- **Remate de cabeza** — *(A puerta / Gol / Fuera)*. Disparo de cabeza.
- **Remate desde fuera** — *(A puerta / Gol / Fuera)*. Disparo desde fuera del
  área.
- **Llegada 2ª línea** — *(A puerta / Gol / Fuera)*. Remate de un jugador que
  llega desde atrás a la frontal (rechaces, segundas jugadas).
- **Generación de ocasión** — *(registro simple)*. El jugador crea una ocasión
  clara que no necesariamente pasa por un pase clave (p. ej. un robo que deja a
  un compañero solo). Evento puntual.

## Defensa
*Faceta del radar: Defensa.*

- **Entrada / tackle** — *(Correcto / Fallo)*. Disputa para arrebatar el balón al
  rival. Correcto si recupera o despeja limpiamente.
- **Intercepción** — *(Correcto / Fallo)*. Cortar un pase rival anticipándose.
  Correcto si corta la jugada.
- **Recuperación** — *(Correcto / Fallo)*. Recuperar la posesión para el equipo
  (tras robo, rechace o presión). Correcto si el balón queda controlado.
- **Despeje** — *(Correcto / Fallo)*. Alejar el balón del área propia sin
  pretender mantener posesión. Correcto si aleja el peligro.
- **Duelo aéreo def.** — *(Correcto / Fallo)*. Disputa por alto en tarea
  defensiva. Correcto si gana el salto.
- **Duelo 1v1 def.** — *(Correcto / Fallo)*. Defender un uno contra uno. Correcto
  si frena al atacante sin que le supere.
- **Presión fuerza error** — *(Correcto / Fallo)*. La presión del jugador induce
  un error del rival (mal pase, pérdida). Correcto si provoca el fallo.
- **Cobertura** — *(Correcto / Fallo)*. Cubrir el espacio o al compañero que sale
  a presionar. Correcto si tapa la amenaza.
- **Bloqueo tiro/centro** — *(Correcto / Fallo)*. Interponerse para bloquear un
  disparo o un centro. Correcto si lo bloquea.
- **Repliegue** — *(Correcto / Fallo)*. Recuperar la posición defensiva tras
  pérdida, volviendo a su zona. Correcto si llega a tiempo a defender.
- **Falta táctica** — *(registro simple)*. Falta cometida deliberadamente para
  frenar una transición rival. Evento puntual (sin éxito/fallo).
- **Falta** — *(Falta)*. Falta cometida por el jugador. Se contabiliza en el
  recuento de faltas.
- **Tarjeta amarilla** — *(Tarjeta amarilla)*. Amonestación recibida. Recuento
  disciplinario propio.
- **Tarjeta roja** — *(Tarjeta roja)*. Expulsión. Recuento disciplinario propio.
- **Penalti cometido** — *(Penalti)*. El jugador comete una pena máxima en contra.
  Opuesto a "Penalti provocado".

## Transiciones y duelos
*Faceta del radar: según la acción (transición/duelo).*

- **Transición ofensiva** — *(Correcto / Fallo)*. Participación en el paso rápido
  de defensa a ataque tras recuperar. Correcto si la transición progresa.
- **Transición defensiva** — *(Correcto / Fallo)*. Reacción inmediata tras perder
  el balón para frenar el contragolpe. Correcto si neutraliza la transición rival.
- **Duelo aéreo of.** — *(Correcto / Fallo)*. Disputa por alto en tarea ofensiva.
  Correcto si gana el salto.
- **Contrapresión** — *(Correcto / Fallo)*. Presión inmediata sobre el rival justo
  tras perder el balón, para recuperarlo cuanto antes. Correcto si recupera o
  fuerza error.

## Balón parado y otros

- **Acción a balón parado** — *(Correcto / Fallo)*. Intervención en una jugada de
  estrategia (córner, falta lanzada o rematada). Correcto si la ejecuta bien.
- **Error grave / pérdida** — *(registro simple)*. Pérdida de balón evitable o
  error de bulto. Evento puntual negativo, sin "acierto" posible.

---

# PARTE 2 · REGISTRO DE EQUIPOS

Acciones colectivas, más generales. Se taguean en sesiones de equipo
(independientes de las de jugadores) y alimentan los gráficos de equipo.

## Pases y posesión

- **Salida de balón** — *(Correcto / Fallo)*. Inicio de la jugada desde atrás
  superando la primera línea de presión rival. Correcto si el equipo progresa
  con posesión.
- **Circulación / posesión** — *(Correcto / Fallo)*. Fase de mantener y mover el
  balón para fijar al rival. Correcto si conserva la posesión con sentido.
- **Progresión con balón** — *(Correcto / Fallo)*. El equipo avanza colectivamente
  hacia campo rival. Correcto si gana metros manteniendo el balón.
- **Cambio de orientación** — *(Correcto / Fallo)*. Traslado del juego de un
  costado al otro a nivel de equipo.
- **Llegada a último tercio** — *(Correcto / Fallo)*. El equipo instala el balón
  en el tercio de ataque. Correcto si genera presencia ofensiva.
- **Pérdida de balón** — *(registro simple)*. Pérdida colectiva de la posesión.
  Evento puntual.

## Ataque

- **Tiro** — *(A puerta / Gol / Fuera)*. Disparo del equipo. Mismo criterio que
  el remate individual.
- **Ocasión de gol** — *(registro simple)*. Ocasión clara generada por el equipo.
- **Centro al área** — *(Correcto / Fallo)*. Envío al área. Correcto si conecta.
- **Córner a favor** — *(registro simple)*. Saque de esquina conseguido.
- **Llegada por banda** — *(Correcto / Fallo)*. Ataque que progresa por el
  costado hasta zona de centro o remate.

## Defensa

- **Recuperación** — *(Correcto / Fallo)*. Recuperación colectiva de la posesión.
- **Presión alta** — *(Correcto / Fallo)*. Presión del equipo en campo rival.
  Correcto si recupera o fuerza error arriba.
- **Robo / intercepción** — *(Correcto / Fallo)*. Corte de la circulación rival.
- **Despeje** — *(registro simple)*. Alejar el peligro del área propia. Evento
  puntual a nivel de equipo.
- **Duelo defensivo** — *(Correcto / Fallo)*. Disputa defensiva colectiva.
- **Falta cometida** — *(Falta)*. Falta del equipo. Recuento de faltas.
- **Tarjeta amarilla** — *(Tarjeta amarilla)*. Amonestación del equipo.
- **Tarjeta roja** — *(Tarjeta roja)*. Expulsión en el equipo.

## Transiciones y balón parado

- **Transición ofensiva** — *(Correcto / Fallo)*. Paso rápido de defensa a ataque
  tras robar.
- **Transición defensiva** — *(Correcto / Fallo)*. Reacción del equipo tras perder
  el balón.
- **Contraataque** — *(registro simple)*. Ataque rápido aprovechando al rival
  descolocado.
- **Saque de banda** — *(registro simple)*. Reanudación lateral a favor.
- **Falta a favor** — *(registro simple)*. Falta señalada a favor del equipo.
- **Fuera de juego provocado** — *(registro simple)*. La defensa deja al rival en
  posición ilegal.
- **Córner en contra** — *(registro simple)*. Saque de esquina concedido al rival.

---

# Notas de contabilización

- El **% de acierto** de un jugador o equipo solo considera acciones con resultado
  Correcto/Fallo o Encontrado/No encontrado. Los eventos de registro simple (—) y
  los disciplinarios no entran en ese porcentaje.
- Las acciones que comparten el mismo nombre entre el panel de jugadores y el de
  equipo (Recuperación, Cambio de orientación, Tarjetas, etc.) se contabilizan en
  sus respectivos análisis por separado, porque las sesiones de jugadores y de
  equipo son independientes.
- Para que las comparativas tengan sentido, registra de forma consistente partido
  a partido: si una jugada dudosa la tagueas hoy como "Pase progresivo", manténla
  igual en los siguientes.
