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
- **Pase atrás** - *(Correcto / Fallo)*. Pase que hace retroceder el balón hacia 
  la portería propia.
- **Pase lateral** - *(Correcto / Fallo)*. Pase que recorre un movimiento horizontalmente 
  recto entre el pasador y el receptor.
- **Pase entre líneas** — *(Correcto / Fallo)*. Pase que rompe una línea de
  presión rival (normalmente entre medios y defensas) y encuentra a un compañero
  entre ellas. Correcto si el receptor controla. El pase entre líneas como Pase Progresivo 
  siempre
- **Pase al espacio** — *(Correcto / Fallo)*. Pase a una zona libre para que el
  compañero corra hacia ella, no a sus pies. Correcto si el compañero llega y
  conserva el balón. El pase al espacio cuenta como Pase progresivo siempre.
- **Cambio de orientación** — *(Correcto / Fallo)*. Pase largo que traslada el
  juego de un costado al otro para aprovechar el lado débil. Correcto si llega al
  destinatario en el otro carril. El cambio de orientación siempre cuenta como
  Pase Progresivo.
- **Pase de primera** — *(Correcto / Fallo)*. Pase a un toque, sin control
  previo. Indicador de velocidad de circulación. Siemprre cuenta como Pase
  Atrás.
- **Pase bajo presión** — *(Correcto / Fallo)*. Pase ejecutado con un rival
  encima. Mide la solvencia técnica en situaciones de agobio. No suma como
  otro pase, sinó como complemento informativo sobre el pase.
- **Pase en largo** — *(Correcto / Fallo)*. Envío de larga distancia (saltando
  líneas o cambiando de zona del campo). Correcto si encuentra destinatario. 
  Siempre cuenta como Pase Progresivo.
- **Asistencia** — *(registro simple)*. Último pase que termina en gol. Se
  registra como evento puntual; no tiene "fallo" porque por definición es
  exitoso. No suma como otro pase, sinó como complemento informativo sobre 
  el pase.
- **Pase clave** — *(Correcto / Fallo)*. Pase que genera una ocasión clara de
  remate (aunque no acabe en gol). Correcto si el compañero llega a rematar.
  No suma como otro pase, sinó como complemento informativo sobre el pase. 
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
- **Control difícil** - *(Correcto / Fallo)*. Controlar un balón fuerte, aéreo,
  bajo presión o cualquier otra circumstancia que dificulte el control de balón.
- **Control fácil fallado** - *(Fallo)*. Control  defectuoso de balón que llegue 
  en perfectas condiciones.
- **Protección de balón** — *(Correcto / Fallo)*. Resguardar el balón con el
  cuerpo ante la presión, ganando una falta, manteniendo posesión o esperando
  apoyo. Correcto si conserva el balón.
- **Recibe entre líneas** — *(Correcto / Fallo)*. El jugador recibe el balón
  situado entre las líneas rivales. Correcto si controla y mantiene.
- **Falta recibida** — *(registro simple)*. El jugador sufre una falta del rival.
  Indicador de valor ofensivo: a quien frenan ilegalmente con frecuencia. No
  registrar si la falta es penalti (usar "Penalti provocado").
- **Penalti provocado** — *(Penalti)*. El jugador fuerza una pena máxima a su
  favor. Conserva su recuento específico de penalti.
- **Duelo aéreo of.** — *(Correcto / Fallo)*. Disputa por alto en tarea ofensiva.
  Correcto si gana el salto.
- **Error grave / pérdida** — *(registro simple)*. Pérdida de balón evitable o
  error de bulto. Evento puntual negativo, sin "acierto" posible.

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
- **Ofrece línea de pase** — *(Encontrado / No encontrado)*. Colocarse en cualquier
  otra posición de las mencionadas para ser opción de pase al poseedor.
- **Entrada en área rival** — *(Encontrado / No encontrado)*. Entrar en el área
  buscando recibir o rematar. Encontrado si le sirven. 

