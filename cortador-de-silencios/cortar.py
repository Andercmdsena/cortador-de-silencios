"""Cortador de Silencios — AI silence remover for DaVinci Resolve.

Detecta tu voz con IA (Silero VAD), quita los silencios y exporta una línea de
tiempo .fcpxml para DaVinci Resolve, sin volver a renderizar el video.

Para la ventana con controles y vista previa usa cortador.bat (o el .exe). Este
archivo es la versión de consola:
     python cortar.py "C:\\ruta\\grabacion.mp4" [opciones]

Opciones:
  --modo cortar       Quita los silencios de todas las pistas (el video queda más corto).
  --modo limpiar      No corta el video: solo deja tu voz en pedazos, con huecos
                      donde no hablas (útil en gameplay).
  --pista N           Número de la pista de audio de tu micrófono (1, 2, 3...).
  --elegir-pista      Vuelve a preguntar cuál es la pista del micrófono.
  --sensibilidad X    0.1 a 0.9. Más bajo = detecta voz más bajita (y más ruido).
  --margen-inicio MS  Colchón antes de cada frase, en milisegundos.
  --margen-final MS   Colchón después de cada frase (si suena brusco, súbelo).
  --silencio MS       Pausa mínima que se corta, en milisegundos.
  --acortar MS        En vez de quitar las pausas largas, las deja de MS milisegundos.
  --preciso           Usa Whisper para cortar al final de la última palabra
                      (más lento: minutos en vez de segundos).
  --muletillas        Exporta además un .edl con marcadores de muletillas
                      (eh, o sea, reinicios, palabras repetidas). Usa Whisper.

Genera junto a cada video un archivo .fcpxml. En DaVinci Resolve:
  Archivo > Importar > Línea de tiempo... y eliges ese archivo.
El video original nunca se modifica. Los valores por defecto se guardan en
config.json, en la carpeta de datos del usuario (%APPDATA%\\CortadorDeSilencios
en Windows).
"""
import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

import av
import numpy as np

__version__ = "1.0.0"
NOMBRE_APP = "Cortador de Silencios"

# Dónde está el programa: la carpeta del código o, en el .exe, la del ejecutable
CONGELADO = getattr(sys, "frozen", False)
BASE = Path(sys.executable).resolve().parent if CONGELADO else Path(__file__).resolve().parent


def carpeta_datos():
    """Configuración, registro y modelos van en la carpeta del usuario, no junto al
    programa: así funciona aunque se instale en una carpeta sin permisos de escritura."""
    if os.environ.get("CORTADOR_DATOS"):
        carpeta = Path(os.environ["CORTADOR_DATOS"])
    elif sys.platform == "win32":
        carpeta = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "CortadorDeSilencios"
    else:
        carpeta = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cortador-de-silencios"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
    except OSError:
        carpeta = Path.cwd()
    return carpeta


DATOS = carpeta_datos()
CONFIG = DATOS / "config.json"
LOG = DATOS / "cortador.log"


def modelo_whisper():
    """Modelo «small» de Whisper: uno ya descargado (variable CORTADOR_MODELO, carpeta
    modelo-small junto al programa o en la carpeta de datos) o, si no hay, el nombre
    «small» para que faster-whisper lo descargue la primera vez (~480 MB)."""
    candidatos = [os.environ.get("CORTADOR_MODELO"), BASE / "modelo-small", DATOS / "modelo-small"]
    for c in candidatos:
        if c and (Path(c) / "model.bin").exists():
            return str(c)
    return "small"
SR_VAD = 16000  # Silero VAD y Whisper trabajan a 16 kHz

DEFAULTS = {
    "modo": "cortar",
    "pista_voz": None,
    "sensibilidad": 0.5,
    "margen_inicio_ms": 200,
    "margen_final_ms": 350,
    "silencio_min_ms": 500,
    "voz_min_ms": 150,
    "limpiar_bordes": True,
    "quitar_respiros": True,
    "pausas": "cortar",
    "pausa_ms": 400,
    "modo_preciso": False,
    "margen_preciso_ms": 60,
    "marcar_muletillas": False,
    "marca_sonora": True,
    "marca_discurso": True,
    "marca_reinicio": True,
    "marca_repetida": True,
}
AYUDA = {
    "modo": "'cortar' (quita silencios de todo) o 'limpiar' (solo parte tu voz, el video sigue igual)",
    "pista_voz": "Número de la pista de audio del micrófono. null = preguntar.",
    "sensibilidad": "0.1 a 0.9. Si te corta frases dichas bajito, bájala (ej. 0.35).",
    "margen_inicio_ms": "Colchón antes de cada frase, en ms.",
    "margen_final_ms": "Colchón después de cada frase, en ms. Si el corte suena brusco, súbelo.",
    "silencio_min_ms": "Pausas más cortas que esto no se cortan.",
    "voz_min_ms": "Sonidos más cortos que esto se ignoran (clics, golpes).",
    "limpiar_bordes": "true = el margen no se extiende sobre clics o respiros pegados a una frase.",
    "quitar_respiros": "true = también corta los respiros en pausas cortas entre frases.",
    "pausas": "'cortar' (quita las pausas) o 'acortar' (las deja de pausa_ms). Solo en modo cortar.",
    "pausa_ms": "Duración que queda de cada pausa larga cuando pausas = 'acortar'.",
    "modo_preciso": "true = usa Whisper para cortar al final de la última palabra. Mucho más lento.",
    "margen_preciso_ms": "Silencio que se deja tras la última palabra en modo preciso.",
    "marcar_muletillas": "true = exporta también un .edl con marcadores de muletillas para DaVinci.",
    "marca_sonora": "Marcar eh, ehh, mmm...",
    "marca_discurso": "Marcar o sea, este..., bueno, pues...",
    "marca_reinicio": "Marcar frases empezadas y repetidas.",
    "marca_repetida": "Marcar palabras usadas 4 o más veces en 20 s.",
}
FPS_COMUNES = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001),
               Fraction(30), Fraction(50), Fraction(60000, 1001), Fraction(60),
               Fraction(120)]
