# CLAUDE.md — qml2lyr

Convierte simbología QGIS a archivos `.lyr` de ArcMap 10.5, vectorial y ráster.
**Forma del producto: plugin QGIS** ("Guardar estilo como .lyr" sobre la capa
activa). Cubre la dirección que SLYR no ofrece gratis (QGIS→ArcMap).

**Restricción de arquitectura que lo condiciona todo:** el plugin corre en el
Python 3 de QGIS; el `.lyr` exige ArcObjects en el Python 2.7 de ArcGIS 10.5.
El plugin SIEMPRE delega en el emisor como subproceso (ADR-001, abajo).

No-gos: dirección inversa ArcMap→QGIS (la hace SLYR community gratis),
rule-based por expresión arbitraria, ArcGIS Pro `.lyrx` (fase futura),
expresiones / geometry-generators / data-defined, etiquetas.

## Flujo de ramas (GitHub Flow)

`main` es lo publicado y **solo cambia por pull request con el CI en verde**. La
regla la impone GitHub (ruleset sobre `main`): PR obligatorio, checks
`parser (py2.7)` y `plugin (py3)` obligatorios, sin force-push. Sin revisores
obligatorios: con un solo mantenedor nadie podría aprobar sus propios PR.

1. `git switch -c <tipo>/<tema>` desde `main` actualizado (`feat/…`, `fix/…`, `docs/…`).
2. Commits en Conventional Commits, en español.
3. **Antes de abrir el PR, en local y con ArcGIS 10.5**:
   `C:\Python27\ArcGIS10.5\python.exe run_regresion_qml.py` — el CI **no** puede
   correr esta suite (no hay ArcGIS en un runner de GitHub), solo `tests/test_parser.py`.
   Pegar el `TOTAL` en la descripción del PR.
4. `git push -u origin <rama>` y `gh pr create`. Merge desde GitHub cuando el CI
   esté en verde (squash), y borrar la rama.
5. **Versiones**: la etiqueta (`vX.Y.Z`) se crea sobre `main` **después** del
   merge, nunca en una rama. Subir antes `version=` en `plugin/qml2lyr/metadata.txt`
   (por PR). Al empujar el tag, `release.yml` empaqueta con `plugin/empaquetar.py`
   y adjunta `qml2lyr-qgis-plugin-X.Y.Z.zip` al release (nunca `qml2lyr-X.Y.Z.zip`:
   se llama igual que el «Source code» de GitHub y el usuario baja el que no es); **aborta si el tag no casa con
   `version=`**.

## Empaquetado: el motor va dentro del plugin

El zip (y `deploy.ps1`) copian **todos los `src/*.py`** a `qml2lyr/motor/`: el
usuario instala el zip y no configura nada. `plugin/qml2lyr/motor/` **no se
versiona** (`.gitignore`): el código del motor vive solo en `src/`.

`rutas.resolver()` decide qué ejecutar:
- Python 2.7: ajuste `qml2lyr/python27` si está relleno; si no, el registro
  `HKLM\SOFTWARE\WOW6432Node\ESRI\Python10.5\PythonDir` + `ArcGIS10.5\python.exe`,
  y en último caso `C:\Python27\ArcGIS10.5\python.exe`.
- Motor: ajuste `qml2lyr/emisor` si está relleno; si no, `motor/emisor.py`.
- **Un ajuste relleno que no existe es un error**, no un permiso para caer a la
  ruta automática. Vacío = automático.

El CI empaqueta en cada PR y comprueba que el zip lleva `motor/emisor.py`.

## Entorno de ejecución

- **Python 2.7 de ArcGIS 10.5**: `C:\Python27\ArcGIS10.5\python.exe` En Torre tiene
  comtypes 1.1.7, **pero se instaló a mano: ArcGIS 10.5 no lo trae.** Por eso el zip
  lleva `vendor/comtypes/` en `motor/comtypes/` (ver `vendor/README.md`); no
  quitarlo creyendo que sobra porque en Torre funcione sin él.
- ArcObjects vía comtypes para emitir; `xml.etree` para parsear; `argparse` para el CLI.
- Sin BD, sin auth, sin red, sin `.env` (no hay secretos).
- Dependencia dura: ArcGIS 10.5 instalado (registro `SOFTWARE\Wow6432Node\ESRI\Desktop10.5`).
- PyQGIS (QGIS 3.44) solo para generar fixtures: `python-qgis-ltr.bat <fichero.py>`
  (el `.bat` **ignora `-c`**: hay que pasarle un fichero).

## Arquitectura