## Finalización
*Faceta del radar: Finalización.*

- **Remate** — *(A puerta / Gol / Fuera/ Bloqueado)*. Disparo a portería con el pie 
  en jugada. A puerta si va entre los tres palos, Gol si entra, Fuera si se marcha,
  bloqueado si algún defensor lo intercepta antes de ir a puerta o fuera.
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

- **Entrada / tackle** — *(Correcto / Fallo)*. Disputa desde el suelo
  para arrebatar el balón al rival. Correcto si recupera o despeja limpiamente.
- **Intercepción** — *(Correcto / Fallo)*. Disputa para arrebatar el balón al
  rival. Correcto si recupera o despeja limpiamente.
- **Anticipación** - *(Correcto / Fallo)*. Predecir el pase de un rival y
  llegar antes al balón. Correcto si recupera o despeja.
- **Recuperación** — *(Correcto / Fallo)*. Recuperar la posesión para el equipo
  (tras robo, rechace o presión). Correcto si el balón queda controlado.
- **Despeje** — *(Correcto / Fallo)*. Alejar el balón del área propia sin
  pretender mantener posesión. Correcto si aleja el peligro.
- **Duelo aéreo def.** — *(Correcto / Fallo)*. Disputa por alto en tarea
  defensiva. Correcto si gana el salto.
- **Duelo 1v1 def.** — *(Correcto / Retrasado / Fallo)*. Defender un uno contra uno. Correcto
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


## ABP
- **Lanzamiento córner** — *(Correcto / Fallo)*. El jugador realiza un lanzamiento
  de córner. Si encuentra rematador es correcto, en el caso contrario se 
  contará ocmo fallo
- **Lanzamiento falta lateral** — *(Correcto / Fallo)*. El jugador realiza un lanzamiento
  de falta ateral. Si encuentra rematador es correcto, en el caso contrario se 
  contará ocmo fallo
- **Falta directa a puerta** — *(A puerta / GOL / Fuera / Barrera)*. Lanzamiento directo
  de falta. 
- **Remate a balón parado** — *(A puerta / GOL / Fuera / Bloqueado)*. Remate en ataque
  de un jugador cuando el balón proviene de un córner o de un lanzamiento de falta
  lateral.
- **Despeje en ABP def.** — *(Correcto / Fallo)*. El jugador despeja el balón en un 
  corner o falta lateral defensiva. Coorecto si aleja el balón del peligro.
- **Duelo en ABP def.** — *(Correcto / Fallo)*. El jugador se antcipa o bloquea a un
  rival atacante en un corner o falta lateral defensiva. Correcto si impide el remate de 
  su marca.

## Sprints
- **Sprint def.** — *(Sprint)*. Sprint prolongado y de alta intensidad cuando el 
  balón lo tiene el equipo contrario.
- **Sprint of. sin balón** — *(Sprint)*. Sprint prolongado y de alta intensidad
  cuando el equipo esta atacando y el jugador no posea el balón. Generalmente 
  en transiciones ofensivas o desmarques de ruptura.
- **Sprint of. con balón** — *(Sprint)*. Sprint prolongado y de alta intensidad
  cuando el jugador tenga el balón en sus pies. Generalmente en conducciones.



# Notas de contabilización

- El **% de acierto** de un jugador solo considera acciones con resultado
  Correcto/Fallo, Encontrado/No encontrado y Gol. Los eventos de registro simple (—) y
  los disciplinarios no entran en ese porcentaje.
- Pases Progresivos totales: Pase Progresivo, Pase entre líneas, Pase largo, Pase al espacio, 
  cambio de orientación.
- Los pases bajo presión y los pases clave no se ocntabilizan como nuevos pases. Son 
  información extra del pase.
- Los pases de primera cuentan como Pase Atrás.
- Los pases mencionados se pueden calcular y visualizar por separado pero se unen para
  generar una estadística de pase más general.
