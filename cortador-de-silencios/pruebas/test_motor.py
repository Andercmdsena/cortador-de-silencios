"""Pruebas automáticas del motor de detección y del FCPXML.

Cómo correrlas: probar.bat (o: python -m unittest discover -s pruebas -v)

Hay dos tipos:
- Sintéticas: no necesitan nada, siempre corren (también en GitHub Actions).
- De referencia: usan grabaciones reales del autor (prueba de estrés, gameplay y
  muletillas) y comparan con los cortes aprobados (referencia.json, solo tiempos).
  El audio no está en el repositorio: si no se encuentra, estas pruebas se saltan.
  La carpeta de videos se cambia con la variable CORTADOR_VIDEOS; las palabras
  transcritas del video de muletillas van en pruebas/locales/ (ignorada por git).

Si cambias el motor A PROPÓSITO y los nuevos cortes te gustan, regenera la referencia:
  python pruebas/test_motor.py --regenerar
"""
import json
import os
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import cortar  # noqa: E402

SR = cortar.SR_VAD
REFERENCIA = AQUI / "referencia.json"
TOLERANCIA = 0.07         # 70 ms (2 bloques de Silero + margen): otras versiones de PyAV u onnxruntime remuestrean distinto
VIDEOS = Path(os.environ.get("CORTADOR_VIDEOS", Path.home() / "Videos"))

# Casos de referencia: nombre -> (wav de la pista del micrófono, palabras de Whisper o None)
CASOS = {
    "estres": ("2026-11-24 18-46-37_pistas/2026-11-24 18-46-37_pista2.wav",
               "2026-11-24 18-46-37_pistas/2026-11-24 18-46-37_palabras_pista2.json"),
    "gameplay": ("2026-11-24 18-38-54_pistas/2026-11-24 18-38-54_pista2.wav", None),
}
VARIANTES = {
    "normal": ({}, "cortar"),
    "limpiar": ({}, "limpiar"),
    "acortar": ({"pausas": "acortar", "pausa_ms": 400}, "cortar"),
    "sin_limpieza": ({"limpiar_bordes": False, "quitar_respiros": False}, "cortar"),
    "preciso": ({"modo_preciso": True}, "cortar"),
}
_analisis = {}


def analisis_de(caso):
    """Analiza una grabación de referencia (una sola vez por corrida)."""
    if caso not in _analisis:
        wav, palabras = CASOS[caso]
        ruta = VIDEOS / wav
        if not ruta.exists():
            _analisis[caso] = None
        else:
            audio = cortar.leer_audio_vad(ruta, 0, 0)
            an = cortar.Analisis(audio)
            if palabras and (VIDEOS / palabras).exists():
                datos = json.loads((VIDEOS / palabras).read_text(encoding="utf-8"))
                an.palabras = [tuple(p) for p in datos["palabras"]]
            _analisis[caso] = an
    return _analisis[caso]


def calcular(an, variante):
    cambios, modo = VARIANTES[variante]
    if cambios.get("modo_preciso") and an.palabras is None:
        return None
    cfg = dict(cortar.DEFAULTS)
    cfg.update(cambios)
    return [[round(i / SR, 4), round(f / SR, 4)] for i, f in cortar.segmentar(an, cfg, modo)]


def voz_justo_afuera(an, tramos, margen=6):
    """Bloques de 10 ms con voz (tono y volumen) pegados por fuera de un corte."""
    malos = []
    for i, f in tramos:
        s0, s1 = int(i * 100), int(f * 100)
        for k in list(range(max(0, s0 - margen), s0)) + list(range(s1, min(len(an.energia), s1 + margen))):
            if cortar.con_tono(an, k) and an.prob(k * cortar.HOP) >= 0.5:
                malos.append(round(k / 100, 2))
    return malos


