"""Ventana del cortador de silencios (CustomTkinter).

Ábrela con cortador.bat (doble clic) o arrastrando un video encima de cortador.bat.
La lógica de detección y exportación está en cortar.py; aquí solo están los
controles, la vista previa y la reproducción.
"""
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import numpy as np

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import cortar  # noqa: E402
import muletillas  # noqa: E402
from ayuda import AYUDA  # noqa: E402

VIDEOS = [("Videos", "*.mp4 *.mkv *.mov *.flv *.ts *.m4v *.webm"), ("Todos", "*.*")]
SR = cortar.SR_VAD
SALTO = 2.0                  # Segundos de los botones −2 s / +2 s
ZOOM_MIN = 2.0               # Lo más cerca que se puede ver: 2 segundos en pantalla

# Paleta
FONDO = "#0F1115"
TARJETA = "#171A21"
BORDE = "#262B36"
CONTROL = "#1F232C"
CONTROL_HOVER = "#2A2F3B"
TEXTO = "#E5E7EB"
SUAVE = "#9CA3AF"
TENUE = "#6B7280"
INDIGO = "#6366F1"
INDIGO_HOVER = "#4F46E5"
INDIGO_CLARO = "#A5B4FC"
ESMERALDA = "#10B981"
ESMERALDA_HOVER = "#059669"
AVISO = "#F59E0B"
ROJO = "#EF4444"
# Colores de la onda (RGB)
ONDA_FONDO = (18, 21, 27)
ONDA_QUITADO = (30, 20, 26)
BARRA_CONSERVA = (16, 185, 129)
BARRA_QUITA = (75, 80, 92)
LINEA_CENTRO = (38, 43, 54)

PRESETS = {
    "Tutorial": {"modo": "cortar", "margen_inicio_ms": 200, "margen_final_ms": 400,
                 "pausas": "acortar", "pausa_ms": 400, "silencio_min_ms": 600,
                 "quitar_respiros": False, "limpiar_bordes": True},
    "Gameplay": {"modo": "limpiar", "margen_inicio_ms": 150, "margen_final_ms": 300,
                 "silencio_min_ms": 400, "quitar_respiros": True, "limpiar_bordes": True},
    "Shorts / Agresivo": {"modo": "cortar", "margen_inicio_ms": 100, "margen_final_ms": 200,
                          "pausas": "cortar", "silencio_min_ms": 300,
                          "quitar_respiros": True, "limpiar_bordes": True},
}


def fuente(tam=13, negrita=False):
    return ctk.CTkFont(size=tam, weight="bold" if negrita else "normal")


def tarjeta(master, **kw):
    return ctk.CTkFrame(master, fg_color=TARJETA, border_width=1, border_color=BORDE,
                        corner_radius=12, **kw)


def boton(master, texto, comando, primario=False, exito=False, **kw):
    if exito:
        colores = dict(fg_color=ESMERALDA, hover_color=ESMERALDA_HOVER, text_color="#04140D")
    elif primario:
        colores = dict(fg_color=INDIGO, hover_color=INDIGO_HOVER, text_color="white")
    else:
        colores = dict(fg_color=CONTROL, hover_color=CONTROL_HOVER, text_color=TEXTO,
                       border_width=1, border_color=BORDE)
    kw.setdefault("height", 32)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", fuente(13, primario or exito))
    return ctk.CTkButton(master, text=texto, command=comando, **colores, **kw)


def tecla(master, tecla_txt, descripcion):
    """Pista de teclado con forma de tecla: [Espacio] Reproducir/Pausa."""
    marco = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(marco, text=f" {tecla_txt} ", fg_color=CONTROL, corner_radius=5, text_color=TEXTO,
                 font=ctk.CTkFont(size=11, weight="bold"), height=20).pack(side="left")
    ctk.CTkLabel(marco, text=descripcion, text_color=SUAVE, font=fuente(11)).pack(side="left", padx=(5, 0))
    return marco


class Seccion(ctk.CTkFrame):
    """Tarjeta plegable con encabezado."""

    def __init__(self, master, titulo, abierta=True):
        super().__init__(master, fg_color=TARJETA, border_width=1, border_color=BORDE,
                         corner_radius=12)
        self.titulo = titulo
        self.abierta = abierta
        self.boton = ctk.CTkButton(self, text="", anchor="w", fg_color="transparent",
                                   hover_color=CONTROL, text_color=TEXTO, height=34,
                                   font=fuente(14, True), command=self.alternar)
        self.boton.pack(fill="x", padx=6, pady=(6, 2))
        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.actualizar()

    def alternar(self):
        self.abierta = not self.abierta
        self.actualizar()

    def actualizar(self):
        self.boton.configure(text=("▾   " if self.abierta else "▸   ") + self.titulo)
        if self.abierta:
            self.cuerpo.pack(fill="x", padx=14, pady=(0, 12))
        else:
            self.cuerpo.pack_forget()


