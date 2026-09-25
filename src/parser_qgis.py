# -*- coding: utf-8 -*-
"""Parser de simbologia QGIS (.qml / .qgz) -> modelo intermedio.

Alcance: los cuatro renderers vectoriales (singleSymbol, categorizedSymbol,
graduatedSymbol, RuleRenderer) con simbolos fill (solido / hueco / tramado /
multicapa), line y marker; y los dos raster (paletted y pseudocolor DISCRETE).
Lo que no encaje lanza SimbologiaNoSoportada (avisar y saltar, nunca degradar
en silencio).

Los simbolos de relleno MULTICAPA (relleno hueco + trama superpuesta, como se
dibujan Red Natura y los espacios protegidos) van a MultiLayerFillSymbol.
Linea y marcador siguen aceptando una sola symbol-layer.

Soporta el formato moderno de QGIS 3.x (mapa de <Option>). Compatible py2.7.

Nota de nombre: NO llamarlo parser.py — colisiona con el modulo stdlib
`parser` de Python 2.7.
"""
import base64
import os
import re
import zipfile
import xml.etree.ElementTree as ET

from modelo import (Contorno, SimboloRelleno, SimboloLinea, SimboloMarcador,
                    SimboloMarcadorCaracter, SimboloTramado, SimboloImagen, SimboloMultiCapa,
                    RendererSimple,
                    ClaseValor, RendererValoresUnicos, ClaseRango,
                    RendererGraduado, RendererRasterValoresUnicos,
                    ClaseCorteRaster, RendererRasterCortes,
                    ParadaColor, RendererRasterEstirado, CapaEstilo,
                    SimbologiaNoSoportada)

_MM2PT = 2.834645669  # 1 mm = 2.834... puntos

# Formas de SimpleMarker que ArcMap sabe representar tal cual
_FORMAS_MARCADOR = {"circle": "circulo", "square": "cuadrado", "cross": "cruz",
                    "cross2": "equis", "diamond": "diamante"}

# Formas que SimpleMarkerSymbol de ArcMap NO tiene y se dibujan con un glifo de
# la fuente ESRI Default Marker (esri_11.ttf, instalada con ArcGIS Desktop).
# forma QGIS -> (codigo del glifo relleno, factor de tamanyo, giro extra).
# Codigos leidos de una hoja de glifos y cajas medidas con QRawFont a em=1000
# (2026-09-24). El factor calibra el tamanyo: QGIS da el tamanyo de la FORMA y
# ArcMap el de la FUENTE, y el glifo ocupa solo ~2/3 del em. Es el lado mayor
# del glifo / em, salvo `equilateral_triangle`: QGIS lo dibuja mas pequenyo
# que su `size` (81 px frente a 94 del glifo a 0,615, render del verificador)
# y se corrige el factor. El giro extra (grados, sentido QGIS) alinea el glifo
# con la forma de QGIS: el hexagono de QGIS tiene un VERTICE arriba y el
# glifo 37 un LADO (visto por render, 2026-09-24).
_GLIFOS_MARCADOR = {
    "triangle": (35, 0.615, 0.0),
    "equilateral_triangle": (35, 0.714, 0.0),
    "pentagon": (36, 0.675, 0.0),
    "hexagon": (37, 0.679, 30.0),
    "octagon": (38, 0.680, 0.0),
    "star": (94, 0.572, 0.0),
}

# Estilos de trazo de QGIS con equivalente en esriSimpleLineStyle. Los nombres
# llevan espacios porque asi los escribe QGIS ("dash dot", no "dashdot").
_ESTILOS_LINEA = ("solid", "dash", "dot", "dash dot", "dash dot dot")

# Los discontinuos: ArcMap los dibuja CONTINUOS a partir de cierto grosor.
_ESTILOS_LINEA_DISCONTINUOS = ("dash", "dot", "dash dot", "dash dot dot")

# Ancho a partir del cual el patron de guiones de esriSimpleLineStyle deja de
# verse. Medido por render real (arcpy.mapping -> PNG, 2026-09-20): a 0,5 y 1 pt
# el patron se ve; a 2, 3 y 6 pt la linea sale continua en los tres estilos
# discontinuos probados.
_ANCHO_PT_TRAZO_CONTINUO = 2.0

# Patrones de relleno tramado de QGIS (Qt brush) que ArcMap sabe reproducir con
# esriSimpleFillStyle. El emisor los traduce al enum concreto.
_TRAMAS_RELLENO = ("horizontal", "vertical", "cross", "b_diagonal",
                   "f_diagonal", "diagonal_x")

# Valor que IUniqueValueRenderer necesita para casar un NULL real. Verificado
# por render (2026-09-20): con "<Null>" la entidad nula recibe su simbolo; con
# "NULL", "" o "<null>" cae al simbolo por defecto.
_VALOR_NULO_ARCMAP = u"<Null>"


def _opciones(layer_elem):
    """Opciones directas de un <layer class=...> de un symbol-layer de QGIS.

    Dos serializaciones, misma informacion y MISMAS CLAVES (`color`,
    `outline_color`, `line_width`, `name`, `distance`...):

    - Moderna (QGIS 3.x): un mapa <Option type="Map"> con hijos <Option
      name= value=>.
    - Legada (<prop k= v=>): hijos directos del <layer>. La usan proyectos 2.x
      y bastantes 3.x guardados/migrados por cierto camino (F4bis, 2026-07-16:
      2 de 3 proyectos reales revisados venian asi). Antes esto reventaba
      con un KeyError crudo al pedir `opts['color']`; ahora se lee.

    GOTCHA (F2): en la forma moderna hay que leer SOLO el <Option type="Map">
    hijo directo, no todos los <Option> descendientes: dentro de
    <data_defined_properties> vive otro mapa con claves homonimas (`name`,
    `type`) y valores vacios que pisan las reales. Con `elem.iter("Option")` un
    SimpleMarker pierde su name="circle". Por el mismo motivo la rama legada usa
    `findall("prop")` (hijos DIRECTOS), no `.iter("prop")`: asi ignora los
    <prop> anidados en <data_defined_properties>.
    """
    mapa = None
    for hijo in layer_elem:
        if hijo.tag == "Option" and hijo.get("type") == "Map":
            mapa = hijo
            break
    if mapa is not None:
        opts = {}
        for opt in mapa:
            if opt.tag != "Option":
                continue
            name, value = opt.get("name"), opt.get("value")
            if name is not None and value is not None:
                opts[name] = value
        return opts
    # Fallback al formato legado <prop k= v=>.
    opts = {}
    for prop in layer_elem.findall("prop"):
        k, v = prop.get("k"), prop.get("v")
        if k is not None and v is not None:
            opts[k] = v
    return opts


def _rgb(valor, que=u"color"):
    """'125,139,143,255,rgb:...' -> ((125,139,143), alpha 0-255).

    Los cuatro primeros campos son siempre r,g,b,a en decimal; lo que sigue
    (rgb:... / hsv:...) es notacion redundante de QGIS y se ignora.

    Un color vacio o ilegible NO se inventa: QGIS lo decodifica a un QColor
    invalido (aparecen en estilos migrados de QGIS 2.x, donde la clave se
    llamaba `border_color`) y lo que Qt pinte con eso no es algo que se pueda
    deducir del XML. Se avisa y se salta la capa.
    """
    partes = (valor or u"").split(",")
    if len(partes) < 3:
        raise SimbologiaNoSoportada(
            u"%s vacio o ilegible (%r): estilo QGIS malformado, normalmente un "
            u"resto de migracion 2.x. Fijalo en QGIS y reexporta" % (que, valor))
    try:
        r, g, b = int(partes[0]), int(partes[1]), int(partes[2])
    except ValueError:
        raise SimbologiaNoSoportada(u"%s ilegible (%r)" % (que, valor))
    a = int(partes[3]) if len(partes) > 3 and partes[3].isdigit() else 255
    return (r, g, b), a


def _rgb_avisando(valor, que, avisos):
    """_rgb() para colores donde la transparencia parcial se pierde.

    ArcMap no tiene alfa por color en estos simbolos: solo opaco o nulo. Un
    alfa intermedio se descarta, pero avisando.
    """
    rgb, alpha = _rgb(valor, que)
    if alpha not in (0, 255):
        avisos.append(_aviso_alfa_opaco(que, alpha))
    return rgb


