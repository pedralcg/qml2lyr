# Plugin QGIS — qml2lyr

Guarda el estilo de la **capa activa** de QGIS como un archivo `.lyr` de ArcMap 10.5
(dirección QGIS → ArcMap). Es la forma final del producto (ADR-001): el motor
ArcObjects (F1–F4) hace el trabajo pesado; este plugin es la cara de usuario.

## Cómo funciona

El plugin corre en el **Python 3 de QGIS**, pero escribir un `.lyr` exige
**ArcObjects en el Python 2.7 de ArcGIS 10.5**. Son incompatibles en el mismo
proceso, así que el plugin **delega en `emisor.py` como subproceso**:

```
capa activa → saveNamedStyle → estilo.qml (temporal)
            + subsetString()  → definition query (no viaja en el .qml)
            → args.json (UTF-8, temporal)
            → subprocess: <py27_arcgis> emisor.py --args-json args.json
            → JSON por stdout → reporte en la UI (avisar y saltar por capa)
```

Los argumentos viajan en un **fichero JSON UTF-8**, no por la línea de comandos:
Python 2.7 recibe `sys.argv` en la codepage ANSI de Windows (cp1252) y un nombre
de capa o una ruta con tilde rompía el JSON de respuesta **después** de escribir
el `.lyr` (stdout vacío, código 1, fichero correcto en disco). Con el fichero de
argumentos pasan también los caracteres que cp1252 no tiene, y la definition
query —llena de comillas— no pasa por el shell.

**Requiere QGIS y ArcGIS Desktop 10.5 instalados en la misma máquina.** No
funciona en equipos sin ArcGIS 10.5.

## Instalación

1. Despliega al perfil de QGIS con el script de doble copia:

   ```powershell
   powershell -ExecutionPolicy Bypass -File plugin\deploy.ps1 -Profile default
   ```

   (Edita siempre el código en `plugin\qml2lyr\` del repo y re-ejecuta el script;
   nunca edites la copia del perfil.)

2. En QGIS: **Complementos → Administrar e instalar complementos → Instalados**,
   activa **qml2lyr**. Si aparece filtrado, marca «Mostrar también complementos
   experimentales».

3. **Complementos → qml2lyr → ajustes…** y fija:
   - Python 2.7 de ArcGIS: `C:\Python27\ArcGIS10.5\python.exe`
   - `emisor.py`: la ruta a `src\emisor.py` de tu copia de este repositorio

## Uso

Clic derecho sobre una capa **vectorial o ráster de fichero** (shapefile,
GeoTIFF, GeoPackage) en el panel de capas → **«Guardar estilo como .lyr…»** →
elige el destino. La barra de mensajes informa del resultado; los avisos
(degradaciones respecto a QGIS) y los errores por capa se muestran en un
diálogo.

Lo que viaja al `.lyr`: la simbología, la **definition query** de la capa, su
**opacidad** y su **visibilidad por escala**. Un estilo rule-based da un `.lyr`
por regla (las reglas desmarcadas en QGIS no se emiten).

**GeoPackage**: se convierte si la capa se añadió eligiéndola en el selector de
capas del `.gpkg` (así su origen lleva `|layername=…`, que es lo que arcpy
necesita). Si se añadió el `.gpkg` a secas, el plugin lo dice y explica cómo
arreglarlo.

Capas de memoria, PostGIS, WMS/WFS y otros contenedores multicapa (`.kml`,
`.sqlite`…) no se convierten: no tienen un dato que arcpy pueda abrir por ruta.

## Estructura

```
plugin/
  deploy.ps1              ← copia al perfil de QGIS
  qml2lyr/
    __init__.py           ← classFactory
    metadata.txt          ← metadatos del plugin
    qml2lyr_plugin.py     ← clase principal (acción, flujo, reportes)
    emisor_runner.py      ← puente subproceso py3 → py2.7 + parseo del JSON
    settings_dialog.py    ← diálogo de rutas (QSettings)
    compat_qt.py          ← enums de Qt/QGIS con y sin scope (Qt5 / Qt6)
    icon.svg
```

## Notas de desarrollo

- Todo lo de Qt se importa de `qgis.PyQt` (shim Qt5/Qt6) y **los enums pasan por
  `compat_qt`**: PyQt6 solo acepta la forma con scope
  (`Qt.CursorShape.WaitCursor`, `QDialogButtonBox.StandardButton.Ok`,
  `Qgis.MessageLevel.Info`) y PyQt5 acepta las dos. `compat_qt` prueba primero
  la de scope y cae a la legada, así que el mismo código vale en QGIS 3.44 (Qt5,
  donde está el QA) y en QGIS 4 (Qt6). No usar enums sin scope en código nuevo.
- Config en `QSettings` bajo la clave `qml2lyr/*` (nunca hardcodear rutas).
- El contrato del subproceso está en `src/emisor.py` (`__main__`) y en el
  `CLAUDE.md` del repo (sección «Interfaz de subproceso»).
