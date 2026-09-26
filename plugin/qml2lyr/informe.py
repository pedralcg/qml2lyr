# -*- coding: utf-8 -*-
"""Textos del informe que el plugin ensena al usuario, sin Qt ni QGIS: asi se
prueban en el CI (tests/test_plugin_informe.py) sin tener QGIS instalado."""

import os


def resumen_mxd(data):
    """JSON del modo MXD -> (titulo, texto, ok). Sin Qt: se puede probar."""
    ok = bool(data.get("ok"))
    salida = data.get("salida", u"")
    verif = data.get("verificacion") or {}
    lineas = []
    if ok:
        titulo = u"MXD creado: %s" % os.path.basename(salida)
        lineas.append(u"%s\n%d capas y %d grupos, comprobado reabriéndolo."
                      % (salida, verif.get("capas", 0), verif.get("grupos", 0)))
    else:
        titulo = u"No se pudo crear el MXD"
        lineas.append(u"%s\n(%s)" % (data.get("error", u"error desconocido"),
                                      data.get("tipo_error", u"")))
    if data.get("dir_lyr"):
        lineas.append(u"Los .lyr de cada capa: %s" % data["dir_lyr"])
    omitidas = data.get("omitidas") or []
    if omitidas:
        lineas.append(u"")
        lineas.append(u"No entran en el MXD (%d):" % len(omitidas))
        lineas.extend(u"✗ %s: %s" % (o.get("nombre"), o.get("motivo"))
                      for o in omitidas)
    rotas = verif.get("rotas") or []
    if rotas:
        lineas.append(u"")
        lineas.append(u"Fuentes que ArcMap verá rotas en esta máquina (su "
                      u"unidad no existe aquí o es un origen de remap): %d"
                      % len(rotas))
    avisos = [u"• %s" % a for a in data.get("avisos") or []]
    for capa in data.get("capas") or []:
        if capa.get("ok"):
            avisos.extend(u"• [%s] %s" % (capa.get("nombre", u"?"), a)
                          for a in capa.get("avisos") or [])
    if avisos:
        lineas.append(u"")
        lineas.append(u"Avisos (degradaciones respecto a QGIS):")
        lineas.extend(avisos)
    return titulo, u"\n".join(lineas), ok