def _aviso_alfa_opaco(que, alpha):
    """Texto del aviso de alfa por simbolo que ArcMap no sabe reproducir.

    Esta redaccion existe porque la anterior ("ArcMap lo pinta opaco") se leia
    como una contradiccion: el 2026-09-21, en el QA de una capa con opacidad de
    CAPA al 50%, el aviso decia "opaco" y en ArcMap se veia translucida. Son
    dos transparencias distintas y el aviso tiene que distinguirlas: la de capa
    SI viaja (`transparencia_pct`), la de simbolo no. Y lo que se pierde de
    verdad no es "algo de transparencia", es la DIFERENCIA entre clases: dos
    clases con alfa 90 y 50 acaban igual de opacas bajo la misma capa.
    """
    return (u"%s con alfa %s/255 (%d%%): el SIMBOLO se emite opaco, ArcMap no "
            u"tiene alfa por simbolo. La transparencia de CAPA si viaja, pero "
            u"es unica para todas las clases"
            % (que, alpha, round(100.0 * int(alpha) / 255.0)))


def _a_puntos(valor, unidad, que):
    """Convierte una medida de QGIS a puntos respetando la unidad declarada.

    DECISION F2 (Pedro, 2026-07-15): se respeta la unidad. El motor original
    aplicaba el factor mm a todo, asi que una anchura declarada en Point salia
    2,83 veces mas gruesa en ArcMap que en QGIS.
    """
    v = float(valor)
    if unidad in ("MM", "Millimeter"):
        return v * _MM2PT
    if unidad in ("Point", "Points"):
        return v
    raise SimbologiaNoSoportada(
        u"%s con unidad '%s' (solo MM y Point)" % (que, unidad))


def _avisar_trazo_grueso(estilo, ancho_pt, que, avisos):
    """Aviso del trazo discontinuo que ArcMap engorda hasta hacerlo continuo.

    El patron de esriSimpleLineStyle esta definido en unidades de dispositivo y
    lo tapa el propio grosor de la pluma. Medido por render real el 2026-09-20
    (ver `_ANCHO_PT_TRAZO_CONTINUO`). No hay nada mejor que emitir con
    esriSLS*: se emite el estilo pedido y se avisa.
    """
    if estilo in _ESTILOS_LINEA_DISCONTINUOS \
            and ancho_pt >= _ANCHO_PT_TRAZO_CONTINUO:
        avisos.append(
            u"%s con trazo '%s' y ancho %.2f pt: medido en ArcMap, a partir de "
            u"%g pt el patron de guiones desaparece y la linea sale CONTINUA"
            % (que, estilo, ancho_pt, _ANCHO_PT_TRAZO_CONTINUO))


def _es_offset_no_nulo(valor):
    """'0,0' / '0' / '' -> False; cualquier desplazamiento real -> True."""
    if valor in (None, u"", u"0"):
        return False
    for trozo in valor.split(","):
        try:
            if abs(float(trozo)) > 1e-9:
                return True
        except ValueError:
            # Un offset ilegible tampoco se puede trasladar: cuenta como aviso.
            return True
    return False


def _propiedades_data_defined(elem):
    """Nombres de las propiedades data-defined ACTIVAS de un <layer>/<symbol>.

    Formato real de QGIS 3.x (verificado contra saveNamedStyle):

        <data_defined_properties>
          <Option type="Map">
            <Option type="Map" name="properties">
              <Option type="Map" name="fillColor">
                <Option type="bool" name="active" value="true"/>
                ...

    Se mira solo el <data_defined_properties> hijo DIRECTO, por el mismo motivo
    que `_opciones`: si no, se cuelan los de los sub-simbolos.
    """
    activas = []
    for dd in elem.findall("data_defined_properties"):
        for mapa in dd.findall("Option"):
            for props in mapa.findall("Option"):
                if props.get("name") != "properties":
                    continue
                for prop in props.findall("Option"):
                    for campo in prop.findall("Option"):
                        if campo.get("name") == "active" \
                                and (campo.get("value") or u"").lower() == u"true":
                            activas.append(prop.get("name") or u"?")
    return activas


def _avisar_data_defined(elem, que, avisos):
    """Una propiedad data-defined activa cambia el simbolo entidad a entidad.

    ArcMap no tiene equivalente: el .lyr sale con el valor FIJO que el XML
    declara como respaldo, que puede no parecerse a lo que pinta QGIS.
    """
    activas = _propiedades_data_defined(elem)
    if activas:
        avisos.append(
            u"%s con propiedades data-defined activas (%s): ArcMap no las "
            u"reproduce, el simbolo sale con el valor fijo del estilo"
            % (que, u", ".join(activas)))


def _contorno_desde_opts(opts, avisos, prefijo="outline"):
    """Lee outline_color / outline_style / outline_width de un SimpleFill."""
    estilo = opts.get(prefijo + "_style", "solid")
    if estilo == "no":
        return Contorno(style="no")
    if estilo not in _ESTILOS_LINEA:
        raise SimbologiaNoSoportada(u"%s_style='%s'" % (prefijo, estilo))
    rgb = _rgb_avisando(opts[prefijo + "_color"], u"contorno", avisos)
    ancho = _a_puntos(opts.get(prefijo + "_width", "0.26"),
                      opts.get(prefijo + "_width_unit", "MM"),
                      prefijo + "_width")
    _avisar_trazo_grueso(estilo, ancho, u"contorno", avisos)
    return Contorno(rgb=rgb, width_pt=ancho, style=estilo)


def _linea_desde_opts(opts, avisos):
    """Lee un symbol-layer SimpleLine -> SimboloLinea."""
    estilo = opts.get("line_style", "solid")
    if opts.get("use_custom_dash") == "1":
        # QGIS IGNORA line_style cuando el guion personalizado esta activo y
        # dibuja el patron de `customdash`. Emitir el line_style (normalmente
        # "solid") daria una linea continua donde QGIS dibuja guiones.
        avisos.append(
            u"linea con guion personalizado activo (use_custom_dash=1, patron "
            u"'%s'): QGIS ignora line_style y dibuja ese patron; ArcMap no lo "
            u"reproduce y la linea sale con el estilo '%s'"
            % (opts.get("customdash") or u"?", estilo))
    if estilo == "no":
        return SimboloLinea(style="no")
    if estilo not in _ESTILOS_LINEA:
        raise SimbologiaNoSoportada(u"line_style='%s'" % estilo)
    rgb = _rgb_avisando(opts["line_color"], u"linea", avisos)
    ancho = _a_puntos(opts.get("line_width", "0.26"),
                      opts.get("line_width_unit", "MM"), "line_width")
    if _es_offset_no_nulo(opts.get("offset")):
        avisos.append(u"linea desplazada %s %s respecto al eje (offset): "
                      u"ArcMap la dibuja sobre el eje"
                      % (opts.get("offset"), opts.get("offset_unit") or u""))
    _avisar_trazo_grueso(estilo, ancho, u"linea", avisos)
    return SimboloLinea(rgb=rgb, width_pt=ancho, style=estilo)


def _contorno_desde_linea(linea):
    """SimboloLinea -> Contorno (misma info, distinto rol)."""
    return Contorno(rgb=linea.rgb, width_pt=linea.width_pt, style=linea.style)


def _relleno_simple(opts, avisos):
    """symbol-layer SimpleFill -> SimboloRelleno.

    Ademas de solido y hueco, QGIS admite rellenos TRAMADOS con los patrones de
    Qt (b_diagonal, f_diagonal, horizontal, vertical, cross, diagonal_x): ArcMap
    los reproduce con los estilos equivalentes de esriSimpleFillStyle, dibujando
    las lineas del patron con el color del relleno. El emisor hace el mapeo; el
    parser solo valida y deja el nombre de estilo de QGIS en el modelo.
    """
    estilo = opts.get("style", "solid")
    if estilo not in ("solid", "no") and estilo not in _TRAMAS_RELLENO:
        raise SimbologiaNoSoportada(u"fill style='%s'" % estilo)
    rgb = None
    if estilo == "solid":
        rgb, alpha = _rgb(opts["color"], u"relleno")
        # Relleno declarado solido pero totalmente transparente: en QGIS es la
        # forma habitual de dibujar solo el contorno.
        if alpha == 0:
            estilo, rgb = "no", None
        elif alpha != 255:
            avisos.append(_aviso_alfa_opaco(u"relleno", alpha))
    elif estilo in _TRAMAS_RELLENO:
        # El color del SimpleFill es el color de las lineas del tramado.
        rgb = _rgb_avisando(opts["color"], u"relleno tramado", avisos)
    return SimboloRelleno(rgb=rgb, style=estilo,
                          contorno=_contorno_desde_opts(opts, avisos))


