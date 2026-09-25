# -*- coding: utf-8 -*-
"""Estructura intermedia de qml2lyr.

Agnostica de origen (XML QGIS) y de destino (ArcObjects). El parser construye
estos objetos; el emisor los consume. Compatible Python 2.7.

Unidades (cambio de F2): anchos y tamanyos viajan SIEMPRE en PUNTOS. QGIS
declara la unidad de cada medida (MM, Point...) junto al valor, asi que la
conversion es responsabilidad del parser, que es quien ve esa declaracion.
El emisor recibe puntos y no convierte nada.
"""


class Contorno(object):
    """Contorno de un relleno o linea suelta."""

    def __init__(self, rgb=None, width_pt=0.0, style="solid"):
        # rgb: tupla (r, g, b) o None si el contorno es nulo (style "no")
        # style: "solid" | "dash" | "dot" | "no"
        self.rgb = rgb
        self.width_pt = width_pt
        self.style = style


class SimboloRelleno(object):
    """SimpleFill de QGIS: relleno solido o hueco con contorno."""

    def __init__(self, rgb=None, style="solid", contorno=None):
        # rgb: (r, g, b) del relleno; None si hueco
        # style: "solid" | "no" (hueco)
        self.rgb = rgb
        self.style = style
        self.contorno = contorno or Contorno()


class SimboloLinea(object):
    """SimpleLine de QGIS -> SimpleLineSymbol de ArcMap."""

    def __init__(self, rgb=None, width_pt=0.0, style="solid"):
        # style: "solid" | "dash" | "dot" | "dash dot" | "dash dot dot" | "no"
        # (los nombres son los de QGIS, con espacios; el emisor los mapea a
        # esriSimpleLineStyle)
        self.rgb = rgb
        self.width_pt = width_pt
        self.style = style


class SimboloMarcador(object):
    """SimpleMarker de QGIS -> SimpleMarkerSymbol de ArcMap."""

    def __init__(self, rgb=None, size_pt=0.0, forma="circulo",
                 contorno_rgb=None, contorno_pt=0.0, angulo=0.0):
        # forma: "circulo" | "cuadrado" | "cruz" | "equis" | "diamante"
        # contorno_pt == 0 -> el marcador se emite sin contorno
        # angulo: rotacion en grados (QGIS `angle`) -> IMarkerSymbol.Angle
        self.rgb = rgb
        self.size_pt = size_pt
        self.forma = forma
        self.contorno_rgb = contorno_rgb
        self.contorno_pt = contorno_pt
        self.angulo = angulo


class SimboloMarcadorCaracter(object):
    """SimpleMarker de QGIS con forma que ArcMap no tiene como SimpleMarker
    (triangulo, estrella, pentagono...) -> CharacterMarkerSymbol con un glifo
    de la fuente ESRI Default Marker.

    `char_relleno` es el glifo relleno (color `rgb`). El borde, si lo hay, se
    emite como HALO del glifo (`contorno_rgb`, `contorno_pt`). `size_pt` ya es
    tamanyo de FUENTE (el parser lo calibra a la caja del glifo), no el
    tamanyo de QGIS.
    """

    def __init__(self, rgb=None, size_pt=0.0, char_relleno=0,
                 contorno_rgb=None, contorno_pt=0.0, angulo=0.0,
                 fuente=u"ESRI Default Marker"):
        self.rgb = rgb
        self.size_pt = size_pt
        self.char_relleno = char_relleno
        self.contorno_rgb = contorno_rgb
        self.contorno_pt = contorno_pt
        self.angulo = angulo
        self.fuente = fuente


class SimboloTramado(object):
    """LinePatternFill de QGIS -> LineFillSymbol de ArcMap.

    `linea` es el SimboloLinea con el que se dibuja cada raya del tramado;
    `separacion_pt` es la distancia entre rayas y `contorno` el borde del
    poligono.
    """

    def __init__(self, angulo=45.0, separacion_pt=5.0, linea=None, contorno=None):
        self.angulo = angulo
        self.separacion_pt = separacion_pt
        self.linea = linea or SimboloLinea()
        self.contorno = contorno or Contorno(style="no")


