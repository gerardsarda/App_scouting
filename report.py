"""
report.py — Generador del informe PDF del jugador (look oficial, antracita + verde).
Recibe datos REALES calculados en analytics.py y dibuja el PDF con reportlab.
Función pública: generar_informe(path, datos, comparacion, notas, foto_path).
"""
import math
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---- PALETA SOBRIA ----
BG       = (0.086, 0.094, 0.102)   # antracita de fondo
PANEL    = (0.122, 0.133, 0.145)   # tarjeta
PANEL_LN = (0.20, 0.22, 0.24)      # borde sutil
ACENTO   = (0.18, 0.72, 0.42)      # verde acento (único color "vivo")
TXT      = (0.93, 0.94, 0.95)      # texto principal
TXT_MID  = (0.66, 0.70, 0.74)
TXT_LO   = (0.42, 0.46, 0.50)
HAIR     = (0.18, 0.20, 0.22)      # pista de barras
# escala de verde para datos (de apagado a vivo)
def verde_escala(t):
    """t en 0..1 -> verde de oscuro/apagado (poco) a claro/vivo (mucho)."""
    t = max(0.0, min(1.0, t))
    r = 0.16 + (0.45 - 0.16) * t
    g = 0.34 + (0.85 - 0.34) * t
    b = 0.24 + (0.50 - 0.24) * t
    return (r, g, b)
# color de comparación (jugador B): gris claro neutro, para no meter otro color vivo
COMP = (0.62, 0.66, 0.70)

W, H = A4


def panel(c, x, y, w, h, r=6):
    c.setFillColorRGB(*PANEL)
    c.roundRect(x, y, w, h, r, fill=1, stroke=0)
    c.setStrokeColorRGB(*PANEL_LN)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, r, fill=0, stroke=1)


def titulo(c, x, y, txt):
    c.setFillColorRGB(*TXT_MID)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x, y, txt.upper())
    # tracking manual no disponible; subrayado fino de acento
    c.setStrokeColorRGB(*ACENTO)
    c.setLineWidth(1.5)
    c.line(x, y - 5, x + 22, y - 5)


def barra_escala(c, x, y, w_max, valor, vmax, etiqueta, valor_txt):
    """Barra en escala de verde: cuanto mayor el valor, más claro/vivo."""
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*TXT)
    c.drawString(x, y + 4, etiqueta)
    by = y - 9
    c.setFillColorRGB(*HAIR)
    c.roundRect(x, by, w_max, 6, 2, fill=1, stroke=0)
    t = (valor / vmax) if vmax else 0
    bw = max(3, w_max * t)
    c.setFillColorRGB(*verde_escala(t))
    c.roundRect(x, by, bw, 6, 2, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*TXT)
    c.drawString(x + w_max + 8, by - 1, valor_txt)


def barra_comp(c, x, y, w_max, etq, va, vb, nombre_b):
    """Compara jugador A (verde) con jugador B (gris) misma posición."""
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*TXT)
    c.drawString(x, y + 5, etq)
    # barra A
    byA = y - 7
    c.setFillColorRGB(*HAIR); c.roundRect(x, byA, w_max, 6, 2, fill=1, stroke=0)
    c.setFillColorRGB(*ACENTO); c.roundRect(x, byA, max(3, w_max * va / 100), 6, 2, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8.5); c.setFillColorRGB(*ACENTO)
    c.drawString(x + w_max + 8, byA - 1, f"{va}%")
    # barra B
    byB = y - 16
    c.setFillColorRGB(*HAIR); c.roundRect(x, byB, w_max, 6, 2, fill=1, stroke=0)
    c.setFillColorRGB(*COMP); c.roundRect(x, byB, max(3, w_max * vb / 100), 6, 2, fill=1, stroke=0)
    c.setFont("Helvetica", 8); c.setFillColorRGB(*COMP)
    c.drawString(x + w_max + 8, byB - 1, f"{vb}%")


def donut(c, cx, cy, r, pct, label, valor_txt):
    c.setStrokeColorRGB(*HAIR); c.setLineWidth(6)
    c.circle(cx, cy, r, fill=0, stroke=1)
    c.setStrokeColorRGB(*ACENTO); c.setLineWidth(6)
    p = c.beginPath()
    steps = max(2, int(60 * pct / 100))
    for i in range(steps + 1):
        a = math.pi / 2 - 2 * math.pi * (i / 60)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
    c.drawPath(p, fill=0, stroke=1)
    c.setFillColorRGB(*TXT); c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(cx, cy - 4, valor_txt)
    c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica", 7)
    c.drawCentredString(cx, cy - r - 11, label.upper())


