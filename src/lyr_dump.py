# -*- coding: utf-8 -*-
"""Lector de .lyr via ArcObjects: vuelca el renderer a un dict comparable.

Base del test de regresion (los .lyr son binarios, no se pueden diffear).
Tambien es la semilla de una futura direccion inversa .lyr -> .qml.

Ejecutar con el Python 2.7 de ArcGIS 10.5.

Alcance F2: SimpleRenderer y UniqueValueRenderer; simbolos SimpleFill,
SimpleLine, LineFill (tramado) y SimpleMarker. Los renderers raster llegan
en F3.
"""
import sys
sys.coinit_flags = 2
import json

from emisor import _init_arcobjects, _mods, _nobj, _qi

# esriSimpleLineStyle
_NOMBRE_ESTILO_LINEA = {0: "solid", 1: "dash", 2: "dot", 3: "dashdot",
                        4: "dashdotdot", 5: "no"}
# esriSimpleFillStyle
_NOMBRE_ESTILO_RELLENO = {0: "solid", 1: "null", 2: "horizontal", 3: "vertical",
                          4: "diagonal_adelante", 5: "diagonal_atras",
                          6: "cruz", 7: "cruz_diagonal"}
# esriSimpleMarkerStyle
_NOMBRE_ESTILO_MARCADOR = {0: "circulo", 1: "cuadrado", 2: "cruz", 3: "equis",
                           4: "diamante"}


def _dump_color(color_obj):
    if color_obj is None:
        return None
    D, _ = _mods()
    c = _qi(color_obj, D.IRgbColor)
    if c is None:
        return {"tipo": "no-rgb"}
    return {"rgb": [c.Red, c.Green, c.Blue], "transparencia": c.Transparency,
            "nulo": bool(c.NullColor)}


def _dump_linea(sym):
    D, _ = _mods()
    ls = _qi(sym, D.ISimpleLineSymbol)
    if ls is None:
        return {"tipo": type(sym).__name__}
    d = {"tipo": "SimpleLine",
         "estilo": _NOMBRE_ESTILO_LINEA.get(ls.Style, ls.Style)}
    if d["estilo"] != "no":
        d["color"] = _dump_color(ls.Color)
        d["ancho_pt"] = round(ls.Width, 3)
    return d


def _dump_marcador(ms):
    d = {"tipo": "SimpleMarker",
         "estilo": _NOMBRE_ESTILO_MARCADOR.get(ms.Style, ms.Style),
         "color": _dump_color(ms.Color),
         "tamanyo_pt": round(ms.Size, 3),
         "contorno": bool(ms.Outline)}
    if d["contorno"]:
        d["contorno_color"] = _dump_color(ms.OutlineColor)
        d["contorno_pt"] = round(ms.OutlineSize, 3)
    # Solo si hay rotacion, como `transparencia_pct`: asi el volcado de los
    # golden anteriores (todos con Angle 0) no cambia de forma.
    if round(ms.Angle, 3):
        d["angulo"] = round(ms.Angle, 3)
    return d


