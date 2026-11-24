# Estimación de Tamaño, Esfuerzo (COCOMO-II / IFPUG / COSMIC) y Matriz de Trazabilidad
## StreetVulkan 🏙️

Este documento consolida las mediciones de tamaño funcional y estructural del proyecto **StreetVulkan**, las estimaciones paramétricas bajo **COCOMO-II Post-Architecture** sincronizadas exactamente con [estimate_cocomo_fp.py](../tools/metrics/estimate_cocomo_fp.py), y la **Matriz de Trazabilidad Completa** requerida por **ISO/IEC 29110-SI** e **ISO/IEC/IEEE 12207**.

---

## 1. Medición de Tamaño Estructural (SLOC / KSLOC)

La recolección automatizada (`collect_project_sloc()`) contabiliza líneas lógicas de código fuente propio (excluyendo líneas en blanco, comentarios puros y bibliotecas de terceros [cgltf.h](../include/cgltf.h) y [stb_image.h](../include/stb_image.h)):

| Capa / Lenguaje | Directorio y Extensiones | SLOC Medido | KSLOC | Porcentaje |
| :--- | :--- | :---: | :---: | :---: |
| **Motor C** | `src/*.c` (15 módulos) | `5,946` | `5.946` | `30.44%` |
| **Cabeceras C** | `include/*.h` (23 archivos propios) | `2,021` | `2.021` | `10.35%` |
| **Shaders GLSL 450** | `shaders/*.vert`, `shaders/*.frag` (2 archivos) | `394` | `0.394` | `2.02%` |
| **Pipeline Python 3** | `tools/**/*.py` (generadores y métricas) | `11,172` | `11.172` | `57.20%` |
| **TOTAL PROPIO** | — | **`19,533`** | **`19.533`** | **`100.00%`** |

---

## 2. Medición Funcional IFPUG (Unadjusted Function Points — UFP)

Utilizando los pesos promedio estándar del Manual de Prácticas de Conteo IFPUG (`EI = 4`, `EO = 5`, `EQ = 4`, `ILF = 10`, `EIF = 7`), el catálogo trazable `IFPUG_CATALOG` suma **`153` puntos de función sin ajustar (UFP)**:

| Tipo de Componente IFPUG | Cantidad | Peso Promedio | Subtotal UFP |
| :--- | :---: | :---: | :---: |
| **EI** (*External Inputs*) | `6` | `4` | `24` |
| **EO** (*External Outputs*) | `5` | `5` | `25` |
| **EQ** (*External Inquiries*) | `4` | `4` | `16` |
| **ILF** (*Internal Logical Files*) | `6` | `10` | `60` |
| **EIF** (*External Interface Files*) | `4` | `7` | `28` |
| **TOTAL IFPUG UFP** | **`25` elementos** | — | **`153 UFP`** |

*(Nota metodológica: la extensión ajustada $\text{AFP} = \text{UFP} \times (0.65 + 0.01 \times \text{TDI})$ permite ajustar por los 14 factores VAF; [estimate_cocomo_fp.py](../tools/metrics/estimate_cocomo_fp.py) reporta la línea base objetiva sin ajuste `UFP = 153`.)*

### Catálogo Trazable IFPUG (`IFPUG_CATALOG`)

