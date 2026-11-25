"""Textos de ayuda de la ventana: (título, explicación completa).

Cada opción tiene además una línea corta debajo del control (SUBTITULOS).
"""

SUBTITULOS = {
    "pista": "La pista de audio donde está tu voz. Las demás se cortan igual, sin analizarlas.",
    "modo": "Cortar acorta el video. Limpiar voz no toca el video: solo silencia tu micrófono "
            "entre frases.",
    "margen_inicio_ms": "Colchón antes de cada frase. Más alto = entradas más suaves, pero "
                        "el video queda más largo.",
    "margen_final_ms": "Colchón después de cada frase. Si los cortes suenan bruscos, súbelo.",
    "pausas": "Quitar elimina las pausas largas. Acortar deja un pedacito de cada una para "
              "conservar el ritmo.",
    "pausa_ms": "Duración que queda de cada pausa larga (además de los márgenes). "
                "Solo con Acortar.",
    "silencio_min_ms": "Pausas más cortas que esto se dejan intactas. Más bajo = más cortes "
                       "y habla más acelerada.",
    "sensibilidad": "Más bajo detecta la voz más bajita, pero también deja pasar más ruido.",
    "voz_min_ms": "Sonidos más cortos que esto no cuentan como voz (clics, golpes).",
    "limpiar_bordes": "Los márgenes no se extienden sobre clics o respiros pegados a una frase.",
    "quitar_respiros": "Corta los respiros entre frases. En modo Cortar deja cortes más "
                       "seguidos.",
    "modo_preciso": "Corta al final de la última palabra usando Whisper. Tarda MINUTOS en vez "
                    "de segundos.",
    "margen_preciso_ms": "Silencio que se deja después de la última palabra en modo preciso.",
}

