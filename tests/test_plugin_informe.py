# -*- coding: utf-8 -*-
"""Tests del informe que el plugin ensena tras «Exportar proyecto a .mxd».

Python 3 y sin QGIS (lo corre el CI en el trabajo `plugin (py3)`):

    python tests/test_plugin_informe.py

El dict de entrada tiene la forma del JSON del motor en modo --mxd
(`emisor.emitir_mxd`); lo que se prueba es que el usuario vea lo que importa:
que el MXD salio y comprobado, que capas no entraron y por que, y los avisos.
"""
import importlib.util
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "informe", os.path.join(RAIZ, "plugin", "qml2lyr", "informe.py"))
informe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(informe)


def test_mxd_ok(fallos):
    titulo, texto, ok = informe.resumen_mxd({
        "ok": True, "salida": "C:\\x\\proyecto Ω.mxd", "dir_lyr": "C:\\x\\p_lyr",
        "verificacion": {"capas": 25, "grupos": 7, "rotas": ["a", "b"]},
        "omitidas": [{"nombre": "Finca", "motivo": "GeometryGenerator"}],
        "avisos": ["global"],
        "capas": [{"ok": True, "nombre": "LIC", "avisos": ["Maplex"]},
                  {"ok": False, "nombre": "Finca", "avisos": ["no sale"]}]})
    if not ok or "proyecto Ω.mxd" not in titulo:
        fallos.append("titulo/ok: %r %r" % (titulo, ok))
    for esperado in ("25 capas y 7 grupos", "✗ Finca: GeometryGenerator",
                     "rotas en esta máquina", ": 2", "• global",
                     "• [LIC] Maplex", "C:\\x\\p_lyr"):
        if esperado not in texto:
            fallos.append("falta %r en el informe" % esperado)
    if "no sale" in texto:
        fallos.append("los avisos de una capa omitida ya van en su motivo")


def test_mxd_error(fallos):
    titulo, texto, ok = informe.resumen_mxd({
        "ok": False, "error": "C:\\x.mxd ya existe", "tipo_error": "SalidaExiste",
        "omitidas": [], "capas": []})
    if ok or "No se pudo" not in titulo:
        fallos.append("titulo/ok del error: %r %r" % (titulo, ok))
    if "ya existe" not in texto or "SalidaExiste" not in texto:
        fallos.append("el error no se ve: %r" % texto)


TESTS = [(n, f) for n, f in sorted(globals().items())
         if n.startswith("test_") and callable(f)]


def main():
    malos = 0
    for nombre, funcion in TESTS:
        fallos = []
        try:
            funcion(fallos)
        except Exception as e:
            fallos.append("excepcion: %r" % (e,))
        print("%-5s %s" % ("PASS" if not fallos else "FAIL", nombre))
        for f in fallos:
            print("      " + f)
        malos += bool(fallos)
    print("\nTOTAL: %d/%d PASS" % (len(TESTS) - malos, len(TESTS)))
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