| ID | Tipo | Peso | Descripción Funcional | Archivos Fuente Trazados |
| :--- | :---: | :---: | :--- | :--- |
| **EI-01** | EI | 4 | Entrada interactiva de cámara libre (WASD, Espacio/Ctrl y ratón) | [main.c](../src/main.c), [math_camera.h](../include/math_camera.h) |
| **EI-02** | EI | 4 | Comandos de menú de pausa y testing (`ESC`/`P`, `F1`–`F8`, `T`, `L`/`F`, flechas) | [pause_menu.h](../include/pause_menu.h) |
| **EI-03** | EI | 4 | Parámetros CLI de extracción cartográfica OSM, Overture y DENUE | [osm_extractor.py](../tools/osm_extractor.py), [open_buildings_fetcher.py](../tools/open_buildings_fetcher.py) |
| **EI-04** | EI | 4 | Parámetros CLI del pipeline procedural (sectores GLB, grafo vial y atlas) | [generate_sector.py](../tools/generate_sector.py), [generate_road_graph.py](../tools/generate_road_graph.py), [generate_texture_atlas.py](../tools/generate_texture_atlas.py) |
| **EI-05** | EI | 4 | Importación de planos fotográficos y generación de monumentos OBJ con Gemini | [photo_plane_importer.py](../tools/photo_plane_importer.py), [photo_scene_extractor.py](../tools/photo_scene_extractor.py), [gemini_obj_generator.py](../tools/gemini_obj_generator.py) |
| **EI-06** | EI | 4 | Configuración por variables de entorno (`TEST_FRAMES`, `TEST_PAUSE`, `GEMINI_API_KEY`) | [main.c](../src/main.c), [gemini_integration.py](../tools/gemini_integration.py) |
| **EO-01** | EO | 5 | Renderizado 3D Vulkan con iluminación día/noche, farolas y vehículos instanciados | [vulkan.c](../src/vulkan.c), [vertex.vert](../shaders/vertex.vert), [fragment.frag](../shaders/fragment.frag) |
| **EO-02** | EO | 5 | Overlay HUD de telemetría ISO 25010/25022 y menú visual de pausa | [debug_overlay.h](../include/debug_overlay.h), [pause_menu.h](../include/pause_menu.h) |
| **EO-03** | EO | 5 | Exportación de telemetría JSON y scorecard de calidad ISO/IEC 25040 | [telemetry.h](../include/telemetry.h), [evaluate_iso25040.py](../tools/metrics/evaluate_iso25040.py) |
| **EO-04** | EO | 5 | Generación de macro-sectores GLB 2.0, grafo binario `road_network.bin` y `chunks.json` | [split_glb_to_sectors.py](../tools/split_glb_to_sectors.py), [generate_road_graph.py](../tools/generate_road_graph.py), [gltf_writer.py](../tools/gltf_writer.py) |
| **EO-05** | EO | 5 | Exportación de modelos GLB de flota vehicular/peatonal y cuadrantes satelitales | [convert_car_models.py](../tools/convert_car_models.py), [procedural_peds.py](../tools/procedural_peds.py), [split_satellite_texture.py](../tools/split_satellite_texture.py) |
| **EQ-01** | EQ | 4 | Consulta de cota topográfica DEM continua (`vulkan_get_ground_elevation` / `terrain_dem_get_elevation`) | [vulkan.c](../src/vulkan.c), [terrain_dem_data.h](../include/terrain_dem_data.h) |
| **EQ-02** | EQ | 4 | Consulta espacial del estado de semáforo por coordenada (`traffic_system_get_light_state_at`) | [traffic_system.c](../src/traffic_system.c) |
| **EQ-03** | EQ | 4 | Consulta de visibilidad frustum por AABB y selección de chunks visibles | [frustum_cull.h](../include/frustum_cull.h), [chunk_system.h](../include/chunk_system.h) |
| **EQ-04** | EQ | 4 | Consulta de capacidades de GPU física Vulkan, extensiones WSI y formato de swapchain | [vulkan_device.c](../src/vulkan_device.c), [vulkan_swapchain.c](../src/vulkan_swapchain.c) |
| **ILF-01** | ILF | 10 | Grafo vial binario CSR en memoria y disco (`RoadGraph` / `models/road_network.bin`) | [road_graph.c](../src/road_graph.c), [road_graph.h](../include/road_graph.h) |
| **ILF-02** | ILF | 10 | Estado de flota vehicular y hash espacial en CPU/GPU (`CarSystem` / 200 vehículos) | [car_system.c](../src/car_system.c), [car_system.h](../include/car_system.h) |
| **ILF-03** | ILF | 10 | Estado de intersecciones, fases y luminarias semafóricas (`TrafficSystem` / `traffic_signals.json`) | [traffic_system.c](../src/traffic_system.c), [traffic_system.h](../include/traffic_system.h) |
| **ILF-04** | ILF | 10 | Índice espacial de macro-sectores y subasignadores de VRAM/RAM (`SectorSystem` / `VulkanMemoryPool`) | [sector_system.c](../src/sector_system.c), [sector_system.h](../include/sector_system.h), [vulkan_memory_pool.c](../src/vulkan_memory_pool.c) |
| **ILF-05** | ILF | 10 | Banco de luces dinámicas y buffer uniforme GPU (`LightingSystem` / `LightingUBO`) | [lighting_system.h](../include/lighting_system.h) |
| **ILF-06** | ILF | 10 | Catálogo semántico de edificios clasificados y estado peatonal (`classified_buildings.json`, `PedSystem`) | [classify_buildings.py](../tools/classify_buildings.py), [ped_system.c](../src/ped_system.c), [ped_system.h](../include/ped_system.h) |
| **EIF-01** | EIF | 7 | Cartografía externa OpenStreetMap y Overture Maps (XML/GeoJSON) | [osm_extractor.py](../tools/osm_extractor.py), [open_buildings_fetcher.py](../tools/open_buildings_fetcher.py) |
| **EIF-02** | EIF | 7 | Elevación satelital NASA SRTM / AWS Terrarium DEM (cachés JSON y grilla embebida) | [geo_dem.py](../tools/geo_dem.py), [terrain_dem_data.h](../include/terrain_dem_data.h) |
| **EIF-03** | EIF | 7 | Diccionario estadístico INEGI DENUE y datos comerciales Rolcar | [extract_rolcar.py](../tools/extract_rolcar.py), [rolcar_vector.py](../tools/rolcar_vector.py) |
| **EIF-04** | EIF | 7 | Cuadrantes de textura satelital PNG y activos externos glTF/OBJ | [vulkan_texture.c](../src/vulkan_texture.c), [vulkan_gltf.c](../src/vulkan_gltf.c), [obj_loader.c](../src/obj_loader.c) |

