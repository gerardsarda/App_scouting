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

MODELO = "gemini-1.5-flash"
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
    lineas.append(f"Minutos analizados: {datos.get('minutos',0)}")
    lineas.append(f"Acciones totales: {datos.get('acciones',0)}")
    lineas.append(f"Porcentaje de acierto global: {datos.get('pct_global',0)}%")

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
    return f"""Eres un analista de scouting profesional de un club de fútbol. A partir de
los datos objetivos de un jugador recogidos en uno o varios partidos, redacta un
informe de análisis con tono formal y objetivo, como el que se entregaría al
cuerpo técnico de un club.

DATOS DEL JUGADOR:
{datos_txt}

INSTRUCCIONES:
- Redacta un análisis DETALLADO estructurado en estos apartados, usando estos
  títulos exactos precedidos de "## ":
  ## Resumen general
  ## Análisis por facetas
  ## Comportamiento por zonas
  ## Comparación
  ## Recomendaciones
- Si no hay datos de comparación, omite ese apartado.
- Básate ÚNICAMENTE en los datos proporcionados. No inventes cifras ni hechos.
- Si los datos son escasos (pocas acciones o minutos), indícalo con prudencia y
  evita conclusiones tajantes.
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
        import google.generativeai as genai
        genai.configure(api_key=st.secrets["GEMINI_KEY"])
        datos_txt = _serializar_datos(datos, comparacion, nombre_b, posicion_larga)
        prompt = _construir_prompt(datos_txt)
        model = genai.GenerativeModel(MODELO)
        resp = model.generate_content(prompt)
        texto = (resp.text or "").strip()
        if not texto:
            return None, "La IA no devolvió texto. Inténtalo de nuevo."
        return texto, "ok"
    except Exception as e:
        return None, f"No se pudo generar el análisis con IA: {e}"
