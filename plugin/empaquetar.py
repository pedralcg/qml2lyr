# -*- coding: utf-8 -*-
"""Empaqueta el plugin en un .zip instalable desde QGIS.

    python plugin/empaquetar.py                 # -> dist/qml2lyr-<version>.zip
    python plugin/empaquetar.py --tag v0.1.0    # ademas exige tag == version

El .zip lleva la carpeta `qml2lyr/` con:
- el codigo del plugin (`plugin/qml2lyr/`, sin caches ni un `motor/` local);
- `motor/`: TODOS los `src/*.py`, que el plugin lanza con el Python 2.7 de
  ArcGIS. Sin lista de ficheros: un modulo nuevo en `src/` entra solo;
- `LICENSE`.

Python 3 y solo la biblioteca estandar: lo corre el CI en Ubuntu y la Action de
release, no hace falta QGIS ni ArcGIS.
"""
import argparse
import configparser
import os
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PLUGIN = os.path.join(RAIZ, "plugin", "qml2lyr")
DIR_SRC = os.path.join(RAIZ, "src")
DIR_DIST = os.path.join(RAIZ, "dist")

# Lo que el plugin necesita del motor para funcionar; si falta, el zip no vale.
IMPRESCINDIBLES = ("emisor.py", "modelo.py", "parser_qgis.py")


def version_metadata():
    cp = configparser.ConfigParser()
    cp.read(os.path.join(DIR_PLUGIN, "metadata.txt"), encoding="utf-8")
    return cp.get("general", "version").strip()


def _ficheros_plugin():
    for base, dirs, ficheros in os.walk(DIR_PLUGIN):
        # `motor/` local lo deja deploy.ps1 en el perfil, no en el repo; si
        # alguien lo crea a mano aqui, no debe colarse por delante de src/.
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "motor")]
        for f in ficheros:
            if f.endswith((".pyc", ".pyo")):
                continue
            ruta = os.path.join(base, f)
            yield ruta, os.path.join("qml2lyr", os.path.relpath(ruta, DIR_PLUGIN))


def _ficheros_motor():
    for f in sorted(os.listdir(DIR_SRC)):
        if f.endswith(".py"):
            yield os.path.join(DIR_SRC, f), os.path.join("qml2lyr", "motor", f)


def empaquetar(tag=None):
    version = version_metadata()
    if tag is not None and tag.lstrip("v") != version:
        sys.exit("el tag %s no coincide con version=%s de metadata.txt"
                 % (tag, version))

    entradas = list(_ficheros_plugin()) + list(_ficheros_motor())
    entradas.append((os.path.join(RAIZ, "LICENSE"),
                     os.path.join("qml2lyr", "LICENSE")))
    en_motor = {os.path.basename(a) for _, a in entradas
                if os.path.dirname(a).endswith("motor")}
    faltan = [f for f in IMPRESCINDIBLES if f not in en_motor]
    if faltan:
        sys.exit("faltan en el motor: %s" % ", ".join(faltan))

    os.makedirs(DIR_DIST, exist_ok=True)
    salida = os.path.join(DIR_DIST, "qml2lyr-%s.zip" % version)
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for origen, arcname in entradas:
            # Separador "/" en el zip, sea cual sea el SO que empaqueta.
            z.write(origen, arcname.replace(os.sep, "/"))
    print(salida)
    return salida


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", help="tag del release (vX.Y.Z); debe casar con metadata.txt")
    empaquetar(ap.parse_args().tag)


if __name__ == "__main__":
    main()
