@echo off
chcp 65001 >nul
cd /d "%~dp0"
title StockWaakhond - dashboard
echo.
echo  ==========================================================
echo   STOCKWAAKHOND - dashboard openen
echo  ==========================================================
echo.
echo   Je browser gaat zo vanzelf open.
echo   Laat dit zwarte venster openstaan zolang je kijkt.
echo.
echo   Klaar met kijken? Sluit dit venster, of druk op Ctrl + C.
echo.
echo  ----------------------------------------------------------
echo.

set PY=C:\Users\bartr\Downloads\StockWaakhond_V7_forward_test\StockWaakhond_V7\.venv\Scripts\python.exe

if not exist "%PY%" (
  echo   FOUT: het Python-programma staat niet op de verwachte plek.
  echo   Laat dit aan Claude weten, dan wordt het rechtgezet.
  echo.
  pause
  exit /b 1
)

"%PY%" -m streamlit run streamlit_app.py --server.port 8511

pause
