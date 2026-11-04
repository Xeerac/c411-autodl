@echo off
REM Lance c411-autodl en continu (un passage toutes les 60 s).
REM Si le programme s'arrete (plantage, coupure reseau...), il est relance 30 s plus tard.
chcp 65001 >nul
cd /d "%~dp0"
:boucle
python c411_autodl.py --boucle 60
echo Programme arrete, relance dans 30 s (fermer la fenetre pour arreter)...
timeout /t 30 /nobreak >nul
goto boucle
