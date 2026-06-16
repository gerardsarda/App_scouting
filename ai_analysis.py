"""
ai_analysis.py — Análisis narrativo del jugador con IA (Google Gemini).

Recibe los datos ya calculados del jugador (de analytics.player_report_data) y
devuelve un análisis en lenguaje natural, en tono de informe de club, detallado
por facetas, zonas y recomendaciones.

La API key se lee de st.secrets["GEMINI_KEY"]. Si no está configurada o la
llamada falla, devuelve None + un mensaje, sin romper la app.
"""
from __future__ import annotations
import streamlit as st

# Modelos candidatos, en orden de preferencia. Si Google retira o renombra uno,
# se prueba el siguiente automáticamente (evita el 404 por nombre obsoleto).
MODELOS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
]


def _generar(prompt):
    """Llama a Gemini con la librería UNIFICADA google-genai (la antigua
    google-generativeai está deprecada y no accede a los modelos nuevos).
    Prueba los modelos candidatos en orden hasta que uno responda."""
    from google import genai
    client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
    ultimo_error = None
    for nombre in MODELOS:
        try:
            resp = client.models.generate_content(model=nombre, contents=prompt)
            texto = (getattr(resp, "text", "") or "").strip()
            if texto:
                return texto
        except Exception as e:
            ultimo_error = e
            continue
    if ultimo_error:
        raise ultimo_error
    return ""
ZONAS_NOMBRE = {0: "primer tercio (defensa)", 1: "segundo tercio (medio)",
                2: "tercer tercio (ataque)"}


def hay_api_key() -> bool:
    try:
        return bool(st.secrets.get("GEMINI_KEY"))
    except Exception:
        return False


def _serializar_datos(datos: dict, comparacion=None, nombre_b=None,
                      posicion_larga="") -> str:
    """Convierte los datos del jugador en un texto estructurado para el prompt."""
    lineas = []
    lineas.append(f"Jugador: {datos.get('jugador','')}")
    lineas.append(f"Posición: {posicion_larga or datos.get('posicion','')}")
    if datos.get("equipo"):
        lineas.append(f"Equipo: {datos['equipo']}")
    if datos.get("edad"):
        lineas.append(f"Edad: {datos['edad']}")
    # Contexto temporal: cuándo jugó, clave para razonar cansancio/impacto.
    min_in = datos.get("min_in")
    min_out = datos.get("min_out")
    if min_in is not None and min_out is not None:
        if min_in > 0 or (min_out < 90):
            lineas.append(f"Participación: entró de SUPLENTE en el minuto {min_in} y "
                          f"{'fue sustituido en el ' + str(min_out) if min_out < 90 else 'jugó hasta el final'}; "
                          f"disputó {datos.get('minutos',0)} minutos reales.")
        else:
            lineas.append(f"Participación: TITULAR, jugó {datos.get('minutos',0)} minutos.")
    else:
        lineas.append(f"Minutos disputados: {datos.get('minutos',0)}")
    lineas.append(f"Acciones totales: {datos.get('acciones',0)}")
    lineas.append(f"Porcentaje de acierto global: {datos.get('pct_global',0)}%")
    # Métricas de analista (las que diferencian un análisis pro):
    if datos.get("acciones_por_90") is not None:
        lineas.append(f"Acciones por 90 min: {datos['acciones_por_90']} "
                      "(volumen normalizado al tiempo jugado; úsalo para comparar con "
                      "justicia a jugadores con minutos distintos, no los totales brutos).")
    if datos.get("acierto_ponderado") is not None:
        lineas.append(f"Acierto ponderado por zona: {datos['acierto_ponderado']}% "
                      "(da más valor a acertar en el último tercio que en zona segura; "
                      "si es mayor que el global, acierta donde más pesa).")
    if datos.get("acierto_por_zona"):
        partes = []
        for zona, v in datos["acierto_por_zona"].items():
            if v["pct"] is not None:
                partes.append(f"{zona}: {v['pct']}% ({v['acciones']} acc)")
        if partes:
            lineas.append("Acierto desglosado por zona: " + " · ".join(partes) +
                          " (NO te quedes en el % global, que mezcla lo fácil con lo "
                          "difícil; valora dónde rinde).")
    if datos.get("posesion") is not None:
        lineas.append(f"Posesión del equipo en el partido: {datos['posesion']}% "
                      "(con poca posesión es normal un menor volumen de acciones; "
                      "no lo interpretes como falta de implicación del jugador).")
    if datos.get("contexto_nivel"):
        lineas.append(f"Contexto de nivel y marcador: {datos['contexto_nivel']} "
                      "(ten en cuenta el nivel del rival y el resultado al valorar el rendimiento).")

    lineas.append("\nEficacia por faceta (% de acierto):")
    for fac, val in (datos.get("facetas") or {}).items():
        lineas.append(f"  - {fac}: {round(val)}%")

    if datos.get("volumen"):
        lineas.append("\nVolumen de acciones (recuento):")
        for etq, val in datos["volumen"]:
            lineas.append(f"  - {etq}: {val}")

    pt = datos.get("por_tercio") or []
    if pt and len(pt) == 3:
        total = sum(pt) or 1
        lineas.append("\nReparto de acciones por zona del campo:")
        for i, v in enumerate(pt):
            lineas.append(f"  - {ZONAS_NOMBRE[i]}: {v} acciones ({round(100*v/total)}%)")

    if datos.get("destacados"):
        lineas.append("\nFacetas donde destaca (detectado por datos):")
        for fac, pct in datos["destacados"]:
            lineas.append(f"  - {fac}: {round(pct)}%")
    if datos.get("mejorar"):
        lineas.append("\nFacetas a mejorar (detectado por datos):")
        for fac, pct in datos["mejorar"]:
            lineas.append(f"  - {fac}: {round(pct)}%")

    if comparacion and nombre_b:
        lineas.append(f"\nComparación con {nombre_b} (misma posición), % de acierto:")
        for est, va, vb in comparacion:
            lineas.append(f"  - {est}: {round(va)}% vs {round(vb)}%")

    return "\n".join(lineas)


