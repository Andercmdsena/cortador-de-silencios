@echo off
rem Crea el entorno de Python (.venv) e instala las dependencias. Solo hace falta una vez.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul
if not errorlevel 1 set PY=py -3
if not exist ".venv\Scripts\python.exe" (
  echo Creando el entorno de Python...
  %PY% -m venv .venv
  if errorlevel 1 goto error
)
echo Instalando dependencias, puede tardar unos minutos...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo Listo. Abre el programa con cortador.bat
pause
exit /b 0
:error
echo.
echo No se pudo instalar. Revisa que tengas Python 3.10 o superior (python.org) e internet.
pause
exit /b 1
