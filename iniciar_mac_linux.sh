#!/usr/bin/env bash
# ============================================================
#  Scouting Mundial - Lanzador para Mac / Linux
#  Uso: ./iniciar_mac_linux.sh
#  (si da permiso denegado: chmod +x iniciar_mac_linux.sh)
# ============================================================

echo ""
echo "  ===================================="
echo "   SCOUTING MUNDIAL - Iniciando..."
echo "  ===================================="
echo ""

# Comprobar si streamlit esta instalado; si no, instalar dependencias
if ! python3 -m streamlit version >/dev/null 2>&1; then
    echo "Instalando dependencias por primera vez..."
    python3 -m pip install -r requirements.txt
fi

echo "Abriendo la app en tu navegador..."
python3 -m streamlit run scouting_app.py
