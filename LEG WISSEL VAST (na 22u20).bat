@echo off
chcp 65001 >nul
cd /d "%~dp0"
title StockWaakhond - wissel vastleggen
echo.
echo  ==========================================================
echo   STOCKWAAKHOND - de portefeuille laten wisselen
echo  ==========================================================
echo.
echo   Dit legt vast tegen welke koersen de portefeuille van de
echo   oude Top-5 naar de nieuwe wisselt. Er komt GEEN geld bij:
echo   wat de portefeuille op die dag waard is, wordt opnieuw
echo   verdeeld. Het gebeurt maar een keer per signaal en kan
echo   daarna niet meer wijzigen.
echo.
echo   Doe dit tussen 22u20 en 06u00 (onze tijd), dus op de avond
echo   van de beursdag na het nieuwe signaal. Na 22u20 is de
echo   Amerikaanse beurs dicht en ligt de wisselkoers van de
echo   slotbel vast. Later dan 06u00 weigert het programma: dan
echo   is niet meer te zien dat er geen gunstig moment is gekozen.
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

echo   Eerst alleen TONEN wat er zou gebeuren.
echo.
"%PY%" scripts\leg_herbalans_vast.py --toon

echo.
echo  ----------------------------------------------------------
echo   Ziet dat goed uit? Dan nu echt vastleggen.
echo   Wil je dat niet, sluit dan dit venster.
echo  ----------------------------------------------------------
pause

"%PY%" scripts\leg_herbalans_vast.py

echo.
echo  ----------------------------------------------------------
echo   Klaar. Je mag dit venster sluiten.
echo  ----------------------------------------------------------
pause