class SimboloImagen(object):
    """RasterFill de QGIS -> PictureFillSymbol de ArcMap.

    Rellena el poligono repitiendo una imagen en mosaico. `imagen_bytes` son los
    bytes de la imagen (QGIS la embebe en base64 dentro del .qgz); `formato` es
    su tipo ('png', 'bmp'...). El emisor la vuelca a un temporal y la carga con
    CreateFillSymbolFromFile. `ancho_pt` es el ancho con el que QGIS dibuja el
    mosaico (para escalar la imagen); `angulo` su rotacion.
    """

    def __init__(self, imagen_bytes, formato="png", ancho_pt=0.0, angulo=0.0,
                 contorno=None):
        self.imagen_bytes = imagen_bytes
        self.formato = formato
        self.ancho_pt = ancho_pt
        self.angulo = angulo
        self.contorno = contorno or Contorno(style="no")


class SimboloMultiCapa(object):
    """Varias symbol-layers superpuestas -> MultiLayerFillSymbol de ArcMap.

    Es como QGIS dibuja Red Natura y los espacios protegidos: relleno hueco con
    borde + trama encima.

    `capas` va en ORDEN DE DIBUJO de QGIS: la primera es la de abajo y las
    siguientes se pintan encima.
    """

    def __init__(self, capas):
        self.capas = capas


class RendererSimple(object):
    """singleSymbol de QGIS -> SimpleRenderer de ArcMap."""

    def __init__(self, simbolo, label=u""):
        self.simbolo = simbolo
        self.label = label


class ClaseValor(object):
    """Una categoria de un renderer de valores unicos."""

    def __init__(self, valor, label, simbolo, variantes=None):
        self.valor = valor
        self.label = label
        self.simbolo = simbolo
        # Otros valores que ArcMap debe agrupar bajo esta clase (una sola
        # entrada de leyenda): los nulos de un valor compuesto de varios campos.
        self.variantes = variantes or []


class RendererValoresUnicos(object):
    """categorizedSymbol de QGIS -> UniqueValueRenderer de ArcMap.

    La categoria de QGIS sin valor (el "todos los demas") no es una clase mas:
    se traduce al simbolo por defecto del renderer de ArcMap.
    """

    def __init__(self, campos, clases, default_simbolo=None, default_label=u"",
                 separador=None):
        self.campos = campos
        self.clases = clases
        self.default_simbolo = default_simbolo
        self.default_label = default_label
        # FieldDelimiter de ArcMap cuando hay varios campos.
        self.separador = separador


class ClaseRango(object):
    """Un intervalo de un renderer graduado. Limites en unidades del campo."""

    def __init__(self, inferior, superior, label, simbolo):
        self.inferior = inferior
        self.superior = superior
        self.label = label
        self.simbolo = simbolo


class RendererGraduado(object):
    """graduatedSymbol de QGIS -> ClassBreaksRenderer de ArcMap.

    ArcMap no guarda el limite inferior de cada clase: guarda un corte por
    clase (su limite superior) mas un minimo global, y da por hecho que las
    clases son contiguas y ascendentes. El parser lo comprueba antes de emitir.
    """

    def __init__(self, campo, rangos):
        self.campo = campo
        self.rangos = rangos  # ordenados ascendentemente


class RendererRasterValoresUnicos(object):
    """paletted de QGIS -> RasterUniqueValueRenderer de ArcMap.

    A diferencia del vectorial, el renderer raster de ArcMap SI agrupa varios
    valores bajo una clase (Value[heading, clase, i]), pero QGIS declara un
    paletteEntry por valor, asi que aqui va una clase por valor.
    """

    def __init__(self, campo, clases):
        self.campo = campo
        self.clases = clases  # ClaseValor


class ClaseCorteRaster(object):
    """Un tramo de un pseudocolor DISCRETE de QGIS.

    QGIS solo declara el TECHO de cada tramo (item value): el suelo es el techo
    del tramo anterior, y el del primero es el minimo del raster.
    """

    def __init__(self, superior, label, simbolo):
        self.superior = superior
        self.label = label
        self.simbolo = simbolo


