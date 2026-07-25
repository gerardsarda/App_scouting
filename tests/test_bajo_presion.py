"""Tests de las acciones bajo presión y de decisión/reacción (2026-07-25).

Cubre: clasificación de las 6 acciones nuevas, sus valores de nota (asimétricos,
matiz para los complementos, castigo reducido para la pérdida forzada), la NO
duplicación del gol en Remate BP, que la Conducción BP es lineal (fuera del freno
de circulación), y el agregado "Bajo presión".
"""
import analytics


# --- clasificación ----------------------------------------------------------

def test_clasificacion_acciones_nuevas():
    casos = [
        ("Conducción bajo presión", "Correcto", "exito"),
        ("Conducción bajo presión", "Fallo", "fallo"),
        ("Despeje bajo presión", "Correcto", "exito"),
        ("Pérdida bajo presión", "—", "fallo_medio"),
        ("Remate bajo presión", "Gol", "exito"),
        ("Remate bajo presión", "A puerta", "parcial"),
        ("Remate bajo presión", "Fuera", "fallo"),
        ("Decisión bajo presión", "Acertada", "exito"),
        ("Decisión bajo presión", "Precipitada", "fallo"),
        ("Decisión bajo presión", "Lenta", "fallo_medio"),
        ("Decisión bajo presión", "Conservadora", "fallo_parcial"),
        ("Tras pérdida", "Contrapresiona y recupera", "exito"),
        ("Tras pérdida", "No reacciona", "fallo"),
        ("Tras pérdida", "Contrapresiona, no recupera", "neutro"),
        ("Tras pérdida", "Falta táctica", "neutro"),
        ("Tras pérdida", "Repliega", "neutro"),
    ]
    for accion, res, esperado in casos:
        assert analytics._clase_por_accion(accion, res) == esperado, (accion, res)


def test_predecible():
    # Pérdida BP no tiene éxito posible -> no predecible (no se ofrece su "% acierto").
    assert analytics.predecible("Pérdida bajo presión") is False
    # Las que sí tienen éxito, predecibles.
    assert analytics.predecible("Conducción bajo presión") is True
    assert analytics.predecible("Remate bajo presión") is True
    assert analytics.predecible("Decisión bajo presión") is True


# --- nota: complementos aditivos son matiz ----------------------------------

def test_pase_bp_es_matiz():
    # Bajado de 0.35 a 0.10: no puede dominar el valor del propio pase.
    assert analytics._NOTA_VALORES["Pase bajo presión"] == {"exito": 0.10, "fallo": -0.05}


def test_remate_bp_no_duplica_gol():
    # Es complemento (como el pase): NO está en SHOT_ACTIONS, así que un gol en
    # Remate BP no cuenta como remate/gol nuevo; el gol lo lleva el remate tipado.
    assert "Remate bajo presión" not in analytics.SHOT_ACTIONS
    assert "Remate bajo presión" in analytics.REMATE_COMPLEMENTO
    # Su nota es matiz, no la escala de +3.0 del remate.
    assert analytics.nota_evento("Remate bajo presión", "Gol", 2) < 0.5


# --- nota: variantes de reemplazo valen más / castigan menos -----------------

def test_conduccion_bp_vale_mas_que_normal_y_es_lineal():
    # Misma zona: la conducción bajo presión aporta más que la normal (mérito).
    bp = analytics.nota_evento("Conducción bajo presión", "Correcto", 2)
    normal = analytics.nota_evento("Conducción progresiva", "Correcto", 2)
    assert bp > normal
    # Y NO entra en el freno de circulación (es mérito, no circulación segura).
    assert "Conducción bajo presión" not in analytics._NOTA_CIRCULACION
    assert "Conducción progresiva" in analytics._NOTA_CIRCULACION


def test_perdida_bp_castiga_menos_que_perdida_normal():
    misma_zona = 0
    bp = analytics.nota_evento("Pérdida bajo presión", "—", misma_zona)
    normal = analytics.nota_evento("Error grave / pérdida", "—", misma_zona)
    assert bp < 0 and normal < 0
    assert bp > normal, "la pérdida forzada debe restar MENOS que la evitable"


def test_despeje_bp_es_defensivo():
    # Premio direccional defensivo: cerca de tu área (zona 0) vale más.
    assert "Despeje bajo presión" in analytics._NOTA_DEFENSIVAS
    cerca = analytics.nota_evento("Despeje bajo presión", "Correcto", 0)
    lejos = analytics.nota_evento("Despeje bajo presión", "Correcto", 2)
    assert cerca > lejos


# --- nota: tras pérdida ------------------------------------------------------

def test_tras_perdida_neutros_no_puntuan():
    # FT / CP-no-recupera / Repliega = neutro -> excluidos de la nota (None).
    for res in ("Falta táctica", "Contrapresiona, no recupera", "Repliega"):
        assert analytics.nota_evento("Tras pérdida", res, 1) is None
    # CP✓ suma, NO resta.
    assert analytics.nota_evento("Tras pérdida", "Contrapresiona y recupera", 1) > 0
    assert analytics.nota_evento("Tras pérdida", "No reacciona", 1) < 0


# --- agregado bajo presión ---------------------------------------------------

def test_agregado_bajo_presion():
    spec = analytics.ACCIONES_AGREGADAS["Bajo presión"]
    assert spec["solo_conteo"] is False  # muestra % (compostura)
    accs = set(spec["acciones"])
    # Incluye flags explícitos + inherentes (regate/recorte/protección).
    for a in ("Pase bajo presión", "Conducción bajo presión", "Regate 1v1",
              "Recorte / cambio ritmo", "Protección de balón", "Control difícil"):
        assert a in accs
    # NO incluye presionar al rival ni la decisión (que cabalga sobre otra acción).
    assert "Presión fuerza error" not in accs
    assert "Decisión bajo presión" not in accs


def test_agregado_bajo_presion_acciones_en_diccionario():
    conocidas = set(analytics._DIC_ACCIONES)
    for a in analytics.ACCIONES_AGREGADAS["Bajo presión"]["acciones"]:
        assert a in conocidas, f"{a} no está en el diccionario"