class Sinteticas(unittest.TestCase):
    """No dependen de ninguna grabación."""

    @classmethod
    def setUpClass(cls):
        # 6 s: tono "vocal" con armónicos, 2 s de silencio, otro tramo, ruido suave al final
        t = np.arange(SR * 6) / SR
        voz = 0.2 * sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((150, 300, 450, 600), 1))
        voz *= 1 + 0.5 * np.sin(2 * np.pi * 4 * t)          # sílabas
        audio = np.zeros(SR * 6, np.float32)
        audio[SR // 2:SR * 2] = voz[SR // 2:SR * 2]
        audio[SR * 4:int(SR * 5.5)] = voz[SR * 4:int(SR * 5.5)]
        cls.audio = audio.astype(np.float32)

    def test_a_frames_une_y_limita(self):
        fps = Fraction(60)
        tramos = [(0, SR), (SR - 100, 2 * SR), (3 * SR, 10 * SR)]
        frames = cortar.a_frames(tramos, fps, total_frames=300)
        self.assertEqual(frames, [(0, 120), (180, 300)])

    def test_comprimir_pausas(self):
        an = cortar.Analisis(self.audio)
        tramos = [(SR // 2, 2 * SR), (4 * SR, int(5.5 * SR))]
        salida = cortar.comprimir_pausas(an, tramos, 400)
        self.assertEqual(len(salida), 3)
        pausa = salida[1]
        self.assertEqual(pausa[1] - pausa[0], 400 * SR // 1000)
        self.assertTrue(2 * SR <= pausa[0] and pausa[1] <= 4 * SR)
        # Pausas más cortas que el valor no se tocan
        self.assertEqual(cortar.comprimir_pausas(an, tramos, 3000), tramos)

    def test_preciso_descarta_tramos_sin_palabras(self):
        an = cortar.Analisis(self.audio)
        an.palabras = [(0.6, 1.0), (1.0, 1.8)]           # Solo el primer tramo tiene palabras
        cfg = dict(cortar.DEFAULTS, modo_preciso=True)
        tramos = cortar.aplicar_palabras(an, [(SR // 2, 2 * SR), (4 * SR, int(5.5 * SR))], cfg)
        self.assertEqual(len(tramos), 1)
        self.assertLessEqual(tramos[0][1], 2 * SR)

    def test_fcpxml_cortar_sincroniza_todas_las_pistas(self):
        info = {"fps": Fraction(60), "ancho": 1920, "alto": 1080, "duracion": 10.0,
                "pistas": [{"canales": 2}, {"canales": 2}, {"canales": 1}]}
        mantener = [(0, 60), (120, 300), (400, 600)]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "v.mp4"
            video.write_bytes(b"")
            wavs = {1: tmp / "p2.wav", 2: tmp / "p3.wav"}
            destino = tmp / "v.fcpxml"
            cortar.generar_fcpxml(video, info, mantener, "cortar", 1, wavs, destino)
            raiz = ET.parse(destino).getroot()
        clips = {}
        for c in raiz.iter("asset-clip"):
            clips.setdefault(c.get("ref"), []).append((c.get("offset"), c.get("start"), c.get("duration")))
        self.assertEqual(len(clips), 3)
        listas = list(clips.values())
        self.assertTrue(all(lst == listas[0] for lst in listas), "Las pistas no quedaron iguales")
        self.assertEqual(listas[0][1], ("60/60s", "120/60s", "180/60s"))

    def test_fcpxml_limpiar_deja_la_voz_en_su_sitio(self):
        info = {"fps": Fraction(30), "ancho": 1280, "alto": 720, "duracion": 10.0,
                "pistas": [{"canales": 2}, {"canales": 1}]}
        mantener = [(30, 60), (90, 150)]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "v.mp4"
            video.write_bytes(b"")
            destino = tmp / "v.fcpxml"
            cortar.generar_fcpxml(video, info, mantener, "limpiar", 1, {1: tmp / "p2.wav"}, destino)
            raiz = ET.parse(destino).getroot()
        voz = [c for c in raiz.iter("asset-clip") if c.get("ref") == "r4"]
        video_clips = [c for c in raiz.iter("asset-clip") if c.get("ref") == "r2"]
        self.assertEqual([(c.get("offset"), c.get("start")) for c in voz],
                         [("30/30s", "30/30s"), ("90/30s", "90/30s")])
        self.assertEqual(len(video_clips), 1)
        self.assertEqual(video_clips[0].get("duration"), "300/30s")


class Referencia(unittest.TestCase):
    """Compara con los cortes de tus grabaciones que ya revisaste en DaVinci."""

    @classmethod
    def setUpClass(cls):
        if not REFERENCIA.exists():
            raise unittest.SkipTest("No hay referencia.json (corre con --regenerar).")
        cls.ref = json.loads(REFERENCIA.read_text(encoding="utf-8"))

    def comparar(self, caso, variante):
        an = analisis_de(caso)
        if an is None:
            self.skipTest(f"No encuentro la grabación de '{caso}' en {VIDEOS}")
        esperado = self.ref.get(caso, {}).get(variante)
        obtenido = calcular(an, variante)
        if esperado is None or obtenido is None:
            self.skipTest(f"Sin datos para {caso}/{variante}")
        self.assertEqual(len(obtenido), len(esperado),
                         f"{caso}/{variante}: {len(obtenido)} tramos en vez de {len(esperado)}")
        for (a, b), (c, d) in zip(obtenido, esperado):
            self.assertAlmostEqual(a, c, delta=TOLERANCIA, msg=f"{caso}/{variante}: inicio {a} vs {c}")
            self.assertAlmostEqual(b, d, delta=TOLERANCIA, msg=f"{caso}/{variante}: final {b} vs {d}")

    def test_vad_igual_a_silero(self):
        """Nuestra segmentación sobre probabilidades guardadas = la de faster-whisper."""
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        for caso in CASOS:
            an = analisis_de(caso)
            if an is None:
                continue
            for umbral, silencio in ((0.5, 500), (0.35, 300)):
                ref = [(x["start"], x["end"]) for x in get_speech_timestamps(
                    an.audio, VadOptions(threshold=umbral, min_speech_duration_ms=150,
                                         min_silence_duration_ms=silencio, speech_pad_ms=0))]
                self.assertEqual(cortar.segmentos_vad(an, umbral, 150, silencio), ref, caso)

    def test_estres_normal(self):
        self.comparar("estres", "normal")

    def test_estres_limpiar(self):
        self.comparar("estres", "limpiar")

    def test_estres_acortar(self):
        self.comparar("estres", "acortar")

    def test_estres_sin_limpieza(self):
        self.comparar("estres", "sin_limpieza")

    def test_estres_preciso(self):
        self.comparar("estres", "preciso")

    def test_gameplay_normal(self):
        self.comparar("gameplay", "normal")

    def test_gameplay_limpiar(self):
        self.comparar("gameplay", "limpiar")

    def test_gameplay_acortar(self):
        self.comparar("gameplay", "acortar")

    def test_estres_respiros_y_suspiro(self):
        """Los casos que revisaste a oído: clic de 19.4 s, respiro nasal de 16.6–17.2 s
        y, en modo preciso, el suspiro con tono de 13.16 s quedan fuera."""
        an = analisis_de("estres")
        if an is None:
            self.skipTest("Falta la grabación de estrés")
        normal = calcular(an, "normal")
        dentro = lambda t, tramos: any(a <= t <= b for a, b in tramos)  # noqa: E731
        self.assertFalse(dentro(19.4, normal), "Se coló el clic de 19.4 s")
        self.assertFalse(dentro(16.9, normal), "Se coló el respiro nasal")
        preciso = calcular(an, "preciso")
        if preciso is not None:
            self.assertFalse(dentro(13.25, preciso), "Se coló el suspiro de 13.16 s")

    def test_ningun_corte_se_come_voz(self):
        """Ningún borde de corte deja voz con tono justo por fuera (palabras mochadas)."""
        for caso in CASOS:
            an = analisis_de(caso)
            if an is None:
                continue
            malos = voz_justo_afuera(an, calcular(an, "normal"))
            self.assertLessEqual(len(malos), 2, f"{caso}: voz pegada fuera del corte en {malos}")


class MuletillasSinteticas(unittest.TestCase):
    """Detección sobre una transcripción inventada (no necesita audio)."""

    PALABRAS = [
        (0.0, 0.3, "Hola,"), (0.4, 0.7, "eh,"), (1.0, 1.2, "esto"), (1.2, 1.4, "es"),
        (1.4, 1.7, "una..."), (2.2, 2.4, "es"), (2.4, 2.6, "una"), (2.6, 3.1, "prueba."),
        (3.5, 3.7, "O"), (3.7, 3.9, "sea,"), (4.0, 4.2, "este"), (4.2, 4.7, "programa"),
        (4.7, 4.9, "corta"), (4.9, 5.3, "silencios."), (5.8, 6.1, "Este,"), (6.4, 6.9, "mmm,"),
        (7.0, 7.6, "básicamente"), (7.6, 7.8, "funciona."), (8.0, 8.6, "Básicamente"),
        (8.6, 8.9, "rápido,"), (9.0, 9.6, "básicamente"), (9.6, 9.9, "fácil"), (10.0, 10.2, "y"),
        (10.2, 10.8, "básicamente"), (10.8, 11.2, "gratis,"), (11.3, 11.5, "¿no?"),
    ]

    def test_tipos(self):
        import muletillas
        marcas = muletillas.detectar(self.PALABRAS)
        por_tipo = {}
        for m in marcas:
            por_tipo.setdefault(m["tipo"], []).append(m["texto"].lower())
        self.assertEqual(sorted(por_tipo["sonora"]), ["eh", "mmm"])
        self.assertEqual(por_tipo["reinicio"], ["es una"])
        self.assertIn("o sea", por_tipo["discurso"])
        self.assertIn("este", por_tipo["discurso"])           # «Este,» con coma sí
        self.assertEqual(len(por_tipo["repetida"]), 4)         # «básicamente» ×4
        textos = [m["texto"].lower() for m in marcas]
        self.assertEqual(textos.count("este"), 1, "«este programa» no es muletilla")


class Muletillas(unittest.TestCase):
    """Detección con el video de muletillas del autor (se salta si no está)."""

    @classmethod
    def setUpClass(cls):
        import muletillas
        cls.m = muletillas
        archivo = AQUI / "locales" / "palabras_muletillas.json"
        if not archivo.exists():
            raise unittest.SkipTest("Falta pruebas/locales/palabras_muletillas.json (datos privados)")
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        cls.palabras = [tuple(p[:3]) for p in datos]

    def test_detecta_lo_que_dijiste(self):
        from collections import Counter
        marcas = self.m.detectar(self.palabras)
        cuenta = Counter(m["tipo"] for m in marcas)
        self.assertEqual(cuenta, {"repetida": 8, "discurso": 7, "sonora": 3, "reinicio": 2})
        textos = {m["texto"].lower() for m in marcas}
        self.assertIn("ahhh", textos)
        self.assertIn("es una", textos)          # reinicio "es una… es una grabación"
        self.assertNotIn("empezar", textos)      # "va a empezar a decir/hablar/repetir" es natural
        este = [m for m in marcas if m["texto"].lower() == "este"]
        self.assertEqual(este, [], "«este programa» no es muletilla")

    def test_inicio_ajustado_al_sonido(self):
        """Whisper ubica algunas palabras hasta 1 s antes; el ajuste las lleva a su ráfaga de voz."""
        ruta = VIDEOS / "2026-11-25 13-23-01_pistas" / "2026-11-25 13-23-01_pista2.wav"
        if not ruta.exists():
            self.skipTest("Falta la pista del micrófono del video de muletillas")
        an = cortar.Analisis(cortar.leer_audio_vad(ruta, 0, 0))
        marcas = self.m.ajustar(an, self.palabras, self.m.detectar(self.palabras))
        esp = [m["inicio"] for m in marcas if m["texto"] == "específicamente"]
        for obtenido, real in zip(esp, (36.80, 39.20, 41.15, 45.07)):
            self.assertAlmostEqual(obtenido, real, delta=0.1)
        ahhh = next(m["inicio"] for m in marcas if m["texto"] == "ahhh")
        self.assertAlmostEqual(ahhh, 7.86, delta=0.1)
        # El «o sea» de 31.9 s que reportaste: Whisper lo pone pegado a «bien», pero en el
        # audio viene después de un respiro, en la ráfaga de 32.52 a 32.96 s.
        o_sea = [m for m in marcas if m["texto"] == "o sea"][-1]
        self.assertAlmostEqual(o_sea["inicio"], 32.52, delta=0.08)
        self.assertLessEqual(o_sea["fin"], 33.05)

    def test_edl_en_la_linea_cortada(self):
        fps = Fraction(60)
        mantener = [(60, 120), (300, 600)]       # se conservan 1–2 s y 5–10 s
        marcas = [{"tipo": "sonora", "inicio": 1.5, "fin": 1.8, "texto": "eh", "detalle": ""},
                  {"tipo": "discurso", "inicio": 3.0, "fin": 3.3, "texto": "o sea", "detalle": ""},
                  {"tipo": "repetida", "inicio": 6.0, "fin": 6.5, "texto": "que", "detalle": "x4"}]
        linea = cortar.marcas_en_linea(marcas, mantener, fps, "cortar")
        self.assertEqual([(f, m["texto"]) for f, _, m in linea], [(30, "eh"), (120, "que")])
        self.assertEqual([f for f, _, _ in cortar.marcas_en_linea(marcas, mantener, fps, "limpiar")],
                         [90, 180, 360])
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "m.edl"
            cortar.generar_edl(linea, fps, destino)
            texto = destino.read_bytes().decode("utf-8")
        self.assertIn("00:00:00:30 00:00:00:31", texto)
        self.assertIn("|C:ResolveColorRed |M:Muletilla sonora: eh |D:18", texto)
        self.assertIn("|C:ResolveColorCyan |M:Repetida: que — x4", texto)
        self.assertIn("\r\n", texto)


def regenerar():
    ref = {}
    for caso in CASOS:
        an = analisis_de(caso)
        if an is None:
            print(f"Falta la grabación de '{caso}' en {VIDEOS}; se omite.")
            continue
        ref[caso] = {v: calcular(an, v) for v in VARIANTES}
        ref[caso] = {k: v for k, v in ref[caso].items() if v is not None}
        print(f"{caso}: " + ", ".join(f"{k}={len(v)} tramos" for k, v in ref[caso].items()))
    REFERENCIA.write_text(json.dumps(ref, indent=1), encoding="utf-8")
    print(f"Guardado en {REFERENCIA}")


if __name__ == "__main__":
    if "--regenerar" in sys.argv:
        regenerar()
    else:
        unittest.main(verbosity=2)
