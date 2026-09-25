# -*- coding: utf-8 -*-
"""Puente py3 (QGIS) -> py2.7 (ArcGIS) por subproceso.

El plugin no puede importar el emisor (ArcObjects solo vive en el Python 2.7 de
ArcGIS 10.5). En su lugar lanza `emisor.py` como proceso hijo con ese Python y
lee el JSON que el contrato F4 emite por stdout. Los errores de arcpy van a
stderr y no contaminan el JSON (ver ADR-001 y el CLAUDE.md del repo).
"""

import os
import json
import subprocess
import tempfile


# Tope de espera del subproceso. Arrancar ArcObjects + emitir una capa viva no
# deberia pasar de unos segundos; 5 min cubre el peor caso razonable sin dejar
# QGIS colgado para siempre.
TIMEOUT_S = 300
# Un proyecto entero a .mxd convierte capa a capa y verifica reabriendo: el POM
# de Majal Blanco (26 capas, WMS incluidos) tarda ~50 s. 30 min de techo.
TIMEOUT_MXD_S = 1800


class EmisorError(Exception):
    """Fallo al lanzar o comunicar con el subproceso (no un fallo de una capa,
    que ese viaja dentro del JSON como ok=False)."""


def _creationflags():
    # CREATE_NO_WINDOW: evita el parpadeo de una consola negra en Windows.
    # Solo existe en Windows; en otro SO devuelve 0 (sin efecto).
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _entorno_limpio(python27):
    """Entorno para el subproceso py2.7 SIN las variables de Python de QGIS.

    GOTCHA CRITICO: QGIS deja en su entorno `PYTHONHOME`/`PYTHONPATH` (y a veces
    `PYTHONSTARTUP`) apuntando a su propio Python 3. Si el subproceso los hereda,
    el Python 2.7 de ArcGIS carga el `site.py` de Python 3.12 de QGIS y revienta
    con `SyntaxError` antes de ejecutar nada. Hay que quitarlos para que py2.7
    use su propia libreria estandar. Fijamos PYTHONHOME al home de ArcGIS para
    forzar el stdlib correcto.
    """
    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONNOUSERSITE"):
        env.pop(k, None)
    # Home del Python de ArcGIS (carpeta que contiene python.exe): asegura que
    # py2.7 encuentre su Lib\site.py y no el de QGIS.
    home = os.path.dirname(python27)
    if home:
        env["PYTHONHOME"] = home
    return env


def _escribir_args_json(args):
    """Vuelca los argumentos a un JSON UTF-8 temporal y devuelve su ruta.

    GOTCHA CRITICO (2026-09-20): el emisor corre en Python 2.7, que recibe
    `sys.argv` en BYTES de la codepage ANSI de Windows (cp1252), no en UTF-8.
    Un nombre de capa o una ruta con tilde reventaba alli el `json.dumps` de la
    respuesta DESPUES de escribir el .lyr: el plugin veia stdout vacio y codigo
    1 sobre un fichero que si existia. Con el fichero de argumentos el texto
    viaja en UTF-8 y la def-query (llena de comillas) no pasa por el shell.
    """
    # El nombre lleva el id del hilo: el modo MXD corre en una QgsTask y puede
    # coincidir con una conversion de capa en el hilo principal.
    import threading
    ruta = os.path.join(tempfile.gettempdir(), "qml2lyr_args_%d_%d.json"
                        % (os.getpid(), threading.get_ident()))
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(args, f, ensure_ascii=False)
    return ruta


def ejecutar_qml(python27, emisor_py, qml, ruta_dato, salida_lyr, nombre=None,
                 defquery=None, servicio=None):
    """Una capa viva -> .lyr. `ruta_dato` para una capa de fichero, o
    `servicio` (su `source()`) para una WMS/WMTS."""
    args = {"qml": qml, "salida": salida_lyr}
    if servicio:
        args["servicio"] = servicio
    else:
        args["dato"] = ruta_dato
    if nombre:
        args["nombre"] = nombre
    if defquery:
        args["defquery"] = defquery
    return ejecutar(python27, emisor_py, args, TIMEOUT_S)


def ejecutar_mxd(python27, emisor_py, qgz, salida_mxd, plantilla=None,
                 remap=None):
    """El proyecto guardado en `qgz` -> un .mxd (modo --mxd del motor).
    `remap`: lista de reglas "ORIGEN=DESTINO"."""
    args = {"modo": "mxd", "qgz": qgz, "salida": salida_mxd}
    if plantilla:
        args["plantilla"] = plantilla
    if remap:
        args["remap"] = list(remap)
    return ejecutar(python27, emisor_py, args, TIMEOUT_MXD_S)


def ejecutar(python27, emisor_py, args, timeout):
    """Lanza el emisor con `args` (un dict, ver `--args-json` del motor) y
    devuelve el dict del JSON.

    Anade dos claves de diagnostico: `_returncode` y `_stderr`. Lanza
    EmisorError si el proceso no arranca o no devuelve JSON parseable.

    Siempre por `--args-json`: ver `_escribir_args_json`.
    """
    if not python27 or not os.path.isfile(python27):
        raise EmisorError(
            u"No se encuentra el Python de ArcGIS:\n%s\n\n"
            u"Configuralo en «Complementos -> qml2lyr -> ajustes»." % python27)
    if not emisor_py or not os.path.isfile(emisor_py):
        raise EmisorError(
            u"No se encuentra emisor.py:\n%s\n\n"
            u"Configuralo en «Complementos -> qml2lyr -> ajustes»." % emisor_py)

    try:
        args_json = _escribir_args_json(args)
    except OSError as e:
        raise EmisorError(u"No se pudo escribir el fichero de argumentos:\n%s" % e)
    cmd = [python27, emisor_py, u"--args-json", args_json]

    try:
        proc = subprocess.run(
            cmd,
            cwd=os.path.dirname(emisor_py),
            env=_entorno_limpio(python27),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_creationflags(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # Sin timeout, un ArcObjects colgado (licencia, COM, dato bloqueado)
        # congelaria QGIS indefinidamente. Mejor abortar y avisar.
        raise EmisorError(
            u"El emisor no respondió en %d s y se canceló.\n\n"
            u"Suele ser un problema de licencia de ArcGIS, del bloqueo COM o de "
            u"un dato inaccesible. Revisa que ArcMap no tenga el dato abierto." % timeout)
    except Exception as e:  # OSError, etc.
        raise EmisorError(u"No se pudo lanzar el emisor:\n%s" % e)
    finally:
        # El fichero de argumentos es de usar y tirar; si no se puede borrar,
        # no se calla: se deja constancia en el log de QGIS.
        try:
            os.remove(args_json)
        except OSError as e:
            from qgis.core import QgsMessageLog
            from .compat_qt import nivel_mensaje
            QgsMessageLog.logMessage(
                u"qml2lyr: no se pudo borrar %s (%s)" % (args_json, e),
                u"qml2lyr", nivel_mensaje("Warning"))

    salida = proc.stdout.decode("utf-8", "replace") if proc.stdout else u""
    err = proc.stderr.decode("utf-8", "replace") if proc.stderr else u""

    try:
        data = json.loads(salida)
    except ValueError:
        raise EmisorError(
            u"El emisor no devolvio un JSON valido (codigo %s).\n\n"
            u"stdout:\n%s\n\nstderr:\n%s"
            % (proc.returncode, salida[:2000] or u"(vacio)",
               err[:2000] or u"(vacio)"))

    data["_returncode"] = proc.returncode
    data["_stderr"] = err
    return data