def _construir_prompt(datos_txt: str) -> str:
    return f"""Eres un PERFORMANCE ANALYST SENIOR de un club profesional. No describes
cifras: las interpretas con criterio. A partir de los datos de un jugador, redacta
un informe de scouting con tono formal y objetivo para el cuerpo técnico.

DATOS DEL JUGADOR:
{datos_txt}

PRINCIPIOS DE ANÁLISIS (aplícalos siempre):
- El % de acierto GLOBAL engaña: mezcla acciones fáciles (pase atrás) con difíciles
  (regate, pase al último tercio). Razona por faceta y por zona, no por el global.
- El VOLUMEN bruto premia al que más toca el balón, no al mejor. Usa las acciones
  por 90 min para comparar, y matiza que más acciones no es mejor jugador.
- DÓNDE rinde importa tanto como cuánto: acertar en el último tercio pesa más que
  en zona segura. Usa el acierto ponderado por zona para detectar esto.

INSTRUCCIONES:
- Estructura con estos títulos exactos precedidos de "## ":
  ## Resumen general
  ## Análisis por facetas
  ## Comportamiento por zonas
  ## Comparación
  ## Recomendaciones
- Si no hay datos de comparación, omite ese apartado.
- Básate ÚNICAMENTE en los datos. No inventes cifras ni hechos.
- Si los datos son escasos (pocas acciones o minutos), indícalo con prudencia y
  evita conclusiones tajantes.
- CONTEXTUALIZA con el marcador y el nivel de los equipos si se proporcionan.
  No atribuyas bajadas de rendimiento a cansancio o presión rival cuando el
  contexto (una goleada, un partido resuelto, un rival muy inferior) sea la
  explicación más probable. Matiza el rendimiento según contra quién se logró.
- INTERPRETA LOS MINUTOS Y EL MOMENTO DE ENTRADA. Si jugó pocos minutos o entró
  como revulsivo (p. ej. en el 70), sus cifras tienen menos peso estadístico: no
  penalices un volumen bajo, y razona el cansancio según cuánto y cuándo jugó
  (un titular que cumple 90' puede acusar desgaste al final; un suplente fresco
  que entra tarde, no). Pondera el volumen también según la posesión del equipo.
- Tono formal, objetivo y técnico. Sin exageraciones ni lenguaje publicitario.
- Escribe en español. Extensión: entre 200 y 350 palabras.
- No uses viñetas en exceso; prioriza prosa de informe."""


