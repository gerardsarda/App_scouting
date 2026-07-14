# Sistema de NOTA (Fase 2) — referencia

Documento de referencia del sistema de puntuación por jugador. Explica la
fórmula (**modelo de VALOR ACUMULADO**), los valores por acción, los pesos de
zona y cómo ajustarlo. Todo es editable a mano en `diccionario_resultados.json`
→ bloque `"nota"`, sin tocar código.

> **Cambio 2026-07-14:** se sustituyó la *media ponderada de acierto* anterior
> por un modelo de **valor acumulado** (tipo rating de analista). La media
> ponderada medía **fiabilidad** (techo 1.0 por acción = un "% de acierto
> ponderado") y sesgaba hacia defensas y pases simples: castigaba la ambición
> (un remate o regate fallado era un cero pesado) y **diluía los goles** (un gol
> valía como un pase completado). Manzambi marcaba 2 goles y sacaba 5.8. El
> modelo nuevo premia el **impacto acumulado** y le da ~9.8.

---

## 1. Qué es la nota

Una **nota 0-10 por jugador**, estilo rating de analista: parte de un
**baseline** ("cumplió") y **suma/resta el valor** de cada acción según su
impacto real en el partido.

- **Mide IMPACTO acumulado, no % de acierto.** Un gol, una asistencia, una
  ocasión creada o un duelo decisivo ganado **suben** la nota; una pérdida en tu
  área, una roja o un penalti cometido la **hunden**. Las cosas neutras o de bajo
  valor (pase atrás, reciclaje) apenas mueven la aguja.
- El `%` de acierto del dashboard se queda como eje de **fiabilidad**; la NOTA es
  el eje de **impacto**. Se leen **juntas**.
- Dos vistas:
  - **Nota total** (badge circular en la cabecera del jugador) — bajo los filtros
    activos (parte, contexto de rival).
  - **Evolución de la nota** — una nota por partido, en **barras** coloreadas por
    banda.

---

## 2. Fórmula

Por cada acción que puntúa (los neutros se excluyen):

```
valor         = valor_outcome(acción, clase)     (premio si sale bien, castigo si sale mal)
factor_zona   = según sea premio o castigo (ver §5)
contribución  = valor × factor_zona

nota = clip( baseline + k · Σ(contribución) , 0 , 10 )
```

- `baseline = 6.0` — punto de partida, "cumplió". Un partido gris (sin acciones
  decisivas ni errores) se queda cerca de 6.0.
- `k = 0.45` — escala la suma acumulada. **Provisional: hay que calibrarlo con
  partidos reales** para que los buenos partidos no saturen demasiado rápido en
  9-10.
- `suma` (el `Σ contribución`, antes de baseline/k) se expone en `nota_jugador`
  y en el dossier del MCP para diagnóstico.

Es una **acumulación (suma), no una media**: por eso el volumen de acciones
decisivas cuenta (un delantero muy participativo y con goles sube más que uno
correcto pero invisible), y los goles ya no se diluyen entre 40 toques.

### Referencia de resultados (con k=0.45, baseline 6.0)

| jugador (ejemplo) | nota |
|---|---|
| Delantero con 2 goles (Manzambi) | ~9.8 |
| Central sólido (cortes, despejes, duelos ganados) | ~9.2 |
| Delantero apagado (pocas acciones, sin gol) | ~6.0 |
| Partido con roja + pérdidas | ~2.1 |

---

## 3. Valores por acción (asimétricos: premio ≠ castigo)

Cada `(acción, clase)` tiene su propio valor en `"valores"`. **El premio y el
castigo son independientes**: un remate fallado de jugada no penaliza (te
colocaste bien), pero una pérdida en tu área sí. El **gol (+3.0) es el ancla**;
todo lo demás es relativo a eso.

**Finalización** — éxito(Gol) +3.0 · parcial(A puerta) +0.5 · fallo 0.0:
Remate · Remate de cabeza · Remate desde fuera · Llegada 2ª línea · Falta directa
a puerta · Remate a balón parado.

**Creación (output decisivo):**
| acción | éxito | fallo |
|---|---|---|
| Asistencia | +2.0 | — |
| Penalti provocado | +2.0 | — |
| Generación de ocasión | +1.5 | — |
| Pase clave | +0.8 | 0.0 |

**Pases:**
| acción | éxito | fallo |
|---|---|---|
| Pase entre líneas | +0.45 | −0.12 |
| Pase al espacio | +0.40 | −0.10 |
| Centro lateral | +0.40 | −0.05 |
| Cambio de orientación | +0.35 | −0.10 |
| Pase bajo presión | +0.35 | −0.12 |
| Pase progresivo | +0.30 | −0.10 |
| Pase en largo | +0.25 | −0.08 |
| Pase de primera | +0.20 | −0.08 |
| Pase lateral | +0.03 | −0.10 |
| Pase atrás | +0.02 | −0.10 |

**Regate / conducción / control:**
| acción | éxito | fallo |
|---|---|---|
| Regate 1v1 | +0.40 | −0.08 |
| Recibe entre líneas | +0.35 | −0.08 |
| Conducción progresiva | +0.30 | −0.10 |
| Recorte / cambio ritmo | +0.25 | −0.08 |
| Control difícil | +0.20 | −0.10 |
| Protección de balón | +0.15 | −0.08 |
| Control fácil fallado | — | −0.20 |

**Movimiento sin balón** (No encontrado ≈ 0, no es culpa del que corre):
| acción | éxito (Encontrado) | fallo |
|---|---|---|
| Entrada en área rival | +0.20 | 0.0 |
| Desmarque de ruptura / Ataque al palo | +0.15 | 0.0 |
| Desmarque de arrastre / apoyo · Amplía el campo · Ofrece línea de pase | +0.10 | 0.0 |
| Duelo aéreo of. | +0.30 | −0.05 |

**Defensa:**
| acción | éxito | parcial | fallo |
|---|---|---|---|
| Entrada / tackle | +0.40 | — | −0.35 |
| Intercepción | +0.40 | — | −0.10 |
| Anticipación | +0.40 | — | −0.15 |
| Bloqueo tiro/centro | +0.40 | — | −0.05 |
| Duelo 1v1 def. | +0.40 | +0.20 (aguantó) | −0.35 |
| Recuperación | +0.25 | — | 0.0 |
| Duelo aéreo def. | +0.35 | — | −0.20 |
| Presión fuerza error | +0.45 | — | *(neutro, excluido)* |
| Despeje en ABP def. | +0.30 | — | −0.20 |
| Duelo en ABP def. | +0.30 | — | −0.25 |
| Cobertura | +0.20 | — | −0.15 |
| Despeje | +0.30 | — | −0.20 |
| Repliegue | +0.10 | — | −0.10 |

**ABP (lanzamientos):** Córner / Falta lateral → éxito +0.15, fallo −0.02.

**Disciplina y errores** (sin zona salvo la pérdida):
| acción | valor |
|---|---|
| Error grave / pérdida | −1.5 *(usa factor pérdida)* |
| Penalti cometido | −3.0 |
| Tarjeta roja | −3.0 |
| Tarjeta amarilla | −0.30 |
| Falta | −0.25 |
| Falta táctica | −0.15 |

**Neutros (excluidos, 0):** Sprints (def./of.), Falta recibida.

`valores_default` (`{exito:0.2, parcial:0.1, fallo:-0.1}`) cubre cualquier acción
nueva sin tabular. Para cambiar un valor, edita `diccionario_resultados.json` →
`"nota"` → `"valores"`. Cambio en caliente, sin tocar código.

---

## 4. Clases de resultado

Cada resultado de cada acción está clasificado en el diccionario (`exito`,
`parcial`, `fallo`, `fallo_parcial`, `fallo_medio`, `fallo_grave`, `neutro`). El
valor de cada clase se lee de `"valores"[acción]`; los `neutro` se excluyen
(`"excluir_clases"`). No hay una tabla de "signo" global: el valor es **por
acción y por clase**, para que un mismo tipo de fallo cueste distinto según la
acción.

---

## 5. Pesos de zona — DOS regímenes

La misma acción no vale lo mismo según dónde ocurre, y **premio y castigo miran
la zona de forma distinta**:

- **Premio** (valor ≥ 0) → **direccional**:
  - Ofensivas/construcción: valen más arriba, `peso_zona_premio_of {0:0.8, 1:1.0, 2:1.3}`.
  - Defensivas: valen más cerca de tu área, `peso_zona_premio_def {0:1.3, 1:1.0, 2:0.8}`.
- **Castigo** (valor < 0) → **zona de pérdida**, `peso_zona_perdida {0:1.3, 1:1.0, 2:0.7}`:
  perder el balón o el duelo **duele más cuanto más cerca de tu portería**, en
  **cualquier** acción. Así un mal regate en campo rival (zona 2) es casi gratis
  (×0.7) y una pérdida en tu tercio (zona 0) es cara (×1.3).
- **Sin zona** (factor 1.0): disciplina fija (roja, penalti cometido, tarjetas,
  faltas) y sprints. Una roja es una roja en cualquier sitio.

**Acciones defensivas** (`acciones_defensivas`, solo afecta a la dirección del
premio): Entrada/tackle, Intercepción, Anticipación, Recuperación, Despeje, Duelo
aéreo def., Duelo 1v1 def., Presión fuerza error, Cobertura, Bloqueo tiro/centro,
Repliegue, Despeje en ABP def., Duelo en ABP def.

**Sin zona** (`acciones_sin_zona`): Falta táctica, Falta, Tarjeta amarilla,
Tarjeta roja, Penalti cometido, los tres Sprints y Falta recibida. *(`Error grave
/ pérdida` NO está aquí: usa el factor pérdida para que cueste más en tu área.)*

Todo lo demás usa la tabla **ofensiva** para el premio. Si `zona_x` no existe en
un evento antiguo, el factor es 1.0.

---

## 6. Neutros y PASE_COMPLEMENTO

- **Neutros** (Sprints, Falta recibida, Presión que no fuerza error): se
  **excluyen** de la nota. Registro informativo. `"excluir_clases": ["neutro"]`.
- **PASE_COMPLEMENTO** (Pase clave, Pase bajo presión, Asistencia): **sí puntúan**
  como acción propia en la nota (suman impacto extra: Asistencia +2.0, Pase clave
  +0.8), aunque en el % de acierto y el volumen se traten como complemento del
  pase base.

---

## 7. Dónde se ve

- **Badge de NOTA** en la cabecera del jugador (dashboard → Gráficos): un
  **círculo** con borde/glow del color de banda y solo el número dentro (sin label
  "Nota" ni contador de acciones). El aviso de "muestra baja" (<15 acciones que
  puntúen) va en el `title`/tooltip.
- **Gráfico "Evolución de la nota"** en **barras**, hasta 3 jugadores agrupados
  por rival, coloreadas por banda. Respeta parte y contexto de rival.
- **Bandas de color** (helper `_color_nota`, mismo criterio en badge y barras):
  `[1,5)` → **rojo**, `[5,7)` → **naranja**, `[7,9)` → **amarillo**, `≥9` → **verde**.

Motor en `analytics.py`: `nota_evento` (→ contribución), `nota_jugador` (→ {nota,
suma, n}), `serie_nota_por_partido`, `_valor_outcome_nota`, `_factor_zona_nota`,
`_cargar_nota_cfg`.

---

## 8. Cómo ajustar

Todo vive en `diccionario_resultados.json` → bloque `"nota"`:

- `valores` — sube/baja el premio o el castigo de una acción concreta (por clase).
- `baseline` — dónde parte "cumplió" (6.0).
- `k` — escala global de la dispersión (subir → más separación entre notas).
- `peso_zona_premio_of` / `peso_zona_premio_def` / `peso_zona_perdida` — los
  multiplicadores de zona.
- `acciones_defensivas` / `acciones_sin_zona` — mueve una acción de bucket de zona.
- `excluir_clases` — qué clases no cuentan.

Tras editar, **Reboot app** en Streamlit Cloud (el JSON se lee al arrancar).

---

## 9. Avisos (leer)

- **`k` NO está calibrado con datos reales todavía.** Con partidos del Mundial
  tagueados, mira la **distribución** de notas de varios jugadores y ajusta `k`
  para que los buenos partidos no saturen demasiado rápido en 9-10. No toques los
  `valores` uno a uno antes de ver esa distribución.
- **La palanca más sensible es el castigo grave.** Un `Penalti cometido`/`Roja`
  (−3.0) o varias `pérdidas` (−1.5 × zona) hunden a un jugador que por lo demás
  jugó bien — que es lo que se busca, pero vigílalo con datos reales.
- **La nota mide impacto, no seguridad.** Un jugador que solo hace pases fáciles
  se queda cerca del baseline (6.0): ni suma ni resta. Para subir hay que
  **producir** (goles, ocasiones, duelos, progresión). Léela junto al volumen y
  al radar.
- **MCP: replicado** en `scouting-mcp/nota.py` (lee el mismo diccionario canónico)
  y enganchado en `dossier.py` → el dossier expone `nota` (total, con `suma`) y
  `contextos_partidos[].nota` (por partido). Da la misma nota que el dashboard. Si
  cambias `valores`/`baseline`/`k` aquí y el MCP se despliega en remoto, copia
  también el JSON a la carpeta del MCP. Reinicia el MCP para que tome los cambios.