def _tramado(layer_elem, avisos):
    """symbol-layer LinePatternFill -> SimboloTramado (LineFillSymbol).

    GOTCHA (F2): la raya del tramado NO son las opciones planas del layer
    (`color`, `line_width`, restos heredados que QGIS 3.x ya no usa) sino un
    <symbol type="line"> ANIDADO dentro del layer. Leer las planas da el color
    equivocado.
    """
    opts = _opciones(layer_elem)
    sub = layer_elem.find("symbol")
    if sub is None:
        raise SimbologiaNoSoportada(u"LinePatternFill sin sub-simbolo de linea")
    linea = _simbolo_desde_symbol(sub, avisos)
    if not isinstance(linea, SimboloLinea):
        raise SimbologiaNoSoportada(
            u"LinePatternFill con sub-simbolo %s" % type(linea).__name__)
    separacion = _a_puntos(opts.get("distance", "5"),
                           opts.get("distance_unit", "MM"), "distance")
    if _es_offset_no_nulo(opts.get("offset")):
        # ILineFillSymbol no tiene desplazamiento del patron: el tramado sale
        # pegado al origen. Hasta 2026-09-21 esto se perdia mudo; hay casos
        # reales con offset=1.5.
        avisos.append(u"tramado con offset %s: ArcMap no desplaza el patron "
                      u"de lineas y lo dibuja sin ese desplazamiento"
                      % opts.get("offset"))
    return SimboloTramado(angulo=float(opts.get("angle", "45")),
                          separacion_pt=separacion,
                          linea=linea,
                          contorno=Contorno(style="no"))


def _imagen_embebida(valor, avisos):
    """imageFile de un RasterFill -> (bytes, formato).

    QGIS embebe la imagen como 'base64:...' dentro del .qgz. Tambien admite una
    ruta a fichero, que aqui no se resuelve (dependeria de rutas del proyecto):
    en ese caso se avisa y se salta.
    """
    if valor and valor.startswith("base64:"):
        try:
            crudo = base64.b64decode(valor[7:])
        except Exception:
            raise SimbologiaNoSoportada(u"RasterFill con base64 ilegible")
        # Firma del formato (solo PNG en los proyectos reales; ArcMap 10.5
        # tambien carga BMP/GIF/JPG por si aparecen).
        if crudo[:8] == b"\x89PNG\r\n\x1a\n":
            formato = "png"
        elif crudo[:2] == b"BM":
            formato = "bmp"
        elif crudo[:3] == b"GIF":
            formato = "gif"
        elif crudo[:2] == b"\xff\xd8":
            formato = "jpg"
        else:
            raise SimbologiaNoSoportada(u"RasterFill con formato de imagen "
                                        u"desconocido")
        return crudo, formato
    raise SimbologiaNoSoportada(
        u"RasterFill con imagen por ruta (no embebida): fijala como embebida "
        u"en QGIS o reexporta")


def _relleno_imagen(layer_elem, avisos):
    """symbol-layer RasterFill -> SimboloImagen (PictureFillSymbol)."""
    opts = _opciones(layer_elem)
    imagen, formato = _imagen_embebida(opts.get("imageFile"), avisos)
    ancho = _a_puntos(opts.get("width", "0"),
                      opts.get("width_unit", "Point"), "width") \
        if opts.get("width") else 0.0
    alpha = opts.get("alpha")
    if alpha is not None and abs(float(alpha) - 1.0) > 1e-6:
        avisos.append(u"RasterFill con opacidad %s en QGIS: ArcMap tesela la "
                      u"imagen tal cual" % alpha)
    avisos.append(u"RasterFill emitido como relleno con imagen (PictureFill): "
                  u"la transparencia del PNG y el tamanyo exacto del mosaico "
                  u"pueden diferir de QGIS; requiere QA visual en ArcMap")
    return SimboloImagen(imagen_bytes=imagen, formato=formato, ancho_pt=ancho,
                         angulo=float(opts.get("angle", "0") or 0),
                         contorno=Contorno(style="no"))


def _capa_de_relleno(layer_elem, avisos):
    """UNA symbol-layer de un <symbol type="fill"> -> simbolo del modelo.

    Formas vistas en proyectos reales:
      - SimpleFill       -> relleno solido o hueco
      - SimpleLine       -> relleno hueco cuyo contorno es esa linea
                            (asi dibuja QGIS un poligono "solo borde")
      - LinePatternFill  -> tramado
      - RasterFill       -> relleno con imagen en mosaico
    """
    clase = layer_elem.get("class")

    if clase == "SimpleFill":
        return _relleno_simple(_opciones(layer_elem), avisos)

    if clase == "SimpleLine":
        linea = _linea_desde_opts(_opciones(layer_elem), avisos)
        return SimboloRelleno(rgb=None, style="no",
                              contorno=_contorno_desde_linea(linea))

    if clase == "LinePatternFill":
        return _tramado(layer_elem, avisos)

    if clase == "RasterFill":
        return _relleno_imagen(layer_elem, avisos)

    raise SimbologiaNoSoportada(u"symbol-layer class='%s' en un fill" % clase)


def _simbolo_fill(layers, avisos):
    """<symbol type="fill"> -> simbolo del modelo.

    Varias symbol-layers superpuestas (relleno hueco + trama = Red Natura, ENP)
    se traducen a un simbolo multicapa; ArcMap lo representa con
    MultiLayerFillSymbol. Una sola capa se emite plana, sin envoltorio.
    """
    if len(layers) == 1:
        return _capa_de_relleno(layers[0], avisos)
    return SimboloMultiCapa([_capa_de_relleno(l, avisos) for l in layers])


