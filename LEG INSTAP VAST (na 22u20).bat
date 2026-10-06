@echo off
chcp 65001 >nul
cd /d "%~dp0"
title StockWaakhond - instap vastleggen
echo.
echo  ==========================================================
echo   STOCKWAAKHOND - de virtuele portefeuille laten instappen
echo  ==========================================================
echo.
echo   Dit legt vast tegen welke koers de 1.000 euro instapt.
echo   Het gebeurt maar een keer en kan daarna niet meer wijzigen.
echo.
echo   Werkt pas na 22u20, als de Amerikaanse beurs dicht is.
echo   Is het nog te vroeg, dan zegt het programma dat gewoon
echo   en is er niets gebeurd. Probeer dan later opnieuw.
echo.
echo  ----------------------------------------------------------
echo.

set PY=C:\Users\bartr\Downloads\StockWaakhond_V7_forward_test\StockWaakhond_V7\.venv\Scripts\python.exe

if not exist "%PY%" (
  echo   FOUT: het Python-programma staat niet op de verwachte plek.
  echo   Verwacht hier: %PY%
  echo.
  echo   Laat dit aan Claude weten, dan wordt het rechtgezet.
  echo.
  pause
  exit /b 1
)

"%PY%" scripts\leg_instap_vast.py

echo.
echo  ----------------------------------------------------------
echo   Klaar. Je mag dit venster sluiten.
echo  ----------------------------------------------------------
pause
