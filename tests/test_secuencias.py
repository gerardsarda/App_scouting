"""Tests del motor de secuencias (Fase 4).

Fixtures SINTÉTICAS y deterministas: no tocan Supabase ni la red.
"""
import pandas as pd
import pytest

import secuencias


def _df(rows):
    """Construye un DataFrame con las columnas mínimas que usa el motor.
    rows = lista de tuplas (session_id, jugador, minuto, accion, resultado, zona_x).
    """
    return pd.DataFrame(
        [
            {"session_id": s, "sesion": f"partido-{s}", "jugador": j,
             "minuto": m, "accion": a, "resultado": r, "zona_x": z}
            for (s, j, m, a, r, z) in rows
        ]
    )


def test_corta_por_gap_mayor_que_ventana():
    """Dos acciones a 10s (0.17') son la MISMA cadena; a 30s (0.5') son dos."""
    df = _df([
        ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 10.17, "Centro lateral", "Correcto", 2),
        ("s1", "Ana", 10.67, "Despeje", "Correcto", 0),
    ])
    out = secuencias.detectar_secuencias(df)
    assert len(out) == 2
    assert list(out["n_acciones"]) == [2, 1]


def test_no_encadena_entre_partidos_ni_entre_jugadores():
    """Mismo minuto, distinto partido o distinto jugador -> cadenas distintas."""
    df = _df([
        ("s1", "Ana", 10.00, "Pase progresivo", "Correcto", 1),
        ("s2", "Ana", 10.05, "Pase progresivo", "Correcto", 1),
        ("s1", "Leo", 10.05, "Pase progresivo", "Correcto", 1),
    ])
    out = secuencias.detectar_secuencias(df)
    assert len(out) == 3
    assert set(out["n_acciones"]) == {1}


def test_columnas_de_la_cadena():
    """minuto_ini/fin, cadena y familias salen en el orden de tagueo."""
    df = _df([
        ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 10.10, "Recorte / cambio ritmo", "Correcto", 2),
        ("s1", "Ana", 10.20, "Centro lateral", "Correcto", 2),
    ])
    out = secuencias.detectar_secuencias(df)
    assert len(out) == 1
    fila = out.iloc[0]
    assert fila["minuto_ini"] == 10.00
    assert fila["minuto_fin"] == 10.20
    assert fila["n_acciones"] == 3
    assert fila["cadena"] == "Conducción progresiva > Recorte / cambio ritmo > Centro lateral"
    assert fila["familias"] == ["Progresa con balón", "Encara/regatea", "Sirve peligro"]


def test_desenlace_lo_marca_la_ultima_accion():
    """peligro / perdida / neutro segun la ULTIMA accion de la cadena."""
    base = ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1)
    peligro = _df([base, ("s1", "Ana", 10.10, "Pase clave", "Encontrado", 2)])
    perdida = _df([base, ("s1", "Ana", 10.10, "Error grave / pérdida", "—", 0)])
    neutro = _df([base, ("s1", "Ana", 10.10, "Pase atrás", "Correcto", 1)])
    assert secuencias.detectar_secuencias(peligro).iloc[0]["desenlace"] == "peligro"
    assert secuencias.detectar_secuencias(perdida).iloc[0]["desenlace"] == "perdida"
    assert secuencias.detectar_secuencias(neutro).iloc[0]["desenlace"] == "neutro"


def test_valor_es_la_suma_de_nota_evento():
    """El valor reusa analytics.nota_evento; los neutros (None) no rompen."""
    import analytics
    df = _df([
        ("s1", "Ana", 10.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 10.10, "Sprint of. sin balón", "Correcto", 1),
    ])
    out = secuencias.detectar_secuencias(df)
    esperado = sum(
        v for v in [analytics.nota_evento("Conducción progresiva", "Correcto", 1),
                    analytics.nota_evento("Sprint of. sin balón", "Correcto", 1)]
        if v is not None
    )
    assert out.iloc[0]["valor"] == pytest.approx(esperado)


