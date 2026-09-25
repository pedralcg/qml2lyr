# -*- coding: utf-8 -*-
"""Emisor: modelo intermedio -> .lyr de ArcMap 10.5.

Ejecutar SIEMPRE con el Python 2.7 de ArcGIS 10.5:
    C:\\Python27\\ArcGIS10.5\\python.exe

Metodo hibrido obligatorio (ver CLAUDE.md): arcpy crea la .lyr base
(ShapefileWorkspaceFactory.OpenFromFile falla siempre en standalone,
COMError 0x80041068) y ArcObjects solo intercambia el renderer.

Unidades: el modelo ya viaja en puntos (lo convierte el parser, que es quien
ve la unidad declarada por QGIS). Aqui no se convierte nada.
"""
import sys
sys.coinit_flags = 2  # antes de importar comtypes
import os
import _winreg

import hashlib
import json
import re as _re

from modelo import (SimboloRelleno, SimboloLinea, SimboloMarcador,
                    SimboloMarcadorCaracter, SimboloTramado, SimboloImagen, SimboloMultiCapa,
                    RendererSimple, RendererValoresUnicos, RendererGraduado,
                    RendererRasterValoresUnicos, RendererRasterCortes,
                    RendererRasterEstirado, SimbologiaNoSoportada)

# Directorio temporal de la emision en curso: lo fija emitir() y lo consume la
# rama de relleno con imagen de _simbolo() (necesita volcar el PNG a fichero,
# porque CreateFillSymbolFromFile solo acepta rutas). La emision es en serie
# por la regla COM, asi que un estado de modulo es seguro.
_TMP = {"dir": None}

# esriIPictureType por formato de imagen.
_PICTURE_TYPES = {"bmp": "esriIPictureBitmap", "emf": "esriIPictureEMF",
                  "gif": "esriIPictureGIF", "jpg": "esriIPictureJPG",
                  "png": "esriIPicturePNG"}

_RENDERERS_RASTER = (RendererRasterValoresUnicos, RendererRasterCortes,
                     RendererRasterEstirado)

# Color con el que se emite un relleno hueco: gris claro totalmente
# transparente (convencion heredada del motor validado a mano).
_HUECO_RGB = (240, 240, 240)

_inicializado = {"ok": False}


def _lib_path():
    key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                          r"SOFTWARE\Wow6432Node\ESRI\Desktop10.5")
    return _winreg.QueryValueEx(key, "InstallDir")[0] + "com\\"


def _init_arcobjects():
    """Carga OLBs e inicializa licencia. Idempotente."""
    if _inicializado["ok"]:
        return
    from comtypes.client import GetModule, CreateObject
    for olb in ["esriSystem.olb", "esriGeometry.olb", "esriDisplay.olb",
                "esriGeoDatabase.olb", "esriCarto.olb"]:
        GetModule(_lib_path() + olb)
    import comtypes.gen.esriSystem as S
    CreateObject(S.AoInitialize, interface=S.IAoInitialize).Initialize(
        S.esriLicenseProductCodeAdvanced)
    _inicializado["ok"] = True


def _mods():
    import comtypes.gen.esriDisplay as D
    import comtypes.gen.esriCarto as CA
    return D, CA


def _nobj(clase, interfaz):
    from comtypes.client import CreateObject
    return CreateObject(clase, interface=interfaz)


def _qi(obj, interfaz):
    """QueryInterface de SONDEO: None si el objeto no expone la interfaz.

    Solo para preguntar "¿eres esto?" (lyr_dump lo usa para identificar el
    tipo de simbolo). Si la conversion es obligatoria, usar _qi_exig: un None
    colado en un Renderer da un .lyr roto sin ruido.
    """
    try:
        return obj.QueryInterface(interfaz)
    except Exception:
        return None


def _qi_exig(obj, interfaz):
    """QueryInterface OBLIGATORIO: revienta si el objeto no expone la interfaz."""
    convertido = _qi(obj, interfaz)
    if convertido is None:
        raise SimbologiaNoSoportada(
            u"%s no expone %s (ArcObjects)"
            % (type(obj).__name__, getattr(interfaz, "__name__", interfaz)))
    return convertido


def _color(rgb, alpha=255):
    D, _ = _mods()
    c = _nobj(D.RgbColor, D.IRgbColor)
    c.Red, c.Green, c.Blue = rgb
    c.Transparency = alpha
    if alpha == 0:
        c.NullColor = True
    return c


# Trama de relleno QGIS -> nombre del miembro esriSimpleFillStyle.
_TRAMAS_RELLENO_AO = {"horizontal": "esriSFSHorizontal",
                      "vertical": "esriSFSVertical",
                      "cross": "esriSFSCross",
                      "b_diagonal": "esriSFSBackwardDiagonal",
                      "f_diagonal": "esriSFSForwardDiagonal",
                      "diagonal_x": "esriSFSDiagonalCross"}

# esriSimpleLineStyle (valores leidos del OLB de ArcGIS 10.5, 2026-09-20).
# Los nombres son los de QGIS, con espacios ("dash dot", no "dashdot").
_ESTILOS_LINEA = {"solid": 0, "dash": 1, "dot": 2, "dash dot": 3,
                  "dash dot dot": 4}
_ESTILOS_MARCADOR = {"circulo": 0, "cuadrado": 1, "cruz": 2, "equis": 3,
                     "diamante": 4}  # esriSMS*


def _enum(tabla, clave, que):
    """Traduce un nombre del modelo a su enum de ArcObjects, o revienta.

    Un `.get(clave, por_defecto)` silencioso esconde un cableado roto: si el
    parser empieza a aceptar un estilo que aqui no esta mapeado, el .lyr sale
    con el estilo por defecto y nadie se entera. Mejor fallar y saltar la capa.
    """
    if clave not in tabla:
        raise SimbologiaNoSoportada(
            u"%s '%s' sin equivalente en ArcMap (mapeados: %s)"
            % (que, clave, u", ".join(sorted(tabla))))
    return tabla[clave]