class Reproductor:
    """Reproduce el audio de 16 kHz sin cortes de tiempo, desde una posición,
    saltando (o silenciando) lo que se quita. La posición se puede cambiar en
    vivo (arrastrando el cabezal) y la ventana la lee para dibujarlo."""

    def __init__(self):
        self.audio = None
        self.pos = 0                 # Muestra actual del audio original
        self.sonando = False
        self.stream = None
        self.inicios = np.zeros(0, np.int64)
        self.finales = np.zeros(0, np.int64)
        self.con_cortes = True
        self.saltar = True           # True: modo Cortar (salta); False: Limpiar (silencia)
        self.error = None

    def preparar(self, audio):
        self.detener()
        self.audio = audio
        self.pos = 0

    def tramos(self, tramos, saltar):
        inicios = np.array([i for i, _ in tramos], np.int64)
        finales = np.array([f for _, f in tramos], np.int64)
        self.inicios, self.finales, self.saltar = inicios, finales, saltar

    def reproducir(self):
        if self.audio is None or self.sonando:
            return
        import sounddevice as sd
        self.pausar()                      # Cierra el stream anterior si terminó solo
        if self.pos >= len(self.audio) - SR // 10:
            self.pos = 0
        self.sonando = True
        try:
            self.stream = sd.OutputStream(samplerate=SR, channels=1, dtype="float32",
                                          blocksize=1024, callback=self._llenar,
                                          finished_callback=self._termino)
            self.stream.start()
        except Exception:
            self.sonando = False
            self.stream = None
            raise

    def _termino(self):
        self.sonando = False

    def _llenar(self, salida, n, _tiempo, _estado):
        import sounddevice as sd
        out = salida[:, 0]
        audio, total = self.audio, len(self.audio)
        hecho = 0
        while hecho < n:
            p = self.pos
            if p >= total:
                out[hecho:] = 0
                raise sd.CallbackStop
            inicios, finales = self.inicios, self.finales
            if self.con_cortes and self.saltar:
                k = np.searchsorted(finales, p, side="right")
                if k >= len(finales):
                    out[hecho:] = 0
                    self.pos = total
                    raise sd.CallbackStop
                p = max(p, int(inicios[k]))
                tomar = min(n - hecho, int(finales[k]) - p)
                out[hecho:hecho + tomar] = audio[p:p + tomar]
            else:
                tomar = min(n - hecho, total - p)
                bloque = audio[p:p + tomar]
                if self.con_cortes and len(finales):     # Limpiar voz: silenciar
                    posiciones = np.arange(p, p + tomar)
                    k = np.searchsorted(finales, posiciones, side="right")
                    dentro = (k < len(finales)) & (posiciones >= inicios[np.minimum(k, len(inicios) - 1)])
                    bloque = np.where(dentro, bloque, 0)
                out[hecho:hecho + tomar] = bloque
            hecho += tomar
            self.pos = p + tomar

    def pausar(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        self.sonando = False

    detener = pausar


class App(ctk.CTk):
    def __init__(self, archivos):
        super().__init__()
        self.cfg = cortar.cargar_config()
        self.ruta = None
        self.info = None
        self.an = None
        self.tramos = []
        self.envolvente = None
        self.vista = (0.0, 1.0)
        self.cola = queue.Queue()
        self.ocupado = None
        self.cancelar = threading.Event()
        self.generacion = 0
        self.pendiente = None
        self.redibujo = None
        self.ultimo_destino = None
        self.marcas = []
        self.vars = {}
        self.foto = None
        self.arrastrando = False
        self.inicio_whisper = 0.0
        self.player = Reproductor()

        self.title(f"{cortar.NOMBRE_APP} {cortar.__version__}")
        self.configure(fg_color=FONDO)
        self.geometry("1280x820")
        self.minsize(1000, 640)
        if sys.platform == "win32":
            self.after(0, lambda: self.state("zoomed"))

        # pack en este orden: lo de abajo se reserva primero y nunca se recorta
        self.crear_encabezado()
        self.crear_pie()
        self.crear_vista_previa()
        self.crear_cuerpo()
        self.mostrar_ayuda("general")
        self.actualizar_habilitados()
        self.marcar_preset()

        self.bind("<space>", lambda e: self.tecla_global(e, self.play_pausa))
        self.bind("<Left>", lambda e: self.tecla_global(e, lambda: self.saltar(-SALTO)))
        self.bind("<Right>", lambda e: self.tecla_global(e, lambda: self.saltar(SALTO)))
        self.bind("<Home>", lambda e: self.tecla_global(e, lambda: self.ir_a(0)))
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.after(80, self.revisar_cola)
        self.after(40, self.tic_cabezal)
        if archivos:
            self.after(300, lambda: self.cargar_video(Path(archivos[0])))

    # ================================================================ estructura

    def crear_encabezado(self):
        barra = tarjeta(self)
        barra.pack(side="top", fill="x", padx=14, pady=(12, 6))
        boton(barra, "Elegir video…", self.elegir_video, primario=True, width=150,
              height=36).pack(side="left", padx=14, pady=10)
        textos = ctk.CTkFrame(barra, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        self.lbl_video = ctk.CTkLabel(textos, text="Ningún video elegido", anchor="w",
                                      text_color=TEXTO, font=fuente(15, True))
        self.lbl_video.pack(fill="x")
        self.lbl_info = ctk.CTkLabel(textos, text="Elige una grabación para empezar.", anchor="w",
                                     text_color=SUAVE, font=fuente(12))
        self.lbl_info.pack(fill="x")

    def crear_pie(self):
        pie = tarjeta(self)
        pie.pack(side="bottom", fill="x", padx=14, pady=(6, 14))
        self.barra_prog = ctk.CTkProgressBar(pie, width=200, height=8, progress_color=INDIGO,
                                             fg_color=CONTROL)
        self.barra_prog.set(0)
        self.barra_prog.pack(side="left", padx=(16, 12), pady=16)
        self.btn_exportar = boton(pie, "Exportar a DaVinci", self.exportar, exito=True, width=200,
                                  height=40, state="disabled")
        self.btn_exportar.pack(side="right", padx=(6, 14), pady=10)
        self.btn_carpeta = boton(pie, "Abrir carpeta", self.abrir_carpeta, width=130, height=40,
                                 state="disabled")
        self.btn_carpeta.pack(side="right", padx=6)
        boton(pie, "ⓘ", lambda: self.mostrar_ayuda("exportar"), width=32).pack(side="right", padx=4)
        self.btn_cancelar = boton(pie, "Cancelar", self.cancelar.set, width=100, height=40)
        self.lbl_estado = ctk.CTkLabel(pie, text="Listo.", anchor="w", text_color=SUAVE,
                                       font=fuente(13))
        self.lbl_estado.pack(side="left", fill="x", expand=True)

    def crear_vista_previa(self):
        marco = tarjeta(self)
        marco.pack(side="bottom", fill="x", padx=14, pady=6)
        # Una sola fila: transporte · tiempo · estadísticas · escucha · zoom
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=(10, 6))
        boton(fila, "⏮", lambda: self.corte_vecino(-1), width=38).pack(side="left", padx=(0, 4))
        boton(fila, "−2 s", lambda: self.saltar(-SALTO), width=52).pack(side="left", padx=3)
        self.btn_play = boton(fila, "▶  Reproducir", self.play_pausa, primario=True, width=140)
        self.btn_play.pack(side="left", padx=3)
        boton(fila, "+2 s", lambda: self.saltar(SALTO), width=52).pack(side="left", padx=3)
        boton(fila, "⏭", lambda: self.corte_vecino(1), width=38).pack(side="left", padx=3)
        self.lbl_tiempo = ctk.CTkLabel(fila, text="0:00.0", text_color=TEXTO, width=70,
                                       font=ctk.CTkFont(family="Consolas", size=15, weight="bold"))
        self.lbl_tiempo.pack(side="left", padx=(10, 6))
        boton(fila, "ⓘ", lambda: self.mostrar_ayuda("vista"), width=32).pack(side="right", padx=(4, 0))
        boton(fila, "Ver todo", self.ver_todo, width=76).pack(side="right", padx=3)
        boton(fila, "+", lambda: self.zoom(1 / 1.6), width=32).pack(side="right", padx=2)
        boton(fila, "−", lambda: self.zoom(1.6), width=32).pack(side="right", padx=2)
        self.var_escucha = tk.StringVar(value="Con cortes")
        ctk.CTkSegmentedButton(fila, values=["Con cortes", "Original"],
                               variable=self.var_escucha, command=lambda _v: self.cambio_escucha(),
                               selected_color=INDIGO, selected_hover_color=INDIGO_HOVER,
                               unselected_color=CONTROL, unselected_hover_color=CONTROL_HOVER,
                               fg_color=CONTROL, text_color=TEXTO, font=fuente(12)
                               ).pack(side="right", padx=(6, 10))
        self.lbl_stats = ctk.CTkLabel(fila, text="", anchor="w", text_color=TEXTO,
                                      font=fuente(13, True))
        self.lbl_stats.pack(side="left", fill="x", expand=True, padx=(6, 0))
        # Onda
        self.lienzo = tk.Canvas(marco, height=140, bg="#%02x%02x%02x" % ONDA_FONDO,
                                highlightthickness=0, cursor="hand2")
        self.lienzo.pack(fill="x", padx=14)
        self.barra_h = ctk.CTkScrollbar(marco, orientation="horizontal", command=self.desplazar,
                                        button_color=CONTROL_HOVER, button_hover_color=INDIGO,
                                        height=14)
        self.barra_h.pack(fill="x", padx=14, pady=(2, 0))
        teclas = ctk.CTkFrame(marco, fg_color="transparent")
        teclas.pack(fill="x", padx=14, pady=(4, 10))
        for t, d in (("Espacio", "Reproducir / Pausa"), ("← →", "±2 s"), ("Clic / Arrastrar", "Mover cabezal"),
                     ("Rueda", "Zoom"), ("Shift + Rueda", "Desplazar"), ("Inicio", "Ir al principio")):
            tecla(teclas, t, d).pack(side="left", padx=(0, 16))

        self.lienzo.bind("<Configure>", lambda _e: self.pedir_redibujo())
        self.lienzo.bind("<ButtonPress-1>", self.presionar_onda)
        self.lienzo.bind("<B1-Motion>", self.arrastrar_onda)
        self.lienzo.bind("<ButtonRelease-1>", self.soltar_onda)
        self.lienzo.bind("<MouseWheel>", self.rueda)
        self.lienzo.bind("<Shift-MouseWheel>", self.rueda_h)
        self.lienzo.bind("<Button-4>", lambda e: self.zoom(1 / 1.25, e.x))   # Linux
        self.lienzo.bind("<Button-5>", lambda e: self.zoom(1.25, e.x))

    def crear_cuerpo(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(side="top", fill="both", expand=True, padx=14, pady=6)
        cuerpo.columnconfigure(0, weight=0)
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        self.controles = ctk.CTkScrollableFrame(cuerpo, width=470, fg_color="transparent",
                                                scrollbar_button_color=CONTROL_HOVER,
                                                scrollbar_button_hover_color=INDIGO)
        self.controles.grid(row=0, column=0, sticky="nsw", padx=(0, 6))

        # Ajustes rápidos
        presets = tarjeta(self.controles)
        presets.pack(fill="x", pady=(0, 10))
        cab = ctk.CTkFrame(presets, fg_color="transparent")
        cab.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(cab, text="Ajustes rápidos", text_color=TEXTO, font=fuente(14, True)).pack(side="left")
        self.lbl_preset = ctk.CTkLabel(cab, text="", text_color=TENUE, font=fuente(11))
        self.lbl_preset.pack(side="left", padx=8)
        boton(cab, "ⓘ", lambda: self.mostrar_ayuda("presets"), width=28, height=26).pack(side="right")
        pills = ctk.CTkFrame(presets, fg_color="transparent")
        pills.pack(fill="x", padx=14, pady=(0, 12))
        self.btn_presets = {}
        for nombre in PRESETS:
            b = ctk.CTkButton(pills, text=nombre, height=30, corner_radius=15, font=fuente(12, True),
                              command=lambda n=nombre: self.aplicar_preset(n))
            b.pack(side="left", padx=(0, 6))
            self.btn_presets[nombre] = b

        basico = Seccion(self.controles, "Básico")
        basico.pack(fill="x", pady=(0, 10))
        c = basico.cuerpo
        self.var_pista = tk.StringVar(value="—")
        self.menu_pista = ctk.CTkOptionMenu(c, variable=self.var_pista, values=["—"],
                                            command=lambda _v: self.cambio_pista(), width=320,
                                            fg_color=CONTROL, button_color=CONTROL_HOVER,
                                            button_hover_color=INDIGO, text_color=TEXTO,
                                            dropdown_fg_color=TARJETA, dropdown_hover_color=CONTROL_HOVER,
                                            font=fuente(13))
        self.fila_control(c, "pista", "Pista del micrófono", self.menu_pista)
        self.var_modo = tk.StringVar(value="Cortar" if self.cfg["modo"] == "cortar" else "Limpiar voz")
        self.seg_modo = self.segmentado(c, ["Cortar", "Limpiar voz"], self.var_modo, "modo")
        self.fila_control(c, "modo", "Modo", self.seg_modo)
        self.deslizador(c, "margen_inicio_ms", "Margen al inicio", 0, 1000, 10, "{:.0f} ms")
        self.deslizador(c, "margen_final_ms", "Margen al final", 0, 1000, 10, "{:.0f} ms")
        self.var_pausas = tk.StringVar(value="Acortar" if self.cfg["pausas"] == "acortar" else "Quitar")
        self.seg_pausas = self.segmentado(c, ["Quitar", "Acortar"], self.var_pausas, "pausas")
        self.fila_control(c, "pausas", "Pausas largas", self.seg_pausas)
        self.deslizador(c, "pausa_ms", "Dejar pausas de", 100, 2000, 50, "{:.0f} ms")

        avanzado = Seccion(self.controles, "Avanzado", abierta=False)
        avanzado.pack(fill="x", pady=(0, 10))
        c = avanzado.cuerpo
        self.deslizador(c, "silencio_min_ms", "Pausa mínima a cortar", 200, 3000, 50, "{:.0f} ms")
        self.deslizador(c, "sensibilidad", "Sensibilidad", 0.1, 0.9, 0.05, "{:.2f}")
        self.deslizador(c, "voz_min_ms", "Ignorar sonidos cortos", 0, 500, 10, "{:.0f} ms")
        self.interruptor(c, "limpiar_bordes", "Sin clics ni respiros pegados a las frases")
        self.interruptor(c, "quitar_respiros", "Quitar respiros en pausas cortas")
        boton(c, "Restaurar valores por defecto", self.restaurar, height=28,
              font=fuente(12)).pack(anchor="e", pady=(10, 0))

        preciso = Seccion(self.controles, "Whisper: modo preciso y muletillas", abierta=False)
        preciso.pack(fill="x", pady=(0, 10))
        c = preciso.cuerpo
        aviso = ctk.CTkFrame(c, fg_color="#2A2113", border_width=1, border_color="#5C4214",
                             corner_radius=8)
        aviso.pack(fill="x", pady=(2, 8))
        ctk.CTkLabel(aviso, justify="left", anchor="w", wraplength=400, text_color=AVISO,
                     font=fuente(12, True),
                     text="⚠  Activar cualquiera de estas dos opciones hace que el análisis "
                          "tarde MINUTOS en vez de segundos: Whisper corre en tu procesador "
                          "(sin GPU), aprox. 1–3 min por cada 10 min de video. Se hace una "
                          "sola vez por video (sirve para las dos) y se puede cancelar."
                     ).pack(fill="x", padx=10, pady=8)
        self.interruptor(c, "modo_preciso", "Modo preciso (cortar por palabras)",
                         lambda: self.cambio_whisper("modo_preciso"))
        self.deslizador(c, "margen_preciso_ms", "Margen tras la última palabra", 0, 300, 10, "{:.0f} ms")
        self.interruptor(c, "marcar_muletillas", "Marcar muletillas en DaVinci",
                         lambda: self.cambio_whisper("marcar_muletillas"))
        tipos = ctk.CTkFrame(c, fg_color="transparent")
        tipos.pack(fill="x", pady=(8, 0))
        tipos.columnconfigure((0, 1), weight=1)
        for n, (tipo, etiqueta) in enumerate((("sonora", "Sonoras: eh, mmm"),
                                              ("discurso", "Muletillas: o sea, bueno"),
                                              ("reinicio", "Reinicios de frase"),
                                              ("repetida", "Palabras repetidas"))):
            self.casilla(tipos, f"marca_{tipo}", etiqueta, muletillas.TIPOS[tipo][2], n // 2, n % 2)
        self.lbl_marcas = ctk.CTkLabel(c, text="", anchor="w", justify="left", wraplength=420,
                                       text_color=SUAVE, font=fuente(12))
        self.lbl_marcas.pack(fill="x", pady=(6, 0))
        self.lbl_palabras = ctk.CTkLabel(c, text="Palabras: sin analizar", anchor="w",
                                         text_color=SUAVE, font=fuente(12))
        self.lbl_palabras.pack(fill="x", pady=(2, 0))

        # Panel de ayuda (fijo hasta que se elija otra opción)
        panel = tarjeta(cuerpo)
        panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(panel, text="DETALLE", anchor="w", text_color=INDIGO_CLARO,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(fill="x", padx=18, pady=(14, 0))
        self.lbl_ayuda = ctk.CTkLabel(panel, text="", anchor="w", justify="left", text_color=TEXTO,
                                      font=fuente(18, True))
        self.lbl_ayuda.pack(fill="x", padx=18, pady=(2, 6))
        self.txt_ayuda = ctk.CTkTextbox(panel, wrap="word", fg_color="transparent", text_color="#D1D5DB",
                                        font=fuente(14), activate_scrollbars=True,
                                        scrollbar_button_color=CONTROL_HOVER)
        self.txt_ayuda.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ================================================================ fábricas de controles

    def segmentado(self, padre, valores, variable, clave):
        def cambio(_v):
            self.mostrar_ayuda(clave)
            self.cambio_ajuste()
        return ctk.CTkSegmentedButton(padre, values=valores, variable=variable, command=cambio,
                                      selected_color=INDIGO, selected_hover_color=INDIGO_HOVER,
                                      unselected_color=CONTROL, unselected_hover_color=CONTROL_HOVER,
                                      fg_color=CONTROL, text_color=TEXTO, font=fuente(13))

    def cabecera(self, padre, clave, titulo, insignia=None):
        """Título + insignia con el valor + botón ⓘ. Clic en el título también
        muestra la ayuda."""
        fila = ctk.CTkFrame(padre, fg_color="transparent")
        fila.pack(fill="x", pady=(12, 4))
        lbl = ctk.CTkLabel(fila, text=titulo, anchor="w", text_color=TEXTO, font=fuente(13, True),
                           cursor="hand2")
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda _e: self.mostrar_ayuda(clave))
        boton(fila, "ⓘ", lambda: self.mostrar_ayuda(clave), width=26, height=24,
              font=fuente(12)).pack(side="right")
        if insignia is not None:
            insignia.pack(in_=fila, side="right", padx=6)
            insignia.lift()
        return fila

    def fila_control(self, padre, clave, titulo, widget):
        self.cabecera(padre, clave, titulo)
        widget.pack(fill="x" if isinstance(widget, ctk.CTkSegmentedButton) else None, anchor="w")

    def deslizador(self, padre, clave, titulo, desde, hasta, paso, fmt):
        var = tk.DoubleVar(value=float(self.cfg[clave]))
        insignia = ctk.CTkLabel(padre, text="", fg_color="#232845", text_color=INDIGO_CLARO,
                                corner_radius=6, font=fuente(12, True), width=72, height=24)

        def mover(_v=None, avisar=True):
            valor = round(var.get() / paso) * paso
            insignia.configure(text=fmt.format(valor))
            if avisar:
                self.mostrar_ayuda(clave)
                self.cambio_ajuste()

        self.cabecera(padre, clave, titulo, insignia)
        control = ctk.CTkSlider(padre, from_=desde, to=hasta, variable=var,
                                number_of_steps=int(round((hasta - desde) / paso)), command=mover,
                                button_color=INDIGO, button_hover_color=INDIGO_HOVER,
                                progress_color=INDIGO, fg_color=CONTROL, height=18)
        control.pack(fill="x")
        mover(avisar=False)
        self.vars[clave] = {"var": var, "paso": paso, "control": control, "mover": mover}

    def interruptor(self, padre, clave, titulo, comando=None):
        var = tk.BooleanVar(value=bool(self.cfg[clave]))
        fila = ctk.CTkFrame(padre, fg_color="transparent")
        fila.pack(fill="x", pady=(12, 0))

        def cambio():
            self.mostrar_ayuda(clave)
            (comando or self.cambio_ajuste)()

        control = ctk.CTkSwitch(fila, text=titulo, variable=var, command=cambio, text_color=TEXTO,
                                font=fuente(13, True), progress_color=INDIGO, button_color="#E5E7EB",
                                button_hover_color="white", fg_color=CONTROL_HOVER)
        control.pack(side="left")
        boton(fila, "ⓘ", lambda: self.mostrar_ayuda(clave), width=26, height=24,
              font=fuente(12)).pack(side="right")
        self.vars[clave] = {"var": var, "paso": None, "control": control}

    def casilla(self, padre, clave, titulo, color, fila, columna):
        var = tk.BooleanVar(value=bool(self.cfg[clave]))

        def cambio():
            self.mostrar_ayuda("marcar_muletillas")
            self.cambio_ajuste()

        control = ctk.CTkCheckBox(padre, text=titulo, variable=var, command=cambio, text_color=TEXTO,
                                  font=fuente(12), fg_color=color, hover_color=color,
                                  border_color=color, checkmark_color="#0F1115",
                                  checkbox_width=18, checkbox_height=18)
        control.grid(row=fila, column=columna, sticky="w", pady=3)
        self.vars[clave] = {"var": var, "paso": None, "control": control}

    def mostrar_ayuda(self, clave):
        titulo, texto = AYUDA[clave]
        if self.lbl_ayuda.cget("text") == titulo:
            return
        self.lbl_ayuda.configure(text=titulo)
        self.txt_ayuda.configure(state="normal")
        self.txt_ayuda.delete("1.0", "end")
        self.txt_ayuda.insert("1.0", texto)
        self.txt_ayuda.configure(state="disabled")

    # ================================================================ ajustes y presets

    def leer_ajustes(self):
        cfg = dict(self.cfg)
        cfg["modo"] = "cortar" if self.var_modo.get() == "Cortar" else "limpiar"
        cfg["pausas"] = "acortar" if self.var_pausas.get() == "Acortar" else "cortar"
        for clave, v in self.vars.items():
            if v["paso"] is None:
                cfg[clave] = bool(v["var"].get())
            else:
                valor = round(v["var"].get() / v["paso"]) * v["paso"]
                cfg[clave] = round(valor, 2) if isinstance(v["paso"], float) else int(round(valor))
        if self.info and len(self.info["pistas"]) > 1:
            cfg["pista_voz"] = self.indice_pista() + 1
        return cfg

    def poner(self, valores):
        """Aplica un conjunto de valores a los controles (sin recalcular)."""
        for clave, valor in valores.items():
            if clave == "modo":
                self.var_modo.set("Cortar" if valor == "cortar" else "Limpiar voz")
            elif clave == "pausas":
                self.var_pausas.set("Acortar" if valor == "acortar" else "Quitar")
            elif clave in self.vars:
                v = self.vars[clave]
                v["var"].set(valor)
                if v["paso"] is not None:
                    v["control"].set(valor)
                    v["mover"](avisar=False)

    def aplicar_preset(self, nombre):
        self.poner(PRESETS[nombre])
        self.mostrar_ayuda("presets")
        self.cambio_ajuste()

    def marcar_preset(self):
        cfg = self.leer_ajustes()
        activo = None
        for nombre, valores in PRESETS.items():
            if all(cfg.get(k) == v for k, v in valores.items()):
                activo = nombre
        for nombre, b in self.btn_presets.items():
            if nombre == activo:
                b.configure(fg_color=INDIGO, hover_color=INDIGO_HOVER, text_color="white",
                            border_width=0)
            else:
                b.configure(fg_color=CONTROL, hover_color=CONTROL_HOVER, text_color=SUAVE,
                            border_width=1, border_color=BORDE)
        self.lbl_preset.configure(text="" if activo else "personalizado")

    def restaurar(self):
        self.poner({k: v for k, v in cortar.DEFAULTS.items()
                    if k not in ("modo_preciso", "pista_voz")})
        self.cambio_ajuste()

    def actualizar_habilitados(self):
        cortar_modo = self.var_modo.get() == "Cortar"
        self.seg_pausas.configure(state="normal" if cortar_modo else "disabled")
        acortar = cortar_modo and self.var_pausas.get() == "Acortar"
        self.vars["pausa_ms"]["control"].configure(state="normal" if acortar else "disabled")
        self.vars["margen_preciso_ms"]["control"].configure(
            state="normal" if self.vars["modo_preciso"]["var"].get() else "disabled")
        marcar = self.vars["marcar_muletillas"]["var"].get()
        for tipo in muletillas.TIPOS:
            self.vars[f"marca_{tipo}"]["control"].configure(state="normal" if marcar else "disabled")
        listo = self.an is not None and self.ocupado is None and bool(self.tramos)
        self.btn_exportar.configure(state="normal" if listo else "disabled")
        varias = bool(self.info) and len(self.info["pistas"]) > 1
        self.menu_pista.configure(state="normal" if varias and self.ocupado is None else "disabled")

    # ================================================================ video y análisis

    def elegir_video(self):
        ruta = filedialog.askopenfilename(title="Elige la grabación", filetypes=VIDEOS)
        if ruta:
            self.cargar_video(Path(ruta))

    def cargar_video(self, ruta):
        if self.ocupado:
            messagebox.showinfo("Cortador", "Espera a que termine la tarea en curso o cancélala.")
            return
        try:
            info = cortar.info_archivo(ruta)
        except Exception as e:
            messagebox.showerror("Cortador", f"No pude leer {ruta.name}:\n{e}")
            return
        self.player.detener()
        self.ruta, self.info, self.an, self.tramos = ruta.resolve(), info, None, []
        self.ultimo_destino = None
        self.btn_carpeta.configure(state="disabled")
        self.lbl_video.configure(text=ruta.name)
        self.lbl_info.configure(text=f"{info['ancho']}x{info['alto']}  ·  {float(info['fps']):.2f} fps  ·  "
                                     f"{cortar.mmss(info['duracion'])}  ·  "
                                     f"{len(info['pistas'])} pista(s) de audio  ·  {self.ruta.parent}")
        opciones = [f"Pista {n} — {p['titulo'] or 'sin nombre'} ({p['canales']} canal(es))"
                    for n, p in enumerate(info["pistas"], start=1)]
        self.menu_pista.configure(values=opciones)
        guardada = self.cfg.get("pista_voz")
        if len(opciones) == 1:
            elegida = 0
        else:
            elegida = guardada - 1 if guardada and guardada <= len(opciones) else 1
        self.var_pista.set(opciones[elegida])
        self.vista = (0.0, max(info["duracion"], ZOOM_MIN))
        self.analizar()

    def indice_pista(self):
        try:
            return list(self.menu_pista.cget("values")).index(self.var_pista.get())
        except ValueError:
            return 0

    def cambio_pista(self):
        self.mostrar_ayuda("pista")
        if self.ruta:
            self.analizar()

    def analizar(self):
        self.generacion += 1
        gen = self.generacion
        ruta, info, indice = self.ruta, self.info, self.indice_pista()
        self.player.detener()
        self.an, self.tramos, self.envolvente, self.marcas = None, [], None, []
        self.lbl_palabras.configure(text="Palabras: sin analizar")
        self.empezar("analisis", "Analizando tu voz…")
        self.pedir_redibujo()

        def tarea():
            try:
                an = cortar.analizar_archivo(ruta, indice, info["duracion"],
                                             lambda x: self.cola.put(("progreso", gen, x)))
                env = envolvente(an.audio)
                palabras = cortar.cargar_palabras(ruta, indice)
                self.cola.put(("analizado", gen, (an, env, palabras)))
            except Exception as e:
                cortar.log(f"Análisis de {ruta}\n{traceback.format_exc()}")
                self.cola.put(("error", gen, f"No pude analizar el audio: {e}"))
        threading.Thread(target=tarea, daemon=True).start()

    def al_analizar(self, an, env, palabras):
        self.an, self.envolvente = an, env
        self.player.preparar(an.audio)
        self.vista = (0.0, max(an.duracion, ZOOM_MIN))
        if palabras is not None:
            an.palabras = palabras
            self.lbl_palabras.configure(text=f"Palabras: {len(palabras)} (guardadas de antes, "
                                             "cargadas al instante)")
            self.marcas = cortar.detectar_marcas(an)
        self.terminar("Análisis listo. Ajusta, pon el cabezal y pulsa Espacio para escuchar.")
        self.recalcular()
        if self.necesita_whisper():
            self.correr_whisper()

    def usa_whisper(self):
        return self.vars["modo_preciso"]["var"].get() or self.vars["marcar_muletillas"]["var"].get()

    def necesita_whisper(self):
        """¿Falta correr Whisper para lo que está activado?"""
        if self.an is None or not self.usa_whisper():
            return False
        p = self.an.palabras
        if p is None:
            return True
        return bool(self.vars["marcar_muletillas"]["var"].get() and p and len(p[0]) < 3)

    def cambio_whisper(self, clave):
        var = self.vars[clave]["var"]
        if not var.get():
            if self.ocupado == "whisper" and not self.usa_whisper():
                self.cancelar.set()
            self.cambio_ajuste()
            return
        if self.an is None or self.necesita_whisper():
            dur = self.info["duracion"] if self.info else None
            detalle = (f"Este video dura {cortar.mmss(dur)}: calcula aproximadamente de "
                       f"{cortar.mmss(dur * 0.1)} a {cortar.mmss(dur * 0.3)} de análisis.\n\n"
                       if dur else "")
            que = ("El modo preciso usa Whisper para ubicar cada palabra." if clave == "modo_preciso"
                   else "Marcar muletillas usa Whisper para transcribir lo que dices y encontrar "
                        "«eh», «o sea», reinicios y palabras repetidas.")
            ok = messagebox.askyesno(
                "Usar Whisper",
                que + "\n\nEl análisis normal tarda SEGUNDOS; Whisper tarda MINUTOS "
                "(Whisper corre en el procesador: aprox. 1 a 3 minutos por cada 10 minutos de video), "
                "con el procesador trabajando al máximo.\n\n" + detalle +
                "Se hace una sola vez por video (queda guardado y sirve para el modo preciso "
                "y para las muletillas) y puedes cancelarlo en cualquier momento.\n\n¿Activarlo?")
            if not ok:
                var.set(False)
                self.actualizar_habilitados()
                return
            if self.necesita_whisper() and self.ocupado is None:
                self.correr_whisper()
        self.cambio_ajuste()

    def correr_whisper(self):
        gen = self.generacion
        ruta, indice, an = self.ruta, self.indice_pista(), self.an
        self.cancelar.clear()
        self.inicio_whisper = time.time()
        self.empezar("whisper", "Whisper: ubicando y transcribiendo palabras…", cancelable=True)

        def tarea():
            try:
                palabras = cortar.obtener_palabras(
                    ruta, indice, an, lambda x: self.cola.put(("progreso", gen, x)),
                    self.cancelar.is_set)
                self.cola.put(("palabras", gen, palabras))
            except cortar.Cancelado:
                self.cola.put(("cancelado", gen, None))
            except Exception as e:
                cortar.log(f"Whisper en {ruta}\n{traceback.format_exc()}")
                self.cola.put(("error", gen, f"Whisper falló: {e}"))
        threading.Thread(target=tarea, daemon=True).start()

    # ================================================================ recálculo

    def cambio_ajuste(self):
        self.actualizar_habilitados()
        self.marcar_preset()
        if self.pendiente:
            self.after_cancel(self.pendiente)
        self.pendiente = self.after(100, self.recalcular)

    def recalcular(self):
        self.pendiente = None
        if self.an is None:
            self.actualizar_habilitados()
            return
        cfg = self.leer_ajustes()
        self.tramos = cortar.segmentar(self.an, cfg, cfg["modo"])
        self.player.tramos(self.tramos, cfg["modo"] == "cortar")
        self.actualizar_stats(cfg)
        self.actualizar_marcas(cfg)
        self.actualizar_habilitados()
        self.pedir_redibujo()

    def marcas_activas(self, cfg=None):
        cfg = cfg or self.leer_ajustes()
        if not cfg.get("marcar_muletillas"):
            return []
        tipos = cortar.tipos_activos(cfg)
        return [m for m in self.marcas if m["tipo"] in tipos]

    def actualizar_marcas(self, cfg):
        if not cfg.get("marcar_muletillas"):
            self.lbl_marcas.configure(text="")
            return
        if self.an is None or not self.an.palabras or len(self.an.palabras[0]) < 3:
            self.lbl_marcas.configure(text="Marcas: falta analizar con Whisper")
            return
        activas = self.marcas_activas(cfg)
        cuenta = {t: sum(m["tipo"] == t for m in activas) for t in muletillas.TIPOS}
        self.lbl_marcas.configure(
            text=f"{len(activas)} marcas  ·  {cuenta['sonora']} sonoras  ·  {cuenta['discurso']} muletillas"
                 f"  ·  {cuenta['reinicio']} reinicios  ·  {cuenta['repetida']} repetidas")

    def actualizar_stats(self, cfg):
        if not self.tramos:
            self.lbl_stats.configure(text="⚠ Sin voz en esta pista: prueba otra o baja la sensibilidad")
            return
        total = self.info["duracion"]
        voz = sum(f - i for i, f in self.tramos) / SR
        if cfg["modo"] == "cortar":
            quitado = max(total - voz, 0)
            self.lbl_stats.configure(
                text=f"{cortar.mmss(total)} → {cortar.mmss(voz)}   −{cortar.mmss(quitado)} "
                     f"({quitado / total:.0%})  ·  {len(self.tramos)} tramos")
        elif self.indice_pista() == 0:
            self.lbl_stats.configure(text="⚠ Limpiar voz necesita el micrófono en otra pista")
        else:
            self.lbl_stats.configure(
                text=f"Misma duración  ·  voz {cortar.mmss(voz)} en {len(self.tramos)} tramos  ·  "
                     f"silencio {cortar.mmss(total - voz)}")

    # ================================================================ onda

    def pedir_redibujo(self):
        """Agrupa varios pedidos seguidos (rueda, arrastre) en un solo dibujo."""
        if self.redibujo is None:
            self.redibujo = self.after(12, self.dibujar)

    def dibujar(self):
        self.redibujo = None
        c = self.lienzo
        ancho, alto = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        if self.an is None or self.envolvente is None:
            c.delete("all")
            self.foto = None
            texto = "Elige un video para ver la vista previa." if self.ruta is None else "Analizando…"
            c.create_text(ancho / 2, alto / 2, text=texto, fill=SUAVE, font=("Segoe UI", 12),
                          tags="vacio")
            self.barra_h.set(0, 1)
            return
        c.delete("vacio")
        v0, v1 = self.vista
        dur = self.an.duracion
        self.barra_h.set(v0 / dur, v1 / dur)
        regla_alto = 18
        img = self.render_onda(ancho, alto - regla_alto, v0, v1)
        cabecera = b"P6 %d %d 255\n" % (ancho, alto - regla_alto)
        foto = tk.PhotoImage(data=cabecera + img.tobytes(), format="PPM")
        if c.find_withtag("onda"):
            c.itemconfigure("onda", image=foto)
        else:
            c.create_image(0, regla_alto, image=foto, anchor="nw", tags="onda")
        self.foto = foto       # Mantener la referencia: si no, Tk la borra
        # Regla de tiempo (pocos elementos)
        c.delete("regla")
        c.create_rectangle(0, 0, ancho, regla_alto, fill="#%02x%02x%02x" % ONDA_FONDO, width=0,
                           tags="regla")
        paso = regla(v1 - v0)
        t = (v0 // paso) * paso
        while t <= v1:
            if t >= v0:
                x = (t - v0) / (v1 - v0) * ancho
                c.create_line(x, regla_alto - 5, x, regla_alto, fill="#3B4252", tags="regla")
                c.create_text(x + 3, 2, text=formato_t(t, paso), anchor="nw", fill=TENUE,
                              font=("Segoe UI", 8), tags="regla")
            t += paso
        # Marcas de muletillas: triángulos de color en la regla
        for m in self.marcas_activas():
            if v0 <= m["inicio"] <= v1:
                x = (m["inicio"] - v0) / (v1 - v0) * ancho
                c.create_polygon(x - 5, 7, x + 5, 7, x, regla_alto, fill=muletillas.TIPOS[m["tipo"]][2],
                                 outline="", tags="regla")
        self.dibujar_cabezal()

    def render_onda(self, ancho, alto, v0, v1):
        """Dibuja la onda como imagen (barras de 2 px con 1 px de separación).
        Cambiar una sola imagen en vez de miles de líneas evita el parpadeo."""
        img = np.empty((alto, ancho, 3), np.uint8)
        img[:] = ONDA_FONDO
        columnas = v0 + (np.arange(ancho) + 0.5) * (v1 - v0) / ancho
        inicios = np.array([i for i, _ in self.tramos], np.float64) / SR
        finales = np.array([f for _, f in self.tramos], np.float64) / SR
        if len(inicios):
            k = np.searchsorted(inicios, columnas, side="right") - 1
            dentro = (k >= 0) & (columnas < finales[np.maximum(k, 0)])
        else:
            dentro = np.zeros(ancho, bool)
        img[:, ~dentro] = ONDA_QUITADO
        # Altura de cada barra (cada 3 px)
        n_barras = (ancho + 2) // 3
        bordes = v0 + np.arange(n_barras + 1) * 3 * (v1 - v0) / ancho
        muestras_por_barra = (bordes[1] - bordes[0]) * SR
        if muestras_por_barra >= cortar.HOP * 2:
            idx = np.clip((bordes * 100).astype(int), 0, len(self.envolvente) - 1)
            idx = np.maximum.accumulate(idx)
            seg = self.envolvente[idx[0]:idx[-1] + 1]
            rel = np.minimum(idx[:-1] - idx[0], max(len(seg) - 1, 0))
            alturas = np.maximum.reduceat(seg, rel) if len(seg) else np.zeros(n_barras)
        else:
            audio = self.an.audio
            idx = np.clip((bordes * SR).astype(int), 0, len(audio) - 1)
            seg = np.abs(audio[idx[0]:idx[-1] + 1])
            rel = np.minimum(idx[:-1] - idx[0], max(len(seg) - 1, 0))
            alturas = np.maximum.reduceat(seg, rel) / self.tope if len(seg) else np.zeros(n_barras)
        alturas = np.clip(alturas, 0, 1) ** 0.7      # Hace visible la voz bajita
        medio = alto // 2
        img[medio, :] = LINEA_CENTRO
        h_col = np.repeat(np.maximum(alturas * (medio - 4), 1), 3)[:ancho]
        hueco = (np.arange(ancho) % 3) == 2
        y = np.abs(np.arange(alto)[:, None] - medio)
        pinta = (y <= h_col[None, :]) & ~hueco[None, :]
        color = np.where(dentro[:, None], np.array(BARRA_CONSERVA, np.uint8),
                         np.array(BARRA_QUITA, np.uint8))
        img[pinta] = np.broadcast_to(color[None, :, :], img.shape)[pinta]
        return img

    def dibujar_cabezal(self):
        c = self.lienzo
        if self.an is None:
            c.delete("cabezal")
            return
        t = self.player.pos / SR
        v0, v1 = self.vista
        ancho, alto = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        x = (t - v0) / (v1 - v0) * ancho
        visible = -2 <= x <= ancho + 2
        if not c.find_withtag("cabezal"):
            c.create_line(0, 0, 0, alto, fill=ROJO, width=2, tags=("cabezal", "cab_linea"))
            c.create_polygon(0, 0, 0, 0, 0, 0, fill=ROJO, outline=ROJO, tags=("cabezal", "cab_punta"))
        if visible:
            c.coords("cab_linea", x, 0, x, alto)
            c.coords("cab_punta", x - 6, 0, x + 6, 0, x, 9)
            c.itemconfigure("cabezal", state="normal")
            c.tag_raise("cabezal")
        else:
            c.itemconfigure("cabezal", state="hidden")
        self.lbl_tiempo.configure(text=formato_t(t, 0.1))

    def tic_cabezal(self):
        """Mientras suena, mueve el cabezal y hace que la vista lo siga."""
        if self.player.error:
            self.estado(self.player.error)
            self.player.error = None
        sonando = self.player.sonando
        if sonando != getattr(self, "sonaba", False) and self.an is not None:
            self.dibujar_cabezal()           # Terminó o empezó: dejarlo en su sitio
        self.sonaba = sonando
        if sonando and not self.arrastrando and self.an is not None:
            t = self.player.pos / SR
            v0, v1 = self.vista
            if t > v1 or t < v0:
                largo = v1 - v0
                n0 = min(max(t - largo * 0.1, 0), self.an.duracion - largo)
                self.vista = (n0, n0 + largo)
                self.pedir_redibujo()
            self.dibujar_cabezal()
        texto = "❚❚  Pausa" if sonando else "▶  Reproducir"
        if self.btn_play.cget("text") != texto:
            self.btn_play.configure(text=texto)
        self.after(33, self.tic_cabezal)

    def x_a_tiempo(self, x):
        v0, v1 = self.vista
        return min(max(v0 + (v1 - v0) * x / max(self.lienzo.winfo_width(), 1), 0),
                   self.an.duracion)

    def presionar_onda(self, e):
        if self.an is None:
            return
        self.arrastrando = True
        self.ir_a(self.x_a_tiempo(e.x))
        self.mostrar_ayuda("vista")

    def arrastrar_onda(self, e):
        if self.an is not None and self.arrastrando:
            self.ir_a(self.x_a_tiempo(e.x))

    def soltar_onda(self, _e):
        self.arrastrando = False

    def zoom(self, factor, x=None):
        if self.an is None:
            return
        v0, v1 = self.vista
        dur = self.an.duracion
        largo = min(max((v1 - v0) * factor, min(ZOOM_MIN, dur)), dur)
        if abs(largo - (v1 - v0)) < 1e-6:
            return                       # Ya en el límite: no redibujar
        ancho = max(self.lienzo.winfo_width(), 10)
        ancla = v0 + (v1 - v0) * ((x / ancho) if x is not None else 0.5)
        if x is None:
            ancla = min(max(self.player.pos / SR, v0), v1)   # Zoom con botones: hacia el cabezal
        fraccion = (ancla - v0) / (v1 - v0)
        n0 = min(max(ancla - fraccion * largo, 0), dur - largo)
        self.vista = (n0, n0 + largo)
        self.pedir_redibujo()

    def ver_todo(self):
        if self.an is not None and self.vista != (0.0, self.an.duracion):
            self.vista = (0.0, self.an.duracion)
            self.pedir_redibujo()

    def rueda(self, e):
        self.zoom(1 / 1.2 if e.delta > 0 else 1.2, e.x)

    def rueda_h(self, e):
        v0, v1 = self.vista
        self.mover((v1 - v0) * (-0.12 if e.delta > 0 else 0.12))

    def mover(self, segundos):
        if self.an is None:
            return
        v0, v1 = self.vista
        largo = v1 - v0
        n0 = min(max(v0 + segundos, 0), self.an.duracion - largo)
        if abs(n0 - v0) < 1e-9:
            return
        self.vista = (n0, n0 + largo)
        self.pedir_redibujo()

    def desplazar(self, *args):
        if self.an is None:
            return
        v0, v1 = self.vista
        largo, dur = v1 - v0, self.an.duracion
        if args[0] == "moveto":
            n0 = float(args[1]) * dur
        else:
            n0 = v0 + int(args[1]) * largo * (0.8 if args[2] == "pages" else 0.1)
        n0 = min(max(n0, 0), dur - largo)
        if abs(n0 - v0) < 1e-9:
            return
        self.vista = (n0, n0 + largo)
        self.pedir_redibujo()

    # ================================================================ transporte

    def tecla_global(self, e, accion):
        """Atajos de teclado, salvo cuando se está escribiendo en un campo."""
        if isinstance(e.widget, (tk.Entry, tk.Text)):
            return
        accion()
        return "break"

    def play_pausa(self):
        if self.an is None:
            return
        if self.player.sonando:
            self.player.pausar()
            self.estado("En pausa.")
            return
        self.player.con_cortes = self.var_escucha.get() == "Con cortes"
        try:
            self.player.reproducir()
        except Exception as e:
            self.estado(f"No se puede reproducir audio: {e}")
            return
        self.estado("Reproduciendo con los cortes…" if self.player.con_cortes
                    else "Reproduciendo el original…")

    def cambio_escucha(self):
        self.player.con_cortes = self.var_escucha.get() == "Con cortes"
        self.mostrar_ayuda("vista")

    def ir_a(self, t):
        if self.an is None:
            return
        self.player.pos = int(min(max(t, 0), self.an.duracion) * SR)
        self.dibujar_cabezal()

    def saltar(self, segundos):
        if self.an is not None:
            self.ir_a(self.player.pos / SR + segundos)
            self.seguir_cabezal()

    def corte_vecino(self, direccion):
        """Lleva el cabezal al inicio del tramo anterior o siguiente."""
        if self.an is None or not self.tramos:
            return
        pos = self.player.pos
        inicios = [i for i, _ in self.tramos]
        if direccion > 0:
            destino = next((i for i in inicios if i > pos + SR // 20), None)
        else:
            destino = next((i for i in reversed(inicios) if i < pos - SR // 4), 0)
        if destino is not None:
            self.ir_a(destino / SR)
            self.seguir_cabezal()

    def seguir_cabezal(self):
        t = self.player.pos / SR
        v0, v1 = self.vista
        if not v0 <= t <= v1:
            largo = v1 - v0
            n0 = min(max(t - largo * 0.3, 0), self.an.duracion - largo)
            self.vista = (n0, n0 + largo)
            self.pedir_redibujo()

    # ================================================================ exportar

    def exportar(self):
        if not self.tramos or self.ocupado:
            return
        self.mostrar_ayuda("exportar")
        cfg = self.leer_ajustes()
        if cfg["modo"] == "limpiar" and self.indice_pista() == 0:
            messagebox.showwarning("Cortador", "Limpiar voz necesita que tu micrófono esté en una "
                                   "pista distinta de la 1. Para este video usa el modo Cortar.")
            return
        self.cfg = cfg
        cortar.guardar_config(cfg)
        fps = self.info["fps"]
        total = round(self.info["duracion"] * fps)
        frames = cortar.a_frames(self.tramos, fps, total)
        ruta, info, indice, gen = self.ruta, self.info, self.indice_pista(), self.generacion
        marcas = self.marcas_activas(cfg) if cfg.get("marcar_muletillas") else None
        self.empezar("exportar", "Exportando…" + ("  (extrayendo pistas de audio a WAV)"
                                                  if len(info["pistas"]) > 1 else ""))

        def tarea():
            try:
                destino = cortar.exportar(ruta, info, frames, cfg["modo"], indice,
                                          lambda x: self.cola.put(("progreso", gen, x)), marcas=marcas)
                cortar.log(f"{ruta} modo={cfg['modo']} pista={indice + 1} tramos={len(frames)} "
                           f"preciso={cfg['modo_preciso']} (ventana)")
                self.cola.put(("exportado", gen, (destino, len(marcas) if marcas else 0)))
            except Exception as e:
                cortar.log(f"Exportar {ruta}\n{traceback.format_exc()}")
                self.cola.put(("error", gen, f"No pude exportar: {e}"))
        threading.Thread(target=tarea, daemon=True).start()

    def abrir_carpeta(self):
        if self.ultimo_destino:
            subprocess.Popen(["explorer", "/select,", str(self.ultimo_destino)])

    # ================================================================ tareas en segundo plano

    def empezar(self, nombre, texto, cancelable=False):
        self.ocupado = nombre
        self.barra_prog.set(0)
        self.estado(texto)
        if cancelable:
            self.btn_cancelar.pack(side="right", padx=6, before=self.btn_carpeta)
        self.actualizar_habilitados()

    def terminar(self, texto):
        self.ocupado = None
        self.barra_prog.set(1)
        self.btn_cancelar.pack_forget()
        self.estado(texto)
        self.actualizar_habilitados()

    def estado(self, texto):
        self.lbl_estado.configure(text=texto)

    def revisar_cola(self):
        try:
            while True:
                tipo, gen, dato = self.cola.get_nowait()
                if gen != self.generacion:
                    continue
                if tipo == "progreso":
                    self.barra_prog.set(dato)
                    if self.ocupado == "whisper" and dato > 0.02:
                        pasado = time.time() - self.inicio_whisper
                        falta = pasado * (1 - dato) / dato
                        texto = f"Whisper {dato:.0%} · faltan unos {cortar.mmss(falta)}"
                        self.estado(texto)
                        self.lbl_palabras.configure(text=texto)
                elif tipo == "analizado":
                    self.al_analizar(*dato)
                elif tipo == "palabras":
                    self.lbl_palabras.configure(text=f"Palabras: {len(dato)} ubicadas y guardadas "
                                                     "(la próxima vez cargan al instante)")
                    self.marcas = cortar.detectar_marcas(self.an)
                    self.terminar("Whisper listo: el modo preciso y las muletillas ya usan las palabras.")
                    self.recalcular()
                elif tipo == "cancelado":
                    self.vars["modo_preciso"]["var"].set(False)
                    self.vars["marcar_muletillas"]["var"].set(False)
                    self.lbl_palabras.configure(text="Palabras: análisis cancelado")
                    self.terminar("Whisper cancelado. Se usa el análisis normal, sin marcas.")
                    self.recalcular()
                elif tipo == "exportado":
                    destino, n_marcas = dato
                    self.ultimo_destino = destino
                    self.btn_carpeta.configure(state="normal")
                    if n_marcas:
                        self.terminar(f"Listo: {destino.name} + {n_marcas} marcas en …_marcadores.edl  ·  "
                                      "Importa la línea de tiempo y luego los marcadores (ver ⓘ)")
                        self.mostrar_ayuda("exportar")
                    else:
                        self.terminar(f"Listo: {destino.name}  ·  En DaVinci: Archivo > Importar > "
                                      "Línea de tiempo…")
                elif tipo == "error":
                    self.terminar("Hubo un error.")
                    messagebox.showerror("Cortador", f"{dato}\n\nDetalle en {cortar.LOG}")
        except queue.Empty:
            pass
        self.after(80, self.revisar_cola)

    def cerrar(self):
        self.player.detener()
        self.cancelar.set()
        try:
            cortar.guardar_config(self.leer_ajustes())
        except Exception:
            pass
        self.destroy()


# ================================================================ utilidades

def envolvente(audio):
    """Amplitud máxima de cada bloque de 10 ms, normalizada, para dibujar la onda."""
    n = len(audio) // cortar.HOP
    amp = np.abs(audio[:n * cortar.HOP]).reshape(n, cortar.HOP).max(axis=1)
    tope = float(np.percentile(amp, 99.5)) if n else 1.0
    App.tope = max(tope, 1e-6)
    return np.clip(amp / App.tope, 0, 1).astype(np.float32)


def regla(largo):
    """Separación cómoda entre las marcas de tiempo según el zoom."""
    for paso in (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800):
        if largo / paso <= 12:
            return paso
    return 3600


def formato_t(t, paso):
    if paso >= 1:
        return cortar.mmss(t)
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}"


def main():
    ctk.set_appearance_mode("dark")
    try:
        app = App(sys.argv[1:])
    except Exception:
        detalle = traceback.format_exc()
        cortar.log(f"Error al abrir la ventana\n{detalle}")
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("Cortador de Silencios",
                             f"No se pudo abrir la ventana:\n\n{detalle[-700:]}\n"
                             f"Detalle en {cortar.LOG}")
        return
    app.mainloop()


if __name__ == "__main__":
    main()