```
src/parser_qgis.py  →  lee .qml/.qgz (XML) → construye el modelo
src/modelo.py       →  estructura intermedia (renderers + símbolos), agnóstica de origen y destino
src/emisor.py       →  modelo → .lyr vía híbrido arcpy + ArcObjects; CLI del subproceso
src/lyr_dump.py     →  lector ArcObjects: vuelca el renderer de un .lyr a JSON (base de los tests)
plugin/qml2lyr/     →  el plugin de QGIS (py3)
run_regresion_qml.py        → cadena completa .qml/.qgz → .lyr → volcado (necesita ArcGIS)
tests/test_parser.py        → solo el parser, Python puro (lo corre el CI)
tests/generar_fixtures_qgis.py → fixtures escritos por PyQGIS
```

`parser_qgis.py` NO puede llamarse `parser.py`: colisiona con el módulo stdlib
`parser` de Python 2.7.

La estructura intermedia es la clave: desacopla parser de emisor para poder añadir
un emisor `.lyrx` (ArcGIS Pro) en el futuro sin tocar el parser.

## Interfaz de subproceso (contrato con el plugin — ADR-001)

`emisor.py` tiene `__main__`. El plugin QGIS (py3) lo invoca con el py2.7
de ArcGIS y lee **JSON por stdout** (los errores de arcpy van a stderr, no lo
contaminan). Tres modos:
- **Recomendado, y el que usa siempre el plugin**: `emisor.py --args-json
  <args.json>` — fichero **UTF-8** con las claves `qml`, `dato`, `salida`
  (obligatorias) y `nombre`, `defquery`, `dir_tmp` (opcionales). Una clave
  desconocida se **rechaza** (una errata tipo `def_query` perdería la def-query
  en silencio). Existe por el gotcha de `sys.argv` en cp1252 (ver abajo), y de
  paso saca la def-query —llena de comillas— de la línea de comandos.
- Posicional (clásico, retrocompatible): `emisor.py <estilo.qml> <ruta_dato>
  <salida.lyr> [--nombre N] [--defquery Q]` — el plugin genera el `.qml` de la
  capa viva con `saveNamedStyle`. `parse_qml` soporta vectorial y ráster. Un
  `.qml` rule-based da N `.lyr` (sufijo `_<etiqueta>`).
- Batch: `emisor.py --batch <proyecto.qgz> <dir_salida>` — resuelve el datasource
  de cada capa (relativo al `.qgz` o absoluto/red) y emite un `.lyr` por capa.
- JSON por capa: `ok`/`nombre`/`salida`/`avisos` o `error`/`tipo_error`, más una
  lista `avisos` de nivel superior para lo que no es de ninguna capa (p.ej. un
  temporal que no se pudo borrar). Una capa que falla se reporta `ok=False` y NO
  aborta el batch (avisar-y-saltar). Exit 0/1 single, 0/2 batch — **el batch da
  exit 0 y `ok=True` aunque falle alguna capa**: el fallo va por capa. Nombres de
  fichero deduplicados (`_nombre_unico`) para no pisar `.lyr` en silencio cuando
  dos capas sanean al mismo nombre.

**La def-query la aporta el llamador, no el `.qml`.** Es propiedad del
*proveedor*, no del estilo: `saveNamedStyle` no la escribe. El plugin la lee con
`QgsVectorLayer.subsetString()` (solo capas vectoriales) y la pasa al emisor;
`emitir_qml` la combina con la de cada regla igual que hace `parse_maplayer` con
la del `.qgz` — las dos por `parser_qgis.combinar_defquery`, que tolera que
cualquiera de las dos falte.

Cobertura: fill sólido/hueco/tramado (los 6 patrones Qt) / multicapa / línea
(`solid`, `dash`, `dot`, `dash dot`, `dash dot dot`) / marcador (5 formas simples
+ 6 por glifo + rotación) / def-query / opacidad de capa / visibilidad por escala.
Ráster: paletted, pseudocolor DISCRETE (clases) e INTERPOLATED (estirado).
RasterFill (imagen). Datos: shapefile, ráster de fichero y **GeoPackage**.

## Gotchas críticos (no redescubrir)

- **`sys.argv` de py2.7 llega en cp1252, no en UTF-8.** El plugin es py3 y pasa
  `str`; Windows se lo entrega al hijo py2.7 en bytes de la codepage ANSI. Un
  `--nombre "Vías pecuarias"` hacía reventar `json.dumps(..., ensure_ascii=False)`
  con `UnicodeDecodeError` **después** de escribir el `.lyr`: el plugin veía
  stdout vacío y exit 1 sobre un fichero que sí existía. Doble cinturón:
  `emisor._u()` decodifica argv al entrar y `emisor._unicodizar()` barre el
  resultado antes del `json.dumps`. Y el plugin usa `--args-json`.
