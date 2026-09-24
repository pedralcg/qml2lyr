# Despliega el plugin qml2lyr al perfil de QGIS (patron de doble copia).
# Edita SIEMPRE en el repo (plugin\qml2lyr) y sincroniza al perfil con este script.
# Uso:  powershell -ExecutionPolicy Bypass -File deploy.ps1 [-Profile default]
param(
    [string]$Profile = "default"
)

$ErrorActionPreference = "Stop"
$origen = Join-Path $PSScriptRoot "qml2lyr"
$destinoBase = Join-Path $env:APPDATA "QGIS\QGIS3\profiles\$Profile\python\plugins"
$destino = Join-Path $destinoBase "qml2lyr"

if (-not (Test-Path $origen)) { throw "No existe el origen: $origen" }
New-Item -ItemType Directory -Force -Path $destinoBase | Out-Null

# Limpia una copia previa (sin tocar __pycache__ de otros plugins).
if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }

# Copia solo el codigo fuente del plugin (sin cache).
Copy-Item -Recurse -Force $origen $destino
Get-ChildItem -Recurse -Force -Path $destino -Include "__pycache__", "*.pyc" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Plugin desplegado en: $destino"
Write-Host "En QGIS: Complementos -> Administrar e instalar -> activa 'qml2lyr'."
Write-Host "Si ya estaba cargado, usa 'Plugin Reloader' o reinicia QGIS."