def _dump_simbolo(sym):
    """Cualquier ISymbol -> dict canonico. Orden: el mas especifico primero.

    OJO: LineFillSymbol tambien responde a IFillSymbol, por eso se prueba
    antes que SimpleFillSymbol.
    """
    if sym is None:
        return None
    D, _ = _mods()

    # El multicapa responde tambien a IFillSymbol: probarlo el PRIMERO.
    ml = _qi(sym, D.IMultiLayerFillSymbol)
    if ml is not None:
        return {"tipo": "MultiLayerFill",
                "capas": [_dump_simbolo(ml.Layer[i])
                          for i in range(ml.LayerCount)]}

    # PictureFillSymbol tambien responde a IFillSymbol: antes que SimpleFill.
    pf = _qi(sym, D.IPictureFillSymbol)
    if pf is not None:
        d = {"tipo": "PictureFill",
             "angulo": round(pf.Angle, 3),
             "contorno": _dump_linea(_qi(pf, D.IFillSymbol).Outline)}
        pic = pf.Picture
        d["tiene_imagen"] = pic is not None
        if pic is not None:
            try:
                d["imagen_tipo"] = int(pic.Type)
            except Exception:
                pass
        return d

    lf = _qi(sym, D.ILineFillSymbol)
    if lf is not None:
        return {"tipo": "LineFill",
                "color": _dump_color(lf.Color),
                "angulo": round(lf.Angle, 3),
                "separacion_pt": round(lf.Separation, 3),
                "linea": _dump_linea(lf.LineSymbol),
                "contorno": _dump_linea(_qi(lf, D.IFillSymbol).Outline)}

    fs = _qi(sym, D.ISimpleFillSymbol)
    if fs is not None:
        return {"tipo": "SimpleFill",
                "estilo": _NOMBRE_ESTILO_RELLENO.get(fs.Style, fs.Style),
                "color": _dump_color(fs.Color),
                "contorno": _dump_linea(fs.Outline)}

    mlm = _qi(sym, D.IMultiLayerMarkerSymbol)
    if mlm is not None:
        d = {"tipo": "MultiLayerMarker",
             "capas": [_dump_simbolo(mlm.Layer[i])
                       for i in range(mlm.LayerCount)]}
        mascara = _qi(sym, D.IMask)
        if mascara is not None and mascara.MaskStyle == D.esriMSHalo:
            relleno = _qi(mascara.MaskSymbol, D.ISimpleFillSymbol)
            d["halo"] = {"tamanyo_pt": round(mascara.MaskSize, 3),
                         "color": _dump_color(relleno.Color)
                         if relleno is not None else None}
        return d

    cm = _qi(sym, D.ICharacterMarkerSymbol)
    if cm is not None:
        d = {"tipo": "CharacterMarker",
             "fuente": cm.Font.Name,
             "caracter": int(cm.CharacterIndex),
             "color": _dump_color(cm.Color),
             "tamanyo_pt": round(cm.Size, 3)}
        if round(cm.Angle, 3):
            d["angulo"] = round(cm.Angle, 3)
        return d

    ms = _qi(sym, D.ISimpleMarkerSymbol)
    if ms is not None:
        return _dump_marcador(ms)

    ls = _qi(sym, D.ISimpleLineSymbol)
    if ls is not None:
        return _dump_linea(sym)

    return {"tipo": "no-soportado", "clase": type(sym).__name__}


def _dump_valores_unicos(uv):
    """IUniqueValueRenderer -> dict. Conserva el orden de clases del renderer."""
    campos = [uv.Field[i] for i in range(uv.FieldCount)]
    clases = []
    for i in range(uv.ValueCount):
        valor = uv.Value[i]
        clase = {"valor": valor,
                 "label": uv.Label[valor] or u"",
                 "simbolo": _dump_simbolo(uv.Symbol[valor])}
        try:
            # Solo existe para un valor agrupado bajo otro (AddReferenceValue);
            # para uno propio, ArcObjects da E_INVALIDARG.
            clase["referencia"] = uv.ReferenceValue[valor]
        except Exception:
            pass
        clases.append(clase)
    d = {"tipo": "valores_unicos",
         "campos": campos,
         "clases": clases,
         "usa_default": bool(uv.UseDefaultSymbol)}
    if len(campos) > 1:
        d["separador"] = uv.FieldDelimiter
    if d["usa_default"]:
        d["default_label"] = uv.DefaultLabel or u""
        d["default_simbolo"] = _dump_simbolo(uv.DefaultSymbol)
    return d


def _dump_renderer(rend):
    _, CA = _mods()

    uv = _qi(rend, CA.IUniqueValueRenderer)
    if uv is not None:
        return _dump_valores_unicos(uv)

    cb = _qi(rend, CA.IClassBreaksRenderer)
    if cb is not None:
        return {"tipo": "cortes",
                "campo": cb.Field,
                "minimo": round(cb.MinimumBreak, 6),
                "clases": [{"corte_superior": round(cb.Break[i], 6),
                            "label": cb.Label[i] or u"",
                            "simbolo": _dump_simbolo(cb.Symbol[i])}
                           for i in range(cb.BreakCount)]}

    sr = _qi(rend, CA.ISimpleRenderer)
    if sr is not None:
        return {"tipo": "simple", "label": sr.Label or u"",
                "simbolo": _dump_simbolo(sr.Symbol)}

    return {"tipo": "no-soportado", "clase": type(rend).__name__}