NOMBRES_GENERICOS = {"", "soundhandler", "sound media handler", "core media audio"}


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def sin_avance(*_):
    pass


class Cancelado(Exception):
    """El usuario canceló una tarea larga (por ejemplo, el análisis con Whisper)."""


# ---------------------------------------------------------------- configuración

def cargar_config():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        try:
            guardado = json.loads(CONFIG.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in guardado.items() if k in DEFAULTS})
        except (OSError, ValueError) as e:
            print(f"Aviso: no pude leer {CONFIG.name} ({e}); uso los valores por defecto.")
    else:
        guardar_config(cfg)
    return cfg


def guardar_config(cfg):
    datos = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    datos["_ayuda"] = AYUDA
    CONFIG.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- lectura del archivo

def normalizar_fps(rate):
    """OBS reporta a veces 59.9999 en vez de 60; lo llevamos a la tasa estándar."""
    rate = Fraction(rate)
    comun = min(FPS_COMUNES, key=lambda f: abs(rate - f))
    if abs(rate - comun) / comun < Fraction(1, 200):
        return comun
    return Fraction(round(float(rate)))


def info_archivo(ruta):
    with av.open(str(ruta)) as c:
        if not c.streams.video:
            raise ValueError("El archivo no tiene video.")
        if not c.streams.audio:
            raise ValueError("El archivo no tiene pistas de audio.")
        v = c.streams.video[0]
        fps = normalizar_fps(v.average_rate or v.guessed_rate or 30)
        if c.duration:
            duracion = c.duration / av.time_base
        else:
            duracion = float(v.duration * v.time_base)
        pistas = []
        for s in c.streams.audio:
            titulo = (s.metadata.get("title") or s.metadata.get("handler_name") or "").strip()
            if titulo.lower() in NOMBRES_GENERICOS:
                titulo = ""
            pistas.append({"titulo": titulo,
                           "canales": s.codec_context.layout.nb_channels,
                           "rate": s.codec_context.sample_rate,
                           "layout": s.codec_context.layout.name})
        return {"fps": fps, "ancho": v.codec_context.width, "alto": v.codec_context.height,
                "duracion": float(duracion), "pistas": pistas}


def leer_audio_vad(ruta, indice, duracion, avance=sin_avance):
    """Decodifica solo la pista elegida y la deja en mono 16 kHz.
    avance(fraccion) recibe el progreso entre 0 y 1."""
    partes = []
    with av.open(str(ruta)) as c:
        s = c.streams.audio[indice]
        rs = av.AudioResampler(format="flt", layout="mono", rate=SR_VAD)
        for n, frame in enumerate(c.decode(s)):
            for f in rs.resample(frame):
                partes.append(f.to_ndarray().reshape(-1))
            if n % 200 == 0 and frame.time is not None and duracion:
                avance(min(frame.time / duracion, 1.0))
        for f in rs.resample(None):
            partes.append(f.to_ndarray().reshape(-1))
    avance(1.0)
    return np.concatenate(partes).astype(np.float32) if partes else np.zeros(0, np.float32)


def extraer_pista(ruta, indice, destino, pista):
    """Copia una pista de audio a WAV (sin pérdida). DaVinci no toma la 2.ª, 3.ª...
    pista de un video desde un FCPXML, así que se le entrega cada una como archivo."""
    if destino.exists() and destino.stat().st_mtime >= ruta.stat().st_mtime:
        return  # Ya extraída en una corrida anterior
    tmp = destino.with_suffix(".tmp.wav")
    with av.open(str(ruta)) as c, av.open(str(tmp), "w", format="wav") as out:
        s = c.streams.audio[indice]
        o = out.add_stream("pcm_s16le", rate=pista["rate"])
        o.layout = pista["layout"]
        rs = av.AudioResampler(format="s16", layout=pista["layout"], rate=pista["rate"])
        for frame in c.decode(s):
            frame.pts = None
            for f in rs.resample(frame):
                for p in o.encode(f):
                    out.mux(p)
        for f in rs.resample(None):
            for p in o.encode(f):
                out.mux(p)
        for p in o.encode(None):
            out.mux(p)
    tmp.replace(destino)


# ---------------------------------------------------------------- análisis (se hace una vez)

HOP = 160            # 10 ms a 16 kHz: resolución para afinar los bordes
VENTANA_VAD = 512    # Silero da una probabilidad cada 32 ms
VENTANA_R = 640      # 40 ms para medir si un sonido tiene tono (voz) o es soplo
SALTO_DB = 9.0       # Un sonido nuevo sube al menos esto sobre el silencio previo
PAUSA_RESPIRO = 8    # Pausa mínima (bloques de 32 ms = 256 ms) para buscar respiros
BORDE = 2            # Bloques de 10 ms de colchón al recortar ante un clic o respiro
MIN_ANTES = 640      # Siempre al menos 40 ms antes de la voz (en muestras)...
MIN_DESPUES = 960    # ...y 60 ms después, para no comerse el borde de una palabra
SONORO = 0.45        # Periodicidad mínima para considerar que un sonido tiene tono
COLA_MIN = 12        # Un soplo sin tono de 120 ms o más pegado a la frase = respiro
CENTROIDE_S = 4500   # Una "s" final es más aguda que esto; un respiro, más grave
CONSERVAR = 1280     # Se dejan 80 ms tras el último sonido con tono (en muestras)
HUECO_PALABRA = 5    # En modo preciso, 50 ms de silencio tras la palabra = terminó


