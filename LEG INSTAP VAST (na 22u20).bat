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
echo   Doe dit tussen 22u20 en 06u00 (onze tijd), dus op de avond
echo   van de beursdag zelf. Na 22u20 is de Amerikaanse beurs
echo   dicht en ligt de wisselkoers van de slotbel vast. Later
echo   dan 06u00 weigert het programma: dan is niet meer te zien
echo   dat er geen gunstig moment is gekozen.
echo.
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