def foto_ph(c, x, y, s, foto_path=None):
    """Dibuja la foto del jugador si se da foto_path; si no, un placeholder."""
    if foto_path:
        try:
            from reportlab.lib.utils import ImageReader
            c.saveState()
            p = c.beginPath()
            p.roundRect(x, y, s, s, 6)
            c.clipPath(p, stroke=0, fill=0)
            c.drawImage(ImageReader(foto_path), x, y, s, s,
                        preserveAspectRatio=True, anchor='c', mask='auto')
            c.restoreState()
            c.setStrokeColorRGB(*PANEL_LN); c.setLineWidth(1)
            c.roundRect(x, y, s, s, 6, fill=0, stroke=1)
            return
        except Exception:
            pass  # si falla, cae al placeholder
    c.setFillColorRGB(0.16, 0.17, 0.19)
    c.roundRect(x, y, s, s, 6, fill=1, stroke=0)
    c.setFillColorRGB(0.28, 0.31, 0.34)
    c.circle(x + s / 2, y + s * 0.62, s * 0.17, fill=1, stroke=0)
    p = c.beginPath()
    p.moveTo(x + s * 0.24, y + s * 0.16)
    p.curveTo(x + s * 0.28, y + s * 0.42, x + s * 0.72, y + s * 0.42, x + s * 0.76, y + s * 0.16)
    p.close(); c.drawPath(p, fill=1, stroke=0)
    c.setStrokeColorRGB(*PANEL_LN); c.setLineWidth(1)
    c.roundRect(x, y, s, s, 6, fill=0, stroke=1)


def radar(c, cx, cy, R, labels, va, vb=None):
    n = len(labels)
    c.setStrokeColorRGB(*HAIR); c.setLineWidth(0.7)
    for frac in (0.33, 0.66, 1.0):
        pts = [(cx + R*frac*math.cos(-math.pi/2+2*math.pi*i/n),
                cy + R*frac*math.sin(-math.pi/2+2*math.pi*i/n)) for i in range(n)]
        for i in range(n):
            c.line(pts[i][0], pts[i][1], pts[(i+1)%n][0], pts[(i+1)%n][1])
    for i, lab in enumerate(labels):
        a = -math.pi/2 + 2*math.pi*i/n
        c.setStrokeColorRGB(*HAIR); c.line(cx, cy, cx+R*math.cos(a), cy+R*math.sin(a))
        lx, ly = cx+(R+15)*math.cos(a), cy+(R+15)*math.sin(a)
        c.setFillColorRGB(*TXT_MID); c.setFont("Helvetica", 7)
        c.drawCentredString(lx, ly-3, lab)
    def poly(vals, col, alpha):
        pts = []
        for i, v in enumerate(vals):
            a = -math.pi/2 + 2*math.pi*i/n
            rr = R*(v/100.0)
            pts.append((cx+rr*math.cos(a), cy+rr*math.sin(a)))
        pth = c.beginPath(); pth.moveTo(*pts[0])
        for q in pts[1:]: pth.lineTo(*q)
        pth.close()
        c.setFillColorRGB(*col); c.setFillAlpha(alpha)
        c.setStrokeColorRGB(*col); c.setLineWidth(1.8)
        c.drawPath(pth, fill=1, stroke=1); c.setFillAlpha(1)
        for q in pts:
            c.setFillColorRGB(*col); c.circle(q[0], q[1], 2, fill=1, stroke=0)
    if vb: poly(vb, COMP, 0.12)
    poly(va, ACENTO, 0.20)


def campo_heat(c, x, y, w, h, grid):
    # césped monocromo sobrio (no franjas vivas)
    c.setFillColorRGB(0.14, 0.16, 0.17)
    c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    cw, ch = w/3, h/3
    mx = max(max(r) for r in grid) or 1
    for yi in range(3):
        for xi in range(3):
            v = grid[yi][xi]
            if v <= 0: continue
            t = v/mx
            cxx = x+xi*cw+cw/2; cyy = y+(2-yi)*ch+ch/2
            for k, al in [(1.0,0.10),(0.7,0.16),(0.45,0.22)]:
                c.setFillColorRGB(*verde_escala(t)); c.setFillAlpha(al*(0.6+t))
                c.ellipse(cxx-cw*0.55*k, cyy-ch*0.55*k, cxx+cw*0.55*k, cyy+ch*0.55*k, fill=1, stroke=0)
            c.setFillAlpha(1); c.setFillColorRGB(*TXT); c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(cxx, cyy-3, str(v))
    c.setStrokeColorRGB(0.40, 0.44, 0.47); c.setLineWidth(1)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.line(x+w/2, y, x+w/2, y+h); c.circle(x+w/2, y+h/2, h*0.16, fill=0, stroke=1)
    c.rect(x, y+h/2-h*0.28, w*0.13, h*0.56, fill=0, stroke=1)
    c.rect(x+w-w*0.13, y+h/2-h*0.28, w*0.13, h*0.56, fill=0, stroke=1)


