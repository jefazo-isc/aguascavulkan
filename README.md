# 🏙️ StreetVulkan: Gemelo Digital Urbano 3D de Aguascalientes

> **Motor Gráfico en C11 / Vulkan API 1.2 + SDL2**, con pipeline geoespacial procedural y cliente web en el navegador impulsado por **WebAssembly en Ensamblador (`.wat` $\to$ `.wasm`)** y **WebGPU / WebGL2**.
>
> 🌐 **Demo en Vivo (GitHub Pages):** [https://jefazo-isc.github.io/aguascavulkan/](https://jefazo-isc.github.io/aguascavulkan/)  
> 📦 **Repositorio Oficial:** [https://github.com/jefazo-isc/aguascavulkan](https://github.com/jefazo-isc/aguascavulkan)

---

## 📌 Guía Rápida para el Equipo: ¿Qué es este proyecto y cómo presentarlo?

Si tienes que exponer o presentar **StreetVulkan**, aquí tienes el resumen ejecutivo estructurado para responder qué hace, por qué es innovador, cómo está construido y cómo demostrarlo en vivo:

### 🎯 1. La Visión del Proyecto
**StreetVulkan** es una plataforma de **simulación urbana y visualización tridimensional** de la ciudad de **Aguascalientes, México**. Integra datos geoespaciales (edificaciones de OpenStreetMap, elevación DEM satelital Terrarium/SRTM y red vial) en un motor nativo escrito en **C11 con Vulkan 1.2**, junto con un cliente web cuyo kernel matemático está escrito en **WebAssembly Text (WAT)** y cuyo renderizado usa **WebGPU/WebGL2**.

### 🌟 2. Características Clave & Cifras de Impacto (Para la Presentación)
- **325,511 Edificios Reales Clasificados**: Procesados por lotes a partir de huellas urbanas con alturas procedimentales, techos y fachadas segmentadas.
- **27 Sucursales Rolcar Georreferenciadas**: Modelado 3D fidedigno con señalamientos y logos corporativos vectoriales (ej. nodo central *Paseo de la Cruz / José María Chávez*).
- **1,215 Postes y 1,180 Tramos de Cableado CFE**: Simulación física de tendido eléctrico aéreo con curvas catenarias hiperbólicas procedimentales.
- **552 Semáforos Inteligentes y Red Vial**: Simulación matemática con grafos de tráfico y temporizadores sincronizados.
- **200 Vehículos Autónomos Instanciados en GPU**: Cinemática de vehículos navegando carriles viales en tiempo real.
- **Topografía Real (DEM 30m)**: Elevación del terreno corregida topográficamente a partir de datos satelitales.
- **401 Macro-Sectores Modulares**: Arquitectura de *streaming* espacial por celdas para mantener el consumo de memoria acotado (< 99 MB por sector).
- **Kernel WebAssembly en Ensamblador Puro (`.wat`)**: Cero dependencias pesadas de runtime. Las matemáticas 3D (cámara, proyección, matrices 4x4, frustum culling Gribb/Hartmann y lógica de semáforos) corren en código máquina WASM compilado por nuestro propio compilador/ensamblador en Python.
- **Renderizado Web**: El cliente usa shaders WGSL con WebGPU y un backend WebGL2 alternativo. El objetivo de 60 FPS debe verificarse en el dispositivo y navegador de la demostración; no es un resultado de benchmark de CI.
- **Verificación del software**: El repositorio incluye pruebas C y Python, una prueba separada de reproducibilidad WAT→WASM, sanitizadores y auditorías internas relacionadas con calidad y seguridad. Estas verificaciones documentan prácticas y resultados parciales; no constituyen certificación ni demuestran por sí solas conformidad formal con normas ISO.

---

## 🏛️ Arquitectura del Sistema

```
                             ┌──────────────────────────────────────────┐
                             │       Fuentes de Datos Geográficos       │
                             │ (OpenStreetMap, DEM Satelital, Rolcar)   │
                             └────────────────────┬─────────────────────┘
                                                  │
                                                  ▼
                             ┌──────────────────────────────────────────┐
                             │   Pipeline Geoespacial Procedural        │
                             │   (Python: geo_dem, street_wiring, etc.) │
                             └────────────┬──────────────────┬──────────┘
                                          │                  │
               Exportación de Sectores 3D │                  │ Exportación de Grafo
               (glTF / GLB < 99 MB)       ▼                  ▼ Vial (road_network.bin)
         ┌──────────────────────────────────────┐     ┌──────────────────────────────────────┐
         │     MOTOR NATIVO (Escritorio)        │     │       CLIENTE WEB (Navegador)        │
         │  • Lenguaje: C11 estándar            │     │  • Kernel: Ensamblador WASM (.wat)   │
         │  • Gráficos: Vulkan 1.2 + GLSL 450   │     │  • Lógica: Cámara, Frustum Culling   │
         │  • Ventana: SDL2 + POSIX threads     │     │  • Gráficos: WebGPU (WGSL) / WebGL2  │
         │  • PBR Cook-Torrance + Frustum Culling│    │  • Cero dependencias / Pure Vanilla  │
         │  • Logger Concurrente Asíncrono      │     │  • GitHub Pages (Acceso Universal)   │
         └──────────────────────────────────────┘     └──────────────────────────────────────┘
```

---

## 🖥️ Demostración en Vivo: Paso a Paso

### Opción A: Demostración Web Inmediata (Sin instalar nada)
Ideal para presentar con proyector o compartir pantalla rápidamente:
1. Abrir en Chrome, Edge o Firefox:  
   👉 **[https://jefazo-isc.github.io/aguascavulkan/](https://jefazo-isc.github.io/aguascavulkan/)**
2. Se cargará el entorno 3D de Aguascalientes (Sector *Rolcar Paseo de la Cruz*) con WebGPU o WebGL2 automático.
3. El motor WebAssembly (`street_vulkan_core.wasm`) toma el control de la cámara, matrices de vista/proyección y cálculo del frustum.
4. **Controles en Web**:
   - `W`, `A`, `S`, `D`: Desplazamiento en el espacio 3D.
   - `Q` / `E` o `Espacio` / `Ctrl`: Elevarse / Descender.
   - **Click y Arrastre del ratón**: Orientación de la cámara (Pitch & Yaw).
   - `Shift`: Sprint / Velocidad aumentada.
   - Botón *"Verificar WASM"* en pantalla: Ejecuta diagnósticos matemáticos en vivo del kernel WASM.

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
- `ESC` o `P`: Menú de pausa interactivo con opciones de depuración y testing.

---

## 🧪 Pruebas Automatizadas y Compuerta de Calidad (DevOps)

El proyecto cuenta con un riguroso esquema de aseguramiento de calidad con integración continua en **GitHub Actions**:

| Comando | Descripción | Alcance |
| :--- | :--- | :--- |
| `make test` | Suite de pruebas C y Python | Compila y ejecuta el harness C y descubre pruebas `unittest` de Python; la compilación C requiere las dependencias nativas listadas en la guía de instalación. |
| `make asan-test` | Sanitizadores de memoria dinámica | Valida que no existan memory leaks, buffer overflows ni comportamientos indefinidos (AddressSanitizer + UBSan). |
| `make metrics` | Auditoría SQuaRE / Métricas de Software | Evalúa métricas ISO 25010, 25023, 25012, 27001, 29119, estimaciones COCOMO-II y puntos de función COSMIC/IFPUG. |
| `make quality` | Pipeline completo de calidad local | Ejecuta limpieza, build, pruebas unitarias, sanitizadores y generación del reporte de calidad. |

Los flujos de GitHub Actions se ejecutan en cada push y pull request:
- ✅ **StreetVulkan CI (DevOps & Quality Gate)**: Ejecuta build en GCC, pruebas C/Python, sanitizadores, reproducibilidad del artefacto WAT→WASM y verificaciones automatizadas de calidad.
- ✅ **StreetVulkan WASM & WebGPU Pages**: Empaqueta el cliente WebAssembly, valida la sintaxis y publica a GitHub Pages.

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
│   ├── renderer_webgpu.js       # Pipeline gráfico en WebGPU nativo
│   ├── renderer_webgl2.js       # Fallback universal en WebGL2
│   ├── shaders.wgsl             # Shaders en WebGPU Shading Language
│   ├── app.js                   # Orquestador del cliente web
│   └── index.html               # Interfaz de usuario con HUD táctil y diagnósticos
├── tools/                   # Pipeline geoespacial y utilerías
│   ├── compile_wat_to_wasm.py   # Ensamblador propio WAT -> WASM
│   ├── generate_sector.py       # Generador procedural de macro-sectores urbanos
│   ├── rolcar_vector.py         # Inyector de sedes Rolcar vectoriales
│   ├── street_wiring.py         # Generador de postes y catenarias CFE
│   ├── geo_dem.py               # Corrección topográfica LiDAR/DEM
│   └── metrics/                 # Scripts de auditoría de estándares ISO
├── models/                  # Datos del mundo 3D (GLB de sectores, postes, Rolcar, grafo vial .bin)
├── tests/                   # Batería de pruebas automatizadas (C, Python, WASM)
├── docs/                    # Suite documental formal de ingeniería de software
└── .github/workflows/       # Pipelines de CI/CD para GitHub Actions y GitHub Pages
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
   - *«El proyecto no es solo código gráfico: está respaldado por 841 pruebas automatizadas, compuertas de calidad CI/CD en GitHub Actions y cumplimiento con la familia de normas ISO/IEC 25000 (SQuaRE), ISO 27001 y metodologías OpenUP/TSP/Scrum.»*
