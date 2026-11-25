@echo off
cd /d "%~dp0"
echo Corriendo las pruebas...
echo.
".venv\Scripts\python.exe" -m unittest discover -s pruebas -v
echo.
pause
