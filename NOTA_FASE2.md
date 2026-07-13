# Sistema de NOTA (Fase 2) — referencia

Documento de referencia del sistema de puntuación por jugador. Explica la
fórmula, los `valor_base`, los pesos de zona y cómo ajustarlo. Todo es editable
a mano en `diccionario_resultados.json` → bloque `"nota"`, sin tocar código.

---

## 1. Qué es la nota

Una **nota 0-10 por jugador**, estilo examen: la **media ponderada** de la
calidad de sus acciones, dando más peso a las acciones que importan y a la zona
del campo donde se producen.

- **Mide eficiencia en lo que importa, NO volumen.** Un jugador que hace pocas
  cosas pero las hace bien puntúa alto; uno que hace muchas y falla lo
  importante, bajo. Léela **al lado del volumen** del dashboard, no sola.
- Dos vistas:
  - **Nota total** (badge en la cabecera del jugador) — media de todas sus
    acciones bajo los filtros activos (parte, contexto de rival).
  - **Evolución de la nota** — una nota por partido en un gráfico de líneas.

---

## 2. Fórmula

Por cada acción que puntúa (los neutros se excluyen):

```
signo   = calidad del resultado        (de -1.0 a +1.0)
peso    = valor_base(acción) × factor_zona(acción, zona)

nota_bruta = Σ(signo × peso) / Σ(peso)         → entre -1 y +1
NOTA (0-10) = nota_bruta × 10, recortada a [0, 10]
```

Es una **media ponderada**: el `valor_base × zona` es cuánto "pesa" esa acción
en el examen; el `signo` es la nota de esa pregunta. Como el `valor_base` está
en el numerador y el denominador, **acertar una acción fácil o una difícil da lo
mismo si la aciertas** (10); la diferencia la marcan (a) **fallar algo
importante** duele más, y (b) los **errores graves** (signo negativo × peso
alto) que hunden la media.

### Equivalencias de la escala
| nota_bruta | NOTA | significado |
|---|---|---|
| +1.0 | 10 | todo éxito |
| +0.5 | 5 | todo a medias (o mitad éxitos / mitad fallos) |
| 0.0 | 0 | todo fallo simple |
| < 0 | 0 (recortado) | dominan los errores graves |

---

## 3. Signos por clase de resultado

Cada resultado de cada acción está clasificado en el diccionario (éxito, parcial,
fallo, fallo_parcial, fallo_medio, fallo_grave, neutro). El **signo** de cada
clase:

| clase | signo | ejemplo |
|---|---|---|
| `exito` | **+1.0** | pase Correcto, Gol, Penalti provocado |
| `parcial` | **+0.5** | remate A puerta, duelo def. Retrasó/aguantó |
| `fallo` | **0.0** | pase Fallo, remate Fuera |
| `fallo_parcial` | **-0.15** | Falta, Tarjeta amarilla, Falta táctica |
| `fallo_medio` | **-0.7** | Error grave / pérdida |
| `fallo_grave` | **-1.0** | Tarjeta roja, Penalti cometido |
| `neutro` | *(excluido)* | Sprint, Falta recibida, presión que no roba |

> Nota: un `fallo` simple es 0 (no resta, pero baja la media hacia 0). Los tres
> tipos de fallo con signo negativo sí restan, cada vez más según la gravedad.

---

## 4. `valor_base` por acción (escala 1–5)

Cuánto pesa cada **tipo** de acción en el examen, independientemente de dónde
pase (de eso se encarga la zona) y de si salió bien (de eso, el signo). Cuanto
más decisiva la acción, más valor.

| valor | Acciones |
|---|---|
| **5** | Asistencia · Penalti provocado · Error grave/pérdida · Tarjeta roja · Penalti cometido |
| **4.5** | Pase clave · Generación de ocasión |
| **4** | Remate · Remate de cabeza · Falta directa a puerta · Remate a balón parado · Duelo 1v1 def. |
| **3.5** | Pase entre líneas · Entrada en área rival · Remate desde fuera · Llegada 2ª línea · Regate 1v1 · Entrada/tackle · Intercepción · Anticipación · Recuperación · Bloqueo tiro/centro |
| **3** | Pase progresivo · Pase al espacio · Pase en largo · Cambio de orientación · Pase bajo presión · Centro lateral · Conducción progresiva · Recibe entre líneas · Desmarque de ruptura · Ataque al palo · Duelo aéreo of. · Despeje · Duelo aéreo def. · Presión fuerza error · Despeje en ABP def. · Duelo en ABP def. · Falta · Tarjeta amarilla |
| **2.5** | Recorte/cambio ritmo · Control difícil · Desmarque de arrastre · Lanzamiento córner · Lanzamiento falta lateral |
| **2** | Pase de primera · Control fácil fallado · Protección de balón · Desmarque de apoyo · Amplía el campo · Ofrece línea de pase · Falta táctica · Falta recibida |
| **1.5** | Pase lateral · Pase atrás · Repliegue · Cobertura |
| **1** | Sprint def. · Sprint of. sin balón · Sprint of. con balón |