def _simbolo_desde_symbol(symbol_elem, avisos):
    tipo = symbol_elem.get("type")
    layers = symbol_elem.findall("layer")
    if not layers:
        raise SimbologiaNoSoportada(u"symbol type='%s' sin symbol-layers" % tipo)

    alpha = symbol_elem.get("alpha")
    if alpha is not None and abs(float(alpha) - 1.0) > 1e-6:
        avisos.append(u"simbolo con opacidad %s en QGIS: ArcMap lo pinta opaco"
                      % alpha)

    # QGIS no dibuja los symbol-layers desactivados; el .lyr tampoco debe.
    apagados = [l for l in layers if l.get("enabled") == "0"]
    if apagados:
        avisos.append(u"%d symbol-layer(s) desactivados en QGIS: no se emiten"
                      % len(apagados))
        layers = [l for l in layers if l.get("enabled") != "0"]
        if not layers:
            raise SimbologiaNoSoportada(
                u"symbol type='%s' con todos los symbol-layers desactivados" % tipo)

    # Propiedades data-defined: ni el simbolo ni sus symbol-layers pueden
    # trasladarlas a ArcMap, pero el usuario tiene que enterarse.
    _avisar_data_defined(symbol_elem, u"simbolo '%s'" % tipo, avisos)
    for l in layers:
        _avisar_data_defined(l, u"symbol-layer %s" % l.get("class"), avisos)

    if tipo == "fill":
        return _simbolo_fill(layers, avisos)

    if tipo == "line":
        if len(layers) > 1 or layers[0].get("class") != "SimpleLine":
            raise SimbologiaNoSoportada(
                u"linea con %d symbol-layers (%s)"
                % (len(layers), ", ".join(l.get("class") for l in layers)))
        return _linea_desde_opts(_opciones(layers[0]), avisos)

    if tipo == "marker":
        if len(layers) > 1 or layers[0].get("class") != "SimpleMarker":
            raise SimbologiaNoSoportada(
                u"marcador con %d symbol-layers (%s)"
                % (len(layers), ", ".join(l.get("class") for l in layers)))
        opts = _opciones(layers[0])
        forma = opts.get("name", "circle")
        if forma not in _FORMAS_MARCADOR and forma not in _GLIFOS_MARCADOR:
            # ArcMap solo tiene 5 formas en SimpleMarkerSymbol (circulo,
            # cuadrado, cruz, equis, diamante). Unas pocas mas se dibujan con
            # un glifo de ESRI Default Marker (_GLIFOS_MARCADOR). El resto
            # (arrow, half_square, heart...) no tiene glifo verificado: no se
            # inventa.
            raise SimbologiaNoSoportada(
                u"marcador de forma '%s': ArcMap solo tiene circle, square, "
                u"cross, cross2 y diamond, y por glifo %s. Cambia la forma en "
                u"QGIS o edita el simbolo en ArcMap"
                % (forma, u", ".join(sorted(_GLIFOS_MARCADOR))))
        rgb = _rgb_avisando(opts["color"], u"marcador", avisos)
        tam = _a_puntos(opts.get("size", "2"), opts.get("size_unit", "MM"), "size")
        ancho_contorno = _a_puntos(opts.get("outline_width", "0"),
                                   opts.get("outline_width_unit", "MM"),
                                   "outline_width")
        contorno_rgb = None
        if ancho_contorno > 0 and opts.get("outline_style", "solid") != "no":
            contorno_rgb = _rgb_avisando(opts["outline_color"],
                                         u"contorno del marcador", avisos)
        else:
            if ancho_contorno == 0 and opts.get("outline_style", "solid") != "no":
                # DECISION (2026-09-20): QGIS dibuja el borde de ancho 0 como
                # hairline (pluma cosmetica de 1 px); ArcMap no tiene hairline
                # y un OutlineSize minimo inventado engordaria el simbolo a
                # cualquier escala de impresion. Se emite SIN borde y se avisa.
                avisos.append(
                    u"borde del marcador con ancho 0 y estilo '%s': QGIS lo "
                    u"dibuja como linea fina de 1 px (hairline) y el .lyr sale "
                    u"SIN borde; ponle un ancho explicito en QGIS si lo quieres"
                    % opts.get("outline_style", "solid"))
            ancho_contorno = 0.0
        if _es_offset_no_nulo(opts.get("offset")):
            avisos.append(u"marcador desplazado %s %s respecto al punto "
                          u"(offset): ArcMap lo dibuja centrado"
                          % (opts.get("offset"), opts.get("offset_unit") or u""))
        angulo = float(opts.get("angle", "0") or 0)
        if forma in _GLIFOS_MARCADOR:
            codigo, lado, giro_extra = _GLIFOS_MARCADOR[forma]
            avisos.append(
                u"marcador '%s' dibujado con un glifo de la fuente ESRI Default "
                u"Marker: tamanyo aproximado%s"
                % (forma, u", y el borde sale como halo por fuera de la forma"
                          if contorno_rgb else u""))
            return SimboloMarcadorCaracter(
                rgb=rgb, size_pt=tam / lado, char_relleno=codigo,
                contorno_rgb=contorno_rgb, contorno_pt=ancho_contorno,
                angulo=(angulo + giro_extra) % 360.0)
        return SimboloMarcador(rgb=rgb, size_pt=tam, forma=_FORMAS_MARCADOR[forma],
                               contorno_rgb=contorno_rgb, contorno_pt=ancho_contorno,
                               angulo=angulo)

    raise SimbologiaNoSoportada(u"symbol type='%s'" % tipo)


def _simbolos_por_nombre(rend_elem, avisos, solo=None):
    """<symbols> -> {name: simbolo}. Los que no se sepan traducir revientan.

    `solo`: nombres de simbolo que de verdad se van a emitir. Los demas NO se
    parsean: un simbolo no soportado en una regla desmarcada tumbaba la capa
    entera por algo que QGIS no dibuja y el .lyr no iba a llevar (2026-09-24).
    """
    fuera = {}
    symbols = rend_elem.find("symbols")
    if symbols is None:
        raise SimbologiaNoSoportada(u"renderer sin <symbols>")
    for s in symbols.findall("symbol"):
        if solo is not None and s.get("name") not in solo:
            continue
        fuera[s.get("name")] = _simbolo_desde_symbol(s, avisos)
    return fuera


# Nombre de campo aceptable: empieza por letra (UNICODE, no solo A-Z) o '_' y
# sigue con letras, digitos o '_'. Con el patron ASCII anterior, un campo
# legitimo como 'Año' o 'Señal' se rechazaba con el mensaje "categorizado por
# expresion", que mandaba a buscar una expresion inexistente.
_RE_CAMPO = re.compile(ur"^[^\W\d]\w*$", re.UNICODE)


def _campo(attr, que=u"renderer"):
    """attr del renderer -> nombre de campo.

    QGIS entrecomilla el campo unas veces si y otras no ('Infraestru' vs
    '"SubtipoRie"'). `que` solo sirve para que el mensaje de error nombre el
    renderer real (categorizado, graduado...) en vez de uno fijo.
    """
    attr = attr or u""
    if isinstance(attr, bytes):
        # ElementTree de py2.7 devuelve str cuando el valor es ASCII puro.
        attr = attr.decode("utf-8")
    attr = attr.strip()
    if len(attr) >= 2 and attr[0] == u'"' and attr[-1] == u'"':
        attr = attr[1:-1]
    if not attr:
        raise SimbologiaNoSoportada(u"%s sin campo de clasificacion" % que)
    if not _RE_CAMPO.match(attr):
        # Un attr que no es un nombre de campo es una expresion: fuera del MVP.
        raise SimbologiaNoSoportada(
            u"%s clasificado por la expresion '%s' y no por un campo: fuera "
            u"del alcance (ArcMap no evalua expresiones de QGIS)" % (que, attr))
    return attr


def _simbolos_visibles(contenedor, etiqueta):
    """Nombres de simbolo de las clases que QGIS SI dibuja (render != false)."""
    return set(e.get("symbol") for e in contenedor.findall(etiqueta)
               if e.get("render") != "false")


def _renderer_categorizado(rend_elem, avisos):
    campo = _campo(rend_elem.get("attr"), u"renderer categorizado")
    clases, default_simbolo, default_label = [], None, u""

    cats = rend_elem.find("categories")
    if cats is None:
        raise SimbologiaNoSoportada(u"categorizado sin <categories>")
    # Solo los simbolos de categorias VISIBLES: uno no soportado en una
    # categoria oculta tumbaba la capa entera (igual que en las reglas).
    simbolos = _simbolos_por_nombre(
        rend_elem, avisos, solo=_simbolos_visibles(cats, "category"))

    for cat in cats.findall("category"):
        if cat.get("render") == "false":
            avisos.append(u"categoria '%s' oculta en QGIS: no se emite"
                          % (cat.get("label") or cat.get("value") or u""))
            continue
        simbolo = simbolos[cat.get("symbol")]
        label = cat.get("label") or u""

        # GOTCHA (F2): una categoria MULTI-VALOR de QGIS no lleva atributo
        # `value` sino hijos <val>. Confundirla con el "todos los demas" (que
        # tampoco lleva `value`) manda sus valores al simbolo por defecto y se
        # come la clase entera. En un proyecto real, una categoria {X, Si} caia ahi.
        vals = cat.findall("val")
        if vals:
            for v in vals:
                valor = v.get("value")
                if valor is None:
                    raise SimbologiaNoSoportada(
                        u"categoria '%s' con <val> sin value" % label)
                # ArcMap no agrupa valores bajo una clase: se emite uno por
                # valor con el mismo simbolo y etiqueta.
                clases.append(ClaseValor(valor=valor, label=label,
                                         simbolo=simbolo))
            if len(vals) > 1:
                avisos.append(
                    u"categoria '%s' agrupa %d valores (%s): en ArcMap sale una "
                    u"entrada de leyenda por valor"
                    % (label, len(vals), u", ".join(v.get("value") for v in vals)))
            continue

        if cat.get("type") == "NULL":
            # Categoria de valores NULOS. QGIS la serializa type="NULL"
            # value="NULL": emitirla tal cual mandaria a ArcMap a casar el
            # TEXTO "NULL". Verificado por render (2026-09-20): el valor que
            # casa los nulos reales de ArcMap es exactamente "<Null>".
            clases.append(ClaseValor(valor=_VALOR_NULO_ARCMAP, label=label,
                                     simbolo=simbolo))
            avisos.append(
                u"categoria '%s' de valores NULOS: se emite con el valor "
                u"'%s', que es como ArcMap nombra el nulo (un shapefile no "
                u"guarda nulos: alli no casara ninguna entidad)"
                % (label, _VALOR_NULO_ARCMAP))
            continue

        valor = cat.get("value")
        if valor is None or valor == u"":
            # Sin `value` y sin <val>: es el "todos los demas" de QGIS.
            default_simbolo, default_label = simbolo, label
            continue
        clases.append(ClaseValor(valor=valor, label=label, simbolo=simbolo))

    if not clases:
        raise SimbologiaNoSoportada(u"categorizado sin clases con valor")
    return RendererValoresUnicos(campos=[campo], clases=clases,
                                 default_simbolo=default_simbolo,
                                 default_label=default_label)