def _dump_renderer_raster(rend):
    _, CA = _mods()

    uv = _qi(rend, CA.IRasterUniqueValueRenderer)
    if uv is not None:
        clases = []
        for h in range(uv.HeadingCount):
            for i in range(uv.ClassCount[h]):
                clases.append({
                    # Una clase raster puede agrupar varios valores.
                    "valores": [uv.Value[h, i, v]
                                for v in range(uv.ValueCount[h, i])],
                    "label": uv.Label[h, i] or u"",
                    "simbolo": _dump_simbolo(uv.Symbol[h, i])})
        return {"tipo": "raster_valores_unicos", "campo": uv.Field,
                "clases": clases, "usa_default": bool(uv.UseDefaultSymbol)}

    cc = _qi(rend, CA.IRasterClassifyColorRampRenderer)
    if cc is not None:
        # Break[0] es el minimo; el techo de la clase i es Break[i+1].
        return {"tipo": "raster_cortes",
                "minimo": round(cc.Break[0], 6),
                "clases": [{"corte_superior": round(cc.Break[i + 1], 6),
                            "label": cc.Label[i] or u"",
                            "simbolo": _dump_simbolo(cc.Symbol[i])}
                           for i in range(cc.ClassCount)]}

    st = _qi(rend, CA.IRasterStretchColorRampRenderer)
    if st is not None:
        return {"tipo": "raster_estirado",
                "banda": int(st.BandIndex),
                "label_min": st.LabelLow or u"",
                "label_max": st.LabelHigh or u"",
                "rampa": _dump_rampa(st.ColorRamp)}

    return {"tipo": "no-soportado", "clase": type(rend).__name__}


def _rgb_de(color_obj):
    """IColor -> [R,G,B] via la propiedad IColor.RGB (BGR empaquetado).

    Los getters tipados (IRgbColor.Red/Green/Blue) y la enumeracion .Colors de
    una rampa son poco fiables en este build de ArcObjects (devuelven NULL o el
    enum no termina). IColor.RGB si es de fiar.
    """
    D, _ = _mods()
    ic = _qi(color_obj, D.IColor)
    if ic is None:
        return None
    bgr = int(ic.RGB)
    return [bgr & 255, (bgr >> 8) & 255, (bgr >> 16) & 255]


def _dump_rampa(ramp):
    """IColorRamp -> estructura verificable de la rampa.

    Releida de un .lyr, la rampa NO conserva sus 256 colores materializados
    (Size vuelve 0; ArcMap los regenera al dibujar), pero SI conserva su
    definicion: los tramos con FromColor/ToColor. Se vuelca eso, que reproduce
    las paradas de color de QGIS y es lo comparable en el test.
    """
    if ramp is None:
        return None
    D, _ = _mods()
    multi = _qi(ramp, D.IMultiPartColorRamp)
    if multi is not None:
        return {"tipo": "multiparte",
                "tramos": [{"de": _rgb_de(_qi(multi.Ramp[i],
                                              D.IAlgorithmicColorRamp).FromColor),
                            "a": _rgb_de(_qi(multi.Ramp[i],
                                            D.IAlgorithmicColorRamp).ToColor)}
                           for i in range(multi.NumberOfRamps)]}
    alg = _qi(ramp, D.IAlgorithmicColorRamp)
    if alg is not None:
        return {"tipo": "tramo", "de": _rgb_de(alg.FromColor),
                "a": _rgb_de(alg.ToColor)}
    return {"tipo": "otra", "tamanyo": int(ramp.Size)}


def dump_lyr(ruta_lyr):
    """Abre un .lyr y devuelve un dict canonico de su simbologia."""
    _init_arcobjects()
    _, CA = _mods()
    lf = _nobj(CA.LayerFile, CA.ILayerFile)
    lf.Open(ruta_lyr)
    try:
        layer = lf.Layer
        resultado = {"nombre": layer.Name}
        efectos = _qi(layer, CA.ILayerEffects)
        if efectos is not None and efectos.Transparency:
            resultado["transparencia_pct"] = int(efectos.Transparency)
        # Visibilidad por escala (ILayer). Se vuelca solo cuando hay limite,
        # igual que la transparencia: 0 = sin limite y es el caso normal.
        if layer.MinimumScale:
            resultado["escala_min"] = float(layer.MinimumScale)
        if layer.MaximumScale:
            resultado["escala_max"] = float(layer.MaximumScale)
        rl = _qi(layer, CA.IRasterLayer)
        if rl is not None:
            resultado["renderer"] = _dump_renderer_raster(rl.Renderer)
            return resultado
        gfl = _qi(layer, CA.IGeoFeatureLayer)
        if gfl is not None:
            resultado["renderer"] = _dump_renderer(gfl.Renderer)
        fld = _qi(layer, CA.IFeatureLayerDefinition)
        if fld is not None and fld.DefinitionExpression:
            resultado["defquery"] = fld.DefinitionExpression
        return resultado
    finally:
        lf.Close()


def dump_json(ruta_lyr):
    """Volcado canonico en texto: lo que compara el test de regresion."""
    return json.dumps(dump_lyr(ruta_lyr), indent=2, sort_keys=True,
                      ensure_ascii=False)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python lyr_dump.py <archivo.lyr>")
        sys.exit(2)
    print(dump_json(sys.argv[1]).encode("utf-8"))
