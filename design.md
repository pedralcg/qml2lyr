---
version: alpha
name: qml2lyr-plugin
description: Identidad visual del plugin QGIS qml2lyr — deliberadamente nativa de QGIS, sin estilos propios.
colors:
  # Único punto de identidad de marca del plugin: el icono. El resto de la UI
  # hereda el tema activo de QGIS (claro/oscuro) y NO se estiliza.
  primary: "#589632"        # verde QGIS (lado origen)
  on-primary: "#FFFFFF"
  secondary: "#E35C3B"      # rojo-teja ArcMap/ArcGIS (lado destino)
  on-secondary: "#FFFFFF"
  tertiary: "#333333"        # trazo de la flecha del icono
  on-tertiary: "#FFFFFF"
  background: "inherit"      # tema de QGIS
  on-background: "inherit"
  surface: "inherit"
  on-surface: "inherit"
  border: "inherit"
  error: "#DC2626"           # se usa el nivel Qgis.Critical / QMessageBox.critical
  success: "#16A34A"         # se usa el nivel Qgis.Success de la messageBar
typography:
  # Se hereda la tipografía del sistema/QGIS. No se define ninguna fuente propia.
  body-md:
    fontFamily: system
    fontSize: inherit
    fontWeight: 400
  mono:
    fontFamily: monospace
    fontSize: inherit
    fontWeight: 400
rounded:
  none: 0px
  sm: 3px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
components:
  layer-action:
    tipo: QAction
    texto: "Guardar estilo como .lyr…"
    icon: "icon.svg"
    contexto: "menú contextual de capa (vector y ráster de fichero)"
  settings-dialog:
    tipo: QDialog
    contenido: "2 filas ruta (QLineEdit + botón …) + QDialogButtonBox Ok/Cancel"
    minWidth: 520px
  message-bar:
    tipo: "iface.messageBar()"
    niveles: "Info / Success / Warning / Critical"
  detail-dialog:
    tipo: QMessageBox
    uso: "listar errores por capa y avisos (degradaciones) cuando los hay"
---

## Overview

qml2lyr es un **plugin nativo de QGIS**, no una app web. Su identidad visual es,
por decisión, **la de QGIS**: usa widgets nativos de Qt (`QAction`, `QDialog`,
`QFileDialog`, `QMessageBox`, `messageBar`) y **no aplica ningún estilo propio**
(sin CSS, sin QSS, sin paleta custom). Así se integra sin fricción, respeta el
tema claro/oscuro del usuario y envejece con QGIS, no contra él.

El único elemento de marca es el **icono** (`icon.svg`): dos paneles —verde QGIS
a la izquierda, rojo-teja ArcMap a la derecha— con una flecha `→` que resume la
dirección de conversión QGIS → ArcMap.

## Colors

- **primary (#589632):** verde de QGIS, lado origen del icono.
- **secondary (#E35C3B):** rojo-teja de ArcGIS/ArcMap, lado destino del icono.
- **tertiary (#333):** trazo de la flecha.
- **error / success:** NO son colores pintados a mano; se expresan eligiendo el
  **nivel** de la messageBar (`Qgis.Success`, `Qgis.Warning`, `Qgis.Critical`) o
  el tipo de `QMessageBox`. QGIS decide el color real según su tema.
- Todo lo demás es `inherit`: fondo, texto, bordes y superficies los pone QGIS.

## Typography

No se define ninguna fuente. Se hereda la del sistema/QGIS. Los paths y el JSON
de diagnóstico se muestran en el cuerpo de `QMessageBox` con la fuente por
defecto (no se fuerza monospace para no romper la integración nativa).

## Layout

- El diálogo de ajustes usa `QVBoxLayout`/`QHBoxLayout` nativos; ancho mínimo
  520px para que las rutas absolutas quepan sin truncar.
- No hay grid ni breakpoints: es UI de escritorio embebida en QGIS.

## Elevation & Depth

Ninguna sombra propia. Los diálogos y la messageBar usan la elevación nativa de
Qt/QGIS.

## Shapes

- Radios los pone Qt/el tema de QGIS. El icono usa esquinas `rx=1.5` en sus dos
  paneles (equivalente a `rounded.sm`), único radio bajo control del proyecto.

## Components

- **layer-action:** la acción de clic derecho. Texto e icono fijos; aparece en
  capas vectoriales y ráster de fichero.
- **settings-dialog:** dos filas de ruta (Python 2.7 de ArcGIS, `emisor.py`) +
  Ok/Cancel. Persiste en `QSettings`.
- **message-bar:** feedback breve y no bloqueante (resumen del resultado).
- **detail-dialog:** solo cuando hay errores por capa o avisos, para listarlos
  completos (la messageBar no basta para texto largo).

## Do's and Don'ts

**Do:**
- Usar widgets nativos de `qgis.PyQt` y dejar que QGIS pinte el tema.
- Expresar severidad con el **nivel** de la messageBar / tipo de QMessageBox, no
  con colores hardcodeados.
- Mantener el icono como único punto de identidad de marca.

**Don't:**
- No aplicar QSS/CSS ni paletas propias a los widgets: rompería el tema del
  usuario (sobre todo el modo oscuro).
- No inventar diálogos elaborados: la UX es «clic derecho → elegir fichero →
  feedback». Mínima por diseño.
- No usar emojis en la UI salvo los marcadores `✗`/`•` ya presentes en el
  listado de errores/avisos (texto plano, no decorativo).

---

## Notas

Caso especial de la convención `design.md`: un plugin nativo QGIS no
tiene sistema de diseño propio; lo correcto es documentar **la ausencia
deliberada de estilos** y el único activo de marca (el icono). Formato: spec
[DESIGN.md de Google Labs](https://github.com/google-labs-code/design.md) (alpha).