def test_df_vacio_no_revienta():
    out = secuencias.detectar_secuencias(pd.DataFrame())
    assert len(out) == 0
    assert "desenlace" in out.columns


# ---------------------------------------------------------------------------
# CONSUMIDORES
# ---------------------------------------------------------------------------
def _df_patrones():
    """Ana conduce->recorta->centra dos veces; una vez conduce->pierde."""
    rows = []
    for base in [10.0, 20.0]:
        rows += [
            ("s1", "Ana", base + 0.00, "Conducción progresiva", "Correcto", 1),
            ("s1", "Ana", base + 0.10, "Recorte / cambio ritmo", "Correcto", 2),
            ("s1", "Ana", base + 0.20, "Centro lateral", "Correcto", 2),
        ]
    rows += [
        ("s1", "Ana", 30.00, "Conducción progresiva", "Correcto", 1),
        ("s1", "Ana", 30.10, "Error grave / pérdida", "—", 0),
    ]
    return _df(rows)


def test_continuidad():
    secs = secuencias.detectar_secuencias(_df_patrones())
    cont = secuencias.continuidad(secs, "Ana", minutos=180)
    assert cont["n_secuencias"] == 3
    assert cont["largo_medio"] == pytest.approx(8 / 3, abs=0.01)
    assert cont["pct_peligro"] == pytest.approx(0.0)      # centro lateral no es peligro
    assert cont["pct_perdida"] == pytest.approx(100 / 3, abs=0.1)
    assert cont["secuencias_90"] == pytest.approx(1.5)    # 3 en 180'


def test_continuidad_jugador_sin_datos():
    secs = secuencias.detectar_secuencias(_df_patrones())
    cont = secuencias.continuidad(secs, "NoExiste", minutos=90)
    assert cont["n_secuencias"] == 0
    assert cont["secuencias_90"] == 0.0


def test_top_secuencias_ordena_por_valor_y_exige_min_acciones():
    secs = secuencias.detectar_secuencias(_df_patrones())
    top = secuencias.top_secuencias(secs, "Ana", n=5)
    assert len(top) == 3
    assert list(top["valor"]) == sorted(top["valor"], reverse=True)
    assert top["n_acciones"].min() >= secuencias.MIN_ACCIONES
    peor = secuencias.top_secuencias(secs, "Ana", n=1, ascendente=True)
    assert peor.iloc[0]["desenlace"] == "perdida"


def test_top_secuencias_filtra_por_desenlace():
    secs = secuencias.detectar_secuencias(_df_patrones())
    out = secuencias.top_secuencias(secs, "Ana", desenlace="perdida")
    assert len(out) == 1
    assert out.iloc[0]["desenlace"] == "perdida"


def test_patrones_bigrama():
    """Tras conducir: 2 de 3 veces recorta, 1 de 3 pierde."""
    secs = secuencias.detectar_secuencias(_df_patrones())
    out = secuencias.patrones_bigrama(secs, "Ana", "Conducción progresiva")
    fila = out[out["siguiente"] == "Recorte / cambio ritmo"].iloc[0]
    assert fila["veces"] == 2
    assert fila["pct"] == pytest.approx(200 / 3, abs=0.1)
    assert out["veces"].sum() == 3


def test_patrones_bigrama_accion_sin_continuacion():
    """La ULTIMA accion de una cadena no cuenta como origen."""
    secs = secuencias.detectar_secuencias(_df_patrones())
    out = secuencias.patrones_bigrama(secs, "Ana", "Centro lateral")
    assert len(out) == 0


def test_patrones_familia_respeta_el_umbral():
    secs = secuencias.detectar_secuencias(_df_patrones())
    # con umbral 2 aparece el patron repetido dos veces
    out = secuencias.patrones_familia(secs, "Ana", min_repes=2)
    assert list(out["patron"]) == ["Progresa con balón > Encara/regatea > Sirve peligro"]
    assert list(out["veces"]) == [2]
    # con umbral 3 no hay nada que ensenar
    assert len(secuencias.patrones_familia(secs, "Ana", min_repes=3)) == 0