def tag(c, x, y, txt, outline=True):
    """Etiqueta sobria: contorno fino, sin relleno de color vivo."""
    tw = c.stringWidth(txt, "Helvetica", 8) + 14
    c.setFillColorRGB(*PANEL)
    c.roundRect(x, y, tw, 14, 7, fill=1, stroke=0)
    c.setStrokeColorRGB(*ACENTO); c.setLineWidth(0.8)
    c.roundRect(x, y, tw, 14, 7, fill=0, stroke=1)
    c.setFillColorRGB(*TXT); c.setFont("Helvetica", 8)
    c.drawCentredString(x+tw/2, y+4, txt)
    return tw


def fondo(c):
    c.setFillColorRGB(*BG); c.rect(0, 0, W, H, fill=1, stroke=0)

def pie(c, pag):
    c.setStrokeColorRGB(*HAIR); c.setLineWidth(0.8); c.line(40, 46, W-40, 46)
    c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica", 7.5)
    c.drawString(40, 34, "SCOUTING MUNDIAL   ·   Informe de jugador")
    c.drawRightString(W-40, 34, f"Pág. {pag}")




def _campo_heat_grid(c, x, y, w, h, grid):
    """Mapa de calor recibiendo grid como lista 3x3 (filas=bandas, cols=tercios)."""
    c.setFillColorRGB(0.14, 0.16, 0.17)
    c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    cw, ch = w/3, h/3
    mx = max(max(r) for r in grid) or 1
    for yi in range(3):
        for xi in range(3):
            v = grid[yi][xi]
            if v <= 0: continue
            t = v/mx
            cxx = x+xi*cw+cw/2; cyy = y+(2-yi)*ch+ch/2
            for k, al in [(1.0,0.10),(0.7,0.16),(0.45,0.22)]:
                c.setFillColorRGB(*verde_escala(t)); c.setFillAlpha(al*(0.6+t))
                c.ellipse(cxx-cw*0.55*k, cyy-ch*0.55*k, cxx+cw*0.55*k, cyy+ch*0.55*k, fill=1, stroke=0)
            c.setFillAlpha(1); c.setFillColorRGB(*TXT); c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(cxx, cyy-3, str(int(v)))
    c.setStrokeColorRGB(0.40, 0.44, 0.47); c.setLineWidth(1)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.line(x+w/2, y, x+w/2, y+h); c.circle(x+w/2, y+h/2, h*0.16, fill=0, stroke=1)
    c.rect(x, y+h/2-h*0.28, w*0.13, h*0.56, fill=0, stroke=1)
    c.rect(x+w-w*0.13, y+h/2-h*0.28, w*0.13, h*0.56, fill=0, stroke=1)