def analizar_jugador(datos: dict, comparacion=None, nombre_b=None,
                     posicion_larga="") -> tuple[str | None, str]:
    """Genera el análisis con Gemini.
    Devuelve (texto_analisis, mensaje_estado). Si texto es None, hubo un problema
    descrito en mensaje_estado."""
    if not hay_api_key():
        return None, ("No hay clave de Gemini configurada. Añade GEMINI_KEY en los "
                      "secrets de Streamlit para activar el análisis con IA.")
    try:
        datos_txt = _serializar_datos(datos, comparacion, nombre_b, posicion_larga)
        prompt = _construir_prompt(datos_txt)
        texto = _generar(prompt)
        if not texto:
            return None, "La IA no devolvió texto. Inténtalo de nuevo."
        return texto, "ok"
    except Exception as e:
        return None, f"No se pudo generar el análisis con IA: {e}"


def _serializar_patrones(pd_datos: dict) -> str:
    """Serializa los datos de patrones tácticos para el prompt."""
    L = []
    L.append(f"Jugador: {pd_datos.get('jugador','')}")
    L.append(f"Partidos analizados: {pd_datos.get('n_partidos',0)}")
    L.append(f"Acciones totales: {pd_datos.get('n_acciones',0)}")
    # Contexto del partido: marcador y nivel, clave para no malinterpretar bajadas.
    if pd_datos.get("contexto_partido"):
        L.append(f"\nCONTEXTO DEL PARTIDO: {pd_datos['contexto_partido']}")
        L.append("Pondera el análisis con este contexto: una bajada de ritmo con el "
                 "partido ya resuelto (goleada) no es cansancio; un buen rendimiento "
                 "ante un rival muy inferior debe matizarse.")
    if pd_datos.get("es_suplente"):
        L.append(f"NOTA: jugó como SUPLENTE, entró tarde (ventana {pd_datos.get('ventana','')}, "
                 f"{pd_datos.get('minutos_jugados','')} min). Entró fresco, así que NO atribuyas "
                 f"a cansancio una bajada al final; y no interpretes la ausencia de datos fuera "
                 f"de su ventana como bajón de rendimiento.")
    else:
        L.append(f"NOTA: jugó como TITULAR ({pd_datos.get('minutos_jugados','')} min). "
                 f"Un descenso de intensidad en el tramo final puede deberse a desgaste "
                 f"acumulado, pero descártalo primero si el marcador explica la relajación.")
    if pd_datos.get("posesion") is not None:
        L.append(f"Posesión del equipo: {pd_datos['posesion']}% "
                 "(poca posesión implica menos acciones; no es falta de implicación).")

    L.append("\nReparto y FALLOS por zona del campo (desglosados por tipo de acción):")
    for zona, v in (pd_datos.get("por_zona") or {}).items():
        linea = f"  - {zona}: {v['acciones']} acciones, {v.get('fallos',0)} fallos"
        cats = v.get("fallos_por_categoria") or {}
        if cats:
            detalle = ", ".join(f"{k}: {n}" for k, n in cats.items())
            linea += f" (por tipo: {detalle})"
        if v.get("accion_mas_fallada"):
            linea += f"; acción más fallada: {v['accion_mas_fallada']}"
        L.append(linea)
    L.append("  IMPORTANTE: un fallo no es siempre una 'pérdida en salida de balón'. "
             "Fíjate en QUÉ acción se falla: fallar una intercepción o un duelo defensivo "
             "es un problema defensivo, no de construcción; fallar pases en el primer "
             "tercio sí es salida de balón. No generalices 'pérdidas' sin mirar el tipo.")

    if pd_datos.get("tramos"):
        L.append("\nRendimiento por tramos de 15 minutos:")
        for tramo, v in pd_datos["tramos"].items():
            pct = v["pct_acierto"]
            L.append(f"  - {tramo}: {v['acciones']} acciones" +
                     (f", {pct}% acierto" if pct is not None else ""))

    p1, p2 = pd_datos.get("primera_parte", {}), pd_datos.get("segunda_parte", {})
    L.append("\n1ª vs 2ª parte:")
    L.append(f"  - 1ª parte: {p1.get('acciones',0)} acciones, "
             f"{p1.get('pct_acierto','-')}% acierto")
    L.append(f"  - 2ª parte: {p2.get('acciones',0)} acciones, "
             f"{p2.get('pct_acierto','-')}% acierto")

    if pd_datos.get("acciones_frecuentes"):
        L.append("\nAcciones más frecuentes:")
        for a, n in pd_datos["acciones_frecuentes"].items():
            L.append(f"  - {a}: {n}")
    return "\n".join(L)