AYUDA = {
    "general": (
        "Cómo se usa",
        "1. Elige un video con «Elegir video».\n"
        "2. El programa analiza tu voz (unos segundos) y dibuja la vista previa abajo: "
        "verde es lo que se conserva y gris lo que se quita.\n"
        "3. Mueve los ajustes: la vista previa se actualiza al instante, sin volver a "
        "analizar.\n"
        "4. Haz clic en la onda para poner el cabezal y pulsa Espacio para escuchar cómo "
        "queda («Con cortes») o cómo era («Original»).\n"
        "5. Cuando te guste, «Exportar a DaVinci». Se crea un .fcpxml junto al video.\n"
        "6. En DaVinci: Archivo > Importar > Línea de tiempo… y eliges ese archivo.\n\n"
        "Tu video original nunca se modifica: el .fcpxml solo le dice a DaVinci qué "
        "pedazos usar.\n\n"
        "Haz clic en el ⓘ de cualquier opción (o cámbiala) para ver aquí su explicación "
        "completa. Se queda fija mientras ajustas."),
    "pista": (
        "Pista del micrófono",
        "OBS puede grabar varias pistas de audio en el mismo video (por ejemplo, la 1 con "
        "el juego o el escritorio y la 2 con tu micrófono).\n\n"
        "Aquí eliges en cuál está tu voz. Solo esa se analiza para decidir dónde cortar; "
        "las demás pistas se cortan exactamente en los mismos puntos, así todo queda "
        "sincronizado.\n\n"
        "Si eliges la pista equivocada, el programa buscará voz en el audio del juego y "
        "los cortes no tendrán sentido.\n\n"
        "Si el video tiene una sola pista, esta opción no se puede cambiar."),
    "modo": (
        "Modo",
        "CORTAR (lo normal para tutoriales y videos hablados)\n"
        "Quita los silencios de todas las pistas a la vez: video, tu voz y el audio del "
        "juego. El video final es más corto y todo sigue sincronizado.\n\n"
        "LIMPIAR VOZ (pensado para gameplay)\n"
        "No corta nada del video ni del juego: dura exactamente lo mismo. Solo tu pista "
        "de micrófono queda partida en pedazos, con huecos donde no hablas. Sirve para "
        "quitar ruidos, respiros y clics de tu micrófono sin perder ni un segundo de "
        "partida.\n\n"
        "Limpiar voz necesita que tu micrófono esté en una pista distinta de la 1. En la "
        "vista previa, el gris de este modo significa «micrófono en silencio», no «se "
        "quita del video»."),
    "margen_inicio_ms": (
        "Margen al inicio",
        "Cuánto tiempo se deja antes de que empieces a hablar en cada frase.\n\n"
        "• Más alto: las entradas suenan más naturales y nunca se come el arranque de "
        "una palabra, pero el video queda un poco más largo.\n"
        "• Más bajo: cortes más ajustados y ritmo más rápido; con valores muy bajos "
        "pueden perderse sonidos suaves al empezar (una «s» o una «f»).\n\n"
        "Valor recomendado: 150–250 ms.\n\n"
        "Si «No incluir clics ni respiros» está activado, el margen se detiene antes de "
        "un clic o un respiro aunque el valor sea más alto."),
    "margen_final_ms": (
        "Margen al final",
        "Cuánto tiempo se deja después de terminar cada frase.\n\n"
        "Es el ajuste más importante para que los cortes no suenen bruscos: las palabras "
        "se van apagando poco a poco y un corte justo ahí se nota.\n\n"
        "• Más alto: finales suaves y naturales; el video queda más largo.\n"
        "• Más bajo: ritmo más rápido, estilo shorts; puede sonar cortado.\n\n"
        "Valor recomendado: 300–450 ms.\n\n"
        "Igual que el de inicio, se detiene antes de clics y respiros si esa opción está "
        "activada."),
    "pausas": (
        "Pausas largas",
        "Qué hacer con las pausas largas entre frases (solo en modo Cortar).\n\n"
        "QUITAR: se eliminan por completo. Entre una frase y la siguiente solo quedan "
        "los márgenes. Es lo más rápido, pero si haces muchas pausas el habla puede "
        "sentirse acelerada, sin respirar.\n\n"
        "ACORTAR: de cada pausa larga se deja un pedacito (el valor de «Dejar pausas "
        "de»), tomado de la parte más silenciosa de esa pausa. Conserva el ritmo natural "
        "y es lo que hace un editor a mano. El video queda un poco más largo.\n\n"
        "En modo Limpiar voz esta opción no aplica, porque el video no se corta."),
    "pausa_ms": (
        "Dejar pausas de",
        "Con «Acortar», cuánto dura cada pausa larga después de recortarla.\n\n"
        "Se suma a los márgenes: con margen final de 350 ms, margen de inicio de 200 ms "
        "y pausas de 400 ms, entre dos frases quedan unos 950 ms en total.\n\n"
        "• 200–400 ms: ritmo ágil pero respirado.\n"
        "• 600–1000 ms: pausas dramáticas o para dar tiempo a leer algo en pantalla.\n\n"
        "Las pausas que ya eran más cortas que esto no se alargan."),
    "silencio_min_ms": (
        "Pausa mínima a cortar",
        "Las pausas más cortas que este valor se dejan intactas, porque son parte del "
        "ritmo normal al hablar (entre palabras o al tomar aire rápido).\n\n"
        "• Más bajo (300–400 ms): corta casi cualquier pausa; el video queda más corto "
        "pero el habla puede sonar atropellada y con más cortes.\n"
        "• Más alto (800–1500 ms): solo quita los silencios largos de verdad; suena muy "
        "natural pero quedan más pausas.\n\n"
        "Valor recomendado: 500 ms.\n\n"
        "Excepción: si «Quitar respiros» está activado, una pausa corta que tenga un "
        "respiro dentro sí se corta."),
    "sensibilidad": (
        "Sensibilidad",
        "Qué tan seguro debe estar el detector de IA (Silero VAD) para decidir que algo "
        "es tu voz.\n\n"
        "• Más bajo (0.30–0.40): detecta frases dichas muy bajito o susurradas, pero "
        "puede tomar ruidos, música o el juego como voz.\n"
        "• Más alto (0.60–0.70): solo voz clara; puede perder frases bajitas o el final "
        "de algunas frases.\n\n"
        "Valor recomendado: 0.50. Bájalo si notas que se come frases dichas bajito."),
    "voz_min_ms": (
        "Ignorar sonidos cortos",
        "Un sonido detectado como voz que dure menos que esto se descarta.\n\n"
        "Sirve para que un golpe en la mesa, un clic del mouse o una tos muy corta no "
        "se conviertan en un pedacito suelto de video.\n\n"
        "• Más alto: menos pedacitos sueltos, pero se pueden perder palabras muy cortas "
        "dichas solas («sí», «ya»).\n"
        "• Más bajo: conserva todo, incluidos algunos ruidos.\n\n"
        "Valor recomendado: 150 ms."),
    "limpiar_bordes": (
        "No incluir clics ni respiros pegados a las frases",
        "ACTIVADO (recomendado): antes y después de cada frase, el programa revisa el "
        "sonido. Si justo antes de hablar tomas aire o haces un clic con la boca, o "
        "justo después exhalas o resoplas por la nariz, el corte se hace antes de ese "
        "sonido aunque el margen sea más largo. Para distinguirlo de tu voz usa el tono: "
        "al hablar tus cuerdas vocales vibran; un respiro es solo aire.\n\n"
        "Protecciones: siempre deja al menos 40 ms antes y 60 ms después de la voz, y no "
        "corta las «s» finales (son más agudas que un respiro).\n\n"
        "DESACTIVADO: los márgenes se aplican completos, incluya lo que incluya. Útil si "
        "notas que algún final suena cortado."),
    "quitar_respiros": (
        "Quitar respiros en las pausas cortas",
        "Normalmente, una pausa más corta que «Pausa mínima a cortar» se deja intacta. "
        "Con esta opción, si dentro de esa pausa hay un respiro o un clic, la frase se "
        "parte ahí y el respiro se quita.\n\n"
        "• En modo LIMPIAR VOZ: muy recomendable. Solo silencia el respiro en tu "
        "micrófono; el video no cambia.\n"
        "• En modo CORTAR: quita los respiros, pero cada uno se convierte en un corte del "
        "video. Si respiras mucho entre frases puedes notar saltos seguidos en la imagen "
        "o un habla entrecortada. Si pasa, desactívala.\n\n"
        "Escucha el resultado en la vista previa para decidir."),
    "modo_preciso": (
        "Modo preciso (Whisper)",
        "Usa Whisper (el modelo de transcripción «small», en tu PC) para saber dónde "
        "está cada palabra. Cada frase termina donde se apaga la última palabra, aunque "
        "después venga un sonido con tono que el análisis normal confunde con voz: un "
        "suspiro, un «mmm», una risa corta. Además descarta los tramos que no tienen "
        "ninguna palabra.\n\n"
        "⚠ TARDA MUCHO MÁS: el análisis normal toma segundos; Whisper toma MINUTOS. En "
        "el procesador (Whisper corre en CPU), calcula aproximadamente de 1 a 3 minutos por cada 10 "
        "minutos de video (un video de 1 hora puede tardar de 6 a 20 minutos). Durante "
        "ese tiempo el procesador trabaja al máximo. La barra de progreso muestra cuánto "
        "falta y puedes cancelar en cualquier momento.\n\n"
        "Solo se hace una vez por video: el resultado se guarda en la carpeta "
        "«_pistas» del video y la próxima vez carga al instante.\n\n"
        "La primera vez que se usa Whisper en un PC se descarga el modelo «small» "
        "(~480 MB, necesita internet). Queda guardado en "
        "%APPDATA%\\CortadorDeSilencios\\modelos.\n\n"
        "La misma pasada de Whisper sirve para «Marcar muletillas».\n\n"
        "Límites: Whisper ubica muy bien el final de las palabras pero no siempre el "
        "comienzo, así que el inicio de cada frase lo sigue decidiendo el análisis del "
        "sonido. Las risas o exclamaciones sin palabras se quitan."),
    "margen_preciso_ms": (
        "Margen tras la última palabra",
        "En modo preciso, cuánto silencio se deja después de que se apaga la última "
        "palabra de cada frase.\n\n"
        "Solo se agrega sobre silencio: si justo después viene un suspiro, el margen se "
        "detiene antes de él.\n\n"
        "• Más alto: finales más suaves.\n"
        "• Más bajo: cortes más ajustados.\n\n"
        "Valor recomendado: 40–100 ms. Es más corto que el margen normal porque aquí el "
        "final ya está medido con precisión."),
    "vista": (
        "Vista previa y reproducción",
        "La onda es tu pista de micrófono.\n\n"
        "• Verde: lo que se conserva.\n"
        "• Gris sobre fondo rojizo: lo que se quita (en Limpiar voz: donde tu micrófono "
        "queda en silencio).\n\n"
        "CABEZAL ROJO (como en DaVinci)\n"
        "• Clic en la onda: lleva el cabezal a ese punto.\n"
        "• Arrastrar: mueve el cabezal; si está sonando, sigue desde donde lo sueltes.\n\n"
        "REPRODUCCIÓN\n"
        "• ▶ / Espacio: reproducir o pausar desde el cabezal, sin límite de tiempo.\n"
        "• −2 s / +2 s (o flechas ← →): saltar 2 segundos.\n"
        "• ⏮ / ⏭: ir al corte anterior o al siguiente.\n"
        "• «Con cortes» suena como quedará el video (salta lo que se quita). "
        "«Original» suena sin cortes, para comparar.\n\n"
        "ZOOM\n"
        "• Rueda del mouse: acercar o alejar donde está el puntero.\n"
        "• Shift + rueda o la barra de abajo: moverse.\n"
        "• «Ver todo»: el video completo.\n\n"
        "El audio de la vista previa es de menor calidad (16 kHz), solo para juzgar los "
        "cortes. El resultado en DaVinci usa tu audio original."),
    "presets": (
        "Ajustes rápidos",
        "Configuran de un clic los márgenes y las pausas para un tipo de video. Después "
        "puedes afinar cualquier valor; si cambias algo, el ajuste rápido deja de estar "
        "marcado («personalizado»).\n\n"
        "TUTORIAL\n"
        "Modo Cortar, márgenes cómodos (200 ms al inicio, 400 ms al final) y pausas "
        "acortadas a 400 ms en vez de quitadas: ritmo natural y fácil de seguir. No parte "
        "las frases por los respiros, para evitar saltos seguidos en la imagen.\n\n"
        "GAMEPLAY\n"
        "Modo Limpiar voz: la partida no se corta, solo se silencia tu micrófono entre "
        "frases, incluidos respiros y clics. Necesita el micrófono en una pista aparte.\n\n"
        "SHORTS / AGRESIVO\n"
        "Modo Cortar con márgenes cortos (100 / 200 ms), pausas quitadas por completo y "
        "pausa mínima de 300 ms: ritmo rápido, estilo TikTok o Shorts. Puede sonar "
        "acelerado en videos largos.\n\n"
        "Ninguno toca la sensibilidad ni el modo preciso."),
    "marcar_muletillas": (
        "Marcar muletillas en DaVinci",
        "Transcribe lo que dices con Whisper y pone un marcador de color en DaVinci en "
        "cada muletilla. No corta nada: tú decides qué quitar.\n\n"
        "🔴 SONORAS: sonidos de duda sin significado («eh», «ehh», «mmm», «o, o»).\n"
        "🟡 MULETILLAS: «o sea» siempre; «este», «bueno», «pues», «entonces», «como» solo "
        "si van seguidas de una pausa o coma («este programa» no se marca); «¿no?» al "
        "cerrar una frase.\n"
        "🟣 REINICIOS: empiezas una frase y la repites enseguida («es una… es una "
        "grabación»). La marca cubre el primer intento, que es lo que se suele borrar.\n"
        "🔵 REPETIDAS: la misma palabra 4 o más veces en 20 segundos («específicamente» "
        "×4), o la misma palabra al inicio de varias frases seguidas («que el televisor, "
        "que el armario, que las…»).\n\n"
        "Las casillas eligen qué tipos se marcan; los triángulos de colores en la regla de "
        "la vista previa muestran dónde caen.\n\n"
        "⚠ Usa Whisper: tarda MINUTOS la primera vez (aprox. 1–3 min por cada 10 min de "
        "video, según el procesador). Después queda guardado y carga al instante.\n\n"
        "Al exportar se crea un archivo …_marcadores.edl junto al .fcpxml (DaVinci no lee "
        "los marcadores dentro del .fcpxml). Cómo importarlo: ver «Exportar a DaVinci»."),
    "exportar": (
        "Exportar a DaVinci",
        "Crea junto al video un archivo .fcpxml con los cortes que ves en la vista "
        "previa.\n\n"
        "MARCADORES DE MULETILLAS (si «Marcar muletillas» está activado)\n"
        "Se crea además un archivo …_marcadores.edl. Después de importar la línea de "
        "tiempo:\n"
        "1. En el Panel multimedia, clic derecho sobre la línea de tiempo importada.\n"
        "2. Líneas de tiempo > Importar > Marcadores de línea de tiempo desde EDL… (en "
        "algunas versiones está en Archivo > Importar).\n"
        "3. Elige el …_marcadores.edl. Aparecen arriba, en la regla, con su color.\n\n"
        "Si el video tiene varias pistas de audio, también crea una carpeta «_pistas» "
        "con cada pista extra en WAV, porque DaVinci solo toma la primera pista de un "
        "video al importar un .fcpxml. No la borres: la línea de tiempo la usa.\n\n"
        "En DaVinci: Archivo > Importar > Línea de tiempo… y eliges el .fcpxml. Si ya "
        "habías importado una versión anterior, borra esa línea de tiempo primero."),
}