- **Asimetría `.qml` vs `.qgz`, cerrada a propósito.** `parse_qml` y
  `parse_maplayer` leen el MISMO XML de estilo. Los atributos de CAPA se leen en
  un único `_cabecera_capa(elem, avisos)` —vale igual para el `<maplayer>` del
  `.qgs` y para la raíz `<qgis>` del `.qml`— y el estilo en `_capas_desde_estilo`.
  **Al añadir algo a uno de los dos caminos, va en esas funciones o volverán a
  divergir.**
- **Reglas desmarcadas: el atributo es `checkstate`, no `checked`** (verificado
  contra `saveNamedStyle` de QGIS 3.44). Una regla desmarcada no se emite, **su
  filtro no entra en el `NOT(...)` del ELSE** y **su símbolo ni se parsea**
  (`_simbolos_por_nombre(..., solo=)`): un símbolo no soportado en una regla que
  QGIS no dibuja tumbaba la capa entera. Lo mismo en categorizado y graduado: los
  símbolos de las clases con `render="false"` tampoco se parsean
  (`_simbolos_visibles`).
- **Categoría de NULOS: el valor que casa en ArcMap es `<Null>`** (verificado
  por render sobre una file geodatabase con un campo nulo). QGIS serializa la
  categoría nula como `type="NULL" value="NULL"`: emitirla tal cual mandaba a
  ArcMap a casar el *texto* "NULL". Se traduce y se avisa.
- **Trazo discontinuo con ancho ≥ 2 pt: ArcMap lo dibuja CONTINUO** (medido por
  render). El patrón de `esriSimpleLineStyle` está en unidades de dispositivo y
  lo tapa el grosor de la pluma. Se emite el estilo pedido y **se avisa**.
- **Valor de celda FUERA de la paleta: ArcMap lo deja TRANSPARENTE** (verificado
  por render). No hace falta emitir una clase con símbolo nulo para él.
- **GeoPackage**: arcpy 10.5 abre una capa suya como `ruta.gpkg\main.<capa>`. El
  `.gpkg` pelado NO, así que sin `layername=` en el datasource se avisa y se
  salta. Con un **punto** en el nombre de la tabla tampoco (arcpy lo toma por
  separador de esquema y culpa al dataset): se detecta antes y se avisa. La
  resolución vive en `parser_qgis.ruta_dataset` (batch) y en
  `Qml2LyrPlugin._resolver_dato` (plugin) — son dos porque son dos runtimes.
- **`ILayer.MinimumScale`/`MaximumScale` y el `Angle` del marcador sobreviven al
  `.lyr`.** Las escalas usan la MISMA convención que QGIS (denominadores, 0 = sin
  límite): `minScale` → `MinimumScale`, `maxScale` → `MaximumScale`.
- **Rotación de marcador: QGIS gira en sentido HORARIO, ArcMap en ANTIHORARIO**
  (render ArcMap vs QGIS: un triángulo a 30° apunta a la izquierda en QGIS y a la
  derecha en ArcMap con el mismo número). `emisor._angulo_arcmap` emite
  `(-a) % 360`; el modelo guarda el ángulo de QGIS. Al probar una rotación, usar
  una forma que no sea simétrica respecto al giro probado: un cuadrado a 45° se
  ve igual en los dos sentidos.
- **Formas de marcador sin `SimpleMarkerSymbol` → glifo de ESRI Default Marker**
  (`esri_11.ttf`, instalada con ArcGIS Desktop): `CharacterMarkerSymbol` con el
  código de `parser_qgis._GLIFOS_MARCADOR` (35 triángulo, 36 pentágono, 37
  hexágono, 38 octógono, 94 estrella). El tamaño de QGIS es el de la FORMA y el
  de ArcMap el de la FUENTE: se divide por el lado mayor del glifo (~0,6 del em,
  medido con `QRawFont`). Render: 90-105 % del de QGIS. **El borde va como HALO
  (`IMask`)**, no con el glifo hueco encima (ArcMap coloca cada glifo por el
  origen de la fuente y se descuadraban). `IMask` **no** lo expone
  `CharacterMarkerSymbol` sino `MultiLayerMarkerSymbol`: el glifo va dentro de
  un multicapa de una capa. **Dos ajustes medidos por render**: el hexágono de
  QGIS tiene un VÉRTICE arriba y el glifo 37 un LADO, así que lleva **+30° de
  giro extra** (tercer valor de `_GLIFOS_MARCADOR`); y `equilateral_triangle`
  QGIS lo dibuja más pequeño que su `size`, así que lleva **factor propio
  (0,714)**. Al añadir una forma, renderizarla en los dos programas: la hoja de
  glifos no dice la orientación.