def _renderer_graduado(rend_elem, avisos):
    """graduatedSymbol -> RendererGraduado (ClassBreaksRenderer)."""
    metodo = rend_elem.get("graduatedMethod") or "GraduatedColor"
    if metodo != "GraduatedColor":
        # Tamanyo graduado: ArcMap lo hace con simbolos proporcionales, que es
        # otro renderer. Fuera del MVP.
        raise SimbologiaNoSoportada(u"graduatedMethod='%s'" % metodo)

    campo = _campo(rend_elem.get("attr"), u"renderer graduado")

    contenedor = rend_elem.find("ranges")
    if contenedor is None:
        raise SimbologiaNoSoportada(u"graduado sin <ranges>")
    simbolos = _simbolos_por_nombre(
        rend_elem, avisos, solo=_simbolos_visibles(contenedor, "range"))

    rangos = []
    for rg in contenedor.findall("range"):
        label = rg.get("label") or u""
        if rg.get("render") == "false":
            avisos.append(u"intervalo '%s' oculto en QGIS: no se emite" % label)
            continue
        if rg.get("lower") is None or rg.get("upper") is None:
            raise SimbologiaNoSoportada(u"intervalo '%s' sin lower/upper" % label)
        inferior, superior = float(rg.get("lower")), float(rg.get("upper"))
        if inferior > superior:
            # Un intervalo invertido generaria cortes no ascendentes y un .lyr
            # malformado. La UI de QGIS no los produce, pero un .qml editado a
            # mano si.
            raise SimbologiaNoSoportada(
                u"intervalo '%s' invertido (%s > %s)" % (label, inferior, superior))
        rangos.append(ClaseRango(inferior=inferior, superior=superior,
                                 label=label,
                                 simbolo=simbolos[rg.get("symbol")]))
    if not rangos:
        raise SimbologiaNoSoportada(u"graduado sin intervalos visibles")

    rangos.sort(key=lambda r: r.inferior)
    for previo, siguiente in zip(rangos, rangos[1:]):
        hueco = abs(previo.superior - siguiente.inferior)
        # QGIS separa clases contiguas con un salto de ~1 ppm (p.ej. 4.0 -> el
        # siguiente empieza en 4.000001, o 2500.0 -> 2500.000001) para que un
        # valor exacto caiga en una sola clase. Es un artefacto de serializacion,
        # no un hueco real, y ArcMap lo absorbe solo: como solo guarda el corte
        # SUPERIOR de cada clase, el suelo del siguiente pasa a ser ese corte y
        # el salto desaparece. Se tolera un desajuste relativo de 1 ppm.
        tol = 1e-6 * max(1.0, abs(previo.superior), abs(siguiente.inferior))
        if hueco > tol:
            # Un hueco DE VERDAD (mayor que el epsilon) si importa: al emitir se
            # rellenaria solo y las entidades del hueco cambiarian de color en
            # silencio. Ahi se avisa y se salta.
            raise SimbologiaNoSoportada(
                u"intervalos graduados no contiguos: %s termina en %s y el "
                u"siguiente empieza en %s" % (previo.label, previo.superior,
                                              siguiente.inferior))
    return RendererGraduado(campo=campo, rangos=rangos)


def _hex_rgb(valor, que=u"color"):
    """'#1b7837' -> (27, 120, 55). Los raster de QGIS usan hex, no r,g,b,a."""
    h = (valor or u"").lstrip(u"#")
    if len(h) != 6:
        raise SimbologiaNoSoportada(u"%s ilegible (%r)" % (que, valor))
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        raise SimbologiaNoSoportada(u"%s ilegible (%r)" % (que, valor))


def _simbolo_nulo():
    """Relleno que ArcMap no dibuja (es como se reproduce 'invisible')."""
    return SimboloRelleno(rgb=None, style="no", contorno=Contorno(style="no"))


def _relleno_raster(color_hex, alpha, que, avisos, permitir_nulo=False):
    """Color de una clase raster -> SimboloRelleno solido sin contorno.

    `permitir_nulo` lo pone el renderer que SI puede dejar una clase sin
    dibujar (el paletado, con simbolo nulo). El clasificado y el estirado no
    pueden: ahi un alfa 0 solo se puede avisar.
    """
    if alpha is not None and int(alpha) == 0:
        # Alfa 0 = la clase es INVISIBLE en QGIS. Devolver el relleno solido
        # la pintaba opaca, que es justo lo contrario, y sin ruido.
        if permitir_nulo:
            return _simbolo_nulo()
        avisos.append(
            u"%s es totalmente transparente en QGIS (alfa 0): ArcMap no puede "
            u"ocultar una clase de este renderer y la pinta OPACA" % que)
    elif alpha is not None and int(alpha) != 255:
        avisos.append(_aviso_alfa_opaco(que, alpha))
    return SimboloRelleno(rgb=_hex_rgb(color_hex, que), style="solid",
                          contorno=Contorno(style="no"))


def _transparencias_por_valor(rr_elem, avisos):
    """<rasterTransparency> -> {valor: % transparente}.

    QGIS deja ocultar valores sueltos de un raster al margen de la paleta (asi
    se oculta, p.ej., el 0 'No combustible' de un raster de modelos de
    combustible). El elemento
    cuelga DENTRO de <rasterrenderer>, no del <pipe>.

    ArcMap no tiene transparencia por clase: solo se puede reproducir el 100%
    (simbolo nulo). Lo demas se avisa.
    """
    fuera = {}
    rt = rr_elem.find("rasterTransparency")
    if rt is None:
        return fuera
    if rt.find("threeValuePixelList") is not None:
        avisos.append(u"la capa oculta valores por combinacion RGB: ArcMap no "
                      u"lo reproduce")
    for e in rt.iter("pixelListEntry"):
        pct = float(e.get("percentTransparent") or 0)
        if pct == 0:
            continue
        vmin, vmax = e.get("min"), e.get("max")
        if vmin != vmax:
            avisos.append(u"QGIS oculta el rango %s-%s al %g%%: ArcMap solo "
                          u"puede ocultar valores sueltos" % (vmin, vmax, pct))
            continue
        if pct != 100:
            avisos.append(u"QGIS pinta el valor %s al %g%% de transparencia: "
                          u"ArcMap no tiene transparencia por clase, sale opaco"
                          % (vmin, pct))
            continue
        fuera[float(vmin)] = pct
    return fuera


def _pseudocolor_interpolado(rr_elem, shader, ocultos, avisos):
    """singlebandpseudocolor INTERPOLATED -> RendererRasterEstirado.

    El rango del estirado es el de la clasificacion QGIS
    (classificationMin/Max del rasterrenderer, o minimumValue/maximumValue del
    shader como respaldo), NO el min/max del raster: asi el reparto de color
    coincide exactamente con lo que pinta QGIS.
    """
    if shader.get("clip") == "1":
        avisos.append(u"el shader tiene 'clip' activo en QGIS: ArcMap no "
                      u"recorta fuera de rango igual")
    if ocultos:
        avisos.append(u"QGIS oculta los valores %s: un renderer estirado de "
                      u"ArcMap no puede ocultar valores sueltos"
                      % u", ".join(str(v) for v in sorted(ocultos)))

    paradas = []
    for it in shader.iter("item"):
        rgb = _hex_rgb(it.get("color"), u"parada '%s'" % (it.get("label") or u""))
        alpha = it.get("alpha")
        if alpha is not None and int(alpha) == 0:
            # Una parada invisible no se puede reproducir: un renderer
            # estirado de ArcMap no tiene clases que ocultar.
            avisos.append(
                u"la parada %s es totalmente transparente en QGIS (alfa 0): un "
                u"renderer estirado de ArcMap no puede ocultarla y la pinta "
                u"OPACA" % it.get("value"))
        elif alpha is not None and int(alpha) != 255:
            avisos.append(u"parada %s con transparencia %s/255: ArcMap la pinta "
                          u"opaca" % (it.get("value"), alpha))
        paradas.append(ParadaColor(valor=float(it.get("value")), rgb=rgb,
                                   label=it.get("label") or u""))
    if len(paradas) < 2:
        raise SimbologiaNoSoportada(
            u"pseudocolor INTERPOLATED con menos de 2 paradas de color")
    paradas.sort(key=lambda p: p.valor)

    def _num(*valores):
        for v in valores:
            if v not in (None, u""):
                return float(v)
        return None

    minimo = _num(rr_elem.get("classificationMin"), shader.get("minimumValue"),
                  paradas[0].valor)
    maximo = _num(rr_elem.get("classificationMax"), shader.get("maximumValue"),
                  paradas[-1].valor)
    if maximo <= minimo:
        raise SimbologiaNoSoportada(
            u"pseudocolor INTERPOLATED con rango invalido (%s..%s)"
            % (minimo, maximo))
    return RendererRasterEstirado(minimo=minimo, maximo=maximo, paradas=paradas)


