<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- Fixture del camino del PLUGIN: raster paletado con una clase de ALFA 0.
     En QGIS esa clase es invisible; hasta 2026-09-20 el parser solo miraba los
     alfas intermedios y la clase salia OPACA, sin aviso. En un paletado ArcMap
     si puede reproducirlo: simbolo nulo, como con <rasterTransparency>. -->
<qgis hasScaleBasedVisibilityFlag="0" maxScale="0" minScale="100000000" version="3.44.12-Solothurn" styleCategories="AllStyleCategories">
  <pipe>
    <rasterrenderer opacity="1" type="paletted" alphaBand="-1" nodataColor="" band="1">
      <colorPalette>
        <paletteEntry color="#ff0000" label="cero (invisible)" value="0" alpha="0"/>
        <paletteEntry color="#00ff00" label="uno" value="1" alpha="255"/>
        <paletteEntry color="#0000ff" label="dos" value="2" alpha="255"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
