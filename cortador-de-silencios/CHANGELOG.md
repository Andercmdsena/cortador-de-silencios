# Changelog

## v1.0.0 — 2026-11-25

Primera versión pública.

- Cortes por voz con Silero VAD y exportación a DaVinci Resolve (.fcpxml), sin renderizar.
- Modos **Cortar** y **Limpiar voz** (gameplay); grabaciones de OBS con varias pistas sincronizadas.
- Bordes inteligentes: márgenes de inicio y final por separado que no incluyen clics, respiros
  ni resoplidos pegados a las frases; respiros entre frases opcionales.
- Pausas largas: quitarlas o acortarlas a X ms.
- Ventana con vista previa en vivo, cabezal arrastrable, reproducción continua con cortes u
  original, zoom, ajustes rápidos y panel de ayuda.
- Modo preciso con Whisper (corta al final de la última palabra).
- Marcadores de muletillas para DaVinci (.edl con colores): sonoras, de discurso, reinicios y
  palabras repetidas, ajustados a la ráfaga real de voz.
- Configuración y registro en %APPDATA%\CortadorDeSilencios; descarga automática del modelo
  de Whisper.
- Pruebas automáticas y compilación del .exe con GitHub Actions.