def _renderer_raster(rr_elem, avisos):
    """<rasterrenderer> -> renderer del modelo. paletted, pseudocolor DISCRETE
    (clases) y pseudocolor INTERPOLATED (estirado)."""
    tipo = rr_elem.get("type")

    if rr_elem.get("alphaBand") not in (None, "-1"):
        avisos.append(u"la capa usa banda alfa (%s): ArcMap no la aplica"
                      % rr_elem.get("alphaBand"))

    ocultos = _transparencias_por_valor(rr_elem, avisos)

    if tipo == "paletted":
        clases = []
        for pal in rr_elem.iter("paletteEntry"):
            label = pal.get("label") or u""
            if float(pal.get("value")) in ocultos:
                # Invisible en QGIS: se emite la clase (para que la leyenda
                # siga igual) pero con simbolo nulo, que es como ArcMap no
                # dibuja nada.
                simbolo = _simbolo_nulo()
            else:
                # permitir_nulo: en el paletado una clase con alfa 0 tambien
                # se reproduce con simbolo nulo, igual que las ocultas por
                # <rasterTransparency>.
                simbolo = _relleno_raster(pal.get("color"), pal.get("alpha"),
                                          u"clase '%s'" % label, avisos,
                                          permitir_nulo=True)
            clases.append(ClaseValor(valor=pal.get("value"), label=label,
                                     simbolo=simbolo))
        if not clases:
            raise SimbologiaNoSoportada(u"paletted sin <paletteEntry>")
        # El campo de un raster paletado en ArcMap es siempre el valor de celda.
        return RendererRasterValoresUnicos(campo=u"Value", clases=clases)

    if tipo == "singlebandpseudocolor":
        shader = rr_elem.find("rastershader/colorrampshader")
        if shader is None:
            raise SimbologiaNoSoportada(u"pseudocolor sin <colorrampshader>")
        rampa = shader.get("colorRampType")
        if rampa == "INTERPOLATED":
            # Rampa continua: el color se interpola entre paradas. Va a un
            # renderer estirado, no a uno de clases. EXACT (valores sueltos)
            # sigue fuera del MVP.
            return _pseudocolor_interpolado(rr_elem, shader, ocultos, avisos)
        if rampa != "DISCRETE":
            raise SimbologiaNoSoportada(
                u"pseudocolor con colorRampType='%s' (solo DISCRETE e "
                u"INTERPOLATED)" % rampa)
        if shader.get("clip") == "1":
            avisos.append(u"el shader tiene 'clip' activo en QGIS: ArcMap no "
                          u"recorta fuera de rango igual")
        if ocultos:
            avisos.append(u"QGIS oculta los valores %s: en un clasificado de "
                          u"ArcMap no se puede ocultar una clase"
                          % u", ".join(str(v) for v in sorted(ocultos)))
        clases = []
        for it in shader.iter("item"):
            label = it.get("label") or u""
            clases.append(ClaseCorteRaster(
                superior=float(it.get("value")), label=label,
                simbolo=_relleno_raster(it.get("color"), it.get("alpha"),
                                        u"clase '%s'" % label, avisos)))
        if not clases:
            raise SimbologiaNoSoportada(u"pseudocolor sin <item>")
        clases.sort(key=lambda c: c.superior)
        return RendererRasterCortes(clases=clases)

    raise SimbologiaNoSoportada(u"rasterrenderer type='%s'" % tipo)


def _campos_citados(filtro):
    """Nombres de campo entrecomillados en un filtro QGIS, en orden."""
    vistos, fuera = set(), []
    for m in re.finditer(r'"([^"]+)"', filtro):
        if m.group(1) not in vistos:
            vistos.add(m.group(1))
            fuera.append(m.group(1))
    return fuera


def _defquery_else(filtros):
    """Filtro de la regla ELSE = lo que no casa con ninguna otra regla.

    En SQL, NOT(campo LIKE x) es NULL cuando campo es NULL, asi que la fila se
    perderia; QGIS en cambio SI la mete en el ELSE. Por eso se anyade el
    IS NULL de cada campo citado.
    """
    if not filtros:
        raise SimbologiaNoSoportada(u"regla ELSE sin reglas hermanas")
    union = u" OR ".join(u"(%s)" % f for f in filtros)
    partes = [u"NOT (%s)" % union]
    for filtro in filtros:
        for campo in _campos_citados(filtro):
            parte = u'"%s" IS NULL' % campo
            if parte not in partes:
                partes.append(parte)
    return u" OR ".join(partes)


def _regla_activa(regla):
    """QGIS no dibuja las reglas desmarcadas en el panel de capas.

    Verificado contra QGIS 3.44 (`saveNamedStyle` de un RuleRenderer con una
    regla `setActive(False)`): el atributo se llama **`checkstate`**, no
    `checked`. Se acepta tambien `checked` por si alguna version lo escribiera
    asi; cualquiera de los dos a "0" apaga la regla.
    """
    return regla.get("checkstate") != "0" and regla.get("checked") != "0"


def _escalas_de_regla(regla):
    """Escalas declaradas en una regla (0 / ausente = sin limite)."""
    fuera = []
    for clave in ("scalemindenom", "scalemaxdenom"):
        valor = regla.get(clave)
        if valor not in (None, u"", u"0"):
            fuera.append(u"%s=%s" % (clave, valor))
    return fuera


def _es_regla_else(regla):
    return (regla.get("filter") or u"").strip().upper() == u"ELSE"


