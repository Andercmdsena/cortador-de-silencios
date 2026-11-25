"""Detección de muletillas, reinicios y palabras repetidas a partir de las
palabras de Whisper (con su texto y tiempos). No corta nada: devuelve marcas
para revisar en DaVinci.

Cada marca es un dict: {"tipo", "inicio", "fin", "texto", "detalle"} en segundos.
Tipos:
  "sonora"     Muletilla sin significado: eh, ehh, ahh, mmm, em, "o, o"…
  "discurso"   Muletilla con palabras: o sea, este (seguido de pausa), bueno, pues…
  "reinicio"   Frase empezada y repetida enseguida: "es una… es una grabación".
               La marca cubre el primer intento (lo que normalmente se borra).
  "repetida"   Palabra usada muchas veces en poco tiempo: específicamente ×4.
"""
import re

import numpy as np

# Pista para Whisper: con estas palabras al inicio, transcribe las muletillas
# en vez de "limpiarlas" del texto.
PROMPT_MULETILLAS = "Eh, este... o sea, mmm, pues, eh... bueno, este, ¿no? Ehh, o sea, mmm."

SONORA = re.compile(r"^(e+h*|a+h+|a{2,}|m{2,}|e+m+|u+m+|u{2,}h*|o+h+|ah|eh|em|mm+)$")
# Muletillas de discurso: (palabras, condición). "pausa": solo si después hay coma,
# puntos suspensivos o un silencio; "siempre": siempre se marca.
DISCURSO = [
    (("o", "sea"), "siempre"),
    (("es", "decir"), "pausa"),
    (("este",), "pausa"),
    (("esto",), "pausa"),
    (("bueno",), "pausa"),
    (("pues",), "pausa"),
    (("entonces",), "pausa"),
    (("como",), "pausa"),
    (("digamos",), "pausa"),
    (("osea",), "siempre"),
    (("no",), "pregunta"),        # "¿no?" al final de una frase
    (("vale",), "pregunta"),
    (("cierto",), "pregunta"),
]
VACIAS = {"a", "al", "de", "del", "el", "la", "las", "los", "lo", "un", "una", "unos", "unas",
          "y", "e", "o", "u", "que", "en", "es", "se", "me", "te", "le", "mi", "tu", "su", "no",
          "por", "para", "con", "muy", "ya", "si", "sí", "más", "pero", "como", "eso", "esto",
          "este", "esta", "va", "voy", "hay", "está", "son", "fue", "ha", "he", "nos", "les"}
PAUSA = 0.25           # Segundos de silencio que cuentan como "pausa" tras una palabra

TIPOS = {   # tipo: (nombre en el marcador, color de DaVinci, color en la vista previa)
    "sonora": ("Muletilla sonora", "ResolveColorRed", "#EF4444"),
    "discurso": ("Muletilla", "ResolveColorYellow", "#F59E0B"),
    "reinicio": ("Reinicio", "ResolveColorPurple", "#A855F7"),
    "repetida": ("Repetida", "ResolveColorCyan", "#22D3EE"),
}


def normal(texto):
    return re.sub(r"[^\wáéíóúñü]", "", texto.lower())


def _tras_pausa(palabras, i):
    """¿La palabra i va seguida de puntuación o de un silencio?"""
    texto = palabras[i][2]
    if re.search(r"[,.;:!?…]$", texto) or texto.endswith("..."):
        return True
    return i + 1 >= len(palabras) or palabras[i + 1][0] - palabras[i][1] >= PAUSA


def _antes_pausa(palabras, i):
    return i == 0 or palabras[i][0] - palabras[i - 1][1] >= PAUSA or \
        re.search(r"[,.;:!?…]$", palabras[i - 1][2]) is not None