---

## 3. Medición Funcional COSMIC (ISO/IEC 19761)

El estándar **ISO/IEC 19761 (COSMIC)** mide el tamaño funcional contando cuatro tipos de movimientos de datos (*Entry* `E`, *Exit* `X`, *Read* `R`, *Write* `W`) por proceso funcional disparado por un evento (*trigger*). El proyecto totaliza **`39` CFP**:

| ID | Proceso Funcional | Evento Disparador (*Trigger*) | `E` | `X` | `R` | `W` | Subtotal CFP | Módulos Involucrados |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **CFP-01** | Renderizado y Streaming de Sectores | Cambio de posición de cámara o inicio de fotograma (`vulkan_draw`) | 2 | 2 | 3 | 1 | **8** | [vulkan.c](../src/vulkan.c), [sector_system.c](../src/sector_system.c), [vulkan_gltf.c](../src/vulkan_gltf.c), [vulkan_memory_pool.c](../src/vulkan_memory_pool.c), [vulkan_swapchain.c](../src/vulkan_swapchain.c), [frustum_cull.h](../include/frustum_cull.h) |
| **CFP-02** | Simulación Vehicular y Semáforos | Tick de simulación a paso fijo de 60 Hz o cambio de modo semafórico | 2 | 2 | 2 | 2 | **8** | [car_system.c](../src/car_system.c), [traffic_system.c](../src/traffic_system.c), [road_graph.c](../src/road_graph.c), [lighting_system.h](../include/lighting_system.h) |
| **CFP-03** | Simulación Peatonal | Tick de actualización peatonal (`ped_system_update`) | 1 | 1 | 2 | 1 | **5** | [ped_system.c](../src/ped_system.c), [ped_system.h](../include/ped_system.h), [procedural_peds.py](../tools/procedural_peds.py) |
| **CFP-04** | Cámara Libre, Menú de Pausa y Telemetría HUD | Evento SDL2 de teclado/ratón o cierre de cuadro (`telemetry_frame_end`) | 3 | 2 | 1 | 1 | **7** | [main.c](../src/main.c), [math_camera.h](../include/math_camera.h), [debug_overlay.h](../include/debug_overlay.h), [pause_menu.h](../include/pause_menu.h), [telemetry.h](../include/telemetry.h) |
| **CFP-05** | Pipeline Procedural Python y Calidad | Ejecución CLI de generación geoespacial o evaluación `make metrics` | 3 | 2 | 3 | 3 | **11** | [generate_sector.py](../tools/generate_sector.py), [generate_road_graph.py](../tools/generate_road_graph.py), [geo_dem.py](../tools/geo_dem.py), [validate_data_quality.py](../tools/metrics/validate_data_quality.py), [evaluate_iso25040.py](../tools/metrics/evaluate_iso25040.py) |
| **TOTAL** | **5 procesos funcionales** | — | **11** | **9** | **11** | **8** | **`39 CFP`** | — |