- **`ExportToPNG` con `data_frame` ignora `resolution`**: para medir tamaños de
  símbolo por render, exportar la PÁGINA (`ExportToPNG(mxd, png, resolution=300)`),
  donde px = pt × 300/72.
- **El subproceso py2.7 hereda el Python de QGIS y revienta**: QGIS deja en su
  entorno `PYTHONHOME`/`PYTHONPATH` apuntando a su Python 3, y el py2.7 muere con
  `SyntaxError` en el `site.py` de QGIS antes de ejecutar nada. El subproceso se
  lanza con un entorno saneado (`emisor_runner._entorno_limpio`).
- `ShapefileWorkspaceFactory.OpenFromFile` **falla siempre** en standalone
  (COMError 0x80041068), con licencia OK y ruta válida. **Solución híbrida
  obligatoria**: arcpy crea la `.lyr` base (`MakeFeatureLayer` + `SaveToLayerFile`
  ABSOLUTE) y ArcObjects solo intercambia el renderer (`ILayerFile.Open` →
  `IGeoFeatureLayer.Renderer`). arcpy.mapping NO puede fijar colores de clases.
- Licencia: `AoInitialize.Initialize(esriLicenseProductCodeAdvanced)` antes de nada.
- `sys.coinit_flags = 2` antes de importar comtypes.
- **Unidades: QGIS declara la unidad de cada medida** (`*_width_unit`, `size_unit`,
  `distance_unit`). mm → ×2.834645669; **Point → tal cual, sin factor**. El modelo
  viaja siempre en puntos y el emisor no convierte nada.
- **`<Option>` anidados**: leer solo el `<Option type="Map">` hijo directo del
  `<layer>`. Con `elem.iter("Option")` se cuelan los de `<data_defined_properties>`,
  que traen claves homónimas vacías y pisan las reales.
- **Categoría multi-valor**: en QGIS no lleva atributo `value` sino hijos `<val>`.
  El "todos los demás" tampoco lleva `value`. Distinguir por la presencia de `<val>`.
- **Tramado (`LinePatternFill`)**: la raya real es un `<symbol type="line">`
  **anidado** dentro del layer. Las opciones planas del layer (`color`,
  `line_width`) son restos heredados que QGIS 3.x ya no usa.
- La def-query de una capa viaja dentro del `<datasource>` (`ruta.shp|subset=...`),
  no en `<subsetstring>`. El `subset=` puede llevar `|` dentro (literal o `||`):
  se corta en el PRIMER `|subset=`, no en todos los `|`.
- **Formato de símbolo legacy `<prop>`**: `_opciones()` lee tanto el mapa
  `<Option>` moderno como los `<prop k= v=>` hijos directos (QGIS 2.x y bastantes
  3.x). Usar `findall("prop")` (hijos DIRECTOS), no `.iter`.
- **Epsilon del graduado**: QGIS separa clases contiguas con un salto de ~1 ppm
  (4.0 → 4.000001). No es un hueco real; se tolera un desajuste relativo de 1 ppm.
- **Estirado INTERPOLATED**: `IMultiPartColorRamp` exige fijar su `Size` total
  ANTES de `CreateRamp()`; si no, el estirado renderiza gris. Leer color por
  `IColor.RGB` (BGR empaquetado): el QI a `IRgbColor` aquí es poco fiable.
- **Estirado, rango**: usa el min/max del DATASET, no el de la clasificación QGIS.
  `emitir()` compara ambos y AVISA si difieren.
- **RasterFill**: ArcObjects 10.5 SÍ soporta `esriIPicturePNG` en
  `CreateFillSymbolFromFile`. El tamaño exacto del mosaico y la transparencia alfa
  quedan para QA visual.
- **Cortes ráster**: `IRasterClassifyColorRampRenderer` **no tiene `MinimumBreak`**.
  Tiene `ClassCount+1` cortes y **`Break[0]` es el mínimo**: el techo de la clase
  `i` es `Break[i+1]`. Antes de emitir hace falta `CalculateStatistics_management`
  y un `Update()`, o el min/max no existen.