def detectar(palabras, frase_min=1, repetida_min=4, ventana_repetida=20.0):
    """palabras: lista de (inicio, fin, texto). Devuelve la lista de marcas."""
    marcas = []
    w = [normal(p[2]) for p in palabras]
    usadas = set()

    def marcar(tipo, i, j, detalle):
        marcas.append({"tipo": tipo, "inicio": palabras[i][0], "fin": palabras[j][1],
                       "texto": " ".join(p[2] for p in palabras[i:j + 1]).strip(" ,.…"),
                       "detalle": detalle})
        usadas.update(range(i, j + 1))

    # 1) Muletillas sonoras, y letras sueltas repetidas ("o, o", "y, y")
    for i, palabra in enumerate(w):
        if palabra and SONORA.match(palabra):
            marcar("sonora", i, i, "Sonido de duda")
        elif palabra in ("o", "y", "e", "a") and i + 1 < len(w) and w[i + 1] == palabra:
            marcar("sonora", i, i + 1, "Letra repetida mientras se piensa")

    # 2) Muletillas de discurso
    for i in range(len(w)):
        if i in usadas:
            continue
        for frase, condicion in DISCURSO:
            n = len(frase)
            if tuple(w[i:i + n]) != frase:
                continue
            j = i + n - 1
            if condicion == "siempre":
                ok = True
            elif condicion == "pausa":
                ok = _tras_pausa(palabras, j)
            else:   # pregunta: "¿no?" al cerrar una frase
                ok = palabras[i][2].endswith("?") or (
                    _tras_pausa(palabras, j) and not _antes_pausa(palabras, i) and w[i] != "no"
                ) or palabras[i][2].startswith("¿")
            if ok:
                marcar("discurso", i, j, "Muletilla")
                break

    # 3) Reinicios: la misma secuencia de 1 a 6 palabras dicha dos veces seguidas
    i = 0
    while i < len(w):
        hecho = False
        for k in range(6, 0, -1):
            a, b = w[i:i + k], w[i + k:i + 2 * k]
            if len(b) < k or a != b or not all(a):
                continue
            if k == 1 and (a[0] in VACIAS and a[0] not in ("es",)):
                continue                      # "o, o" ya es sonora; "que que" no siempre
            hueco = palabras[i + k][0] - palabras[i + k - 1][1]
            if hueco > 2.0:
                continue
            # Repeticiones seguidas (aló, aló, aló): marcar todas menos la última
            fin = i + k
            while w[fin:fin + k] == a and fin + k <= len(w) and w[fin + k:fin + 2 * k] == a:
                fin += k
            marcar("reinicio", i, fin - 1, f"Se repite «{' '.join(palabras[q][2] for q in range(i, i + k)).strip(' ,.…')}»"
                                           " (se suele borrar el primer intento)")
            i = fin
            hecho = True
            break
        if not hecho:
            i += 1

    # 4) Palabras con contenido usadas muchas veces en poco tiempo
    vistas = {}
    for i, palabra in enumerate(w):
        if len(palabra) < 5 or palabra in VACIAS:
            continue
        vistas.setdefault(palabra, []).append(i)
    for palabra, indices in vistas.items():
        # Agrupar apariciones cercanas (cada una a menos de `ventana_repetida` de la anterior)
        grupos, grupo = [], []
        for i in indices:
            if grupo and palabras[i][0] - palabras[grupo[-1]][0] > ventana_repetida:
                grupos.append(grupo)
                grupo = []
            grupo.append(i)
        grupos.append(grupo)
        for grupo in grupos:
            if len(grupo) < repetida_min:
                continue
            lapso = palabras[grupo[-1]][0] - palabras[grupo[0]][0]
            for g in grupo:
                if g not in usadas:
                    marcar("repetida", g, g, f"«{palabra}» {len(grupo)} veces en {lapso:.0f} s")

    # 5) Misma palabra vacía al inicio de varias frases seguidas ("que el…, que el…, que las…")
    iniciales = [i for i in range(len(w)) if w[i] and _antes_pausa(palabras, i) and i not in usadas]
    racha = []
    for i in iniciales:
        if racha and w[i] == w[racha[-1]] and palabras[i][0] - palabras[racha[-1]][0] <= 8:
            racha.append(i)
        else:
            if len(racha) >= repetida_min:
                for g in racha:
                    marcar("repetida", g, g, f"«{w[racha[0]]}» al inicio de {len(racha)} frases seguidas")
            racha = [i]
    if len(racha) >= repetida_min:
        for g in racha:
            marcar("repetida", g, g, f"«{w[racha[0]]}» al inicio de {len(racha)} frases seguidas")

    return sorted(marcas, key=lambda m: m["inicio"])