def generar_informe(path, datos, comparacion=None, notas=None, foto_path=None,
                    nombre_b=None, analisis_ia=None):
    """Genera el informe PDF del jugador con datos REALES.

    datos: dict de analytics.player_report_data().
    comparacion: lista de (faceta, pct_a, pct_b) de analytics.player_comparison(), o None.
    notas: lista de strings (notas del analista) o None.
    foto_path: ruta a la foto del jugador o None.
    nombre_b: nombre del jugador comparado (para la leyenda).
    analisis_ia: texto markdown del análisis con IA (Gemini) o None.
    """
    c = canvas.Canvas(path, pagesize=A4)
    M = 42
    FAC = ["Pase", "Regate", "Finalización", "Defensa", "Mov. sin balón"]
    FAC_CORTO = ["Pase", "Regate", "Final.", "Def.", "Mov.", "Vol."]

    # ===== PÁGINA 1 =====
    fondo(c)
    panel(c, M, H-152, W-2*M, 116)
    foto_ph(c, M+16, H-140, 92, foto_path=foto_path)
    tx = M+124
    c.setFillColorRGB(*TXT); c.setFont("Helvetica-Bold", 22)
    c.drawString(tx, H-66, datos["jugador"][:26])
    c.setFillColorRGB(*TXT_MID); c.setFont("Helvetica", 10)
    # Posición en texto completo (la app la pasa ya traducida en 'posicion_larga').
    pos_txt = datos.get("posicion_larga") or datos.get("posicion", "")
    extras = []
    if datos.get("equipo"):
        extras.append(str(datos["equipo"]))
    if datos.get("edad"):
        extras.append(f"{datos['edad']} años")
    linea2 = pos_txt + ("   ·   " + "   ·   ".join(extras) if extras else "")
    c.drawString(tx, H-83, linea2)
    c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica", 8.5)
    c.drawString(tx, H-104, f"{datos['minutos']} min  ·  {datos['acciones']} acciones registradas")
    if datos.get("contexto_nivel"):
        c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica-Oblique", 8)
        c.drawString(tx, H-117, datos["contexto_nivel"][:80])
    # donut acierto global + faceta top
    donut(c, W-M-115, H-92, 24, datos["pct_global"], "Acierto", f"{datos['pct_global']:.0f}%")
    fac_top = max(datos["facetas"].items(), key=lambda kv: kv[1]) if datos["facetas"] else ("", 0)
    donut(c, W-M-52, H-92, 24, fac_top[1], fac_top[0][:6], f"{fac_top[1]:.0f}%")

    # Destaca en
    yb = H-178
    titulo(c, M, yb, "Destaca en")
    yb -= 20; cx = M
    if datos["destacados"]:
        for fac, pct in datos["destacados"]:
            cx += tag(c, cx, yb, f"{fac} ({pct:.0f}%)") + 7
    else:
        c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(M, yb+3, "Sin datos suficientes para destacar facetas.")

    # A mejorar
    yb -= 28
    titulo(c, M, yb, "A mejorar")
    yb -= 20; cx = M
    if datos["mejorar"]:
        for fac, pct in datos["mejorar"]:
            cx += tag(c, cx, yb, f"{fac} ({pct:.0f}%)") + 7
    else:
        c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(M, yb+3, "Sin debilidades claras con los datos actuales.")

    # Volumen / Eficacia
    ycol = yb - 26
    colw = (W-2*M-26)/2
    panel(c, M, ycol-168, colw, 160)
    panel(c, M+colw+26, ycol-168, colw, 160)
    titulo(c, M+14, ycol-16, "Volumen de acciones")
    y = ycol-42
    vol = datos["volumen"] or [("(sin métricas elegidas)", 0)]
    vmax = max([v for _, v in vol] + [1])
    for etq, val in vol[:6]:
        barra_escala(c, M+14, y, colw-58, val, vmax, etq, str(val)); y -= 27
    titulo(c, M+colw+40, ycol-16, "Eficacia por faceta")
    y = ycol-42
    for fac in FAC:
        p = datos["facetas"].get(fac, 0)
        barra_escala(c, M+colw+40, y, colw-68, p, 100, fac, f"{p:.0f}%"); y -= 27

    # Radar + heat
    yr = ycol-192
    panel(c, M, yr-166, colw, 158)
    titulo(c, M+14, yr-16, "Perfil del jugador")
    radar(c, M+colw/2, yr-92, 56, FAC_CORTO, datos["radar"])
    panel(c, M+colw+26, yr-166, colw, 158)
    titulo(c, M+colw+40, yr-16, "Mapa de calor")
    _campo_heat_grid(c, M+colw+40, yr-148, colw-28, 108, datos["grid"])

    pie(c, 1)
    c.showPage()

    # ===== PÁGINA 2 =====
    fondo(c)
    c.setFillColorRGB(*TXT); c.setFont("Helvetica-Bold", 15)
    c.drawString(M, H-52, f"{datos['jugador'][:30]} · Comparación y detalle")
    c.setFillColorRGB(*TXT_MID); c.setFont("Helvetica", 9)
    sub = f"Frente a {nombre_b}" if nombre_b else "Detalle por zonas"
    c.drawString(M, H-68, sub)

    yc = H-100
    if comparacion:
        panel(c, M, yc-232, W-2*M, 224)
        titulo(c, M+14, yc-16, f"Comparativa · {datos.get('posicion','')}")
        c.setFillColorRGB(*ACENTO); c.circle(M+16, yc-32, 3, fill=1, stroke=0)
        c.setFillColorRGB(*TXT); c.setFont("Helvetica", 8); c.drawString(M+24, yc-35, datos["jugador"][:20])
        c.setFillColorRGB(*COMP); c.circle(M+150, yc-32, 3, fill=1, stroke=0)
        c.setFillColorRGB(*TXT); c.drawString(M+158, yc-35, (nombre_b or "Comparado")[:20])
        y = yc-58
        for etq, va, vb in comparacion:
            barra_comp(c, M+14, y, W-2*M-70, etq, round(va), round(vb), "B"); y -= 33
        yr2 = yc-252
    else:
        c.setFillColorRGB(*TXT_LO); c.setFont("Helvetica-Oblique", 9)
        c.drawString(M, yc-20, "No se eligió jugador de comparación.")
        yr2 = yc-40

    # Radar comparativo + tercios
    half = (W-2*M-26)/2
    panel(c, M, yr2-170, half, 162)
    titulo(c, M+14, yr2-16, "Radar comparativo" if comparacion else "Radar")
    vb_vals = None
    if comparacion:
        # reconstruir vector B en orden de facetas del radar (5 + volumen aprox)
        mapa = {e: vb for e, _, vb in comparacion}
        vb_vals = [mapa.get(f, 0) for f in FAC] + [datos["radar"][5]]
    radar(c, M+half/2, yr2-95, 56, FAC_CORTO, datos["radar"], vb=vb_vals)

    panel(c, M+half+26, yr2-170, half, 162)
    titulo(c, M+half+40, yr2-16, "Acciones por tercio")
    ter = [("1er tercio", datos["por_tercio"][0]),
           ("2º tercio", datos["por_tercio"][1]),
           ("3er tercio", datos["por_tercio"][2])]
    tmax = max([v for _, v in ter] + [1]); y = yr2-46
    for etq, val in ter:
        barra_escala(c, M+half+40, y, half-66, val, tmax, etq, str(int(val))); y -= 34

    # Notas
    yn = yr2-194
    titulo(c, M, yn, "Notas del analista")
    panel(c, M, yn-66, W-2*M, 60)
    c.setFillColorRGB(*TXT); c.setFont("Helvetica", 9)
    ty = yn-22
    notas_list = notas or ["(Sin notas registradas en la sesión.)"]
    for n in notas_list[:3]:
        c.setFillColorRGB(*ACENTO); c.drawString(M+12, ty, "—")
        c.setFillColorRGB(*TXT); c.drawString(M+26, ty, n[:120]); ty -= 16

    pie(c, 2)
    c.showPage()

    # ===== PÁGINA 3: ANÁLISIS IA (solo si hay texto) =====
    if analisis_ia:
        _pagina_analisis_ia(c, analisis_ia, datos)

    c.save()