class RendererRasterCortes(object):
    """singlebandpseudocolor DISCRETE -> RasterClassifyColorRampRenderer.

    GOTCHA que costo un bug en el motor original: este renderer NO tiene
    MinimumBreak (el vectorial si). Tiene ClassCount+1 cortes y **Break[0] es
    el minimo**; el techo de la clase i es Break[i+1]. Escribir los techos en
    Break[0..n-1] desplaza todas las clases una posicion.
    """

    def __init__(self, clases):
        self.clases = clases  # ClaseCorteRaster, ascendentes


class ParadaColor(object):
    """Una parada de una rampa de color continua: valor -> color.

    En una rampa INTERPOLATED de QGIS cada <item> es una parada; el color de un
    valor intermedio se interpola linealmente entre las dos paradas vecinas.
    """

    def __init__(self, valor, rgb, label=u""):
        self.valor = valor
        self.rgb = rgb      # (r, g, b)
        self.label = label


class RendererRasterEstirado(object):
    """singlebandpseudocolor INTERPOLATED de QGIS -> RasterStretchColorRampRenderer.

    A diferencia del DISCRETE (clases con corte), aqui el color varia de forma
    continua entre `minimo` y `maximo`. ArcMap lo representa estirando una rampa
    de color multiparte (una IAlgorithmicColorRamp por cada tramo entre paradas
    consecutivas) sobre el rango [minimo, maximo].

    `minimo`/`maximo` son los de la clasificacion QGIS (classificationMin/Max),
    no necesariamente los del raster; el emisor fuerza ese rango para que el
    reparto de color coincida con QGIS.
    """

    def __init__(self, minimo, maximo, paradas):
        self.minimo = minimo
        self.maximo = maximo
        self.paradas = paradas  # ParadaColor, ascendentes por valor


class CapaEstilo(object):
    """Estilo completo de una capa: lo que el emisor convierte en un .lyr."""

    def __init__(self, nombre, renderer, defquery=None, datasource=None,
                 opacidad=1.0, avisos=None, escala_min=0.0, escala_max=0.0):
        self.nombre = nombre          # nombre visible de la capa
        self.renderer = renderer
        self.defquery = defquery      # definition query o None
        self.datasource = datasource  # ruta del dato tal como la declara QGIS (puede ser relativa)
        self.opacidad = opacidad      # 0.0-1.0 como en QGIS (1 = opaca)
        # Visibilidad por escala. Misma convencion que QGIS y que ArcMap: son
        # DENOMINADORES y 0 = sin limite. escala_min es el limite alejado
        # (denominador grande, QGIS `minScale` / ArcMap MinimumScale) y
        # escala_max el limite acercado (QGIS `maxScale` / ArcMap MaximumScale).
        self.escala_min = escala_min
        self.escala_max = escala_max
        # avisos: degradaciones conscientes (p.ej. symbol-layers descartados).
        # Nunca silenciosas: el llamador las imprime o las devuelve en su JSON.
        self.avisos = avisos if avisos is not None else []
        # Capa de servicio (WMS): ServicioWMS. Sin dato de fichero ni renderer.
        self.servicio = None


class ServicioWMS(object):
    """Capa WMS de QGIS -> WMSMapLayer de ArcMap. No tiene renderer: el estilo
    lo pone el servidor. Va en `CapaEstilo.servicio` y `renderer` queda None."""

    def __init__(self, url, capas, estilos=None, formato=None, crs=None):
        self.url = url
        self.capas = capas          # nombres WMS de `layers=`, en su orden
        self.estilos = estilos or []
        self.formato = formato
        self.crs = crs


class ServicioWMTS(object):
    """Capa WMTS de QGIS -> WMTSLayer de ArcMap. Como ServicioWMS: va en
    `CapaEstilo.servicio` y no tiene renderer."""

    def __init__(self, url, capa, matriz, estilo=None, formato=None):
        self.url = url
        self.capa = capa            # identificador de la capa (`layers=`)
        self.matriz = matriz        # TileMatrixSet (`tileMatrixSet=`)
        self.estilo = estilo
        self.formato = formato


class SimbologiaNoSoportada(Exception):
    """Variante de simbologia QGIS que el parser no sabe traducir.

    Regla del proyecto: ante esto se avisa y se salta la capa. Nunca se
    degrada en silencio.
    """
    pass