HUECO = 10         # 100 ms sin voz separan dos ráfagas (las "p", "t", "c" hacen silencios más cortos)


def _umbral_local(an, f0, f1):
    """Nivel a partir del cual algo es "voz fuerte" cerca de [f0, f1]: 20 dB por
    debajo de lo fuerte que hablas en esa zona. Un respiro o el ruido entre dos
    palabras queda por debajo, aunque sea audible."""
    zona = an.energia[max(f0 - 150, 0):min(f1 + 150, len(an.energia))]
    if not len(zona):
        return an.piso + 10
    return max(an.piso + 10, float(np.percentile(zona, 95)) - 20)


def _bloques(an, f0, f1, umbral):
    """Ráfagas de voz (por encima de `umbral`, con huecos de menos de 100 ms)
    que tocan [f0, f1], en bloques de 10 ms. Cada ráfaga se extiende hacia
    afuera sin límite para saber dónde empieza y termina de verdad."""
    energia = an.energia
    bloques, f = [], max(f0, 0)
    f1 = min(f1, len(energia) - 1)
    while f <= f1:
        if energia[f] <= umbral:
            f += 1
            continue
        ini, quieto = f, 0
        while ini > 0 and quieto <= HUECO:
            ini -= 1
            quieto = quieto + 1 if energia[ini] <= umbral else 0
        ini = ini + quieto if quieto > HUECO else ini
        fin, quieto = f, 0
        while fin < len(energia) - 1 and quieto <= HUECO:
            fin += 1
            quieto = quieto + 1 if energia[fin] <= umbral else 0
        fin -= quieto
        bloques.append((ini, fin))
        f = fin + HUECO + 1
    return bloques


def ubicar(an, inicio, fin, anterior):
    """Whisper a veces estira una palabra sobre la pausa o el respiro anterior, o
    la corre hacia la siguiente. Se parte el audio en ráfagas de voz (separadas
    por respiros o silencios) y se toma la que más se superpone con la marca.
    Devuelve (inicio, fin) ajustados, en segundos.
    Si esa ráfaga también contiene la palabra anterior (habla fluida, sin pausa),
    no se puede saber dónde empieza: se deja el inicio de Whisper."""
    f0, f1 = int(inicio * 100), int(fin * 100)
    umbral = _umbral_local(an, f0, f1)
    mejor, solape = None, 0
    for b in _bloques(an, f0 - 30, f1 + 10, umbral):
        fuertes = int(np.sum(an.energia[max(b[0], f0):min(b[1], f1) + 1] > umbral))
        if fuertes > solape:
            mejor, solape = b, fuertes
    if mejor is None:
        return inicio, fin
    b0, b1 = mejor[0] / 100, (mejor[1] + 1) / 100
    nuevo_inicio = b0 if b0 >= anterior - 0.1 else max(inicio, b0)
    # El final: donde termina la ráfaga, sin pasar mucho del final de Whisper
    nuevo_fin = min(b1, max(fin, nuevo_inicio) + 0.15) if b1 > nuevo_inicio else fin
    return round(nuevo_inicio, 2), round(max(nuevo_fin, nuevo_inicio + 0.1), 2)


def ajustar(an, palabras, marcas):
    """Corrige inicio y fin de cada marca a la ráfaga de voz real."""
    inicios = [p[0] for p in palabras]
    for m in marcas:
        n = inicios.index(m["inicio"]) if m["inicio"] in inicios else None
        anterior = palabras[n - 1][1] if n else -1.0
        m["inicio_whisper"], m["fin_whisper"] = m["inicio"], m["fin"]
        m["inicio"], m["fin"] = ubicar(an, m["inicio"], m["fin"], anterior)
    return marcas
