# PyInstaller: genera dist/CortadorDeSilencios/CortadorDeSilencios.exe (carpeta, no un solo
# archivo: arranca mucho más rápido). Uso: build.bat, o  pyinstaller --noconfirm cortador.spec
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = (
    collect_data_files("faster_whisper")      # silero_vad_v6.onnx (detector de voz)
    + collect_data_files("customtkinter")     # temas y fuentes de la interfaz
    # PortAudio (reproducción) lo agrega el hook de sounddevice de pyinstaller-hooks-contrib
    + [("LICENSE", "."), ("README.md", ".")]
)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")

a = Analysis(
    ["cortar_gui.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["cortar", "muletillas", "ayuda", "sounddevice", "_sounddevice_data"],
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CortadorDeSilencios",
    console=False,          # sin ventana negra
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="CortadorDeSilencios")
