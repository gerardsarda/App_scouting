# -*- coding: utf-8 -*-
"""Tests de los totales de conducción/despeje/remates + exclusión de meta-tags
en los gráficos espaciales (2026-07-28)."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


def _df(filas, **cols):
    """(jugador, accion, resultado) -> df con las columnas que usa el motor."""
    base = []
    for j, a, r in filas:
        fila = {"session_id": "s1", "sesion": "S1", "fecha": "2026-01-01",
                "jugador": j, "posicion": "MC", "accion": a, "resultado": r,
                "zona_x": 1, "zona_y": 1, "minuto": 10.0}
        fila.update(cols)
        base.append(fila)
    df = pd.DataFrame(base)
    df["exito"] = df.apply(lambda x: analytics.is_success(x["resultado"], x["accion"]), axis=1)
    df["intento"] = df.apply(lambda x: analytics.is_attempt(x["resultado"], x["accion"]), axis=1)
    df["peso"] = df.apply(lambda x: analytics.success_weight(x["resultado"], x["accion"]), axis=1)
    return df


# --- 1. Exclusión de meta-tags en mapas -------------------------------------

def test_meta_no_volumen_contenido():
    # Los 4 meta-tags: juicios + complementos aditivos.
    assert analytics.META_NO_VOLUMEN == {
        "Decisión bajo presión", "Tras pérdida",
        "Pase bajo presión", "Remate bajo presión"}


def test_zone_grid_excluye_meta_tags():
    df = _df([
        ("Ana", "Pase progresivo", "Correcto"),   # cuenta
        ("Ana", "Pase bajo presión", "Correcto"),  # NO (complemento aditivo)
        ("Ana", "Decisión bajo presión", "Acertada"),  # NO (juicio)
        ("Ana", "Tras pérdida", "Contrapresiona y recupera"),  # NO (juicio)
        ("Ana", "Remate bajo presión", "A puerta"),  # NO (complemento aditivo)
        ("Ana", "Conducción bajo presión", "Correcto"),  # SÍ (reemplazo real)
        ("Ana", "Despeje bajo presión", "Correcto"),  # SÍ (reemplazo real)
        ("Ana", "Pérdida bajo presión", "—"),  # SÍ (reemplazo real)
    ])
    # Sin excluir: cuenta las 8.
    assert int(analytics.zone_grid_counts(df).sum()) == 8
    # Excluyendo los meta-tags: quedan 4 (progresivo + 3 reemplazos BP).
    assert int(analytics.zone_grid_counts(
        df, excluir=analytics.META_NO_VOLUMEN).sum()) == 4


def test_zone_grid_default_no_cambia():
    # Sin el argumento excluir, comportamiento idéntico al de antes.
    df = _df([("Ana", "Pase bajo presión", "Correcto")])
    assert int(analytics.zone_grid_counts(df).sum()) == 1


def test_influencia_excluye_meta_tags():
    df = _df([
        ("Ana", "Pase progresivo", "Correcto"),
        ("Ana", "Conducción bajo presión", "Correcto"),
        ("Ana", "Pase bajo presión", "Correcto"),
        ("Ana", "Decisión bajo presión", "Acertada"),
        ("Ana", "Tras pérdida", "No reacciona"),
        ("Ana", "Remate bajo presión", "Fuera"),
    ])
    r = analytics.influencia_por_minuto(df, "Ana")
    # Franja 0-15: solo el progresivo + la conducción BP (los 4 meta-tags fuera).
    assert sum(r["volumen"]) == 2


# --- 2/5. Conducción progresiva incluye BP (card sincronizada) --------------

def test_conduccion_equiv_y_card():
    assert analytics.CONDUCCION_EQUIV == ["Conducción progresiva",
                                          "Conducción bajo presión"]
    assert analytics.METRICAS_DASH["conduccion"]["acciones"] == analytics.CONDUCCION_EQUIV
    df = _df([("Ana", "Conducción progresiva", "Correcto"),
              ("Ana", "Conducción bajo presión", "Correcto")])
    assert analytics.metrica_dashboard(df, "Ana", "conduccion", "total") == 2


# --- 3. Despeje incluye BP + ABP (card sincronizada) ------------------------

def test_despeje_equiv_y_card():
    assert analytics.DESPEJE_EQUIV == ["Despeje", "Despeje bajo presión",
                                       "Despeje en ABP def."]
    assert analytics.METRICAS_DASH["despeje"]["acciones"] == analytics.DESPEJE_EQUIV
    df = _df([("Ana", "Despeje", "Correcto"),
              ("Ana", "Despeje bajo presión", "Correcto"),
              ("Ana", "Despeje en ABP def.", "Correcto")])
    assert analytics.metrica_dashboard(df, "Ana", "despeje", "total") == 3


# --- Estadísticas: filas-total (patrón pase progresivo) ---------------------

def test_estadisticas_total_conduccion():
    df = _df([("Ana", "Conducción progresiva", "Correcto"),
              ("Ana", "Conducción bajo presión", "Fallo")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    labels = [f["label"] for f in out.get("Ataque", [])]
    assert "Conducción progresiva (total)" in labels
    assert "Conducción bajo presión" in labels          # variante suelta sigue
    total = next(f for f in out["Ataque"] if f["label"] == "Conducción progresiva (total)")
    assert total["total"] == 2


def test_estadisticas_total_despeje_incluye_abp():
    df = _df([("Ana", "Despeje", "Correcto"),
              ("Ana", "Despeje bajo presión", "Correcto"),
              ("Ana", "Despeje en ABP def.", "Correcto")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    total = next(f for f in out["Defensa"] if f["label"] == "Despeje (total)")
    assert total["total"] == 3                            # incluye el de ABP
    # El renglón de ABP sigue existiendo por su cuenta en su sección.
    abp_labels = [f["label"] for f in out.get("ABP", [])]
    assert "Despeje en ABP def." in abp_labels


def test_estadisticas_total_solo_con_dos_variantes():
    # Con una sola variante presente NO se añade la fila-total (sería idéntica).
    df = _df([("Ana", "Despeje", "Correcto")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    labels = [f["label"] for f in out.get("Defensa", [])]
    assert "Despeje (total)" not in labels
    assert "Despeje" in labels


# --- 4. Remates totales (agregado) + Remate BP fuera ------------------------

def test_remates_totales_agregado_excluye_bp():
    spec = analytics.ACCIONES_AGREGADAS["Remates totales"]
    assert "Remate bajo presión" not in spec["acciones"]
    assert set(spec["acciones"]) == set(analytics.SHOT_ACTIONS)


def test_remates_totales_no_cuenta_remate_bp():
    df = _df([("Ana", "Remate", "Gol"),
              ("Ana", "Remate de cabeza", "A puerta"),
              ("Ana", "Remate bajo presión", "A puerta")])
    out = analytics.estadisticas_por_seccion(df, "Ana")
    agg = next(f for f in out["Agregadas"] if f["label"] == "Remates totales")
    assert agg["total"] == 2                              # los 2 tipados, no el BP
    # Remate BP aparece como fila propia (en Ataque), fuera del total.
    at_labels = [f["label"] for f in out.get("Ataque", [])]
    assert "Remate bajo presión" in at_labels
