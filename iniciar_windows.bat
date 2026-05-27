@echo off
REM ============================================================
REM  Scouting Mundial - Lanzador para Windows
REM  Doble clic en este archivo para arrancar la app.
REM ============================================================

echo.
echo   ====================================
echo    SCOUTING MUNDIAL - Iniciando...
echo   ====================================
echo.

REM Comprobar si streamlit esta instalado; si no, instalar dependencias
python -m streamlit version >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias por primera vez...
    python -m pip install -r requirements.txt
)

echo Abriendo la app en tu navegador...
python -m streamlit run scouting_app.py

pause
