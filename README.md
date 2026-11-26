# 🏙️ StreetVulkan: Gemelo Digital Urbano 3D de Aguascalientes

[![CI](https://github.com/jefazo-isc/aguascavulkan/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jefazo-isc/aguascavulkan/actions/workflows/ci.yml)
[![Pages](https://github.com/jefazo-isc/aguascavulkan/actions/workflows/wasm-pages.yml/badge.svg)](https://github.com/jefazo-isc/aguascavulkan/actions/workflows/wasm-pages.yml)

> **Arquitectura Web-First impulsada por WebGL2, WebGPU y WebAssembly (`.wat` $\to$ `.wasm`)**, con motor nativo de referencia en C11 / Vulkan 1.2 + SDL2 y pipeline geoespacial procedural.
>
> 🌐 **Demo en Vivo (GitHub Pages):** [https://jefazo-isc.github.io/aguascavulkan/](https://jefazo-isc.github.io/aguascavulkan/)  
> 📦 **Repositorio Oficial:** [https://github.com/jefazo-isc/aguascavulkan](https://github.com/jefazo-isc/aguascavulkan)

---

## 📌 Guía Rápida para el Equipo: ¿Qué es este proyecto y cómo presentarlo?

Si tienes que exponer o presentar **StreetVulkan**, aquí tienes el resumen ejecutivo estructurado para responder qué hace, por qué es innovador, cómo está construido y cómo demostrarlo en vivo:

### 🎯 1. La Visión del Proyecto
**StreetVulkan** es una plataforma de **simulación urbana y visualización tridimensional** de la ciudad de **Aguascalientes, México**. Integra datos geoespaciales (edificaciones de OpenStreetMap, elevación DEM satelital Terrarium/SRTM y red vial) en una moderna plataforma web con soporte universal **WebGL2 / WebGPU**, cuyo kernel matemático está escrito en **WebAssembly Text (WAT)** puro, complementado por un motor de referencia nativo en C11/Vulkan 1.2.

### 🌟 2. Características Clave & Cifras de Impacto (Para la Presentación)
- **325,511 Edificios Reales Clasificados**: Dataset pre-clasificado en `models/classified_buildings.json` a partir de huellas Overture con alturas procedimentales, techos y fachadas segmentadas (su regeneración con `tools/classify_buildings.py` requiere los archivos externos Overture GeoJSON / INEGI DENUE CSV).
- **27 Sucursales Rolcar Georreferenciadas**: Modelado 3D fidedigno con señalamientos y logos corporativos vectoriales (ej. nodo central *Paseo de la Cruz / José María Chávez*).
- **1,215 Postes y 1,180 Tramos de Cableado CFE**: Simulación de tendido eléctrico aéreo con curvas de flecha parabólica (aproximación de catenaria) procedimentales.
- **552 Semáforos Inteligentes y Red Vial**: Simulación matemática con grafos de tráfico y temporizadores sincronizados.
- **200 Vehículos Autónomos Instanciados**: Cinemática y simulación de vehículos navegando carriles viales en tiempo real en WebGL2 y WebGPU.
- **Topografía Real (DEM 30m)**: Elevación del terreno corregida topográficamente a partir de datos satelitales.
- **401 Macro-Sectores Modulares (Sector Showcase en Repo)**: `models/sectors.json` declara 401 celdas de *streaming* espacial para mantener el consumo de memoria acotado (< 99 MB por sector); el repositorio distribuye en disco el sector central `models/sectors/sector_0_0.glb` (`chunks_0_0.json`), y generar los 401 sectores completos requiere los insumos externos OSM/Overture.
- **Kernel WebAssembly en Ensamblador Puro (`.wat`)**: Cero dependencias pesadas de runtime. Las matemáticas 3D (cámara, proyección, matrices 4x4, frustum culling Gribb/Hartmann, lógica de semáforos y simulación cinemática vehicular) corren en código máquina WASM compilado por nuestro propio compilador/ensamblador en Python.
- **Renderizado Web Universal (WebGL2 & WebGPU)**: El cliente implementa shaders PBR especializados para arquitectura urbana (`vs_building`, `fs_building`, `VS_BUILDING_GLSL300`, `FS_BUILDING_GLSL300`), streaming LRU y fallback universal garantizado sin instalar drivers o dependencias de escritorio.
- **Verificación del software**: El repositorio incluye pruebas C y Python, una prueba separada de reproducibilidad WAT→WASM, sanitizadores y auditorías internas relacionadas con calidad y seguridad. Estas verificaciones documentan prácticas y resultados parciales; no constituyen certificación ni demuestran por sí solas conformidad formal con normas ISO.

---

## System Overview

StreetVulkan integrates three primary runtime and tooling layers around shared geospatial, mesh, and lighting contracts:

1. **Offline Geospatial, Asset & Quality Pipeline (`tools/`, `tools/metrics/`)**: Python generators and fetchers ingest OpenStreetMap XML, AWS Terrarium DEM tiles, Overture GeoJSON footprints, INEGI DENUE records, ArcGIS World Imagery, Google Street View/KartaView photos, and Gemini API vision outputs to build `models/sectors.json`, `models/sectors/*.glb`, `models/chunks.json`, `models/road_network.bin`, `models/traffic_signals.json`, vehicle/pedestrian `.glb` assets, and procedural textures. The same toolchain assembles `web/street_vulkan_core.wat` into `web/street_vulkan_core.wasm` and executes the ISO/IEC 25040/25041 evaluation suite (`tools/metrics/evaluate_iso25040.py`).
2. **Native C11 / Vulkan 1.2 Engine (`include/`, `src/`, `shaders/`)**: Reference engine compiled with GCC against SDL2, Vulkan 1.2, `libm`, and `pthread` (`Makefile`), using GLSL 450 shaders compiled to SPIR-V (`shaders/*.spv`) via `glslangValidator -V`. `src/main.c` runs a fixed-timestep (`1/60` s) simulation loop (`traffic_system`, `car_system`, `ped_system`) paired with mutex-serialized text/JSONL logging (`src/logger.c`), pooled Vulkan device/host suballocation (`src/vulkan_memory_pool.c`), and an asynchronous POSIX `pthread` worker (`src/sector_system.c`) that streams 1 km x 1 km macro-sectors around the camera.
3. **Browser WebAssembly + WebGL2/WebGPU Client (`web/`)**: Primary Web-First client (`web/index.html`) loading `web/app.js` as an ES module, instantiating a fixed 2-page (128 KiB) WebAssembly math/culling/traffic kernel (`web/street_vulkan_core.wasm`, mirrored in C by `web/main_wasm.c` + `src/math_camera.c`), streaming GLB 2.0 sectors, chunk manifests, texture atlases, dynamic vehicles, and optional traffic signals via HTTP `GET`/`HEAD`, and rendering via universal `WebGL2Renderer` (`VS_GLSL300`/`FS_GLSL300`, `VS_BUILDING_GLSL300`/`FS_BUILDING_GLSL300`) or accelerated `WebGPURenderer` (`web/shaders.wgsl`).

```text
  ┌────────────────────────────────────────────────────────────────────────────┐
  │         External Data & APIs (OSM/Overpass, AWS Terrarium, ArcGIS,         │
  │           Overture, INEGI DENUE, StreetView/KartaView, Gemini)             │
  └───────────────────────────────────┬────────────────────────────────────────┘
                                      │ HTTP/HTTPS + local ingest
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  Offline Pipeline & Tooling (`tools/`, `tools/metrics/`)                   │
  │  • `generate_sector.py`, `gltf_writer.py`, `split_glb_to_sectors.py`       │
  │  • `generate_road_graph.py`, `compile_wat_to_wasm.py`, `evaluate_iso25040` │
  └───────────┬───────────────────────┬──────────────────────────┬─────────────┘
              │ GLB 2.0 (< 99 MB),    │ RGP1 road_network.bin,   │ Assembled
              │ chunks & JSONs        │ atlases & plates         │ .wasm
              ▼                       ▼                          ▼
  ┌───────────────────────────────────────────┐   ┌────────────────────────────┐
  │  Storage Backends (`models/`, `assets/`)  │   │ `web/` Browser Client      │
  └─────────────────────┬─────────────────────┘   │ • `app.js` HTTP streaming  │
                        │ mmap / FILE* +          │ • `street_vulkan_core.wat` │
                        │ async `pthread`         │ • `WebGPURenderer` (WGSL)  │
                        ▼                         │ • `WebGL2Renderer` fallback│
  ┌───────────────────────────────────────────┐   └────────────────────────────┘
  │ Native Engine (`include/`, `src/`,        │
  │   `shaders/`)                             │
  │ • C11 + SDL2 + Vulkan 1.2 + GLSL 450      │
  │ • Fixed 1/60s sim + `pthread` sector      │
  │   streaming + `g_logger_mutex` logs       │
  └───────────────────────────────────────────┘
```

## Subdirectories & System Boundaries

### Documented Code Subsystems
- **include**: [./include/README.md](./include/README.md) — C11 header contracts (`VulkanEngine`, 52-byte `Vertex`, 96-byte `CarInstanceData`, `RGP1` road structs, `VulkanMemoryPool`, `64x64` DEM terrain inline math, `SectorSystem`, `TrafficSystem`, `LightingSystem`, `DebugOverlay`, `PauseMenu`, `TelemetrySystem`, `Logger`) plus vendored `cgltf.h` v1.15 and `stb_image.h` v2.30.
- **shaders**: [./shaders/README.md](./shaders/README.md) — GLSL `#version 450` graphics stages (`vertex.vert`, `fragment.frag`) compiled to `shaders/*.spv` via `glslangValidator -V`, implementing static/instanced transforms, `matID` Cook-Torrance GGX/Schlick PBR shading, atmospheric sky fog, and `ACESFilm` tone mapping.
- **src**: [./src/README.md](./src/README.md) — 16 C11 translation units implementing the SDL2/Vulkan 1.2 runtime, device/memory-pool/swapchain/pipeline/texture management, OBJ/glTF/RGP1 loaders, async `pthread` macro-sector streaming, 6-phase traffic lights, vehicles, pedestrians, and mutex-synchronized logging.
- **tools**: [./tools/README.md](./tools/README.md) — Offline Python geospatial acquisition, procedural 3D sector/road/bridge/prop/wiring generation, glTF 2.0 serialization, Gemini 3D extraction, pure-Python WAT-to-WASM assembler, GitHub WASM staging, and X11 capture scripts; delegates quality/compliance auditing to child contract [./tools/metrics/README.md](./tools/metrics/README.md).
- **tools/metrics**: [./tools/metrics/README.md](./tools/metrics/README.md) — ISO/IEC 25040/25041 evaluation orchestrator (`evaluate_iso25040.py`) and 8 standalone quality, McCabe maintainability, dataset validation, security, testing, QMS, traceability, and COCOMO-II/IFPUG/COSMIC estimation scripts.
- **web**: [./web/README.md](./web/README.md) — Browser client (`streetvulkan-web`) combining ES module GLB/atlas/signal streaming (`app.js`), a fixed 2-page WASM math/culling/traffic kernel (`street_vulkan_core.wat` / `main_wasm.c`), and `WebGPURenderer` (`shaders.wgsl`) / `WebGL2Renderer` (`VS_GLSL300`, `FS_GLSL300`).

### Non-Code & Test Directories (Excluded from Contract Generation)
- `assets/`: Texture atlases (`texture_atlas_16x16.png`), street name plates (`assets/plates/`), Street View imagery (`assets/streetview/`), Rolcar signage textures, and source vehicle model kits (`assets/models/`).
- `docs/`: Software engineering methodology, ISO/IEC quality, traceability, and roadmap Markdown documentation.
- `models/`: Generated and cached 3D datasets (`sectors.json`, `sectors/*.glb`, `chunks.json`, `road_network.bin`, `traffic_signals.json`, `cars/`, `peds/`, DEM caches, classified buildings).
- `tests/`: Automated C, Python, and WASM verification suites (`test_c_modules.c`, `test_python_tools.py`, `test_wasm_port.py`).

## Global Invariants

- **52-Byte Vertex Format & `matID` Channel Overload**: `[tools/gltf_writer.py:FastMeshBuilder]`, `[include/vertex_format.h:Vertex]`, `[shaders/vertex.vert:inPosition]`, `[shaders/fragment.frag:fragColor]`, `[web/renderer_webgpu.js:WebGPURenderer.uploadSector]`, and `[web/renderer_webgl2.js:WebGL2Renderer.uploadSector]` share a 52-byte (`13`-float) vertex layout (`pos[3], norm[3], uv[2], col[4], em[1]`), encoding material ID (`matID`) in `color.a` (`0.0` terrain, `0.35` rooftop, `0.6` shadow, `0.7` trunk, `0.8` foliage, `0.95` street, `1.0` atlas facade/prop, `1.14`/`1.18` Rolcar stucco/shutter, `1.3` photo plane, `2.0` instanced vehicles) and reserving `emission >= 9.5` to bypass PBR/fog/tone-mapping for 2D HUD overlays.
- **96-Byte Per-Instance Stream & Static Sentinel**: `[include/car_system.h:CarInstanceData]`, `[src/vulkan_pipeline.c:create_pipeline_and_descriptors]`, `[src/car_system.c:car_system_init]`, and `[shaders/vertex.vert:inInstanceTint]` require vertex binding `1` to carry 96-byte packed instance records (`mat4 model`, `vec4 tint`, `float brake`, `float pad[3]`); static geometry binds `staticDummyBuffer` with `tint.a < 0.5` while instanced vehicles use `tint.a >= 0.5`.
- **Descriptor Bindings & 64-Light UBO Cap**: `[include/lighting_system.h:MAX_GPU_LIGHTS]`, `[include/lighting_system.h:LightingUBO]`, `[src/vulkan_pipeline.c:create_pipeline_and_descriptors]`, `[src/vulkan_texture.c:init_satellite_texture]`, `[shaders/fragment.frag:LightingBlock]`, `[web/shaders.wgsl:Uniforms]`, and `[web/renderer_webgl2.js:FS_GLSL300]` cap dynamic `PointLight` arrays at `64` (`0 <= lightCount <= 64`) and bind `satelliteTex` and `facadeTex` alongside the lighting uniform buffer (`photoTex` at binding `3` on native Vulkan).
- **Aguascalientes Coordinate Frame & DEM Parity**: `[tools/geo_dem.py:geo_to_meters]`, `[include/terrain_dem_data.h:TERRAIN_DEM_ORIGIN_LAT]`, and `[tools/metrics/measure_iso25023.py:check_dem_topography_precision]` map East to `+X` and North to `-Z` around `(21.8807, -102.2965)` (`M_PER_LAT = 111320.0`) over a `64x64` elevation grid (`[21.800, 21.950]` x `[-102.370, -102.245]`, base `1871.0` m), enforcing `< 0.05` m elevation divergence between C and Python across 14 reference coordinates.
- **GLB 2.0 Streaming Sector & Chunk Contract**: `[tools/gltf_writer.py:CHUNK_SIZE]`, `[tools/split_glb_to_sectors.py:MAX_FILE_BYTES]`, `[include/sector_system.h:SectorSystem]`, `[src/sector_system.c:read_sector_glb_attributes]`, and `[web/app.js:parseGLB]` share `128.0` m chunks, `1024.0` m macro-sectors capped at `99` MiB (`MAX_FILE_BYTES`), GLB magic `0x46546C67`, and `BIN` chunk `0x004E4942`.
- **WebAssembly ABI & Dual-Backend Projection Contract**: `[web/app.js:loadStreetVulkanWasm]`, `[web/street_vulkan_core.wat:get_version]`, `[web/main_wasm.c:get_version]`, and `[Makefile.wasm:EXPORTED_FUNCS]` lock 10 exported functions (`get_version() == 1`), fixed 2-page (`131,072`-byte) non-growing linear memory offsets (`0x0004..0x8400`, reserving `0x0000..0x0003` as a NULL guard for C/Emscripten ABI parity), column-major right-handed matrices, and `0 <= z <= w` Gribb/Hartmann frustum culling on `MEM_MVP_WGPU_PTR` for both WebGPU and WebGL2.
- **Single-TU Vendored Headers & Compile-Time Frame Guards**: `[include/cgltf.h:CGLTF_IMPLEMENTATION]` (`[src/vulkan_gltf.c:CGLTF_IMPLEMENTATION]`) and `[include/stb_image.h:STB_IMAGE_IMPLEMENTATION]` (`[src/vulkan_texture.c:STB_IMAGE_IMPLEMENTATION]`) must be defined in exactly one translation unit; `[include/vulkan_types.h:PushConstants]` enforces `sizeof(PushConstants) <= 128` via `_Static_assert` and sizes per-frame Vulkan resources by `MAX_FRAMES_IN_FLIGHT = 2`.
- **RGP1 Binary Road Graph & Vehicle GLB Contract**: `[tools/generate_road_graph.py:main]`, `[include/road_graph.h:RoadNode]`, `[src/road_graph.c:road_graph_load]`, and `[tools/metrics/validate_data_quality.py:check_road_network_bin]` share the `16`-byte header (`RGP1`), `20`-byte node (`<fffiBBBB`), `28`-byte edge (`<IIIIffBBBB`), and `12`-byte point (`<fff`) binary layout for `models/road_network.bin`; `[tools/gltf_writer.py:export_glb_mesh]` and `[tools/gltf_writer.py:export_glb_and_chunks]` share the 52-byte glTF 2.0 vertex schema with `tools/convert_car_models.py` and `src/vulkan_gltf.c`.

## Global Side Effects

- **GPU Device, Windowing, Threading & Logger I/O**: Native execution creates an SDL2 window and Vulkan 1.2 device/pools/swapchain/pipelines/textures (`[src/main.c:main]`, `[src/vulkan.c:vulkan_init]`, `[src/vulkan_memory_pool.c:vulkan_memory_pool_suballocate]`), performs synchronous transfer barriers (`vkQueueWaitIdle` / `vkWaitForFences`) and full device stalls (`vkDeviceWaitIdle`), spawns a POSIX `pthread` sector streaming worker (`[src/sector_system.c:sector_worker_thread]`), and creates/rotates `logs/street_vulkan.{log,jsonl}` under `g_logger_mutex` (`[src/logger.c:logger_init]`). Browser execution acquires WebGPU or WebGL2 contexts, mutates DOM HUD/canvas state, and runs a continuous `requestAnimationFrame` loop (`[web/app.js:main]`).
- **Filesystem Caches & Build Outputs**: Offline pipeline tools and build targets read/write `models/` caches/JSON/GLB/`RGP1` artifacts, `assets/` textures/plates/imagery, `shaders/*.spv`, `web/street_vulkan_core.wasm`, `build/quality_scorecard.json`, and `build/rolcar_supply_chain_report.json` (`[tools/generate_sector.py:generate_sector]`, `[tools/compile_wat_to_wasm.py:compile_wat_to_wasm]`, `[tools/metrics/evaluate_iso25040.py:main]`).
- **Network I/O**: Offline tools perform outbound HTTP/HTTPS requests to OpenStreetMap/Overpass (`[tools/osm_extractor.py:fetch_osm_data]`), AWS Terrarium (`[tools/geo_dem.py:fetch_dem_grid]`), ArcGIS World Imagery (`[tools/download_satellite.py:download_tile]`), Google Street View / KartaView (`[tools/street_fetcher.py:fetch_street_image]`), and Google Gemini APIs (`[tools/gemini_obj_generator.py:call_gemini]`, `[tools/photo_scene_extractor.py:analyze_photo_with_gemini]`); the web client fetches WASM, WGSL, textures, sector manifests, GLBs, and traffic signals over HTTP `GET`/`HEAD` (`[web/app.js:main]`).

## System Verification

- Run: `make test`
- Run: `make asan-test`
- Run: `make all`
- Run: `make metrics`
- Run: `make quality`
- Run: `make -f Makefile.wasm wat`
- Run: `make -f Makefile.wasm check-c`

---

## 🖥️ Demostración en Vivo: Paso a Paso

### Opción A: Demostración Web Inmediata (Sin instalar nada)
Ideal para presentar con proyector o compartir pantalla rápidamente:
1. Abrir en Chrome, Edge o Firefox:  
   👉 **[https://jefazo-isc.github.io/aguascavulkan/](https://jefazo-isc.github.io/aguascavulkan/)**
2. Se cargará el entorno 3D de Aguascalientes (Sector *Rolcar Paseo de la Cruz*) con WebGPU o WebGL2 automático.
3. El motor WebAssembly (`street_vulkan_core.wasm`) toma el control de la cámara, matrices de vista/proyección y cálculo del frustum.
4. **Controles en Web**:
   - `W`, `A`, `S`, `D` o **Flechas**: Desplazamiento horizontal en el espacio 3D.
   - `E` / `Espacio` y `Q` / `C` / `Ctrl`: Elevarse / Descender.
   - **Clic (Pointer Lock) o Arrastre del ratón**: Orientación libre de la cámara (Pitch & Yaw).
   - `Shift`: Sprint 4x / Velocidad aumentada.
   - **Barra de herramientas / atajos**: `R` (Rolcar Paseo de la Cruz), `T` (Hora), `Y` (Pausa/Reanudar avance solar), `F` (Linterna), `K` (Frustum Culling WASM) y `H` (Mostrar/Ocultar HUD).

### Opción B: Ejecución Local Nativa (Linux / Vulkan)
Para mostrar el motor compilado en C nativo con máxima fidelidad gráfica y Vulkan 1.2 directo:

```bash
# 1. Clonar el repositorio
git clone https://github.com/jefazo-isc/aguascavulkan.git
cd aguascavulkan

# 2. Compilar shaders SPIR-V y binario nativo
make clean && make

# 3. Lanzar el simulador
./street_vulkan
```

**Controles en Escritorio**:
- `W`, `A`, `S`, `D`: Movimiento de cámara en el plano horizontal.
- `Espacio` / `Ctrl` o `C`: Subir y bajar verticalmente.
- `Shift`: Sprint.
- `Ratón`: Mirar en 360 grados.
- `TAB`: Capturar / Liberar puntero del ratón.
- `ESC` o `P`: Menú de pausa interactivo con opciones de depuración y testing (dentro de pausa: `F1`–`F4`/`F6` teletransporte POI, `F5` frustum culling, `F8` telemetría ISO 25010, `F11` pantalla completa, `F`/`L` linterna, `T` velocidad de tiempo, `Y` congelar sol, `[` / `]` ajuste ±1 h).

---

## 🧪 Pruebas Automatizadas y Compuerta de Calidad (DevOps)

El proyecto cuenta con un riguroso esquema de aseguramiento de calidad con integración continua en **GitHub Actions**:

| Comando | Descripción | Alcance |
| :--- | :--- | :--- |
| `make test` | Suite de pruebas C y Python | Compila y ejecuta el harness C y descubre pruebas `unittest` de Python; la compilación C requiere las dependencias nativas listadas en la guía de instalación. |
| `make asan-test` | Sanitizadores de memoria dinámica | Valida que no existan memory leaks, buffer overflows ni comportamientos indefinidos (AddressSanitizer + UBSan). |
| `make metrics` | Auditoría SQuaRE / Métricas de Software | Evalúa métricas ISO 25010, 25023, 25012, 27001, 29119, estimaciones COCOMO-II y puntos de función COSMIC/IFPUG. |
| `make quality` | Pipeline completo de calidad local | Ejecuta limpieza, build, pruebas unitarias, sanitizadores y generación del reporte de calidad. |
| `make e2e` | Prueba E2E del cliente web | Sirve el repo, abre Chrome headless (WebGL2 por SwiftShader, sin GPU) y verifica sector 0,0, mapa base, tráfico y teleports; deja capturas y `report.json` en `e2e-artifacts/`. Requiere Node ≥ 22 (o `node --experimental-websocket` en Node 20). |

### Pipeline CI/CD

```text
push / pull request a main
        │
        ▼
┌──────────────────────────── CI: StreetVulkan CI (DevOps & Quality Gate) ───────────────────────────┐
│ build-and-test: build web + nativo, pruebas C/Python, ASan/UBSan, WAT→WASM reproducible, ISO   │
│        │                                                                                          │
│        ▼                                                                                          │
│ e2e-smoke: Chrome headless + WebGL2 → sector 0,0 sin escena de respaldo, mapa base, tráfico,      │
│            teleports Primer/Tercer Anillo → artefacto con capturas + report.json                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
        │ solo si CI terminó en verde (workflow_run, conclusion == success)
        ▼
CD: StreetVulkan WASM & WebGPU Pages → empaqueta el bundle web del mismo commit y despliega a GitHub Pages
```

- ✅ **StreetVulkan CI (DevOps & Quality Gate)**: corre en cada push y pull request; el job `e2e-smoke` depende de `build-and-test` y publica las capturas como artefacto descargable en la pestaña *Actions*.
- 🚀 **StreetVulkan WASM & WebGPU Pages**: despliegue continuo; se dispara al terminar el CI de `main` y solo publica commits con CI exitoso (también puede lanzarse a mano con *Run workflow*).

---

## 📂 Organización del Repositorio

```text
aguascavulkan/
├── src/                     # Código fuente del motor nativo en C11 (main, vulkan, sector, logger, car, traffic)
├── include/                 # Cabeceras (.h) e interfaces modulares del sistema
├── shaders/                 # Shaders GLSL 450 (vertex.vert, fragment.frag) compilados a SPIR-V
├── web/                     # Cliente WebAssembly & WebGPU
│   ├── street_vulkan_core.wat   # Kernel matemático en Ensamblador WebAssembly (cámara, culling, semáforos)
│   ├── street_vulkan_core.wasm  # Binario WebAssembly ensamblado
│   ├── main_wasm.c              # Puerto C11/Emscripten alternativo con el mismo ABI WASM
│   ├── package.json             # Manifiesto ES module (`streetvulkan-web`)
│   ├── renderer_webgpu.js       # Pipeline gráfico en WebGPU nativo
│   ├── renderer_webgl2.js       # Fallback universal en WebGL2
│   ├── shaders.wgsl             # Shaders en WebGPU Shading Language
│   ├── app.js                   # Orquestador del cliente web
│   └── index.html               # Interfaz de usuario con HUD táctil y controles
├── tools/                   # Pipeline geoespacial y utilerías
│   ├── compile_wat_to_wasm.py   # Ensamblador propio WAT -> WASM
│   ├── generate_sector.py       # Generador procedural de macro-sectores urbanos
│   ├── rolcar_vector.py         # Inyector de sedes Rolcar vectoriales
│   ├── street_wiring.py         # Generador de postes y cableado CFE
│   ├── geo_dem.py               # Elevación DEM satelital (AWS Terrarium) y corrección topográfica fluvial/fallas
│   └── metrics/                 # Scripts de auditoría de estándares ISO
├── assets/                  # Texturas base, placas viales, Street View y atlas (`texture_atlas_16x16.png`)
├── models/                  # Datos del mundo 3D (GLB de sectores, postes, Rolcar, grafo vial .bin)
├── tests/                   # Batería de pruebas automatizadas (C, Python, WASM)
├── docs/                    # Suite documental formal de ingeniería de software
├── .github/workflows/       # Pipelines de CI/CD para GitHub Actions y GitHub Pages
├── index.html               # Redirección raíz hacia `web/index.html` para GitHub Pages
├── Makefile                 # Compilación nativa C11/SPIR-V, pruebas (`test`/`asan-test`) y métricas
├── Makefile.wasm            # Targets `wat`, `emcc` y `check-c` del núcleo WebAssembly
├── CREDITS.md               # Atribuciones de fuentes y librerías de terceros
├── Modelfile                # Configuración de modelo local para utilerías auxiliares
└── .nojekyll                # Desactiva procesamiento Jekyll en GitHub Pages
```

---

## 📚 Documentación de Metodologías y Normas ISO (Para Evaluaciones Académicas)

Para sustentar la metodología de ingeniería de software y estándares de calidad ante profesores o evaluadores, el proyecto incluye una suite documental completa en el directorio `docs/`:

La guía operativa recomendada para organizar cambios futuros es **[docs/GUIA_METODOLOGIA_PRACTICA.md](docs/GUIA_METODOLOGIA_PRACTICA.md)**. Distingue la práctica de trabajo propuesta de los informes históricos y explica cómo interpretar las pruebas, métricas y limitaciones.

1. **[docs/OPENUP_TSP.md](docs/OPENUP_TSP.md)**: Proceso Unificado Abierto (OpenUP) cruzado con Team Software Process (TSP). Documento de Visión, Stakeholders, roles de equipo, métricas de valor ganado (EV/SPI/CPI) y bitácoras de tiempo/defectos PSP1.
2. **[docs/SCRUM_XP.md](docs/SCRUM_XP.md)**: Marco ágil Scrum combinado con Extreme Programming (XP). Historias de usuario (`HU-01` a `HU-12`), Sprints 1 a 4, desarrollo guiado por pruebas (TDD), integración continua y actas de retrospectiva.
3. **[docs/ESTIMACION_Y_TRAZABILIDAD.md](docs/ESTIMACION_Y_TRAZABILIDAD.md)**: Estimación de esfuerzo mediante **COCOMO-II**, puntos de función **IFPUG** y **COSMIC** (ISO/IEC 19761), junto con la matriz de trazabilidad bidireccional Requisitos $\to$ Código $\to$ Pruebas.
4. **[docs/ISO_IEC_25010.md](docs/ISO_IEC_25010.md)** y **[docs/ISO_IEC_25023.md](docs/ISO_IEC_25023.md)**: Modelo de calidad del producto de software y reporte cuantitativo de métricas de calidad.
5. **[docs/ISO_IEC_25012_25024.md](docs/ISO_IEC_25012_25024.md)**: Modelo y evaluación cuantitativa de calidad de datos para los datasets geográficos.
6. **[docs/ISO_IEC_27001_27034.md](docs/ISO_IEC_27001_27034.md)**: Seguridad de la información y auditoría de seguridad en el ciclo de vida del software.
7. **[docs/ISO_IEC_29119.md](docs/ISO_IEC_29119.md)**: Estándar internacional para los procesos y diseño de pruebas de software.
8. **[docs/ISO_9001_31000.md](docs/ISO_9001_31000.md)**: Gestión de la calidad y matriz cuantitativa de administración de riesgos del proyecto.
9. **[docs/ROADMAP_FUTURO.md](docs/ROADMAP_FUTURO.md)**: Hoja de ruta para futuras expansiones (simulación de peatones en GPU, sombreado dinámico y monumentos históricos generados con Gemini AI).
10. **[docs/GUIA_PRESENTACION_EQUIPO.md](docs/GUIA_PRESENTACION_EQUIPO.md)**: Guía de presentación del proyecto y demostración en vivo para exposiciones del equipo.

---

## 👥 Guion Rápido Sugerido para una Presentación de 5 Minutos

1. **Minuto 1 - Introducción & Problema**:
   - *«Presentamos StreetVulkan, un gemelo digital 3D de Aguascalientes diseñado con arquitectura de ultra-bajo nivel en Vulkan y C11 para resolver la visualización masiva de datos urbanos a 60 FPS.»*
2. **Minuto 2 - Tecnologías y Retos Técnicos**:
   - *«En lugar de usar motores pesados comerciales, construimos el pipeline gráfico desde cero: Vulkan 1.2 nativo con GLSL/SPIR-V, streaming de sectores por celdas, topografía satelital real y simulación de infraestructura (postes CFE, semáforos, sucursales Rolcar).»*
3. **Minuto 3 - Innovación Web (WASM en Ensamblador + WebGPU)**:
   - *«Para llevarlo a cualquier persona sin instalar nada, tradujimos el núcleo matemático a Ensamblador WebAssembly puro (.wat), con matrices, cámara y frustum culling en código máquina, renderizado con WebGPU directo en el navegador.»*
4. **Minuto 4 - Demostración en Vivo**:
   - Mostrar la URL de GitHub Pages en pantalla completa navegando por la ciudad de Aguascalientes y mostrando la consola con el HUD de diagnósticos WASM.
5. **Minuto 5 - Calidad de Software e Ingeniería**:
   - *«El proyecto no es solo código gráfico: está respaldado por 44 pruebas automatizadas (15 funciones de prueba en C y 29 casos unittest en Python/WASM), compuertas de calidad CI/CD en GitHub Actions y cumplimiento con la familia de normas ISO/IEC 25000 (SQuaRE), ISO 27001 y metodologías OpenUP/TSP/Scrum.»*