---

## 4. Estimación Paramétrica COCOMO-II (Estadio 3: Post-Architecture)

Siguiendo la formulación estándar de **COCOMO-II.2000** (Unidad 02, Slide 133):

$$E = B + 0.01 \times \sum_{j=1}^{5} \text{SF}_j, \qquad PM = A \times (\text{KSLOC})^E \times \prod_{i=1}^{17} \text{EM}_i$$

$$TDEV = C \times (PM)^{\left(D + 0.2 \times (E - B)\right)}, \qquad \text{Equipo Promedio} = \frac{PM}{TDEV}$$

Con constantes base $A = 2.94$, $B = 0.91$, $C = 3.67$, $D = 0.28$ y multiplicadores de esfuerzo en nivel nominal ($\prod \text{EM}_i = \text{EAF} = 1.0$):

### 4.1 Factores de Escala ($\text{SF}_j$) Nominales Aplicados

| Factor de Escala | Significado | Calificación | Valor $\text{SF}_j$ |
| :--- | :--- | :---: | :---: |
| **PREC** (*Precedentedness*) | Familiaridad / precedencia con motores gráficos y SIG | Nominal | `3.72` |
| **FLEX** (*Development Flexibility*) | Flexibilidad de desarrollo y restricciones de arquitectura | Nominal | `3.04` |
| **RESL** (*Architecture / Risk Resolution*) | Resolución de arquitectura y mitigación de riesgos | Nominal | `4.24` |
| **TEAM** (*Team Cohesion*) | Cohesión y cooperación del equipo | Nominal | `3.29` |
| **PMAT** (*Process Maturity*) | Madurez del proceso organizacional | Nominal | `4.68` |
| **Suma ($\sum \text{SF}_j$)** | — | — | **`18.97`** |

$$\implies E = 0.91 + 0.01 \times 18.97 = \mathbf{1.0997}$$

### 4.2 Resultados Calculados por `estimate_cocomo_fp.py`

| Escenario Evaluado | Tamaño (`KSLOC`) | Exponente ($E$) | Esfuerzo ($PM$) | Duración ($TDEV$) | Equipo Promedio |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Base Actual StreetVulkan** (`19,533 SLOC`) | `19.533` (`19.53`) | `1.0997` | **`77.23` persona-mes** | **`14.62` meses** | **`5.28` personas** |
| **Roadmap Futuro** ([ROADMAP_FUTURO.md](ROADMAP_FUTURO.md)) | `2.50` | `1.0997` | **`8.05` persona-mes** | **`7.12` meses** | **`1.13` personas** |

*Interpretación de Ingeniería:* El cálculo de `77.23` persona-mes en COCOMO-II Post-Architecture refleja el costo equivalente en un entorno industrial completo (especificación formal, documentación extensiva, validación multi-entorno e infraestructura completa) para un sistema de `19.533 KSLOC`. Dentro del entorno académico ágil-disciplinado de la UAA (con reutilización de SDKs Vulkan/SDL2, bibliotecas `cgltf`/`stb_image` y automatización procedural), el proyecto alcanzó la capacidad operativa base en `280` horas reales de taller/desarrollo registradas en [OPENUP_TSP.md](OPENUP_TSP.md).

---

## 5. Matriz de Trazabilidad Completa (ISO/IEC 29110-SI e ISO/IEC/IEEE 12207)

La trazabilidad bidireccional enlaza cada Historia de Usuario (`HU-01`..`HU-12`) con los componentes funcionales IFPUG/COSMIC, el diseño arquitectónico, los módulos implementados, los casos de verificación y los estándares ISO/IEC correspondientes.

