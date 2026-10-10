# StreetVulkan - Plan Fase 3 Low-Poly

Estado actual: 02:00 AM, 03/10/2026
GLB: 109M, 2,035,530 verts, 1428 árboles 6-8m icosaedro low-poly con 4 especies
Build: OK, shader matID fix (0.0 terreno, 0.35 azotea, 0.6 sombra, 0.7 tronco, 0.8 follaje, 0.95 carretera)

## Objetivo

Mantener estilo low-poly simple ahora. Bases sólidas primero, efectos avanzados como ray tracing después. El satélite 4096x4096 se usa solo como guía para mapeo manual.

## Problema actual

32,305 edificios grises sin identidad. No se distingue casa, tienda, OXXO, escuela.

## Solución: Clasificación de edificios

### Fuentes de datos

1.  **INEGI DENUE (Directorio Nacional de Unidades Económicas)**
    - CSV gratuito por estado. Aguascalientes ~60k registros.
    - Campos: lat, lon, nombre, actividad económica, tipo.
    - Ejemplo: OXXO aparece como `Comercio al por menor en minisupers` nombre `OXXO`.
    - Descarga: https://www.inegi.org.mx/app/descarga/?ti=6

2.  **OSM / Overture Buildings**
    - Ya cargados en `models/overture_buildings.geojson` (33,882 edificios).
    - Tags útiles: `shop`, `amenity`, `brand`, `building:levels`.

3.  **API Gemini (ya disponible)**
    - Para edificios sin tag claro.
    - Input: crop 64x64 de `assets/satellite.png` + DENUE más cercano en 30m + tags OSM.
    - Output JSON: `{"type": "oxxo|house_1|house_2|local|school"}`

### Workflow propuesto

```
tools/classify_buildings.py
1. Cargar overture_buildings.geojson
2. Cargar DENUE_Aguascalientes.csv
3. Spatial join: por cada edificio buscar negocio DENUE en radio 30m
4. Si match con marca conocida (OXXO, 3B, etc) -> asignar tipo directo
5. Si no, llamar Gemini API con contexto satélite para clasificar
6. Guardar en models/custom_buildings.geojson con properties {type, color, levels}
```

### Biblioteca de prefabs low-poly

En `tools/procedural_props.py` crear funciones simples, no modelos realistas:

- `make_oxxo(cx,gy,cz)` - caja roja + detalle amarillo, 12 tris, matID 0.35
- `make_house_1floor(cx,gy,cz)` - caja beige + techo plano
- `make_house_2floor(cx,gy,cz)` - caja beige + segundo piso 0.7 altura
- `make_local(cx,gy,cz)` - caja gris claro + letrero
- `make_school(cx,gy,cz)` - caja L grande

Cada prefab usa 2 colores máximo y el sistema de matID ya implementado.

### Integración en generate_sector.py

```python
# En lugar de make_box gris genérico
if building_type == "oxxo":
    verts.extend(make_oxxo(cx,gy,cz))
elif building_type == "house_1":
    verts.extend(make_house_1floor(cx,gy,cz))
else:
    verts.extend(make_building_generic(...)
```

`generate_sector.py` debe dar prioridad a `custom_buildings.geojson` sobre Overture.

## Próximos pasos inmediatos

1. Backup actual: `models/aguascalientes_sector1.glb` 109M ya validado
2. Descargar DENUE Aguascalientes
3. Implementar `tools/classify_buildings.py` con spatial join
4. Crear 3 prefabs iniciales: oxxo, house_1, house_2
5. Fase 3 carretera: líneas blancas + banqueta 0.15m (más simple que edificios)

## Nota técnica

Mantener GLB < 120MB y verts < 2.2M. Low-poly con variación de color (como se hizo con 4 especies de árboles) funciona mejor que texturas PBR pesadas en este hardware.
