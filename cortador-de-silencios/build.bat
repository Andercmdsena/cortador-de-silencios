@echo off
rem Genera dist\CortadorDeSilencios-v1.0.0-windows.zip con el .exe listo para compartir.
rem Recomendado: Python 3.12 (el mismo que usa GitHub Actions).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta instalar.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m PyInstaller --noconfirm cortador.spec
if errorlevel 1 goto error
for /f %%v in ('".venv\Scripts\python.exe" -c "import cortar; print(cortar.__version__)"') do set VERSION=%%v
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\CortadorDeSilencios' -DestinationPath 'dist\CortadorDeSilencios-v%VERSION%-windows.zip'"
echo.
echo Listo: dist\CortadorDeSilencios\CortadorDeSilencios.exe
echo        dist\CortadorDeSilencios-v%VERSION%-windows.zip
pause
exit /b 0
:error
echo Fallo la compilacion.
pause
exit /b 1