| ID Requisito / HU | ID Funcional (IFPUG / COSMIC) | Diseño / Arquitectura | Módulos C / GLSL / Python | Casos de Prueba / Verificación | Estándar ISO/IEC Asociado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **HU-01** Cámara libre, instancia Vulkan y swapchain resiliente | `EI-01`, `EQ-04` / `CFP-01`, `CFP-04` | Bucle `FIXED_DELTA_TIME` 60 Hz, Vulkan 1.2 + SDL2, recreación `VK_ERROR_OUT_OF_DATE_KHR` | [main.c](../src/main.c), [vulkan.c](../src/vulkan.c), [vulkan_device.c](../src/vulkan_device.c), [vulkan_swapchain.c](../src/vulkan_swapchain.c), [vulkan_pipeline.c](../src/vulkan_pipeline.c), [math_camera.c](../src/math_camera.c), [math_camera.h](../include/math_camera.h) | `test_math_camera()` en [test_c_modules.c](../tests/test_c_modules.c); checks `Q-CMP-02`, `Q-PRT-01`, `Q-MNT-01` en [measure_iso25023.py](../tools/metrics/measure_iso25023.py) | ISO/IEC 25010 (Usabilidad, Fiabilidad, Portabilidad), 25023 (`Q-PRT-01`, `Q-REL-02`) |
| **HU-02** Carga glTF 2.0 Zero-Copy (`mmap`) y mallas OBJ | `EIF-04` / `CFP-01` | Mapeo directo POSIX `mmap` + `MADV_SEQUENTIAL` y parser `.obj`/`.mtl` | [vulkan_gltf.c](../src/vulkan_gltf.c), [vulkan_gltf.h](../include/vulkan_gltf.h), [obj_loader.c](../src/obj_loader.c), [obj_loader.h](../include/obj_loader.h) | `test_obj_loader_and_sector_bounds()` en [test_c_modules.c](../tests/test_c_modules.c); check `Q-CMP-01` en [measure_iso25023.py](../tools/metrics/measure_iso25023.py) | ISO/IEC 25010 (Eficiencia, Compatibilidad), 25023 (`Q-CMP-01`) |
| **HU-03** Pipeline geoespacial Python (OSM, Overture, DENUE, puentes) | `EI-03`, `EI-04`, `ILF-06`, `EIF-01`, `EIF-03` / `CFP-05` | Arquitectura procedural modular (`terrain` + `roads` + `SpatialGrid2D` + triangulación) | [generate_sector.py](../tools/generate_sector.py), [sector_terrain.py](../tools/sector_terrain.py), [sector_roads.py](../tools/sector_roads.py), [classify_buildings.py](../tools/classify_buildings.py), [bridge_generator.py](../tools/bridge_generator.py), [topography_math.py](../tools/topography_math.py) | `TestTopographyMath` (`4` pruebas) en [test_python_tools.py](../tests/test_python_tools.py); auditoría `classified_buildings.json` (`325,511` reg.) en [validate_data_quality.py](../tools/metrics/validate_data_quality.py) | ISO/IEC 25012 / 25024 (`DQ-CMP-01`, `DQ-UND-01`) |
| **HU-04** Topografía real unificada (`1871.0 m`, 4 ríos, 2 fallas) | `EQ-01`, `EI-05`, `EIF-02` / `CFP-01`, `CFP-05` | Grilla `64x64` Terrarium embebida en C (`double`) alineada con `geo_dem.py` | [terrain_dem_data.h](../include/terrain_dem_data.h), [vulkan.c](../src/vulkan.c), [geo_dem.py](../tools/geo_dem.py), [photo_plane_importer.py](../tools/photo_plane_importer.py), [photo_scene_extractor.py](../tools/photo_scene_extractor.py) | `test_dem_topography_precision()` (`14` puntos, `< 0.05 m`) en [test_c_modules.c](../tests/test_c_modules.c); probe C automatizado `Q-FNC-02` (`max_diff = 0.000018 m`) en [measure_iso25023.py](../tools/metrics/measure_iso25023.py); `7` DEMs en [validate_data_quality.py](../tools/metrics/validate_data_quality.py) | ISO/IEC 25010 (Corrección Funcional), 25023 (`Q-FNC-02`), 25012/25024 (`DQ-ACC-01`) |
| **HU-05** Texturizado PBR, cuadrantes satelitales y fallback 4x4 | `EO-01`, `EO-05`, `EIF-04` / `CFP-01` | PBR Cook-Torrance GGX/Schlick, 4 cuadrantes PNG, chequeo `samplerAnisotropy`/blit, fallback `4x4` | [vulkan_texture.c](../src/vulkan_texture.c), [vulkan_texture.h](../include/vulkan_texture.h), [vertex.vert](../shaders/vertex.vert), [fragment.frag](../shaders/fragment.frag), [generate_texture_atlas.py](../tools/generate_texture_atlas.py), [split_satellite_texture.py](../tools/split_satellite_texture.py) | Compilación SPIR-V (`Q-CMP-02`), paridad `.vert`/`.frag` $\leftrightarrow$ `.spv` en [check_traceability.py](../tools/metrics/check_traceability.py) y compilación limpia `-Wall -Wextra` | ISO/IEC 25010 (Fiabilidad, Compatibilidad), 25023 (`Q-CMP-02`, `Q-REL-01`), 29110-SI |
| **HU-06** Grafo vial `RGP1` y simulación de `200` vehículos instanciados | `EO-04`, `ILF-01`, `ILF-02` / `CFP-02` | Binario empaquetado `RGP1` + CSR en CPU + hash espacial + `CarInstanceData` (96 B) | [road_graph.c](../src/road_graph.c), [road_graph.h](../include/road_graph.h), [car_system.c](../src/car_system.c), [car_system.h](../include/car_system.h), [generate_road_graph.py](../tools/generate_road_graph.py), [convert_car_models.py](../tools/convert_car_models.py) | `test_road_graph_binary()` y `test_car_system_headless()` en [test_c_modules.c](../tests/test_c_modules.c); `road_network.bin` y `cars/manifest.json` en [validate_data_quality.py](../tools/metrics/validate_data_quality.py) | ISO/IEC 25010 (Adecuación Funcional, Eficiencia), 25012/25024 (`DQ-INT-01`, `DQ-AVL-01`) |
| **HU-07** Control semafórico de 6 fases e iluminación de 64 luces | `EQ-02`, `ILF-03`, `ILF-05` / `CFP-02` | FSM determinista, resolución diferida por `intersectionIndex`, `LightingUBO` std140 | [traffic_system.c](../src/traffic_system.c), [traffic_system.h](../include/traffic_system.h), [lighting_system.h](../include/lighting_system.h), [celestial_stars.py](../tools/celestial_stars.py) | `test_traffic_system_fsm()` y `test_traffic_system_o1_intersection_resolution()` en [test_c_modules.c](../tests/test_c_modules.c); `traffic_signals.json` (`552` reg.) en [validate_data_quality.py](../tools/metrics/validate_data_quality.py) | ISO/IEC 25010 (Adecuación Funcional, Seguridad memoria), 25023 (`Q-FNC-03`, `Q-SEC-02`) |
| **HU-08** Streaming de macro-sectores (`< 99 MB`) y frustum culling | `EQ-03`, `EO-04`, `ILF-04` / `CFP-01` | Macro-sectores `1024 m`, trabajador POSIX `pthread`, liberación diferida, chunks `128 m` | [sector_system.c](../src/sector_system.c), [sector_system.h](../include/sector_system.h), [chunk_system.h](../include/chunk_system.h), [frustum_cull.h](../include/frustum_cull.h), [split_glb_to_sectors.py](../tools/split_glb_to_sectors.py) | `test_frustum_culling()` y `test_sector_system_manifest()` en [test_c_modules.c](../tests/test_c_modules.c); check `Q-PRF-03` (`max=76.94 MB`); `sectors.json` y `chunks.json` en [validate_data_quality.py](../tools/metrics/validate_data_quality.py) | ISO/IEC 25010 (Eficiencia, Portabilidad POSIX), 25023 (`Q-PRF-03`, `Q-PRF-05`), 25012 (`DQ-CON-01`) |
| **HU-09** Subasignador centralizado `VulkanMemoryPool` | `ILF-04` / `CFP-01` | 3 pools (`vramBufferPool`, `vramImagePool`, `hostVisiblePool`) con alineación y coalescencia | [vulkan_memory_pool.c](../src/vulkan_memory_pool.c), [vulkan_memory_pool.h](../include/vulkan_memory_pool.h) | `test_vulkan_memory_pool()` en [test_c_modules.c](../tests/test_c_modules.c) bajo `make test` y `make asan-test` | ISO/IEC 25010 (Eficiencia, Fiabilidad), 25023 (`Q-SEC-02`) |
| **HU-10** Telemetría en tiempo real (HUD) y menú de pausa | `EI-02`, `EI-06`, `EO-02`, `EO-03` / `CFP-04` | Fuente bitmap 5×7 NDC (`emission=2.0`), promedios móviles 60 frames y JSON ISO 25022 | [telemetry.h](../include/telemetry.h), [debug_overlay.h](../include/debug_overlay.h), [pause_menu.h](../include/pause_menu.h) | `test_recoverability_and_iso25022()` en [test_c_modules.c](../tests/test_c_modules.c) | ISO/IEC 25010 (Usabilidad), 25022 / 25062, 25023 (`Q-USA-02`, `Q-USA-03`) |
| **HU-11** Automatización XP, ASan/UBSan, métricas SQuaRE y CI | `EO-03` / `CFP-05` | Evaluador maestro `evaluate_iso25040.py` (`PASS`/`WARN`/`FAIL`), pipeline GitHub Actions | [Makefile](../Makefile), [ci.yml](../.github/workflows/ci.yml), [estimate_cocomo_fp.py](../tools/metrics/estimate_cocomo_fp.py), [validate_data_quality.py](../tools/metrics/validate_data_quality.py), [measure_iso25023.py](../tools/metrics/measure_iso25023.py), [measure_maintainability.py](../tools/metrics/measure_maintainability.py), [check_traceability.py](../tools/metrics/check_traceability.py), [evaluate_iso25040.py](../tools/metrics/evaluate_iso25040.py) | `make test`, `make asan-test`, `make metrics`; `8` pruebas métricas en [test_python_tools.py](../tests/test_python_tools.py) (`12` unittest totales) | ISO/IEC 19761, 25040, 25041, 29110-SI, 12207, 14764 |
| **HU-12** Simulación peatonal base en C y hoja de ruta GPU | `EO-05`, `ILF-06` / `CFP-03` | Máquina de estados `PED_WALKING`/`PED_WAITING_RED`/`PED_CROSSING` y malla `ped.glb` | [ped_system.c](../src/ped_system.c), [ped_system.h](../include/ped_system.h), [procedural_peds.py](../tools/procedural_peds.py), [ROADMAP_FUTURO.md](ROADMAP_FUTURO.md) | `test_ped_system()` en [test_c_modules.c](../tests/test_c_modules.c); `peds/manifest.json` en [validate_data_quality.py](../tools/metrics/validate_data_quality.py). *(Render GPU pendiente)* | ISO/IEC 25010 (Adecuación Funcional parcial), 25023 (`Q-FNC-01`), 19761 (`CFP-03`) |

---

## 6. Verificación Automatizada de Trazabilidad Técnica ([check_traceability.py](../tools/metrics/check_traceability.py))

La auditoría bajo **ISO/IEC 29110-SI** e **ISO/IEC/IEEE 12207** verifica de manera automática:
1. **Paridad GLSL $\to$ SPIR-V:** Los `2` archivos fuente ([vertex.vert](../shaders/vertex.vert), [fragment.frag](../shaders/fragment.frag)) poseen su binario compilado `.spv` vigente (`missing=0`, `stale=0`).
2. **Modularidad y Cobertura C:** `14` de `15` módulos `.c` en `src/` cuentan con cabecera `.h` homónima en `include/` (se permite `main.c` sin cabecera al ser punto de entrada), y los subsistemas centrales están directamente ejercitados por las `12` funciones de prueba unitaria en [test_c_modules.c](../tests/test_c_modules.c).