def _linea_simple(rgb, width_pt, style):
    """-> ISimpleLineSymbol ya configurado."""
    D, _ = _mods()
    ls = _nobj(D.SimpleLineSymbol, D.ISimpleLineSymbol)
    if style == "no":
        ls.Style = D.esriSLSNull
    else:
        ls.Style = _enum(_ESTILOS_LINEA, style, u"estilo de linea")
        ls.Color = _color(rgb)
        ls.Width = float(width_pt)
    return ls


def _contorno(contorno):
    """modelo.Contorno -> ILineSymbol para usar como borde."""
    D, _ = _mods()
    ls = _linea_simple(contorno.rgb, contorno.width_pt, contorno.style)
    return _qi_exig(ls, D.ILineSymbol)


def _volcar_imagen(imagen_bytes, formato):
    """Escribe los bytes de la imagen a un fichero temporal y devuelve su ruta.

    CreateFillSymbolFromFile solo acepta rutas, no bytes. Se nombra por hash del
    contenido: varias categorias comparten la misma textura y asi se escribe
    una sola vez.
    """
    if _TMP["dir"] is None:
        raise SimbologiaNoSoportada(
            u"relleno con imagen sin directorio temporal (bug del emisor)")
    nombre = "img_%s.%s" % (hashlib.md5(imagen_bytes).hexdigest()[:12], formato)
    ruta = os.path.join(_TMP["dir"], nombre)
    if not os.path.exists(ruta):
        f = open(ruta, "wb")
        try:
            f.write(imagen_bytes)
        finally:
            f.close()
    return ruta


def _simbolo_imagen(simbolo):
    """SimboloImagen -> IPictureFillSymbol con la imagen teselada."""
    D, _ = _mods()
    tipo_nombre = _PICTURE_TYPES.get(simbolo.formato)
    if tipo_nombre is None:
        raise SimbologiaNoSoportada(
            u"formato de imagen '%s' no soportado por ArcMap" % simbolo.formato)
    ruta = _volcar_imagen(simbolo.imagen_bytes, simbolo.formato)
    pf = _nobj(D.PictureFillSymbol, D.IPictureFillSymbol)
    pf.CreateFillSymbolFromFile(getattr(D, tipo_nombre), ruta)
    if simbolo.angulo:
        pf.Angle = float(simbolo.angulo)
    _qi_exig(pf, D.IFillSymbol).Outline = _contorno(simbolo.contorno)
    return pf


def _simbolo(simbolo):
    """Cualquier simbolo del modelo -> ISymbol de ArcObjects."""
    D, _ = _mods()

    if isinstance(simbolo, SimboloRelleno):
        fs = _nobj(D.SimpleFillSymbol, D.ISimpleFillSymbol)
        if simbolo.style == "no":
            fs.Style = D.esriSFSSolid
            fs.Color = _color(_HUECO_RGB, alpha=0)
        elif simbolo.style == "solid":
            fs.Style = D.esriSFSSolid
            fs.Color = _color(simbolo.rgb)
        else:
            # Tramado: el estilo esriSFS pinta las lineas del patron con Color.
            fs.Style = getattr(D, _TRAMAS_RELLENO_AO[simbolo.style])
            fs.Color = _color(simbolo.rgb)
        fs.Outline = _contorno(simbolo.contorno)
        return _qi_exig(fs, D.ISymbol)

    if isinstance(simbolo, SimboloLinea):
        ls = _linea_simple(simbolo.rgb, simbolo.width_pt, simbolo.style)
        return _qi_exig(ls, D.ISymbol)

    if isinstance(simbolo, SimboloTramado):
        lf = _nobj(D.LineFillSymbol, D.ILineFillSymbol)
        lf.Angle = float(simbolo.angulo)
        lf.Separation = float(simbolo.separacion_pt)
        lf.LineSymbol = _qi_exig(_linea_simple(simbolo.linea.rgb,
                                               simbolo.linea.width_pt,
                                               simbolo.linea.style),
                                 D.ILineSymbol)
        if simbolo.linea.rgb is not None:
            lf.Color = _color(simbolo.linea.rgb)
        _qi_exig(lf, D.IFillSymbol).Outline = _contorno(simbolo.contorno)
        return _qi_exig(lf, D.ISymbol)

    if isinstance(simbolo, SimboloMultiCapa):
        ml = _nobj(D.MultiLayerFillSymbol, D.IMultiLayerFillSymbol)
        # ORDEN (comprobado): AddLayer INSERTA EN EL INDICE 0, no apila al
        # final; Layer[0] es la ultima anyadida. En ArcObjects el indice 0 es
        # la capa de delante (por eso AddLayer la pone ahi), igual que la
        # ultima symbol-layer de QGIS es la de encima. Anyadir en el orden de
        # QGIS deja, pues, el dibujado correcto — y el volcado sale invertido
        # respecto al .qgz, que es lo esperado.
        for capa in simbolo.capas:
            ml.AddLayer(_qi_exig(_simbolo(capa), D.IFillSymbol))
        return _qi_exig(ml, D.ISymbol)

    if isinstance(simbolo, SimboloImagen):
        return _qi_exig(_simbolo_imagen(simbolo), D.ISymbol)

    if isinstance(simbolo, SimboloMarcador):
        ms = _nobj(D.SimpleMarkerSymbol, D.ISimpleMarkerSymbol)
        ms.Style = _enum(_ESTILOS_MARCADOR, simbolo.forma, u"forma de marcador")
        ms.Color = _color(simbolo.rgb)
        ms.Size = float(simbolo.size_pt)
        # Rotacion: ISimpleMarkerSymbol expone Angle y el .lyr la conserva
        # (verificado por ida y vuelta el 2026-09-20). Solo se toca si hay
        # angulo, para no escribir un 0 donde antes no se escribia nada.
        if getattr(simbolo, "angulo", 0):
            ms.Angle = _angulo_arcmap(simbolo.angulo)
        if simbolo.contorno_pt and simbolo.contorno_pt > 0:
            ms.Outline = True
            ms.OutlineColor = _color(simbolo.contorno_rgb)
            ms.OutlineSize = float(simbolo.contorno_pt)
        else:
            ms.Outline = False
        return _qi_exig(ms, D.ISymbol)

    if isinstance(simbolo, SimboloMarcadorCaracter):
        relleno = _marcador_caracter(simbolo.fuente, simbolo.char_relleno,
                                     simbolo.size_pt, simbolo.rgb,
                                     simbolo.angulo)
        if simbolo.contorno_rgb is not None and simbolo.contorno_pt > 0:
            # Borde = HALO del glifo relleno (IMask). Superponer el glifo
            # hueco de la fuente se descuadraba (visto por render,
            # 2026-09-24); el halo rodea la forma exacta y respeta el grosor.
            # IMask no lo expone CharacterMarkerSymbol sino el multicapa
            # (sondeado 2026-09-24): el glifo va dentro de uno de una capa.
            ml = _nobj(D.MultiLayerMarkerSymbol, D.IMultiLayerMarkerSymbol)
            ml.AddLayer(_qi_exig(relleno, D.IMarkerSymbol))
            relleno = ml
            mascara = _qi_exig(relleno, D.IMask)
            mascara.MaskStyle = D.esriMSHalo
            mascara.MaskSize = float(simbolo.contorno_pt)
            halo = _nobj(D.SimpleFillSymbol, D.ISimpleFillSymbol)
            halo.Style = D.esriSFSSolid
            halo.Color = _color(simbolo.contorno_rgb)
            sin_borde = _nobj(D.SimpleLineSymbol, D.ISimpleLineSymbol)
            sin_borde.Style = D.esriSLSNull
            halo.Outline = sin_borde
            mascara.MaskSymbol = _qi_exig(halo, D.IFillSymbol)
        return _qi_exig(relleno, D.ISymbol)

    raise SimbologiaNoSoportada(
        u"simbolo %s sin emisor" % type(simbolo).__name__)