def _prompt_patrones(datos_txt: str, fiabilidad: str) -> str:
    avisos = {
        "baja": ("ATENCIÓN: hay MUY POCOS datos (un solo partido o escasas acciones). "
                 "Debes empezar el análisis con una advertencia clara de que las "
                 "observaciones son PRELIMINARES y NO deben tomarse como patrones "
                 "consolidados. Usa lenguaje muy prudente ('parece', 'en este partido', "
                 "'habría que confirmar con más encuentros')."),
        "media": ("Hay datos moderados (varios partidos). Señala patrones con prudencia, "
                  "indicando que la muestra aún es limitada y conviene seguir confirmando."),
        "alta": ("Hay datos suficientes para señalar patrones con razonable confianza, "
                 "aunque sin presentarlos como certezas absolutas."),
    }
    return f"""Eres un analista táctico de un club de fútbol. A partir de datos objetivos
de un jugador, tu tarea es DETECTAR PATRONES DE COMPORTAMIENTO, no solo describir
cifras. Busca tendencias: zonas donde pierde el balón, tramos del partido donde
baja su rendimiento, diferencias entre partes, concentración de acciones.

{avisos.get(fiabilidad, avisos['media'])}

DATOS:
{datos_txt}

INSTRUCCIONES:
- Estructura la respuesta con estos títulos precedidos de "## ":
  ## Nivel de fiabilidad
  ## Patrones detectados
  ## Zonas de influencia y riesgo
  ## Evolución durante el partido
  ## Conclusión táctica
- En "Nivel de fiabilidad", explica en una frase cuántos datos hay y qué peso
  tienen las conclusiones.
- Básate SOLO en los datos. No inventes. Si un patrón no se sostiene con los
  datos, no lo afirmes.
- CONTEXTUALIZA SIEMPRE con el marcador, el nivel de los equipos y el momento
  del partido. NO atribuyas una bajada de intensidad al final a "cansancio" o
  "presión rival" si el contexto la explica mejor: si el equipo va ganando con
  holgura (goleada), lo normal es que el ritmo baje porque el partido está
  resuelto, no por agotamiento del jugador. Igualmente, un rendimiento alto
  contra un rival muy inferior debe matizarse por esa diferencia de nivel.
  Antes de proponer una causa (cansancio, presión, lesión...), descarta que el
  marcador o el contexto del partido sean la explicación más probable.
- Tono formal y técnico, en español. Entre 200 y 350 palabras."""


def detectar_patrones(pd_datos: dict) -> tuple[str | None, str]:
    """Genera el análisis de patrones tácticos con Gemini, con aviso de
    fiabilidad según el volumen de datos. Devuelve (texto, mensaje_estado)."""
    if not pd_datos:
        return None, "No hay datos del jugador para analizar patrones."
    if not hay_api_key():
        return None, ("No hay clave de Gemini configurada. Añade GEMINI_KEY en los "
                      "secrets de Streamlit para activar la detección de patrones.")
    try:
        datos_txt = _serializar_patrones(pd_datos)
        prompt = _prompt_patrones(datos_txt, pd_datos.get("fiabilidad", "media"))
        texto = _generar(prompt)
        if not texto:
            return None, "La IA no devolvió texto. Inténtalo de nuevo."
        return texto, "ok"
    except Exception as e:
        return None, f"No se pudo generar el análisis de patrones: {e}"