def _capas_desde_reglas(rend_elem, nombre_base, avisos):
    """RuleRenderer -> una CapaEstilo por regla (ArcMap no tiene rule-based).

    Cada regla se convierte en su propia capa con la definition query de su
    filtro. Solo el caso plano: reglas sin anidar y con simbolo. Una regla SIN
    filtro es legitima en QGIS (dibuja todas las entidades) y se emite sin
    definition query.
    """
    contenedor = rend_elem.find("rules")
    if contenedor is None:
        raise SimbologiaNoSoportada(u"RuleRenderer sin <rules>")

    reglas = []
    for regla in contenedor.findall("rule"):
        if not _regla_activa(regla):
            avisos.append(
                u"regla '%s' desmarcada en QGIS: alli no se dibuja, asi que no "
                u"se emite .lyr y tampoco cuenta para el filtro del ELSE"
                % (regla.get("label") or regla.get("filter") or u""))
            continue
        reglas.append(regla)

    for regla in reglas:
        if regla.find("rule") is not None:
            raise SimbologiaNoSoportada(u"reglas anidadas")
        if regla.get("symbol") is None:
            raise SimbologiaNoSoportada(u"regla sin simbolo (solo agrupa)")
        escalas = _escalas_de_regla(regla)
        if escalas:
            # La visibilidad por escala de una REGLA no tiene sitio en el .lyr:
            # ArcMap solo tiene escalas por capa, y la capa ya lleva las suyas.
            avisos.append(
                u"regla '%s' con visibilidad por escala (%s): se ignora, el "
                u".lyr se dibuja a cualquier escala"
                % (regla.get("label") or u"", u", ".join(escalas)))

    # Solo DESPUES de descartar las desmarcadas: sus simbolos no se tocan.
    # Cada simbolo con SU lista de avisos: cada regla es un .lyr aparte, y un
    # aviso del simbolo de una regla aparecia tambien en las demas.
    simbolos, avisos_simbolo = {}, {}
    for nombre in set(r.get("symbol") for r in reglas):
        propios = []
        simbolos.update(_simbolos_por_nombre(rend_elem, propios,
                                             solo=set([nombre])))
        avisos_simbolo[nombre] = propios

    normales = [r for r in reglas if not _es_regla_else(r)]
    filtros_normales = [(r.get("filter") or u"").strip() for r in normales
                        if (r.get("filter") or u"").strip()]
    sin_filtro = [r for r in normales if not (r.get("filter") or u"").strip()]

    # Primera pasada: decidir la def-query de cada regla y acumular TODOS los
    # avisos. Las capas se construyen despues porque cada una se lleva una
    # COPIA de la lista, y un aviso decidido tarde no llegaria a las ya hechas.
    plan = []
    for regla in reglas:
        filtro = (regla.get("filter") or u"").strip()
        etiqueta = regla.get("label") or u""
        if _es_regla_else(regla):
            if sin_filtro:
                # Con una regla que dibuja TODO, en QGIS el ELSE no casa nada.
                avisos.append(
                    u"la regla ELSE '%s' no se emite: la regla '%s' no tiene "
                    u"filtro y ya dibuja todas las entidades, asi que en QGIS "
                    u"el ELSE se queda sin ninguna"
                    % (etiqueta, sin_filtro[0].get("label") or u""))
                continue
            if not filtros_normales:
                avisos.append(
                    u"la regla ELSE '%s' es la unica regla activa: se emite sin "
                    u"definition query, que es lo que dibuja QGIS" % etiqueta)
                plan.append((regla, None))
                continue
            plan.append((regla, _defquery_else(filtros_normales)))
            continue
        if filtro:
            plan.append((regla, filtro))
            continue
        avisos.append(
            u"regla '%s' sin filtro: en QGIS dibuja todas las entidades, asi "
            u"que su .lyr sale sin definition query" % etiqueta)
        plan.append((regla, None))

    capas = []
    for regla, defquery in plan:
        capas.append(CapaEstilo(
            nombre=regla.get("label") or nombre_base,
            renderer=RendererSimple(simbolos[regla.get("symbol")]),
            defquery=defquery,
            # list(avisos): cada capa se lleva su COPIA. Compartir la lista
            # hacia que un aviso de una regla apareciese en las demas.
            avisos=list(avisos) + avisos_simbolo.get(regla.get("symbol"), [])))
    if not capas:
        raise SimbologiaNoSoportada(
            u"RuleRenderer sin ninguna regla que emitir (todas desmarcadas o "
            u"sin simbolo)")
    return capas


def _renderer_desde_elem(rend_elem, avisos):
    """Renderers de capa unica (los que no multiplican capas)."""
    tipo = rend_elem.get("type")
    if tipo == "singleSymbol":
        symbols = rend_elem.find("symbols")
        symbol = symbols.find("symbol") if symbols is not None else None
        if symbol is None:
            raise SimbologiaNoSoportada(u"singleSymbol sin <symbol>")
        return RendererSimple(_simbolo_desde_symbol(symbol, avisos))
    if tipo == "categorizedSymbol":
        return _renderer_categorizado(rend_elem, avisos)
    if tipo == "graduatedSymbol":
        return _renderer_graduado(rend_elem, avisos)
    raise SimbologiaNoSoportada(u"renderer-v2 type='%s'" % tipo)


def combinar_defquery(externa, propia):
    """Une la def-query de la CAPA con la de una regla. Cualquiera puede faltar.

    Una regla sin filtro (legitima en QGIS: dibuja todas las entidades) deja
    `propia` a None; concatenar a ciegas producia la cadena literal
    "(subset) AND (None)".
    """
    if externa and propia:
        return u"(%s) AND (%s)" % (externa, propia)
    return externa or propia or None


def ruta_dataset(ruta, layername=None, layerid=None):
    """Ruta OGR de QGIS -> ruta de dataset que arcpy sabe abrir.

    Un GeoPackage es un contenedor MULTICAPA: arcpy 10.5 abre una capa suya
    como `ruta.gpkg\\main.<layername>` (verificado el 2026-09-20 con
    MakeFeatureLayer y con una emision completa a .lyr). El `.gpkg` pelado NO
    lo abre ("el dataset ... no existe"), asi que sin `layername` no hay nada
    que resolver y se avisa con un mensaje que diga que hacer.
    """
    ext = os.path.splitext(ruta)[1].lower()
    if ext == u".gpkg":
        if layername:
            if u"." in layername:
                # Medido el 2026-09-21: con un punto en el nombre,
                # `Exists(...\main.t12_2_Art12Polygons_12.1)` da False y
                # MakeFeatureLayer casca con ERROR 000732 culpando al DATASET.
                # El mismo GPKG con el punto cambiado por `_` abre sin more.
                # Sin este aviso el usuario busca el fallo donde no esta.
                raise SimbologiaNoSoportada(
                    u"la capa '%s' de %s lleva un PUNTO en el nombre y arcpy "
                    u"10.5 no sabe abrirla (el punto separa esquema y tabla: "
                    u"cree que main.%s es un esquema). Renombra la tabla "
                    u"dentro del GeoPackage sin puntos, o exportala a "
                    u"shapefile" % (layername, ruta, layername.split(u".")[0]))
            return u"%s\\main.%s" % (ruta, layername)
        raise SimbologiaNoSoportada(
            u"capa de GeoPackage sin nombre de capa en el datasource (%s): "
            u"arcpy no abre un .gpkg entero. Vuelve a cargarla en QGIS desde "
            u"el selector de capas del GeoPackage, o exportala a shapefile"
            % ruta)
    if layername:
        raise SimbologiaNoSoportada(
            u"capa multicapa '%s' dentro de %s: solo se soportan shapefile, "
            u"raster de fichero y GeoPackage. Exportala a shapefile"
            % (layername, ruta))
    # `layerid` suelto se ignora: QGIS lo anyade tambien a shapefiles de una
    # sola capa y ahi no aporta nada.
    return ruta


def _prefijo_ruta(texto):
    """Prefijo de ruta normalizado: barras de Windows y sin separador final.
    `Z:`, `Z:\\` y `Z:/` quedan igual (`Z:`)."""
    return texto.strip().replace(u"/", u"\\").rstrip(u"\\")


def parse_remap(texto):
    """'Z:=L:\\Mi unidad\\Carto' -> (u'Z:', u'L:\\Mi unidad\\Carto').

    Regla de `--remap`: el prefijo de la IZQUIERDA es el que escribe el
    proyecto (y el que conserva el .lyr); el de la DERECHA, donde se lee el dato
    en esta maquina. Se parte por el PRIMER `=`: una ruta de Windows no lo lleva
    en la unidad, pero si podria llevarlo mas adentro."""
    origen, sep, destino = texto.partition(u"=")
    origen, destino = _prefijo_ruta(origen), _prefijo_ruta(destino)
    if not sep or not origen or not destino:
        raise ValueError(u"regla de --remap mal formada: %r (se espera "
                         u"ORIGEN=DESTINO, p.ej. \"Z:=L:\\Mi unidad\\Carto\")"
                         % texto)
    return origen, destino


def remapear(ruta, reglas):
    """Aplica la primera regla cuyo ORIGEN es prefijo de `ruta`.

    -> (ruta donde leer el dato, regla aplicada o None). El prefijo tiene que
    acabar en un separador de la ruta: `C:\\datos` no casa con
    `C:\\datos_viejos\\x.shp`. Sin distinguir mayusculas, como Windows."""
    if not ruta:
        return ruta, None
    normal = ruta.replace(u"/", u"\\")
    for origen, destino in reglas or ():
        n = len(origen)
        if normal[:n].lower() == origen.lower() and (
                len(normal) == n or normal[n] == u"\\"):
            return destino + normal[n:], (origen, destino)
    return ruta, None


#: Tokens del URI de OGR que sabemos leer o descartar a sabiendas. Cualquier
#: otro se avisa en vez de tirarse en silencio.
_TOKENS_DATASOURCE = (u"subset=", u"layername=", u"layerid=", u"geometrytype=")