def _marcador_caracter(fuente, codigo, size_pt, rgb, angulo):
    """-> ICharacterMarkerSymbol con un glifo de `fuente`."""
    D, _ = _mods()
    from comtypes.client import CreateObject
    import comtypes.gen.stdole as stdole
    font = CreateObject(stdole.StdFont, interface=stdole.IFontDisp)
    font.Name = fuente
    cm = _nobj(D.CharacterMarkerSymbol, D.ICharacterMarkerSymbol)
    cm.Font = font
    cm.CharacterIndex = int(codigo)
    cm.Color = _color(rgb)
    cm.Size = float(size_pt)
    if angulo:
        cm.Angle = _angulo_arcmap(angulo)
    return cm


def _angulo_arcmap(angulo_qgis):
    """Rotacion de marcador QGIS -> IMarkerSymbol.Angle.

    QGIS gira los marcadores en sentido HORARIO y ArcMap en ANTIHORARIO
    (visto por render el 2026-09-24: un triangulo a 30 grados apunta a la
    izquierda en QGIS y a la derecha en ArcMap). Hasta entonces se copiaba el
    angulo tal cual; el unico caso con test era un cuadrado a 45, simetrico,
    que se ve igual girado en los dos sentidos.
    """
    return (-float(angulo_qgis)) % 360.0


def _renderer(renderer_modelo):
    _, CA = _mods()

    if isinstance(renderer_modelo, RendererSimple):
        r = _nobj(CA.SimpleRenderer, CA.ISimpleRenderer)
        r.Symbol = _simbolo(renderer_modelo.simbolo)
        if renderer_modelo.label:
            r.Label = renderer_modelo.label
        return _qi_exig(r, CA.IFeatureRenderer)

    if isinstance(renderer_modelo, RendererValoresUnicos):
        r = _nobj(CA.UniqueValueRenderer, CA.IUniqueValueRenderer)
        r.FieldCount = len(renderer_modelo.campos)
        for i, campo in enumerate(renderer_modelo.campos):
            r.Field[i] = campo
        for clase in renderer_modelo.clases:
            r.AddValue(clase.valor, "", _simbolo(clase.simbolo))
            r.Label[clase.valor] = clase.label
        if renderer_modelo.default_simbolo is not None:
            r.DefaultSymbol = _simbolo(renderer_modelo.default_simbolo)
            r.UseDefaultSymbol = True
            r.DefaultLabel = renderer_modelo.default_label
        else:
            r.UseDefaultSymbol = False
        return _qi_exig(r, CA.IFeatureRenderer)

    if isinstance(renderer_modelo, RendererGraduado):
        r = _nobj(CA.ClassBreaksRenderer, CA.IClassBreaksRenderer)
        r.Field = renderer_modelo.campo
        rangos = renderer_modelo.rangos
        # BreakCount dimensiona los arrays: fijarlo ANTES de tocar Break/Symbol.
        r.BreakCount = len(rangos)
        r.MinimumBreak = rangos[0].inferior
        for i, rango in enumerate(rangos):
            # ArcMap guarda solo el corte SUPERIOR de cada clase; el inferior
            # es el corte de la clase previa (o MinimumBreak en la primera).
            r.Break[i] = rango.superior
            r.Symbol[i] = _simbolo(rango.simbolo)
            r.Label[i] = rango.label
        return _qi_exig(r, CA.IFeatureRenderer)

    raise SimbologiaNoSoportada(
        u"renderer %s sin emisor" % type(renderer_modelo).__name__)


