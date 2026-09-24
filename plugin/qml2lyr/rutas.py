# -*- coding: utf-8 -*-
"""Donde estan el Python 2.7 de ArcGIS y el motor (emisor.py).

Sin configurar nada, el plugin funciona solo:
- el motor va DENTRO del plugin (`motor/`, lo copian `empaquetar.py` y
  `deploy.ps1` desde `src/`; no se versiona en `plugin/`);
- el Python 2.7 se lee del registro de ArcGIS 10.5 (`Python10.5\\PythonDir`).

Los ajustes (QSettings `qml2lyr/python27` y `qml2lyr/emisor`) quedan para casos
raros y para desarrollo (apuntar al `src/` del repo). Un ajuste VACIO significa
"automatico". Un ajuste RELLENO que no existe es un error, no un permiso para
caer en silencio a la ruta automatica: el usuario pidio esa ruta por algo.
"""

import os

from qgis.PyQt.QtCore import QSettings

# Solo ArcGIS 10.5: el emisor abre su clave de registro (`Desktop10.5`).
CLAVE_PYTHON_ARCGIS = r"SOFTWARE\WOW6432Node\ESRI\Python10.5"
SUBCARPETA_PYTHON = r"ArcGIS10.5\python.exe"
PY27_POR_DEFECTO = r"C:\Python27\ArcGIS10.5\python.exe"

EMISOR_INCLUIDO = os.path.join(os.path.dirname(__file__), "motor", "emisor.py")


class RutaNoValida(Exception):
    """Mensaje listo para enseñar al usuario."""


def detectar_python27():
    """Ruta al python.exe de ArcGIS 10.5, o None si no se encuentra."""
    candidatos = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLAVE_PYTHON_ARCGIS) as k:
            base, _ = winreg.QueryValueEx(k, "PythonDir")
        candidatos.append(os.path.join(base, SUBCARPETA_PYTHON))
    except (ImportError, OSError):
        # Sin winreg (no es Windows) o sin la clave (ArcGIS no instalado, o
        # instalado sin Python): queda la ruta de instalacion por defecto.
        pass
    candidatos.append(PY27_POR_DEFECTO)
    for ruta in candidatos:
        if os.path.isfile(ruta):
            return ruta
    return None


def emisor_incluido():
    return EMISOR_INCLUIDO if os.path.isfile(EMISOR_INCLUIDO) else None


def _ajuste(clave):
    valor = QSettings().value(clave, "")
    return (valor or "").strip()


def resolver():
    """(python27, emisor) listos para usar. Lanza RutaNoValida si no hay."""
    py27 = _ajuste("qml2lyr/python27")
    if py27:
        if not os.path.isfile(py27):
            raise RutaNoValida(
                u"El Python de ArcGIS de los ajustes no existe:\n%s\n\n"
                u"Corrígelo o deja el campo vacío para detectarlo solo." % py27)
    else:
        py27 = detectar_python27()
        if not py27:
            raise RutaNoValida(
                u"No se encuentra el Python 2.7 de ArcGIS 10.5.\n\n"
                u"qml2lyr necesita ArcGIS Desktop 10.5 instalado en este equipo. "
                u"Si lo está en una ruta no estándar, indica su python.exe en "
                u"«Complementos → qml2lyr → ajustes».")

    emisor = _ajuste("qml2lyr/emisor")
    if emisor:
        if not os.path.isfile(emisor):
            raise RutaNoValida(
                u"El emisor.py de los ajustes no existe:\n%s\n\n"
                u"Corrígelo o deja el campo vacío para usar el motor incluido." % emisor)
    else:
        emisor = emisor_incluido()
        if not emisor:
            raise RutaNoValida(
                u"Falta el motor dentro del plugin:\n%s\n\n"
                u"Reinstala qml2lyr desde el .zip del release. Si lo copiaste a "
                u"mano desde el repositorio, usa plugin\\deploy.ps1, que copia "
                u"también el motor." % EMISOR_INCLUIDO)
    return py27, emisor
