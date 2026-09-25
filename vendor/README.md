# vendor/

Código de terceros que viaja dentro del zip del plugin. **No se edita**: se
sustituye entero por otra versión publicada.

## comtypes 1.1.7

- Qué es: el puente de Python a COM con el que el motor (`src/emisor.py`) habla
  con ArcObjects.
- Por qué va aquí: **el Python 2.7 de ArcGIS 10.5 no lo trae de serie.** Sin él,
  el plugin se instala pero cada exportación falla con
  `No module named comtypes.client`. El zip lo copia a `qml2lyr/motor/comtypes/`,
  y el motor se lanza como script desde `motor/`, así que esta copia tiene
  prioridad sobre cualquier otra instalada en el Python de ArcGIS.
- Origen: sdist de PyPI `comtypes-1.1.7.zip`,
  sha256 `c9d59f57d559613940f22da54d70add066faa23b4fa9b5cd95facdc501a63b0b`.
  Se copia la carpeta `comtypes/` **sin `test/`**.
- Versión: 1.1.7 es la que se ha probado con el motor en ArcGIS 10.5
  (`run_regresion_qml.py`). Es de las últimas que soportan Python 2.7.
- Licencia: MIT, en `comtypes/LICENSE.txt`, que va dentro del zip.
- `comtypes/gen/` no se versiona: comtypes lo crea la primera vez que genera los
  envoltorios de las OLB de ArcObjects.