def _renderer_raster(renderer_modelo, raster):
    """Renderer raster del modelo -> IRasterRenderer ya enganchado al raster."""
    _, CA = _mods()

    if isinstance(renderer_modelo, RendererRasterValoresUnicos):
        uvr = _nobj(CA.RasterUniqueValueRenderer, CA.IRasterUniqueValueRenderer)
        rr = _qi_exig(uvr, CA.IRasterRenderer)
        rr.Raster = raster
        rr.Update()
        uvr.Field = renderer_modelo.campo
        uvr.HeadingCount = 1
        uvr.ClassCount[0] = len(renderer_modelo.clases)
        for i, clase in enumerate(renderer_modelo.clases):
            uvr.AddValue(0, i, str(clase.valor))
            uvr.Label[0, i] = clase.label
            uvr.Symbol[0, i] = _simbolo(clase.simbolo)
        rr.Update()
        return rr

    if isinstance(renderer_modelo, RendererRasterCortes):
        ccr = _nobj(CA.RasterClassifyColorRampRenderer,
                    CA.IRasterClassifyColorRampRenderer)
        rr = _qi_exig(ccr, CA.IRasterRenderer)
        rr.Raster = raster
        ccr.ClassCount = len(renderer_modelo.clases)
        # Update() clasifica el raster por su cuenta: deja Break[0] en el minimo
        # y Break[ClassCount] en el maximo. Imprescindible ANTES de escribir.
        rr.Update()
        for i, clase in enumerate(renderer_modelo.clases):
            # GOTCHA: hay ClassCount+1 cortes y Break[0] es el MINIMO (este
            # renderer no tiene MinimumBreak, al reves que el vectorial), asi
            # que el techo de la clase i es Break[i+1]. El motor original
            # escribia los techos en Break[0..n-1]: desplazaba todas las clases
            # una posicion, dejaba la ultima vacia y el tramo inferior sin
            # clase. Verificado 2026-07-15 contra los datos.
            ccr.Break[i + 1] = float(clase.superior)
            ccr.Label[i] = clase.label
            ccr.Symbol[i] = _simbolo(clase.simbolo)
        rr.Update()
        return rr

    if isinstance(renderer_modelo, RendererRasterEstirado):
        return _renderer_estirado(renderer_modelo, raster)

    raise SimbologiaNoSoportada(
        u"renderer raster %s sin emisor" % type(renderer_modelo).__name__)


def _rampa_multiparte(paradas, minimo, maximo, resolucion=256):
    """Paradas de color de QGIS -> IColorRamp multiparte para el estirado.

    Una IAlgorithmicColorRamp por tramo entre paradas consecutivas, con
    algoritmo LINEAL (QGIS interpola en RGB), y con tantos colores como su
    fraccion del rango total (asi los tramos desiguales reparten bien). El
    estirado luego muestrea esta rampa sobre [minimo, maximo].
    """
    D, _ = _mods()
    algoritmo = getattr(D, "esriLinearAlgorithm", 2)
    multi = _nobj(D.MultiPartColorRamp, D.IMultiPartColorRamp)
    ancho_total = float(maximo - minimo)
    total = 0
    for anterior, siguiente in zip(paradas, paradas[1:]):
        seg = _nobj(D.AlgorithmicColorRamp, D.IAlgorithmicColorRamp)
        seg.Algorithm = algoritmo
        seg.FromColor = _color(anterior.rgb)
        seg.ToColor = _color(siguiente.rgb)
        frac = (siguiente.valor - anterior.valor) / ancho_total if ancho_total else 0
        seg.Size = max(2, int(round(resolucion * frac)))
        if seg.CreateRamp() is False:
            raise SimbologiaNoSoportada(u"no se pudo crear el tramo de rampa")
        total += seg.Size
        multi.AddRamp(_qi_exig(seg, D.IColorRamp))
    # GOTCHA: hay que fijar el Size total del multiparte ANTES de su CreateRamp;
    # si no, queda en Size 0, CreateRamp lanza E_FAIL y el estirado renderiza
    # gris. Con Size fijado, el multiparte reparte los colores por sus tramos y
    # reproduce las paradas de QGIS. (Verificado 2026-07-16 muestreando Color[i].)
    multi.Size = total
    if multi.CreateRamp() is False:
        raise SimbologiaNoSoportada(u"no se pudo crear la rampa multiparte")
    return _qi_exig(multi, D.IColorRamp)


