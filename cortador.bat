@echo off
rem Abre la ventana. Puedes arrastrar un video encima de este archivo.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Primero ejecuta instalar.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0cortar_gui.pyw" %*
