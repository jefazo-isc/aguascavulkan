# StreetVulkan 🏙️

Motor de renderizado 3D y simulación urbana en C11/Linux usando **Vulkan API 1.2** y **SDL2**, con cliente web en el navegador impulsado por **WebAssembly Assembly (`.wat` $\to$ `.wasm`)** + **WebGPU (Vulkan)** / **WebGL2**. Generación procedural de ciudad para Aguascalientes (calles, banquetas elevadas 3D con guarniciones rojas/amarillas, `552` semáforos dinámicos, simulación cinemática de `200` vehículos instanciados en GPU, `325,511` edificios clasificados, `27` sucursales vectoriales **Rolcar**, `1,215` postes y `1,180` tramos de cableado eléctrico CFE, iluminación PBR Cook-Torrance, streaming por `401` macro-sectores modulares `< 99 MB`, logger concurrente rotativo y ciclo día/noche) impulsado por scripts geoespaciales en Python.

---

## 🌐 Cliente Web en Vivo (WebAssembly + WebGPU / WebGL2)

- **GitHub Pages**: `https://jefazo-isc.github.io/aguascavulkan/` (orquestado mediante [wasm-pages.yml](.github/workflows/wasm-pages.yml) y entrada raíz [index.html](index.html)).
- **Ejecución local en navegador**:
  ```bash
  python3 -m http.server 8080
  # Abrir http://localhost:8080/web/
  ```
- **Kernel en Ensamblador WebAssembly**: [street_vulkan_core.wat](web/street_vulkan_core.wat) se ensambla sin dependencias externas a [street_vulkan_core.wasm](web/street_vulkan_core.wasm) mediante [compile_wat_to_wasm.py](tools/compile_wat_to_wasm.py), ejecutando cámara libre, matrices `mat4`, extracción de frustum Gribb/Hartmann, *culling* AABB por lotes y ciclo determinístico de semáforos directamente en WASM, mientras [renderer_webgpu.js](web/renderer_webgpu.js) ([shaders.wgsl](web/shaders.wgsl)) y [renderer_webgl2.js](web/renderer_webgl2.js) renderizan `sector_0_0.glb` (Rolcar Paseo de la Cruz) en el cliente. También incluye port C/Emscripten en [main_wasm.c](web/main_wasm.c) y [Makefile.wasm](Makefile.wasm).

---

## 🚀 Requisitos Previos

- **Entorno Linux/POSIX** con **GCC** (soporte C11, POSIX `mmap`/`pthread`/`dirent`).
- **Vulkan SDK** (`libvulkan-dev` / `vulkan-tools`).
- **glslangValidator** (`glslang-tools`, para compilar GLSL 450 a SPIR-V).
- **SDL2** (`libsdl2-dev`).
- **Python 3** con `Pillow` y `numpy` (para los scripts en `tools/`, ej. [generate_sector.py](tools/generate_sector.py)).

En Debian/Ubuntu/Devuan:
```bash
sudo apt update
sudo apt install build-essential libsdl2-dev libvulkan-dev vulkan-tools glslang-tools python3-pip
pip install pillow numpy
```

---

## 🛠️ Compilación, Ejecución y Pruebas

Compilar el motor y shaders SPIR-V:
```bash
make clean && make
```

Ejecutar el motor:
```bash
./street_vulkan
```

Controles principales:
- **WASD / Espacio / Ctrl / C**: Movimiento de la cámara libre (`Shift` para sprint).
- **Ratón**: Orientación (*Pitch & Yaw*).
- **TAB**: Capturar / Liberar ratón.
- **ESC / P**: Pausar y abrir menú interactivo de testing ([pause_menu.h](include/pause_menu.h)).

### Pruebas Automatizadas XP y Auditoría SQuaRE

- **Pruebas unitarias en C y Python:**
  ```bash
  make test
  ```
- **Sanitizadores de memoria y comportamiento indefinido (ASan + UBSan):**
  ```bash
  make asan-test
  ```
- **Auditoría cuantitativa ISO/IEC 25040 (COCOMO-II, IFPUG/COSMIC, 25012/25024, 25023, mantenibilidad y trazabilidad):**
  ```bash
  make metrics
  ```
- **Compuerta completa de calidad local (`clean all test asan-test metrics`):**
  ```bash
  make quality
  ```

---

## 🎨 Generación Procedural de Texturas y Mallas 3D

Para generar el atlas de texturas pixel-art (`512x512` con casillas `64x64`):
```bash
python3 tools/generate_texture_atlas.py
```

Para procesar la ciudad 3D y sectores urbanos modulares:
```bash
python3 tools/generate_sector.py
python3 tools/split_glb_to_sectors.py
```

---

## 📂 Estructura del Proyecto