def _prop_raster(arcpy, ruta_dato, propiedad):
    """GetRasterProperties -> float, o None si falla. Tolera la coma decimal
    del locale es-ES (arcpy devuelve p.ej. '67,09')."""
    try:
        texto = arcpy.GetRasterProperties_management(
            ruta_dato, propiedad).getOutput(0)
    except Exception:
        return None
    try:
        return float(texto.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _renderer_estirado(renderer_modelo, raster):
    """RendererRasterEstirado -> IRasterStretchColorRampRenderer.

    El estirado usa el min/max del DATASET (StretchType MinimumMaximum). Cuando
    coincide con el rango de la clasificacion QGIS (lo normal: el raster se creo
    con ese rango) el reparto de color es identico. Cuando difieren, ArcMap
    estira sobre el rango del dataset; emitir() lo detecta y lo AVISA (aqui no se
    puede: esta funcion no ve la lista de avisos). Forzar el rango QGIS exigiria
    una RasterStatistics custom que este build de ArcObjects no expone limpiamente.
    """
    _, CA = _mods()
    D, _ = _mods()
    m = renderer_modelo
    rsr = _nobj(CA.RasterStretchColorRampRenderer,
                CA.IRasterStretchColorRampRenderer)
    rr = _qi_exig(rsr, CA.IRasterRenderer)
    rr.Raster = raster
    rr.Update()
    rsr.BandIndex = 0
    rsr.ColorRamp = _rampa_multiparte(m.paradas, m.minimo, m.maximo)
    rsr.LabelLow = u"%g" % m.minimo
    rsr.LabelHigh = u"%g" % m.maximo
    est = _qi_exig(rsr, CA.IRasterStretch)
    est.StretchType = CA.esriRasterStretch_MinimumMaximum
    rr.Update()
    return rr


def emitir(capa_estilo, ruta_dato, ruta_lyr_salida, dir_tmp):
    """Genera un .lyr desde una CapaEstilo del modelo.

    ruta_dato: shapefile o raster fuente (absoluto). La resolucion de
    datasources relativos del .qgs es responsabilidad del llamador (fase F4).
    """
    _init_arcobjects()
    import arcpy
    _, CA = _mods()

    es_raster = isinstance(capa_estilo.renderer, _RENDERERS_RASTER)
    if isinstance(capa_estilo.renderer,
                  (RendererRasterCortes, RendererRasterEstirado)):
        # Ambos leen el min/max del raster: el clasificado para colocar Break[0]
        # (si no, saldria mal) y el estirado para el rango del estirado y para el
        # aviso de divergencia de abajo. Se calculan SOLO si faltan: son datos
        # del usuario y CalculateStatistics reescribe sus sidecars (.aux.xml) en
        # cada pasada; en una carpeta sincronizada eso dispara un resync inutil.
        try:
            arcpy.GetRasterProperties_management(ruta_dato, "MINIMUM")
        except Exception:
            arcpy.CalculateStatistics_management(ruta_dato)

    if isinstance(capa_estilo.renderer, RendererRasterEstirado):
        # El estirado usa el min/max del DATASET (StretchType MinimumMaximum).
        # Si difiere del rango de la clasificacion QGIS, ArcMap reparte el color
        # sobre otro rango -> los colores no coinciden con QGIS y la leyenda
        # (LabelLow/High, que si llevan el rango QGIS) mentiria. NO se degrada en
        # silencio: se avisa. (Forzar el rango QGIS exigiria una RasterStatistics
        # custom que este build de ArcObjects no expone limpiamente.)
        m = capa_estilo.renderer
        d_min = _prop_raster(arcpy, ruta_dato, "MINIMUM")
        d_max = _prop_raster(arcpy, ruta_dato, "MAXIMUM")
        if d_min is not None and d_max is not None:
            tol = 1e-6 * max(1.0, abs(m.minimo), abs(m.maximo))
            if abs(d_min - m.minimo) > tol or abs(d_max - m.maximo) > tol:
                capa_estilo.avisos.append(
                    u"el rango de la clasificacion QGIS (%g..%g) no coincide con "
                    u"el del raster (%g..%g): ArcMap estira el color sobre el "
                    u"rango del raster, asi que los colores diferiran de QGIS"
                    % (m.minimo, m.maximo, d_min, d_max))

    if not os.path.isdir(dir_tmp):
        os.makedirs(dir_tmp)
    _TMP["dir"] = dir_tmp  # lo consume la rama de relleno con imagen
    base = os.path.join(dir_tmp, "base.lyr")

    # Nombre de la capa en memoria y del .lyr base: unicos POR PROCESO. Con
    # nombres fijos, dos QGIS convirtiendo a la vez comparten el mismo
    # base.lyr del temporal y se pisan.
    tmp_layer = "tmpL_%d" % os.getpid()
    if arcpy.Exists(tmp_layer):
        arcpy.Delete_management(tmp_layer)
    if os.path.exists(base):
        os.remove(base)
    if es_raster:
        arcpy.MakeRasterLayer_management(ruta_dato, tmp_layer)
    elif capa_estilo.defquery:
        arcpy.MakeFeatureLayer_management(ruta_dato, tmp_layer,
                                          capa_estilo.defquery)
    else:
        arcpy.MakeFeatureLayer_management(ruta_dato, tmp_layer)
    arcpy.SaveToLayerFile_management(tmp_layer, base, "ABSOLUTE")

    lf = _nobj(CA.LayerFile, CA.ILayerFile)
    lf.Open(base)
    layer = lf.Layer
    if capa_estilo.nombre:
        layer.Name = capa_estilo.nombre
    if es_raster:
        rl = _qi_exig(layer, CA.IRasterLayer)
        rl.Renderer = _renderer_raster(capa_estilo.renderer, rl.Raster)
    else:
        _qi_exig(layer, CA.IGeoFeatureLayer).Renderer = _renderer(
            capa_estilo.renderer)

    # Opacidad QGIS (0-1) -> transparencia ArcMap (0-100), redondeada al entero
    # que admite ILayerEffects.
    if abs(capa_estilo.opacidad - 1.0) > 1e-6:
        _qi_exig(layer, CA.ILayerEffects).Transparency = int(
            round((1.0 - capa_estilo.opacidad) * 100))

    # Visibilidad por escala. Misma semantica que QGIS (denominadores, 0 = sin
    # limite): minScale = limite alejado -> MinimumScale; maxScale = limite
    # acercado -> MaximumScale. Verificado que el .lyr las conserva al releerlo.
    if getattr(capa_estilo, "escala_min", 0):
        layer.MinimumScale = float(capa_estilo.escala_min)
    if getattr(capa_estilo, "escala_max", 0):
        layer.MaximumScale = float(capa_estilo.escala_max)

    if capa_estilo.defquery:
        fld = _qi(layer, CA.IFeatureLayerDefinition)
        if fld is not None:
            fld.DefinitionExpression = capa_estilo.defquery

    if os.path.exists(ruta_lyr_salida):
        os.remove(ruta_lyr_salida)
    olf = _nobj(CA.LayerFile, CA.ILayerFile)
    olf.New(ruta_lyr_salida)
    olf.ReplaceContents(_qi_exig(layer, CA.ILayer))
    olf.Save()
    olf.Close()
    lf.Close()
    return ruta_lyr_salida


# ---------------------------------------------------------------------------
# Contrato F4: interfaz de subproceso para el plugin (ADR-001).
#
# El plugin QGIS (py3) no puede tocar ArcObjects, asi que lanza este modulo con
# el Python 2.7 de ArcGIS como subproceso y lee un JSON por stdout. Tres modos:
#   Recomendado: emisor.py --args-json <args.json>   (el que usa el plugin)
#   Posicional:  emisor.py <estilo.qml> <ruta_dato> <salida.lyr>
#                          [--nombre N] [--defquery Q]
#   Batch:       emisor.py --batch <proyecto.qgz> <dir_salida>
# El JSON reporta ok/avisos/error por capa: la UI hace "avisar y saltar" sin que
# el subproceso reviente. Una capa que falla NO aborta el batch.
# ---------------------------------------------------------------------------

def _u(valor):
    """Cualquier texto -> unicode. Nunca revienta.

    GOTCHA (reproducido el 2026-09-20): en py2.7 `sys.argv` llega en BYTES de
    la codepage ANSI de Windows (cp1252 aqui), NO en utf-8. Un `--nombre "Vias
    pecuarias"` con tilde entraba al dict de resultado como str cp1252 y
    `json.dumps(..., ensure_ascii=False)` reventaba con UnicodeDecodeError al
    juntar trozos str con los avisos unicode del parser -- y lo hacia DESPUES
    de escribir el .lyr, asi que el plugin veia stdout vacio y exit 1 sobre un
    fichero que si existia. Sin avisos unicode no reventaba, pero escupia
    bytes cp1252 en un stdout que el plugin decodifica como utf-8 (mojibake).
    """
    if valor is None or isinstance(valor, unicode):
        return valor
    if isinstance(valor, bytes):
        for codec in (sys.getfilesystemencoding() or "mbcs", "utf-8"):
            try:
                return valor.decode(codec)
            except (UnicodeDecodeError, LookupError):
                continue
        return valor.decode("utf-8", "replace")
    return valor


def _unicodizar(obj):
    """Recorre el resultado y deja TODO texto en unicode antes del json.dumps."""
    if isinstance(obj, dict):
        return dict((_u(k), _unicodizar(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_unicodizar(v) for v in obj]
    if isinstance(obj, bytes):
        return _u(obj)
    return obj


def _texto_error(e):
    try:
        return _u(unicode(e))
    except UnicodeDecodeError:
        # Mensaje de COM/arcpy en cp1252: `unicode(e)` intenta ascii y falla.
        return _u(str(e))
    except Exception:
        return _u(repr(e))


def _nombre_fichero(nombre):
    """Nombre de capa -> nombre de fichero seguro (sin caracteres problematicos)."""
    limpio = _re.sub(u"[^0-9A-Za-z._-]+", u"_", nombre or u"capa").strip(u"_")
    return limpio or u"capa"


def _nombre_unico(etiqueta, usados):
    """Etiqueta de fichero no usada aun, registrandola en `usados`.

    `usados` es un set con TODAS las etiquetas finales ya asignadas (incluidas
    las sufijadas). Al comprobar el candidato contra ese conjunto se evitan las
    dos colisiones que detecto el verificador: dos nombres que sanean igual (p.ej.
    labels que solo difieren en puntuacion) Y un nombre base que coincide con un
    sufijo autogenerado (['foo','foo','foo_1']). Sin esto, .lyr se pisaban en
    silencio con ok=True mentiroso."""
    candidato = etiqueta
    n = 1
    while candidato in usados:
        candidato = u"%s_%d" % (etiqueta, n)
        n += 1
    usados.add(candidato)
    return candidato


def _resolver_datasource(ruta, dir_proyecto):
    """Ruta de dato del .qgs -> ruta absoluta. Los datasources relativos van
    contra la carpeta del proyecto; los absolutos (C:\\, unidad de red, UNC) se
    dejan igual.

    Aqui ya NO se parte por `|`: lo hace `parser_qgis._partir_datasource`, que
    es quien sabe distinguir un `subset=` de un `layername=` de GeoPackage.
    Partir otra vez se comia el `\\main.<capa>` de un .gpkg ya resuelto."""
    if not ruta:
        return None
    if _re.match(u"^[A-Za-z]:", ruta) or ruta.startswith(u"\\\\") \
            or ruta.startswith(u"/"):
        return os.path.normpath(ruta)
    return os.path.normpath(os.path.join(dir_proyecto, ruta))


def _existe_dataset(ruta):
    """Existe el dato? Un .gpkg resuelto (`x.gpkg\\main.capa`) no es un fichero
    del sistema, asi que `os.path.exists` diria que no: para esos se comprueba
    que exista el contenedor."""
    if os.path.exists(ruta):
        return True
    contenedor = os.path.dirname(ruta)
    return bool(contenedor) and os.path.splitext(contenedor)[1].lower() \
        == u".gpkg" and os.path.exists(contenedor)


def _reapuntar_lyr(ruta_lyr, regla):
    """Devuelve el .lyr (leido por el DESTINO de una regla de --remap) a la
    ruta ORIGINAL del proyecto, sin validar: la unidad original puede no
    existir en esta maquina, que es justo el caso de uso.

    -> (dataSource final leido de vuelta, avisos). Se relee el fichero: lo que
    cuenta es lo que quedo guardado, no lo que se pidio."""
    import arcpy
    import parser_qgis
    origen, destino = regla
    avisos = []
    lyr = arcpy.mapping.Layer(ruta_lyr)
    ws = lyr.workspacePath
    ws_original, aplicada = parser_qgis.remapear(ws, [(destino, origen)])
    if aplicada is None:
        raise RuntimeError(u"el espacio de trabajo del .lyr (%s) no empieza "
                           u"por %s: no se puede reapuntar a %s"
                           % (_u(ws), destino, origen))
    lyr.findAndReplaceWorkspacePath(ws, ws_original, False)
    lyr.save()
    del lyr
    final = _u(arcpy.mapping.Layer(ruta_lyr).dataSource)
    if not final.lower().startswith(ws_original.lower()):
        raise RuntimeError(u"el .lyr quedo apuntando a %s, no a %s"
                           % (final, ws_original))
    unidad = os.path.splitdrive(ws_original)[0]
    if unidad and not unidad.startswith(u"\\\\") \
            and not os.path.exists(unidad + u"\\"):
        avisos.append(u"el .lyr apunta a %s y la unidad %s no existe en esta "
                      u"maquina: ArcMap vera la capa rota hasta abrirla donde "
                      u"%s exista" % (final, unidad, unidad))
    return final, avisos


def _emitir_capa_segura(capa, ruta_dato, ruta_salida, dir_tmp):
    """Emite UNA capa y devuelve su dict de resultado. NUNCA lanza: un fallo se
    reporta como ok=False (doctrina avisar-y-saltar)."""
    try:
        emitir(capa, ruta_dato, ruta_salida, dir_tmp)
        return {"ok": True, "nombre": capa.nombre, "salida": ruta_salida,
                "avisos": list(capa.avisos)}
    except SimbologiaNoSoportada as e:
        return {"ok": False, "nombre": capa.nombre,
                "error": _texto_error(e), "tipo_error": "SimbologiaNoSoportada",
                "avisos": list(capa.avisos)}
    except Exception as e:
        return {"ok": False, "nombre": capa.nombre,
                "error": _texto_error(e), "tipo_error": type(e).__name__,
                "avisos": list(capa.avisos)}


def _dir_tmp_por_defecto(dir_tmp):
    """-> (directorio temporal, hay_que_borrarlo_al_terminar).

    El nombre lleva el PID: dos QGIS convirtiendo a la vez tenian el mismo
    `qml2lyr_tmp` y se pisaban el `base.lyr` y las texturas."""
    if dir_tmp:
        return dir_tmp, False
    import tempfile
    return (os.path.join(tempfile.gettempdir(),
                         "qml2lyr_tmp_%d" % os.getpid()), True)


def _limpiar_dir_tmp(dir_tmp, avisos):
    """Borra el temporal propio (base.lyr + texturas). Un fallo se AVISA."""
    import shutil
    if not os.path.isdir(dir_tmp):
        return
    try:
        shutil.rmtree(dir_tmp)
    except OSError as e:
        avisos.append(u"no se pudo borrar el directorio temporal %s: %s"
                      % (_u(dir_tmp), _texto_error(e)))


def emitir_qml(ruta_qml, ruta_dato, ruta_lyr_salida, nombre=None, dir_tmp=None,
               defquery=None):
    """Modo principal: un .qml (estilo de la capa viva) -> .lyr.

    Un .qml normal da una capa; un .qml rule-based da N (una .lyr por regla,
    con sufijo _<etiqueta> sobre la ruta de salida).

    `defquery` es la definition query de la capa VIVA de QGIS
    (`QgsVectorLayer.subsetString()`): el .qml no la lleva, asi que la aporta
    el llamador. Si la capa es rule-based, acota a todas las reglas, igual que
    hace `parse_maplayer` con la del .qgz."""
    import parser_qgis
    dir_tmp, propio = _dir_tmp_por_defecto(dir_tmp)
    avisos_globales = []
    try:
        capas = parser_qgis.parse_qml(ruta_qml)
    except Exception as e:
        return {"ok": False, "modo": "qml", "entrada": ruta_qml,
                "error": _texto_error(e), "tipo_error": type(e).__name__,
                "capas": [], "avisos": avisos_globales}
    base, ext = os.path.splitext(ruta_lyr_salida)
    resultados = []
    usados = set()
    for i, capa in enumerate(capas):
        if capa.nombre is None and nombre:
            capa.nombre = nombre
        capa.defquery = parser_qgis.combinar_defquery(defquery, capa.defquery)
        if len(capas) == 1:
            salida = ruta_lyr_salida
        else:
            etiqueta = _nombre_unico(
                _nombre_fichero(capa.nombre or (u"regla_%d" % i)), usados)
            salida = u"%s_%s%s" % (base, etiqueta, ext)
        resultados.append(_emitir_capa_segura(capa, ruta_dato, salida, dir_tmp))
    if propio:
        _limpiar_dir_tmp(dir_tmp, avisos_globales)
    return {"ok": all(r["ok"] for r in resultados) if resultados else False,
            "modo": "qml", "entrada": ruta_qml, "capas": resultados,
            "avisos": avisos_globales}


def emitir_qgz(ruta_qgz, dir_salida, dir_tmp=None, remap=None):
    """Modo batch (secundario): un proyecto .qgz entero -> un .lyr por capa.

    Resuelve la ruta del dato de cada capa (relativa al .qgz). Una capa sin dato
    o con simbologia no soportada se reporta ok=False y se salta; el batch sigue.

    `remap`: reglas (origen, destino) de `parser_qgis.parse_remap`. Una capa
    cuya ruta empieza por `origen` se LEE en `destino` y su .lyr se guarda
    apuntando a la ruta ORIGINAL (caso: un proyecto con rutas `Z:` convertido
    en una maquina donde esa unidad se llama de otra forma)."""
    import parser_qgis
    dir_tmp, propio = _dir_tmp_por_defecto(dir_tmp)
    avisos_globales = []
    dir_proyecto = os.path.dirname(os.path.abspath(ruta_qgz))
    try:
        raiz = parser_qgis._raiz_qgs(ruta_qgz)
    except Exception as e:
        return {"ok": False, "modo": "qgz", "entrada": ruta_qgz,
                "error": _texto_error(e), "tipo_error": type(e).__name__,
                "capas": [], "avisos": avisos_globales}
    if not os.path.isdir(dir_salida):
        os.makedirs(dir_salida)
    resultados = []
    usados = set()
    for ml in raiz.iter("maplayer"):
        nombre_capa = ml.findtext("layername") or u"sin_nombre"
        try:
            capas = parser_qgis.parse_maplayer(ml)
        except SimbologiaNoSoportada as e:
            resultados.append({"ok": False, "nombre": nombre_capa,
                               "error": _texto_error(e),
                               "tipo_error": "SimbologiaNoSoportada", "avisos": []})
            continue
        except Exception as e:
            resultados.append({"ok": False, "nombre": nombre_capa,
                               "error": _texto_error(e),
                               "tipo_error": type(e).__name__, "avisos": []})
            continue
        for capa in capas:
            ruta_dato = _resolver_datasource(capa.datasource, dir_proyecto)
            ruta_lectura, regla = parser_qgis.remapear(ruta_dato, remap)
            if not ruta_lectura or not _existe_dataset(ruta_lectura):
                donde = capa.datasource
                if regla:
                    donde = u"%s (leido como %s por --remap)" % (
                        capa.datasource, ruta_lectura)
                resultados.append({"ok": False, "nombre": capa.nombre,
                                   "error": u"dato no encontrado: %s" % donde,
                                   "tipo_error": "DatoNoEncontrado",
                                   "avisos": list(capa.avisos)})
                continue
            etiqueta = _nombre_unico(
                _nombre_fichero(capa.nombre or nombre_capa), usados)
            salida = os.path.join(dir_salida, etiqueta + u".lyr")
            resultado = _emitir_capa_segura(capa, ruta_lectura, salida, dir_tmp)
            if regla and resultado["ok"]:
                try:
                    final, avisos = _reapuntar_lyr(salida, regla)
                    resultado["dato"] = final
                    resultado["avisos"].extend(avisos)
                except Exception as e:
                    # El .lyr existe pero apunta a la ruta de LECTURA, no a la
                    # del proyecto: no es lo que se pidio, asi que no es ok.
                    resultado.update({
                        "ok": False, "tipo_error": "ReapunteFallido",
                        "error": u"el .lyr se escribio leyendo %s pero no se "
                                 u"pudo reapuntar a la ruta original: %s"
                                 % (ruta_lectura, _texto_error(e))})
            resultados.append(resultado)
    if propio:
        _limpiar_dir_tmp(dir_tmp, avisos_globales)
    ok = sum(1 for r in resultados if r["ok"])
    return {"ok": True, "modo": "qgz", "entrada": ruta_qgz,
            "resumen": {"ok": ok, "error": len(resultados) - ok,
                        "total": len(resultados)},
            "capas": resultados, "avisos": avisos_globales}


def _imprimir_json(obj):
    """JSON utf-8 por stdout. `_unicodizar` es el cinturon: aunque algo entre
    en bytes al dict de resultado, aqui ya no puede reventar el json.dumps."""
    texto = json.dumps(_unicodizar(obj), ensure_ascii=False, indent=2,
                       sort_keys=True)
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", "replace")
    sys.stdout.write(texto.encode("utf-8") + "\n")


_CLAVES_ARGS_JSON = ("qml", "dato", "salida", "nombre", "defquery", "dir_tmp")


def _leer_args_json(ruta):
    """Fichero JSON en UTF-8 con los argumentos del modo .qml.

    Es el modo que usa el plugin: asi ni los textos con tilde (que en py2.7
    llegan a `sys.argv` en cp1252 y rompen el JSON de salida) ni la def-query
    (llena de comillas) tienen que pasar por la linea de comandos.

    Claves: qml, dato, salida (obligatorias) + nombre, defquery, dir_tmp.
    """
    f = open(ruta, "rb")
    try:
        datos = json.loads(f.read().decode("utf-8"))
    finally:
        f.close()
    if not isinstance(datos, dict):
        raise ValueError(u"%s no contiene un objeto JSON" % _u(ruta))
    faltan = [k for k in ("qml", "dato", "salida") if not datos.get(k)]
    if faltan:
        raise ValueError(u"faltan claves obligatorias en %s: %s"
                         % (_u(ruta), u", ".join(faltan)))
    sobran = [k for k in datos if k not in _CLAVES_ARGS_JSON]
    if sobran:
        # Una clave de mas suele ser una errata (`def_query` por `defquery`):
        # ignorarla en silencio perderia la def-query sin que nadie lo note.
        raise ValueError(u"claves no reconocidas en %s: %s (validas: %s)"
                         % (_u(ruta), u", ".join(sorted(sobran)),
                            u", ".join(_CLAVES_ARGS_JSON)))
    return datos


def _main(argv):
    import argparse
    # py2.7 entrega argv en bytes de la codepage ANSI: se decodifica ANTES de
    # que nada de esto entre en el dict de resultado (ver `_u`).
    argv = [_u(a) for a in argv]
    p = argparse.ArgumentParser(
        prog="emisor.py",
        description="Emite .lyr de ArcMap desde estilo QGIS (contrato F4).")
    p.add_argument("--batch", action="store_true",
                   help="modo batch: entrada=.qgz, salida=directorio")
    p.add_argument("--args-json", dest="args_json", default=None,
                   help="fichero JSON utf-8 con qml/dato/salida/nombre/"
                        "defquery/dir_tmp (modo recomendado: evita la "
                        "codepage de la linea de comandos)")
    p.add_argument("--nombre", default=None,
                   help="nombre de la capa en el .lyr (modo .qml de una capa)")
    p.add_argument("--defquery", default=None,
                   help="definition query de la capa (modo .qml)")
    p.add_argument("--remap", action="append", default=[],
                   metavar="ORIGEN=DESTINO",
                   help="modo --batch, repetible: lee en DESTINO lo que el "
                        "proyecto tiene en ORIGEN y deja el .lyr apuntando a "
                        "ORIGEN (p.ej. \"Z:=L:\Mi unidad\Carto\")")
    p.add_argument("posicionales", nargs="*",
                   help=".qml <dato> <salida.lyr>  |  --batch .qgz <dir_salida>")
    args = p.parse_args(argv)
    if args.remap and not args.batch:
        # En los modos .qml el llamador ya pasa la ruta del dato resuelta.
        p.error("--remap solo vale en modo --batch")

    if args.args_json:
        if args.posicionales:
            p.error("--args-json no lleva argumentos posicionales")
        try:
            datos = _leer_args_json(args.args_json)
        except Exception as e:
            _imprimir_json({"ok": False, "modo": "qml",
                            "entrada": args.args_json,
                            "error": _texto_error(e),
                            "tipo_error": type(e).__name__,
                            "capas": [], "avisos": []})
            return 1
        resultado = emitir_qml(datos["qml"], datos["dato"], datos["salida"],
                               nombre=datos.get("nombre"),
                               defquery=datos.get("defquery"),
                               dir_tmp=datos.get("dir_tmp"))
        _imprimir_json(resultado)
        return 0 if resultado.get("ok") else 1

    if args.batch:
        if len(args.posicionales) != 2:
            p.error("modo --batch: <proyecto.qgz> <dir_salida>")
        import parser_qgis
        try:
            reglas = [parser_qgis.parse_remap(r) for r in args.remap]
        except ValueError as e:
            p.error(_texto_error(e).encode("utf-8"))
        resultado = emitir_qgz(args.posicionales[0], args.posicionales[1],
                               remap=reglas)
        _imprimir_json(resultado)
        return 0 if resultado.get("ok") else 2

    if len(args.posicionales) != 3:
        p.error("modo .qml: <estilo.qml> <ruta_dato> <salida.lyr>")
    qml, dato, salida = args.posicionales
    resultado = emitir_qml(qml, dato, salida, nombre=args.nombre,
                           defquery=args.defquery)
    _imprimir_json(resultado)
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