*(Falta recibida y los Sprints son neutros: su `valor_base` está por
completitud pero NO entran en la nota.)*

Para cambiar un valor, edita `diccionario_resultados.json` → `"nota"` →
`"valor_base"`. Cambio en caliente, sin tocar código.

---

## 5. Pesos de zona (DIRECCIONAL)

La misma acción no vale lo mismo según dónde ocurre. Pero **la dirección depende
del tipo de acción**:

- **Ofensivas / construcción** → valen más cuanto más arriba:
  `{0: 0.8, 1: 1.0, 2: 1.3}` (0=def, 1=medio, 2=ataque).
- **Defensivas** → valen más cuanto más cerca de tu área (INVERTIDO):
  `{0: 1.3, 1: 1.0, 2: 0.8}`. Un corte o un bloqueo a última línea vale MÁS, no
  menos — por eso no se usa la tabla ofensiva para ellas.
- **Disciplina / errores / sprints** → **sin zona** (factor 1.0): una roja es
  una roja en cualquier sitio.

**Acciones defensivas** (`acciones_defensivas` en el JSON): Entrada/tackle,
Intercepción, Anticipación, Recuperación, Despeje, Duelo aéreo def., Duelo 1v1
def., Presión fuerza error, Cobertura, Bloqueo tiro/centro, Repliegue, Despeje
en ABP def., Duelo en ABP def.

**Sin zona** (`acciones_sin_zona`): Error grave/pérdida, Falta táctica, Falta,
Tarjeta amarilla, Tarjeta roja, Penalti cometido, los tres Sprints y Falta
recibida.

Todo lo demás usa la tabla **ofensiva**. Si `zona_x` no existe en un evento
antiguo, el factor es 1.0.

---

## 6. Neutros y PASE_COMPLEMENTO

- **Neutros** (Sprints, Falta recibida, Presión que no fuerza error): se
  **excluyen** de la nota (ni suman, ni restan, ni diluyen). Son registro
  informativo. Configurado en `"excluir_clases": ["neutro"]`.
- **PASE_COMPLEMENTO** (Pase clave, Pase bajo presión, Asistencia): **sí
  puntúan** como acción propia en la nota (suman calidad extra), aunque en el %
  de acierto y el volumen se traten como complemento del pase base.

---

## 7. Dónde se ve

- **Badge de NOTA** en la cabecera del jugador (dashboard → Gráficos). Color:
  verde ≥7, ámbar 5–6.9, rojo <5. Avisa "muestra baja" con menos de 15 acciones
  que puntúen.
- **Gráfico "Evolución de la nota"** debajo de la evolución de métricas: una
  nota 0-10 por partido, hasta 3 jugadores. Respeta parte y contexto de rival.

Motor en `analytics.py`: `nota_evento`, `nota_jugador`, `serie_nota_por_partido`,
`_factor_zona_nota`, `_valor_base`, `_cargar_nota_cfg`.

---

## 8. Cómo ajustar

Todo vive en `diccionario_resultados.json` → bloque `"nota"`:

- `valor_base` — sube/baja el peso de un tipo de acción.
- `signo` — cambia cuánto premia/penaliza cada clase de resultado.
- `peso_zona_ofensiva` / `peso_zona_defensiva` — cambia los multiplicadores.
- `acciones_defensivas` / `acciones_sin_zona` — mueve una acción de bucket de zona.
- `excluir_clases` — qué clases no cuentan.

Tras editar, **Reboot app** en Streamlit Cloud (el JSON se lee al arrancar).

---

## 9. Avisos (leer)

- **Nada está calibrado con datos reales todavía.** Los `valor_base` son un
  borrador razonable. Con partidos del Mundial tagueados, contrasta las notas
  con tu ojo y ajusta.
- **La palanca más sensible es el error grave.** Un solo `fallo_grave` (roja,
  penalti) o varios `fallo_medio` (pérdidas) pueden hundir a un jugador que por
  lo demás jugó bien. Si te parece excesivo, baja su `valor_base` o su `signo`.
- **La nota mide eficiencia, no ambición.** Un jugador seguro (solo pases
  fáciles, todos acertados) puntúa alto. Es lo esperado en una media de examen:
  léela junto al volumen y al perfil del radar.
- **MCP: replicado** en `scouting-mcp/nota.py` (lee el mismo diccionario
  canónico) y enganchado en `dossier.py` → el dossier expone `nota` (total) y
  `contextos_partidos[].nota` (por partido). Da la misma nota que el dashboard.
  Si cambias `valor_base` aquí y el MCP se despliega en remoto, copia también el
  JSON a la carpeta del MCP. Reinicia el MCP para que tome los cambios.