- **Ráster, opacidad**: no está en `<layerOpacity>` sino en el atributo `opacity`
  del `<rasterrenderer>`.
- **Ráster, valores ocultos**: `<rasterTransparency>` cuelga DENTRO de
  `<rasterrenderer>` y oculta valores sueltos al margen de la paleta. ArcMap no
  tiene transparencia por clase: el 100% se reproduce con símbolo nulo y lo demás
  se avisa.
- **Estadísticas del ráster**: `CalculateStatistics` reescribe los sidecars
  `.aux.xml` en cada pasada (resync inútil en una carpeta sincronizada). Se
  calcula solo si `GetRasterProperties` falla.
- `IRasterUniqueValueRenderer` indexa `Value[heading, clase, i]` con `ValueCount`:
  el ráster **sí** agrupa varios valores por clase. Su campo se llama `Field`,
  pero el del clasificado es **`ClassField`**.
- **Multicapa**: `IMultiLayerFillSymbol.AddLayer` **inserta en el índice 0**: hay
  que añadir en el orden del `.qgz` y el volcado sale invertido respecto al XML.
- **Color vacío** (`outline_color=""`, estilos migrados de QGIS 2.x): lo que Qt
  pinte con eso no se deduce del XML → se avisa y se salta, NO se inventa un negro.
- Encoding: Python 2.7 + acentos → literales `u""` siempre.
- **Temporales por proceso**: la capa en memoria de arcpy es `tmpL_<pid>` y el
  directorio temporal por defecto `qml2lyr_tmp_<pid>`, que se borra al terminar
  (solo si lo creó el emisor).
- **Nada de `.get(clave, por_defecto)` al traducir a enums de ArcObjects**: se
  usa `_enum()`, que revienta con `SimbologiaNoSoportada`. Un default silencioso
  esconde un cableado roto.
- Ante variante XML de QGIS no soportada: **avisar y saltar la capa**. Nunca `except: pass`.
- Degradación consciente → añadir a `capa.avisos`, nunca callar. `_qi()` del
  emisor es sondeo (devuelve None a propósito); si la conversión es obligatoria,
  usar `_qi_exig()`.

## Tests

- **`tests/test_parser.py`** — Python 2.7 puro, sin ArcGIS: el parser sobre los
  fixtures. Es lo que corre el CI.
- **`run_regresion_qml.py`** — la cadena entera con ArcGIS 10.5: lanza `emisor.py`
  como **subproceso de verdad** en sus modos (`--args-json`, posicional y
  `--batch`) y comprueba cada `.lyr` con `lyr_dump`. Datos sintéticos con arcpy
  en `tmp/regresion_qml/`, salidas en `out/qml/` (ambos en `.gitignore`). Para el
  modo posicional codifica los argumentos a la codepage ANSI a mano: es lo que
  Windows entrega a un py2.7 lanzado desde el py3 del plugin. El `stdout` se
  decodifica **en estricto** a propósito.
- **Fixtures**: en `tests/fixtures/`. **Todos** los escribe **QGIS de verdad**
  (`tests/generar_fixtures_qgis.py`, necesita antes los datos de
  `run_regresion_qml.py`). Nunca escribir uno a mano: si QGIS escribiera algo
  distinto a lo que suponemos, el caso pasaría igual sin probar nada (pasó: el
  `reglas_con_desmarcada.qml` a mano tenía `scalemindenom`/`scalemaxdenom`
  invertidos respecto a QGIS 3.44).
- **Regenerar solo lo que se toca**: `generar_fixtures_qgis.py <nombre> ...`
  (`--listar` da los nombres). QGIS cambia UUID, orden de atributos y colores
  aleatorios en cada pasada: regenerarlos todos ensucia el diff.
- `batch_sintetico.qgz` guarda rutas **relativas** a `tmp/regresion_qml/`: vale en
  cualquier clon del repo.
- La regresión solo compara lo que `lyr_dump` vuelca. Al añadir una propiedad al
  emisor, añadirla también al volcado **y a un fixture con valor distinto del
  neutro**, o el test no la cubre. Las propiedades nuevas se vuelcan solo si no
  son el valor neutro, para no cambiar la forma de los volcados existentes.
- Un caso nuevo que arregla un defecto debe **fallar contra el código anterior**:
  comprobarlo antes de dar el arreglo por probado.

## Qué NO tocar

- No copiar código fuente de SLYR (GPL): el emisor debe ser original.
- No versionar datos reales de terceros: los fixtures son sintéticos o generados
  a propósito.

## Convenciones

- Comentarios, commits y documentación en español (Conventional Commits); código en inglés.