- `src/`: Código fuente en C ([main.c](src/main.c), [vulkan.c](src/vulkan.c), [logger.c](src/logger.c), [sector_system.c](src/sector_system.c), [car_system.c](src/car_system.c), [traffic_system.c](src/traffic_system.c), [road_graph.c](src/road_graph.c), [vulkan_memory_pool.c](src/vulkan_memory_pool.c), [vulkan_gltf.c](src/vulkan_gltf.c), etc.).
- `include/`: Archivos de cabecera (`.h`) e interfaces de subsistemas (ej. [vulkan_types.h](include/vulkan_types.h), [logger.h](include/logger.h), [terrain_dem_data.h](include/terrain_dem_data.h)).
- `shaders/`: Código fuente GLSL 450 ([vertex.vert](shaders/vertex.vert), [fragment.frag](shaders/fragment.frag)).
- `web/`: Cliente navegador WebAssembly + WebGPU/WebGL2 ([index.html](web/index.html), [app.js](web/app.js), [street_vulkan_core.wat](web/street_vulkan_core.wat), [shaders.wgsl](web/shaders.wgsl), [main_wasm.c](web/main_wasm.c)).
- `tools/`: Generadores procedurales geoespaciales ([generate_sector.py](tools/generate_sector.py), [rolcar_vector.py](tools/rolcar_vector.py), [street_wiring.py](tools/street_wiring.py), [compile_wat_to_wasm.py](tools/compile_wat_to_wasm.py), [geo_dem.py](tools/geo_dem.py)) y scripts de métricas en `tools/metrics/`.
- `tests/`: Pruebas unitarias XP ([test_c_modules.c](tests/test_c_modules.c), [test_python_tools.py](tests/test_python_tools.py), [test_wasm_port.py](tests/test_wasm_port.py)).
- `assets/`: Recursos gráficos, atlas de texturas ([texture_atlas_16x16.png](assets/texture_atlas_16x16.png)).
- `models/`: Mallas glTF/GLB (`sector_0_0.glb`), manifiestos de sectores ([sectors.json](models/sectors.json)), catálogo Rolcar ([rolcar_aguascalientes.json](models/rolcar_aguascalientes.json)), postes CFE ([utility_poles_rolcar.json](models/utility_poles_rolcar.json)), grafo vial binario ([road_network.bin](models/road_network.bin)) y DEMs.
- [ci.yml](.github/workflows/ci.yml) y [wasm-pages.yml](.github/workflows/wasm-pages.yml): Integración continua y despliegue a GitHub Pages.
- [Makefile](Makefile) y [Makefile.wasm](Makefile.wasm): Compilación nativa Vulkan/SDL2, pruebas, sanitización, métricas y compilación WebAssembly.

---

## 📋 Suite Documental de Metodologías y Estándares de Calidad

La ingeniería del proyecto está documentada bajo la familia **ISO/IEC SQuaRE** y las metodologías integradas del curso **Metodologías de Desarrollo de Sistemas (UAA Clave 24967)**:

### Metodologías de Proceso (Rigor y Agilidad)
- **[Proceso Integrado OpenUP-TSP y Formatos PSP](docs/OPENUP_TSP.md)**: Fases OpenUP × 5 flujos de trabajo, Documento de Visión, Stakeholders, arquitectura C/Vulkan + Python, estructura TSP (Launch, 5 roles, métricas EV/SPI/CPI/DRE) y bitácoras reales PSP1 de tiempo y defectos (Parte I — 30%).
- **[Proceso Integrado SCRUM-XP](docs/SCRUM_XP.md)**: Roles Scrum, Product Backlog (`HU-01`..`HU-12`), Sprints 1–4 mapeados al repositorio, prácticas XP (`make test`, `make asan-test`, `make quality`) y actas de Revisión/Retrospectiva con deuda técnica documentada (Parte II — 30%).
- **[Estimación de Tamaño/Esfuerzo y Trazabilidad](docs/ESTIMACION_Y_TRAZABILIDAD.md)**: Mediciones exactas de SLOC, IFPUG UFP, COSMIC CFP (ISO/IEC 19761), modelo COCOMO-II Post-Architecture y matriz completa de trazabilidad Requisitos/HU $\to$ Arquitectura $\to$ Módulos $\to$ Pruebas $\to$ ISO/IEC.

### Estándares de Calidad ISO/IEC SQuaRE, Seguridad, Pruebas y Hoja de Ruta
- **[ISO/IEC 25010](docs/ISO_IEC_25010.md)**: Modelo de calidad del producto de software (8 características, alcance de portabilidad Linux/POSIX y estado honesto con deuda abierta).
- **[ISO/IEC 25023](docs/ISO_IEC_25023.md)**: Medición cuantitativa de calidad del producto (catálogo de 25 métricas y scorecard real generado tras las auditorías).
- **[ISO/IEC 25012 e ISO/IEC 25024](docs/ISO_IEC_25012_25024.md)**: Modelo y auditoría cuantitativa de calidad de datos sobre los 8 conjuntos de datos reales del proyecto.
- **[ISO/IEC 27001 e ISO/IEC 27034](docs/ISO_IEC_27001_27034.md)**: Seguridad de la información y auditoría de código/secretos (`tools/metrics/audit_iso27001_27034.py`).
- **[ISO/IEC/IEEE 29119](docs/ISO_IEC_29119.md)**: Proceso y auditoría de pruebas automatizadas C/Python/WASM (`tools/metrics/audit_iso29119.py`).
- **[ISO 9001 e ISO 31000](docs/ISO_9001_31000.md)**: Sistema de Gestión de Calidad y registro cuantitativo de riesgos (`tools/metrics/audit_iso9001_31000.py`).
- **[Roadmap de Funcionalidades Futuras](docs/ROADMAP_FUTURO.md)**: Plan técnico para integración visual GPU de peatones (`ped_system`), pipeline 2D/Font Atlas, shadow mapping y monumentos con Gemini AI.