def _partir_datasource(datasource, avisos=None):
    """'ruta.shp|subset=...' -> (ruta de dataset, defquery).

    QGIS mete la definition query del proveedor OGR dentro del datasource, no
    en <subsetstring>. Asi viaja la def-query de las capas filtradas. El mismo
    separador `|` lleva `layername=` en los contenedores multicapa: tirarlo
    (lo que se hacia antes) dejaba una ruta que arcpy no sabe abrir.

    GOTCHA (2026-09-21): el valor de `subset=` es SQL y puede llevar `|`
    dentro de un literal ('x|y') o el concatenador `||`. Partir por TODOS los
    `|` truncaba la def-query por la mitad y tiraba el resto sin decir nada:
    `subset="A" = 'x|y'` se quedaba en `"A" = 'x`. Por eso se corta en el
    PRIMER `|subset=` y todo lo que va detras es la def-query, literal.
    QGIS lo escribe siempre el ultimo (QgsOgrProviderMetadata), asi que no se
    pierde ningun otro token por hacerlo asi.
    """
    if not datasource:
        return None, None
    cabeza, sep, cola = datasource.partition(u"|subset=")
    defquery = cola if sep else None
    trozos = cabeza.split(u"|")
    layername, layerid = None, None
    for trozo in trozos[1:]:
        if trozo.startswith(u"layername="):
            layername = trozo[len(u"layername="):]
        elif trozo.startswith(u"layerid="):
            layerid = trozo[len(u"layerid="):]
        elif avisos is not None and not trozo.startswith(_TOKENS_DATASOURCE):
            # Nunca callar lo que se descarta: si QGIS mete un token que no
            # conocemos, que se vea en vez de perderse.
            avisos.append(u"token '%s' del origen de datos ignorado: no se "
                          u"traslada al .lyr" % trozo)
    return ruta_dataset(trozos[0], layername, layerid), defquery


def _cabecera_capa(elem, avisos):
    """Atributos de CAPA (no de simbolo) -> dict, y avisos de lo que se pierde.

    Vale igual para el <maplayer> de un .qgs y para la raiz <qgis> de un .qml:
    QGIS escribe los MISMOS atributos en los dos sitios (`labelsEnabled`,
    `hasScaleBasedVisibilityFlag` + `minScale`/`maxScale`, hijo
    <layerOpacity>). Verificado contra `saveNamedStyle` de QGIS 3.44.

    Esta funcion existe para que los dos caminos no puedan volver a divergir:
    hasta 2026-09-20 `parse_qml` no leia <layerOpacity> (la transparencia de
    capa se perdia entera por la via del plugin) ni avisaba de las etiquetas.

    GOTCHA heredado: en un raster la opacidad NO esta en <layerOpacity> (que no
    aparece) sino en el atributo `opacity` del <rasterrenderer>.
    """
    if elem.get("labelsEnabled") == "1":
        # Las etiquetas son otro sistema entero (ILabelEngineLayerProperties),
        # fuera del MVP de simbologia. Pero el usuario tiene que enterarse de
        # que su capa etiquetada llega a ArcMap muda.
        avisos.append(u"la capa lleva etiquetas activas en QGIS: el .lyr sale "
                      u"sin etiquetar (fuera del alcance del MVP)")

    rr_elem = elem.find("pipe/rasterrenderer")
    if rr_elem is not None:
        opacidad = float(rr_elem.get("opacity") or 1.0)
    else:
        # Opacidad de CAPA (no de simbolo): QGIS la guarda 0-1, ArcMap la
        # expresa como transparencia 0-100 (lo traduce el emisor).
        opacidad = float(elem.findtext("layerOpacity") or 1.0)

    escala_min, escala_max = 0.0, 0.0
    if elem.get("hasScaleBasedVisibilityFlag") == "1":
        # Misma convencion en los dos programas: son DENOMINADORES y 0 = sin
        # limite. QGIS `minScale` (el mayor, limite alejado) -> ArcMap
        # MinimumScale; QGIS `maxScale` (el menor, limite acercado) ->
        # MaximumScale. Comprobado en los .qgs reales, donde la capa sin
        # limites sale con minScale=1e+08 y maxScale=0.
        escala_min = float(elem.get("minScale") or 0)
        escala_max = float(elem.get("maxScale") or 0)
    return {"opacidad": opacidad, "escala_min": escala_min,
            "escala_max": escala_max}


def _capas_desde_estilo(elem, nombre, avisos):
    """Tronco comun de parse_maplayer y parse_qml: el XML del ESTILO -> capas.

    Devuelve la lista de CapaEstilo sin los atributos de capa (los pone
    `_aplicar_cabecera`). Un RuleRenderer da N capas, una por regla.
    """
    rr_elem = elem.find("pipe/rasterrenderer")
    if rr_elem is not None:
        return [CapaEstilo(nombre=nombre,
                           renderer=_renderer_raster(rr_elem, avisos),
                           avisos=avisos)]

    rend_elem = elem.find("renderer-v2")
    if rend_elem is None:
        raise SimbologiaNoSoportada(
            u"capa '%s' sin renderer (ni <renderer-v2> ni "
            u"<pipe/rasterrenderer>)" % (nombre or u"sin nombre"))

    if rend_elem.get("type") == "RuleRenderer":
        return _capas_desde_reglas(rend_elem, nombre or u"sin_nombre", avisos)

    return [CapaEstilo(nombre=nombre,
                       renderer=_renderer_desde_elem(rend_elem, avisos),
                       avisos=avisos)]


def _aplicar_cabecera(capas, cabecera, datasource=None, defquery=None):
    """Pega los atributos de capa a cada CapaEstilo (tambien a las de reglas)."""
    for capa in capas:
        capa.opacidad = cabecera["opacidad"]
        capa.escala_min = cabecera["escala_min"]
        capa.escala_max = cabecera["escala_max"]
        if datasource is not None:
            capa.datasource = datasource
        # La def-query de la CAPA acota a todas las reglas.
        capa.defquery = combinar_defquery(defquery, capa.defquery)
    return capas


def parse_maplayer(maplayer_elem):
    """<maplayer> de un .qgs -> LISTA de CapaEstilo.

    Es una lista porque un RuleRenderer de QGIS se traduce a N capas de ArcMap
    (una por regla, con definition query).
    """
    nombre = maplayer_elem.findtext("layername") or u"sin_nombre"
    avisos = []
    ruta, defquery_ds = _partir_datasource(
        maplayer_elem.findtext("datasource"), avisos)
    defquery = maplayer_elem.findtext("subsetstring") or defquery_ds or None

    cabecera = _cabecera_capa(maplayer_elem, avisos)
    capas = _capas_desde_estilo(maplayer_elem, nombre, avisos)
    return _aplicar_cabecera(capas, cabecera, datasource=ruta,
                             defquery=defquery)


def parse_qml(ruta_qml):
    """Un .qml exportado por QGIS (`saveNamedStyle` de la capa viva).

    Un .qml es solo estilo: no trae ni nombre ni dato ni def-query (el llamador
    los conoce: es la via principal del plugin, ADR-001). SI trae, en cambio,
    los atributos de capa de la cabecera (opacidad, etiquetas, escalas), que se
    leen con el mismo codigo que en el .qgz (`_cabecera_capa`).
    """
    raiz = ET.parse(ruta_qml).getroot()
    avisos = []
    cabecera = _cabecera_capa(raiz, avisos)
    capas = _capas_desde_estilo(raiz, None, avisos)
    return _aplicar_cabecera(capas, cabecera)


def _raiz_qgs(ruta_qgz):
    zf = zipfile.ZipFile(ruta_qgz)
    try:
        nombre_qgs = [n for n in zf.namelist() if n.lower().endswith(".qgs")][0]
        return ET.fromstring(zf.read(nombre_qgs))
    finally:
        zf.close()


def parse_qgz(ruta_qgz, nombre_capa):
    """Extrae el estilo de una capa concreta de un proyecto .qgz.

    Devuelve lista de CapaEstilo (ver parse_maplayer).
    """
    raiz = _raiz_qgs(ruta_qgz)
    candidatas = [ml for ml in raiz.iter("maplayer")
                  if ml.findtext("layername") == nombre_capa]
    if not candidatas:
        raise KeyError(u"capa '%s' no encontrada en %s" % (nombre_capa, ruta_qgz))
    capas = parse_maplayer(candidatas[0])
    if len(candidatas) > 1:
        # Un .qgz puede repetir el nombre de capa (el fixture trae 04_ZAR dos
        # veces). Se usa la primera, pero el usuario tiene que saberlo.
        for capa in capas:
            capa.avisos.append(
                u"el proyecto tiene %d capas llamadas '%s': se usa la primera"
                % (len(candidatas), nombre_capa))
    return capas