class Analisis:
    """Todo lo que se calcula una sola vez por pista: la vista previa y el
    resultado final salen de aquí sin volver a leer el video."""

    def __init__(self, audio, avance=sin_avance):
        self.audio = audio
        self.muestras = len(audio)
        self.duracion = len(audio) / SR_VAD
        avance(0.05)
        self.energia = energia_db(audio)
        self.probs = probabilidades_vad(audio)
        avance(0.6)
        self.piso = piso_ruido(self.energia, self.probs)
        self.periodicidad, self.centroide = rasgos_vectorizados(
            audio, self.energia, self.piso, lambda x: avance(0.6 + 0.4 * x))
        self.palabras = None   # Lista de (inicio, fin) en segundos, si se usó Whisper

    def prob(self, muestra):
        i = min(max(muestra // VENTANA_VAD, 0), len(self.probs) - 1)
        return self.probs[i]


def energia_db(audio):
    """Volumen (dBFS) de cada bloque de 10 ms."""
    n = len(audio) // HOP
    bloques = audio[:n * HOP].reshape(n, HOP).astype(np.float64)
    return np.maximum(10 * np.log10((bloques ** 2).mean(axis=1) + 1e-12), -100.0)


def probabilidades_vad(audio):
    """Probabilidad de voz de Silero para cada bloque de 32 ms."""
    from faster_whisper.vad import get_vad_model
    relleno = (-len(audio)) % VENTANA_VAD
    x = np.pad(audio, (0, relleno)).astype(np.float32)
    return np.asarray(get_vad_model()(x)).reshape(-1)


def piso_ruido(energia, probs):
    """Volumen a partir del cual algo cuenta como sonido en esta grabación:
    un poco por encima del ruido de fondo del micrófono cuando no hablas."""
    idx = np.minimum(np.arange(len(energia)) * HOP // VENTANA_VAD, len(probs) - 1)
    fondo = energia[(probs[idx] < 0.2) & (energia > -95)]
    base = np.percentile(fondo, 10) if len(fondo) > 50 else -80.0
    return float(min(max(base + 18, -75.0), -45.0))


def rasgos_vectorizados(audio, energia, piso_db, avance=sin_avance):
    """Para cada bloque audible de 10 ms: periodicidad (la voz tiene tono, un
    respiro no) y centroide espectral (qué tan agudo es el sonido)."""
    n = len(energia)
    periodicidad = np.zeros(n, np.float32)
    centroide = np.zeros(n, np.float32)
    audibles = np.flatnonzero(energia > piso_db)
    if not len(audibles):
        return periodicidad, centroide
    x = np.pad(audio, (0, VENTANA_R)).astype(np.float32)
    hann = np.hanning(VENTANA_R).astype(np.float32)
    freqs = np.fft.rfftfreq(VENTANA_R, 1 / SR_VAD).astype(np.float32)
    lote = 4096
    for k in range(0, len(audibles), lote):
        idx = audibles[k:k + lote]
        bloques = x[idx[:, None] * HOP + np.arange(VENTANA_R)]
        bloques = bloques - bloques.mean(axis=1, keepdims=True)
        r = np.fft.irfft(np.abs(np.fft.rfft(bloques, 2 * VENTANA_R, axis=1)) ** 2,
                         axis=1)[:, :VENTANA_R]
        r0 = r[:, 0]
        periodicidad[idx] = np.where(r0 > 1e-12, r[:, 40:200].max(axis=1) / np.maximum(r0, 1e-12), 0)
        espectro = np.abs(np.fft.rfft(bloques * hann, axis=1))
        centroide[idx] = (espectro * freqs).sum(axis=1) / (espectro.sum(axis=1) + 1e-12)
        avance(min((k + lote) / len(audibles), 1.0))
    return periodicidad, centroide


def analizar_archivo(ruta, indice, duracion, avance=sin_avance):
    audio = leer_audio_vad(ruta, indice, duracion, lambda x: avance(0.5 * x))
    return Analisis(audio, lambda x: avance(0.5 + 0.5 * x))


# ---------------------------------------------------------------- segmentación (rápida)

def segmentos_vad(an, umbral, voz_min_ms, silencio_min_ms):
    """El mismo algoritmo de Silero (get_speech_timestamps), pero sobre las
    probabilidades ya calculadas: así se puede repetir al mover un ajuste."""
    neg = max(umbral - 0.15, 0.01)
    voz_min = voz_min_ms * SR_VAD // 1000
    silencio_min = silencio_min_ms * SR_VAD // 1000
    tramos, activo, inicio, fin_tentativo = [], False, 0, 0
    for i, p in enumerate(an.probs):
        pos = i * VENTANA_VAD
        if p >= umbral and fin_tentativo:
            fin_tentativo = 0
        if p >= umbral and not activo:
            activo, inicio = True, pos
            continue
        if p < neg and activo:
            if not fin_tentativo:
                fin_tentativo = pos
            if pos - fin_tentativo < silencio_min:
                continue
            if fin_tentativo - inicio > voz_min:
                tramos.append((inicio, fin_tentativo))
            activo, fin_tentativo = False, 0
    if activo and an.muestras - inicio > voz_min:
        tramos.append((inicio, an.muestras))
    return tramos


def extender(an, borde, limite, paso, umbral):
    """Avanza desde el borde de una frase hasta el límite del margen, pero se
    detiene si aparece un sonido nuevo que no es voz (clic, respiro, golpe):
    el volumen baja al terminar la frase y vuelve a subir de golpe."""
    energia = an.energia
    f = borde // HOP
    fin = limite // HOP
    piso = energia[min(max(f, 0), len(energia) - 1)]
    while (f < fin if paso > 0 else f > fin):
        f += paso
        if not 0 <= f < len(energia):
            break
        piso = min(piso, energia[f])
        if (energia[f] > max(piso + SALTO_DB, an.piso)
                and an.prob(f * HOP) < umbral
                and an.periodicidad[f] < SONORO):  # Con tono es voz, no un clic
            guardia = (f - paso * BORDE) * HOP
            return max(borde, guardia) if paso > 0 else min(borde, guardia + HOP)
    return limite


def hay_ruido(an, f0, f1):
    """¿Hay un sonido (respiro, clic) dentro de esta pausa? Ignora los bordes,
    que son la cola o el arranque de la voz."""
    f0, f1 = f0 + 6, f1 - 6
    if f1 - f0 < 3:
        return False
    tramo = an.energia[f0:f1]
    piso = np.minimum.accumulate(tramo)
    return bool(np.any(tramo > np.maximum(piso + SALTO_DB, an.piso)))


def partir_en_respiros(an, tramos, umbral):
    """Una pausa corta entre frases normalmente se deja (es el ritmo natural),
    pero si dentro hay un respiro o un clic, se parte la frase ahí."""
    salida = []
    probs = an.probs
    for ini, fin in tramos:
        c0, c1 = ini // VENTANA_VAD, -(-fin // VENTANA_VAD)
        actual, c = ini, c0
        while c < c1:
            if probs[c] < umbral:
                d = c
                while d < c1 and probs[d] < umbral:
                    d += 1
                if d - c >= PAUSA_RESPIRO and d < c1 and hay_ruido(
                        an, c * VENTANA_VAD // HOP, d * VENTANA_VAD // HOP):
                    salida.append((actual, c * VENTANA_VAD))
                    actual = d * VENTANA_VAD
                c = d
            else:
                c += 1
        salida.append((actual, fin))
    return salida


def con_tono(an, f):
    return an.energia[f] > an.piso + 10 and an.periodicidad[f] >= SONORO


def cortar_soplo(an, borde, limite, paso):
    """Busca un respiro pegado a la frase: desde el último (o primer) sonido con
    tono, un tramo sin tono, audible y grave de 120 ms o más. Si lo encuentra,
    devuelve dónde cortar; si no, None."""
    energia = an.energia
    f = borde // HOP + paso * 30          # Silero reacciona con hasta ~300 ms de retraso
    f_limite = limite // HOP
    sonoro = None
    while (f >= f_limite if paso > 0 else f <= f_limite):
        if 0 <= f < len(energia) and con_tono(an, f):
            sonoro = f
            break
        f -= paso
    if sonoro is None:
        return None
    soplo, centroides, quieto = 0, [], 0
    f = sonoro + paso
    while 0 <= f < len(energia) and quieto <= 5:   # Tolera huecos de hasta 50 ms
        if energia[f] <= an.piso:
            quieto += 1
        else:
            quieto = 0
            if con_tono(an, f):
                return None          # Vuelve a haber voz: no es un respiro
            soplo += 1
            centroides.append(an.centroide[f])
        f += paso
    if soplo < COLA_MIN or np.median(centroides) >= CENTROIDE_S:
        return None                  # Muy corto, o agudo como una "s" final
    return (sonoro + 1) * HOP + CONSERVAR if paso > 0 else max(0, sonoro * HOP - CONSERVAR)


def borde_real(an, borde, paso):
    """Silero avisa tarde (en bloques de 32 ms): la palabra suele empezar un poco
    antes de su marca y terminar un poco después. Corre el borde hasta el último
    sonido con tono que siga pegado a la frase (sin silencios de más de 50 ms)."""
    energia = an.energia
    f = borde // HOP
    real, quieto = f, 0
    for _ in range(30):                  # Hasta 300 ms
        f += paso
        if not 0 <= f < len(energia) or quieto > 5:
            break
        if energia[f] <= an.piso:
            quieto += 1
            continue
        quieto = 0
        if con_tono(an, f):
            real = f
    return real * HOP if paso < 0 else (real + 1) * HOP


def limpiar_bordes(an, tramos, cfg, umbral):
    antes = int(cfg["margen_inicio_ms"]) * SR_VAD // 1000
    despues = int(cfg["margen_final_ms"]) * SR_VAD // 1000
    nuevos = []
    for i, f in tramos:
        # 1) Respiro pegado a la frase (inhalar antes, exhalar después)
        ini = cortar_soplo(an, i, min(f, i + 4800), -1)
        fin = cortar_soplo(an, f, i, 1)
        # 2) Si no hay, el margen normal, que se detiene ante clics o golpes
        if ini is None:
            i = min(i, borde_real(an, i, -1))
            ini = min(extender(an, i, max(0, i - antes), -1, umbral), i - min(antes, MIN_ANTES))
        if fin is None:
            f = max(f, borde_real(an, f, 1))
            fin = max(extender(an, f, min(an.muestras, f + despues), 1, umbral),
                      f + min(despues, MIN_DESPUES))
        if fin > ini:
            nuevos.append((max(0, ini), min(an.muestras, fin)))
    return nuevos


def aplicar_palabras(an, tramos, cfg):
    """Modo preciso: Whisper sabe dónde están las palabras. Se descartan los
    tramos sin ninguna palabra (suspiros, risas, ruidos) y cada tramo termina
    donde se apaga la última palabra, aunque después venga un suspiro con tono.
    El inicio lo sigue decidiendo el análisis del sonido, porque Whisper ubica
    bien el final de las palabras pero no siempre el comienzo."""
    palabras = sorted(an.palabras)
    inicios = np.array([p[0] for p in palabras]) * SR_VAD
    finales = np.array([p[1] for p in palabras]) * SR_VAD
    margen = int(cfg["margen_preciso_ms"]) * SR_VAD // 1000 // HOP
    energia = an.energia
    nuevos = []
    for ini, fin in tramos:
        dentro = np.flatnonzero((inicios < fin) & (finales > ini))
        if not len(dentro):
            continue                     # Sin palabras: suspiro, risa o ruido
        ultima = dentro[-1]
        if finales[ultima] >= fin:
            nuevos.append((ini, fin))    # La palabra llega hasta el final: no se toca
            continue
        # Desde el final de la palabra, avanzar mientras siga sonando (la cola
        # de la palabra) hasta el primer silencio de 50 ms...
        f = int(finales[ultima]) // HOP
        quieto = 0
        while f < len(energia) and f * HOP < fin and quieto < HUECO_PALABRA:
            quieto = quieto + 1 if energia[f] <= an.piso + 10 else 0
            f += 1
        corte = f - quieto
        # ...y dejar el margen, pero solo sobre silencio, sin tomar lo que venga después
        extra = 0
        while (extra < margen and corte + extra < len(energia)
               and energia[corte + extra] <= an.piso + 10):
            extra += 1
        nuevos.append((ini, max(ini + HOP, min(fin, (corte + extra) * HOP))))
    return nuevos


def comprimir_pausas(an, tramos, pausa_ms):
    """En vez de quitar cada pausa larga, deja un pedacito de X ms de la parte
    más silenciosa de esa pausa: el ritmo del habla se conserva."""
    largo = pausa_ms * SR_VAD // 1000
    if largo <= 0 or len(tramos) < 2:
        return tramos
    salida = [tramos[0]]
    for siguiente in tramos[1:]:
        hueco_ini, hueco_fin = salida[-1][1], siguiente[0]
        if hueco_fin - hueco_ini > largo:
            f0, f1 = hueco_ini // HOP + 1, hueco_fin // HOP - 1
            n = largo // HOP
            if f1 - f0 > n:
                suma = np.convolve(an.energia[f0:f1], np.ones(n), mode="valid")
                mejor = f0 + int(np.argmin(suma))
                salida.append((mejor * HOP, mejor * HOP + largo))
        salida.append(siguiente)
    return salida


def unir(tramos):
    salida = []
    for i, f in sorted(tramos):
        if salida and i <= salida[-1][1]:
            salida[-1] = (salida[-1][0], max(salida[-1][1], f))
        else:
            salida.append((i, f))
    return salida


def segmentar(an, cfg, modo="cortar"):
    """Tramos que se conservan, en muestras de 16 kHz. Es rápido: se repite cada
    vez que se mueve un ajuste en la vista previa."""
    umbral = float(cfg["sensibilidad"])
    tramos = segmentos_vad(an, umbral, int(cfg["voz_min_ms"]), int(cfg["silencio_min_ms"]))
    if not tramos:
        return []
    if cfg.get("quitar_respiros", True):
        voz_min = int(cfg["voz_min_ms"]) * SR_VAD // 1000
        tramos = [t for t in partir_en_respiros(an, tramos, umbral) if t[1] - t[0] >= voz_min]
    if cfg.get("limpiar_bordes", True):
        tramos = limpiar_bordes(an, tramos, cfg, umbral)
    else:
        antes = int(cfg["margen_inicio_ms"]) * SR_VAD // 1000
        despues = int(cfg["margen_final_ms"]) * SR_VAD // 1000
        tramos = [(max(0, i - antes), min(an.muestras, f + despues)) for i, f in tramos]
    if cfg.get("modo_preciso") and an.palabras is not None:
        tramos = aplicar_palabras(an, tramos, cfg)
    tramos = unir(tramos)
    if modo == "cortar" and cfg.get("pausas") == "acortar":
        tramos = unir(comprimir_pausas(an, tramos, int(cfg["pausa_ms"])))
    return tramos


def a_frames(tramos, fps, total_frames):
    """Pasa los tramos de muestras a fotogramas del video, sin pisarse."""
    frames = []
    for i, f in tramos:
        ini = max(0, math.floor(Fraction(i, SR_VAD) * fps))
        fin = min(total_frames, math.ceil(Fraction(f, SR_VAD) * fps))
        if fin <= ini:
            continue
        if frames and ini <= frames[-1][1]:
            frames[-1] = (frames[-1][0], max(frames[-1][1], fin))
        else:
            frames.append((ini, fin))
    return frames


def detectar_voz(audio, cfg, fps, total_frames, modo="cortar"):
    """Atajo: analiza y segmenta un audio de 16 kHz. Devuelve fotogramas."""
    return a_frames(segmentar(Analisis(audio), cfg, modo), fps, total_frames)


# ---------------------------------------------------------------- Whisper (modo preciso)

def ruta_cache_palabras(ruta, indice):
    return ruta.with_name(f"{ruta.stem}_pistas") / f"{ruta.stem}_palabras_pista{indice + 1}.json"


def cargar_palabras(ruta, indice, con_texto=False):
    """Palabras guardadas de una corrida anterior (si el video no cambió).
    con_texto=True exige la versión con el texto de cada palabra (para las
    muletillas); las cachés viejas solo tienen tiempos."""
    cache = ruta_cache_palabras(ruta, indice)
    try:
        datos = json.loads(cache.read_text(encoding="utf-8"))
        st = ruta.stat()
        if datos.get("tamano") == st.st_size and datos.get("mtime") == int(st.st_mtime):
            palabras = [tuple(p) for p in datos["palabras"]]
            if con_texto and (not palabras or len(palabras[0]) < 3):
                return None
            return palabras
    except (OSError, ValueError, KeyError):
        pass
    return None


def guardar_palabras(ruta, indice, palabras):
    cache = ruta_cache_palabras(ruta, indice)
    cache.parent.mkdir(exist_ok=True)
    st = ruta.stat()
    cache.write_text(json.dumps({"version": 2, "tamano": st.st_size, "mtime": int(st.st_mtime),
                                 "palabras": palabras}, ensure_ascii=False), encoding="utf-8")


def transcribir_palabras(audio, avance=sin_avance, cancelado=lambda: False):
    """Ubica cada palabra con Whisper (modelo small, en CPU). Es la parte lenta:
    puede tardar minutos en un video largo. Devuelve (inicio, fin, texto).
    La pista inicial con muletillas hace que Whisper las escriba en vez de
    "limpiarlas" del texto."""
    from faster_whisper import WhisperModel
    from muletillas import PROMPT_MULETILLAS
    whisper = WhisperModel(modelo_whisper(), device="cpu", compute_type="int8",
                           cpu_threads=os.cpu_count() or 4,
                           download_root=str(DATOS / "modelos"))
    duracion = len(audio) / SR_VAD
    segmentos, _ = whisper.transcribe(audio, language="es", word_timestamps=True,
                                      vad_filter=True, beam_size=1,
                                      condition_on_previous_text=False,
                                      initial_prompt=PROMPT_MULETILLAS)
    palabras = []
    for s in segmentos:
        if cancelado():
            raise Cancelado()
        palabras.extend((round(w.start, 3), round(w.end, 3), w.word.strip()) for w in (s.words or []))
        avance(min(s.end / duracion, 1.0) if duracion else 1.0)
    avance(1.0)
    return palabras


def obtener_palabras(ruta, indice, an, avance=sin_avance, cancelado=lambda: False, con_texto=True):
    palabras = cargar_palabras(ruta, indice, con_texto)
    if palabras is None:
        palabras = transcribir_palabras(an.audio, avance, cancelado)
        guardar_palabras(ruta, indice, palabras)
    an.palabras = palabras
    return palabras


# ---------------------------------------------------------------- marcas de muletillas

def tipos_activos(cfg):
    return {t for t in ("sonora", "discurso", "reinicio", "repetida") if cfg.get(f"marca_{t}", True)}


def detectar_marcas(an):
    """Marcas de muletillas (en segundos del audio original), con el inicio
    ajustado al sonido real. Necesita an.palabras con texto."""
    import muletillas
    if not an.palabras or len(an.palabras[0]) < 3:
        return []
    palabras = sorted(an.palabras)
    return muletillas.ajustar(an, palabras, muletillas.detectar(palabras))


def marcas_en_linea(marcas, mantener, fps, modo):
    """Pasa cada marca del audio original a la línea de tiempo exportada.
    En modo cortar, la línea es la suma de los tramos conservados; una marca que
    cae en una parte quitada se omite. Devuelve (fotograma, duración, marca)."""
    salida = []
    for m in marcas:
        f = int(Fraction(m["inicio"]).limit_denominator(1000) * fps)
        dur = max(1, round((m["fin"] - m["inicio"]) * float(fps)))
        if modo != "cortar":
            salida.append((f, dur, m))
            continue
        pos = 0
        for ini, fin in mantener:
            if ini <= f < fin:
                salida.append((pos + f - ini, min(dur, fin - f), m))
                break
            pos += fin - ini
    return salida


def timecode(f, fps):
    base = round(fps)
    h, r = divmod(f, 3600 * base)
    m, r = divmod(r, 60 * base)
    s, fr = divmod(r, base)
    return f"{h:02d}:{m:02d}:{s:02d}:{fr:02d}"


def generar_edl(marcas_linea, fps, destino):
    """Marcadores de línea de tiempo en el formato EDL que DaVinci importa
    (con color y duración). DaVinci ignora los marcadores dentro del FCPXML."""
    import muletillas
    lineas = ["TITLE: Muletillas", "FCM: NON-DROP FRAME", ""]
    for n, (f, dur, m) in enumerate(sorted(marcas_linea, key=lambda x: x[0]), start=1):
        nombre, color, _ = muletillas.TIPOS[m["tipo"]]
        texto = f"{nombre}: {m['texto']}"
        if m["tipo"] == "repetida" or m["tipo"] == "reinicio":
            texto += f" — {m['detalle']}"
        texto = texto.replace("|", "/")
        lineas.append(f"{n:03d}  001      V     C        {timecode(f, fps)} {timecode(f + 1, fps)} "
                      f"{timecode(f, fps)} {timecode(f + 1, fps)}  ")
        lineas.append(f" |C:{color} |M:{texto} |D:{dur}")
        lineas.append("")
    with open(destino, "w", encoding="utf-8", newline="") as f:   # \r\n tal cual, también en Windows
        f.write("\r\n".join(lineas) + "\r\n")


# ---------------------------------------------------------------- FCPXML

def generar_fcpxml(ruta, info, mantener, modo, indice_voz, wavs, destino):
    """Arma la línea de tiempo. Sigue la misma estructura que auto-editor usa
    para DaVinci: las pistas extra van primero en el spine y DaVinci las pone
    en pistas de audio separadas."""
    fps = info["fps"]
    total = round(info["duracion"] * fps)

    def t(frames):
        if frames == 0:
            return "0s"
        # Sin simplificar (ej. 356/60s), como lo escribe auto-editor para DaVinci
        return f"{frames * fps.denominator}/{fps.numerator}s"

    def formato(rid):
        return ET.Element("format", id=rid, name="FFVideoFormatRateUndefined",
                          frameDuration=t(1), width=str(info["ancho"]),
                          height=str(info["alto"]), colorSpace="1-1-1 (Rec. 709)")

    raiz = ET.Element("fcpxml", version="1.11")
    recursos = ET.SubElement(raiz, "resources")

    def agregar_asset(n, nombre, archivo, con_video, canales):
        rf, ra = f"r{2 * n + 1}", f"r{2 * n + 2}"
        recursos.append(formato(rf))
        asset = ET.SubElement(recursos, "asset", id=ra, name=nombre, start="0s",
                              duration=t(total), hasVideo="1" if con_video else "0",
                              hasAudio="1", audioSources="1", audioChannels=str(canales),
                              format=rf)
        ET.SubElement(asset, "media-rep", kind="original-media", src=archivo.resolve().as_uri())
        return ra

    nombre = ruta.stem
    ref_video = agregar_asset(0, nombre, ruta, True, info["pistas"][0]["canales"])
    refs_extra = {}
    for n, (indice, wav) in enumerate(sorted(wavs.items()), start=1):
        refs_extra[indice] = agregar_asset(n, wav.stem, wav, False, info["pistas"][indice]["canales"])

    sufijo = "cortado" if modo == "cortar" else "voz limpia"
    lib = ET.SubElement(raiz, "library")
    evento = ET.SubElement(lib, "event", name="Cortador de silencios")
    proyecto = ET.SubElement(evento, "project", name=f"{nombre} ({sufijo})")
    secuencia = ET.SubElement(proyecto, "sequence", format="r1", tcStart="0s", tcFormat="NDF",
                              audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(secuencia, "spine")

    def clip(ref, offset, inicio, dur, nombre_clip):
        ET.SubElement(spine, "asset-clip", ref=ref, name=nombre_clip, offset=t(offset),
                      start=t(inicio), duration=t(dur), tcFormat="NDF")

    def cortes_en_secuencia(ref, nombre_clip):
        pos = 0
        for ini, fin in mantener:
            clip(ref, pos, ini, fin - ini, nombre_clip)
            pos += fin - ini

    # Pistas extra (de la última a la 2.ª), luego el video con la pista 1
    for indice in sorted(refs_extra, reverse=True):
        ref, nombre_clip = refs_extra[indice], wavs[indice].stem
        if modo == "cortar":
            cortes_en_secuencia(ref, nombre_clip)
        elif indice == indice_voz:  # limpiar: voz en pedazos, en su sitio original
            for ini, fin in mantener:
                clip(ref, ini, ini, fin - ini, nombre_clip)
        else:  # limpiar: las demás pistas completas
            clip(ref, 0, 0, total, nombre_clip)

    if modo == "cortar":
        cortes_en_secuencia(ref_video, nombre)
    else:
        clip(ref_video, 0, 0, total, nombre)

    ET.indent(raiz)
    ET.ElementTree(raiz).write(destino, encoding="utf-8", xml_declaration=True)


def exportar(ruta, info, mantener, modo, indice_voz, avance=sin_avance, marcas=None):
    """Extrae las pistas extra a WAV (si hace falta) y escribe el .fcpxml.
    Con marcas, escribe además un .edl con los marcadores de muletillas."""
    if modo == "limpiar" and indice_voz == 0:
        raise ValueError("El modo 'limpiar' necesita la voz en una pista distinta de la 1 "
                         "(ej. gameplay con micrófono aparte). Para este video usa el modo cortar.")
    wavs = {}
    extra = range(1, len(info["pistas"]))
    if len(info["pistas"]) > 1:
        carpeta = ruta.with_name(f"{ruta.stem}_pistas")
        carpeta.mkdir(exist_ok=True)
        for n, i in enumerate(extra):
            wav = carpeta / f"{ruta.stem}_pista{i + 1}.wav"
            extraer_pista(ruta, i, wav, info["pistas"][i])
            wavs[i] = wav
            avance((n + 1) / len(extra))
    sufijo = "cortado" if modo == "cortar" else "voz_limpia"
    destino = ruta.with_name(f"{ruta.stem}_{sufijo}.fcpxml")
    generar_fcpxml(ruta, info, mantener, modo, indice_voz, wavs, destino)
    edl = destino.with_name(f"{ruta.stem}_{sufijo}_marcadores.edl")
    if marcas:
        generar_edl(marcas_en_linea(marcas, mantener, info["fps"], modo), info["fps"], edl)
    return destino


# ---------------------------------------------------------------- flujo de consola

def elegir_pista(info, cfg, args):
    pistas = info["pistas"]
    if len(pistas) == 1:
        return 0
    if args.pista:
        if not 1 <= args.pista <= len(pistas):
            raise ValueError(f"La pista {args.pista} no existe; el archivo tiene {len(pistas)}.")
        return args.pista - 1
    guardada = cfg.get("pista_voz")
    if guardada and not args.elegir_pista and 1 <= guardada <= len(pistas):
        print(f"  Pista del micrófono: {guardada} (guardada; usa --elegir-pista para cambiarla)")
        return guardada - 1

    print("\n  Este video tiene varias pistas de audio:")
    for i, p in enumerate(pistas, start=1):
        titulo = f'"{p["titulo"]}"' if p["titulo"] else "(sin nombre)"
        print(f"    {i}. {titulo}  {p['canales']} canal(es), {p['rate']} Hz")
    sugerida = guardada if guardada and 1 <= guardada <= len(pistas) else 2
    while True:
        r = input(f"  ¿Cuál es tu micrófono? [{sugerida}]: ").strip() or str(sugerida)
        if r.isdigit() and 1 <= int(r) <= len(pistas):
            cfg["pista_voz"] = int(r)
            guardado = cargar_config()  # Sin los cambios de --modo, --margen...
            guardado["pista_voz"] = int(r)
            guardar_config(guardado)
            print(f"  Guardado. La próxima vez uso la pista {r} sin preguntar.")
            return int(r) - 1
        print("  Número no válido.")


def mmss(segundos):
    m, s = divmod(int(round(segundos)), 60)
    return f"{m // 60}:{m % 60:02d}:{s:02d}" if m >= 60 else f"{m}:{s:02d}"


def barra(texto):
    ultimo = [-1]

    def avance(x):
        pct = int(x * 100) // 10 * 10
        if pct > ultimo[0]:
            ultimo[0] = pct
            print(f"\r  {texto}... {pct}%", end="" if pct < 100 else "\n", flush=True)
    return avance


def procesar(ruta, cfg, elegir):
    """elegir(info) devuelve el índice (desde 0) de la pista del micrófono."""
    inicio = time.time()
    print(f"\n=== {ruta.name} ===")
    info = info_archivo(ruta)
    fps = info["fps"]
    total = round(info["duracion"] * fps)
    print(f"  {info['ancho']}x{info['alto']} a {float(fps):.2f} fps, {mmss(info['duracion'])}, "
          f"{len(info['pistas'])} pista(s) de audio")

    modo = cfg["modo"]
    if modo not in ("cortar", "limpiar"):
        raise ValueError(f"Modo desconocido: {modo!r} (usa 'cortar' o 'limpiar').")
    indice_voz = elegir(info)
    if modo == "limpiar" and indice_voz == 0:
        raise ValueError("El modo 'limpiar' necesita la voz en una pista distinta de la 1 "
                         "(ej. gameplay con micrófono aparte). Para este video usa --modo cortar.")

    an = analizar_archivo(ruta, indice_voz, info["duracion"], barra("Analizando audio"))
    if cfg.get("modo_preciso") or cfg.get("marcar_muletillas"):
        print("  Whisper: ubicando palabras (puede tardar minutos)...")
        obtener_palabras(ruta, indice_voz, an, barra("Whisper"),
                         con_texto=bool(cfg.get("marcar_muletillas")))
    mantener = a_frames(segmentar(an, cfg, modo), fps, total)
    if not mantener:
        raise ValueError("No detecté voz en esa pista. ¿Es la del micrófono? "
                         "Prueba --elegir-pista o baja la sensibilidad.")
    if len(info["pistas"]) > 1:
        print("  Extrayendo pistas de audio a WAV...")
    marcas = None
    if cfg.get("marcar_muletillas"):
        tipos = tipos_activos(cfg)
        marcas = [m for m in detectar_marcas(an) if m["tipo"] in tipos]
        print(f"  {len(marcas)} marcas de muletillas.")
    destino = exportar(ruta, info, mantener, modo, indice_voz, marcas=marcas)

    con_voz = sum(f - i for i, f in mantener) / fps
    print(f"\n  Listo en {time.time() - inicio:.0f} s -> {destino.name}")
    if modo == "cortar":
        quitado = info["duracion"] - float(con_voz)
        print(f"  Duración: {mmss(info['duracion'])} -> {mmss(float(con_voz))} "
              f"(se quitan {mmss(quitado)}, {quitado / info['duracion']:.0%}) en {len(mantener)} tramos")
    else:
        print(f"  Tu voz quedó en {len(mantener)} tramos; el video conserva su duración.")
    log(f"{ruta} modo={modo} pista={indice_voz + 1} tramos={len(mantener)} "
        f"voz={float(con_voz):.1f}s/{info['duracion']:.1f}s preciso={bool(cfg.get('modo_preciso'))}")
    return destino


def main():
    p = argparse.ArgumentParser(description=f"{NOMBRE_APP} {__version__}: silencios fuera con IA, "
                                            "línea de tiempo para DaVinci Resolve.")
    p.add_argument("--version", action="version", version=f"{NOMBRE_APP} {__version__}")
    p.add_argument("archivos", nargs="*", type=Path)
    p.add_argument("--modo", choices=["cortar", "limpiar"])
    p.add_argument("--pista", type=int)
    p.add_argument("--elegir-pista", action="store_true")
    p.add_argument("--sensibilidad", type=float)
    p.add_argument("--margen-inicio", type=int, dest="margen_inicio_ms")
    p.add_argument("--margen-final", type=int, dest="margen_final_ms")
    p.add_argument("--silencio", type=int, dest="silencio_min_ms")
    p.add_argument("--acortar", type=int, metavar="MS")
    p.add_argument("--preciso", action="store_true")
    p.add_argument("--muletillas", action="store_true")
    args = p.parse_args()

    if not args.archivos:
        print(__doc__)
        print(f"Versión {__version__} · configuración y registro en {DATOS}")
        return 1

    cfg = cargar_config()
    for clave in ("modo", "sensibilidad", "margen_inicio_ms", "margen_final_ms",
                  "silencio_min_ms"):
        if getattr(args, clave) is not None:
            cfg[clave] = getattr(args, clave)  # Solo para esta corrida
    if args.acortar is not None:
        cfg["pausas"], cfg["pausa_ms"] = "acortar", args.acortar
    if args.preciso:
        cfg["modo_preciso"] = True
    if args.muletillas:
        cfg["marcar_muletillas"] = True

    errores = 0
    for ruta in args.archivos:
        try:
            procesar(ruta.resolve(), cfg, lambda info: elegir_pista(info, cfg, args))
        except Exception as e:
            errores += 1
            print(f"\n  ERROR con {ruta.name}: {e}")
            log(f"{ruta}\n{traceback.format_exc()}")

    if errores == 0:
        print("\nEn DaVinci: Archivo > Importar > Línea de tiempo... y eliges el .fcpxml")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