def _wrap_texto(c, texto, font, size, max_w):
    """Parte un texto en líneas que caben en max_w puntos."""
    c.setFont(font, size)
    palabras = texto.split()
    lineas, actual = [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if c.stringWidth(prueba, font, size) <= max_w:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _pagina_analisis_ia(c, analisis_ia, datos):
    """Renderiza el texto markdown del análisis IA en una o varias páginas."""
    M = 42
    ancho = W - 2 * M
    def cabecera_pagina():
        fondo(c)
        c.setFillColorRGB(*TXT); c.setFont("Helvetica-Bold", 15)
        c.drawString(M, H - 52, f"{datos.get('jugador','')[:30]} · Análisis con IA")
        c.setFillColorRGB(*TXT_MID); c.setFont("Helvetica", 9)
        c.drawString(M, H - 68, "Generado automáticamente a partir de los datos registrados (Gemini)")
        return H - 92
    y = cabecera_pagina()

    for raw in analisis_ia.split("\n"):
        linea = raw.strip()
        if not linea:
            y -= 6
            continue
        # salto de página si no queda espacio
        if y < 80:
            pie(c, 3)
            c.showPage()
            y = cabecera_pagina()
        if linea.startswith("## "):
            titulo(c, M, y, linea[3:].strip())
            y -= 22
        elif linea.startswith("# "):
            titulo(c, M, y, linea[2:].strip())
            y -= 22
        else:
            # limpiar marcas markdown básicas
            txt = linea.replace("**", "").replace("*", "").lstrip("- ").strip()
            for sub in _wrap_texto(c, txt, "Helvetica", 9.5, ancho):
                if y < 70:
                    pie(c, 3)
                    c.showPage()
                    y = cabecera_pagina()
                c.setFillColorRGB(*TXT); c.setFont("Helvetica", 9.5)
                c.drawString(M, y, sub)
                y -= 14
            y -= 4
    pie(c, 3)
    c.showPage()
