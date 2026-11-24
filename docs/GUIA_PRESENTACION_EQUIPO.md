# 🎤 Guía Maestra de Presentación: StreetVulkan 🏙️
> **Documento de Contexto y Apoyo para Exposición de Equipo**  
> **Proyecto:** StreetVulkan — Gemelo Digital 3D Urbano de Aguascalientes  
> **Tecnologías:** C11 / Vulkan 1.2 / WebAssembly (WAT) / WebGPU / WebGL2 / Python / ISO SQuaRE  
> **Demo en Vivo:** [https://jefazo-isc.github.io/aguascavulkan/](https://jefazo-isc.github.io/aguascavulkan/)  
> **Repositorio:** [https://github.com/jefazo-isc/aguascavulkan](https://github.com/jefazo-isc/aguascavulkan)

---

## 🧭 1. Resumen Ejecutivo (El "Elevator Pitch")

> *"StreetVulkan es un gemelo digital 3D de la ciudad de Aguascalientes de ultra-alto rendimiento. En vez de utilizar motores de videojuegos comerciales pesados (Unity o Unreal Engine), el motor gráfico fue programado desde cero en **C11 nativo con Vulkan API 1.2**. Además, el núcleo matemático (cámara, proyección, matrices 4x4, frustum culling y lógica de semáforos) fue codificado en **Ensamblador puro para WebAssembly (`.wat`)**, permitiendo que cualquier persona lo ejecute en su navegador web a 60 FPS mediante **WebGPU (Vulkan en la Web)** sin instalar nada."*

---

## 📊 2. Cifras y Datos Clave para Sorprender a la Audiencia

Úsalas en diapositivas con números grandes:

| Métrica | Cifra | Explicación Técnica |
| :--- | :--- | :--- |
| **Edificios 3D** | **325,511** | Extraídos de datos geoespaciales reales y clasificados por altura y uso de suelo. |
| **Sucursales Rolcar** | **27** | Modelado 3D fidedigno con señalética vectorial corporativa en Aguascalientes. |
| **Infraestructura CFE** | **1,215 postes / 1,180 cables** | Postes geolocalizados y cables generados con curvas catenarias físicas procedimentales. |
| **Semáforos Inteligentes** | **552** | Controladores con lógica de ciclos semafóricos sincronizados con la red vial. |
| **Tráfico en Tiempo Real** | **200 vehículos** | Simulación cinemática instanciada por GPU siguiendo grafos viales reales. |
| **Topografía Real** | **DEM 30 metros** | Corrección de elevación topográfica a partir de mallas de satélite/LiDAR. |
| **Macro-Sectores** | **401 sectores** | Celdas modulares con límites `< 99 MB` para carga dinámica y compatibilidad con GitHub. |
| **Pruebas Automatizadas** | **841 pruebas (0 fallos)** | 815 en C11 + 26 en Python/WASM con AddressSanitizer y UBSan activos. |
| **Normas ISO Cumplidas** | **8 estándares** | ISO/IEC 25010, 25023, 25012, 25024, 27001, 27034, 29119, 9001/31000. |

---

## 🏗️ 3. Arquitectura del Proyecto (Explicación por Capas)

Si les piden explicar cómo funciona el sistema, divídanlo en 4 capas:

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. CAPA DE DATOS GEOESPACIALES & PROCEDURALES (Python)                 │
│    • Ingesta de OpenStreetMap (huellas de edificios, calles, carriles)  │
│    • Malla de elevación topográfica satelital (DEM)                    │
│    • Inyección de 27 sucursales Rolcar y tendido eléctrico CFE         │
│    • Generador de mallas glTF/GLB y grafo vial binario (.bin)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
┌───────────────────────────────────┐ ┌───────────────────────────────────┐
│ 2. MOTOR NATIVO ESCRITORIO (C11)  │ │ 3. CLIENTE WEB UNIVERSAL          │
│ • API: Vulkan 1.2 + GLSL 450      │ │ • Kernel: Ensamblador WAT -> WASM │
│ • Ventana & Eventos: SDL2         │ │ • Gráficos: WebGPU (WGSL) / WebGL2│
│ • Pipeline PBR Cook-Torrance      │ │ • Cero dependencias de framework  │
│ • Frustum Culling AABB SIMD       │ │ • Desplegado en GitHub Pages      │
│ • Logger Concurrente Asíncrono    │ │ • Diagnósticos WASM en el cliente │
└───────────────────────────────────┘ └───────────────────────────────────┘
                                    ▲
                                    │
┌───────────────────────────────────┴───────────────────────────────────┐
│ 4. INGENIERÍA DE SOFTWARE & DEVOPS (CI/CD + SQuaRE)                   │
│ • 841 Pruebas Unitarias + Sanitizadores (ASan / UBSan)                │
│ • GitHub Actions: Workflows de compilación, pruebas y despliegue      │
│ • Métricas de software: COCOMO-II, IFPUG, COSMIC CFP                  │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 💡 4. Los Dos Puntos Más Innovadores (Hagan Énfasis en Esto)

### A. El Motor WebAssembly programado en Ensamblador (`.wat`)
- **¿Qué responder si preguntan cómo compilaron a WebAssembly?**:  
  *"No usamos Emscripten ni librerías pesadas para el runtime web. Escribimos directamente el código en **WebAssembly Text Format (`street_vulkan_core.wat`)** y creamos nuestro propio compilador/ensamblador en Python (`tools/compile_wat_to_wasm.py`) que genera el binario `.wasm` puro de 3.7 KB. Este binario calcula la matriz de vista, la proyección en perspectiva, el frustum culling plano a plano y el estado de los semáforos directamente en la memoria lineal del navegador a velocidad de código máquina."*

### B. Renderizado WebGPU (La evolución de Vulkan en la Web)
- **¿Por qué WebGPU?**:  
  *"WebGPU es el estándar web moderno diseñado sobre los conceptos de Vulkan, DirectX 12 y Metal. Usamos shaders en **WGSL** que aprovechan directamente la GPU del dispositivo del usuario con capacidades de cómputo y renderizado que superan ampliamente al tradicional WebGL."*

---

## 🎬 5. Guion Sugerido de la Presentación (5 a 7 Minutos)

### Diapositiva 1: Portada e Introducción (1 minuto)
- **Ponente 1**:  
  *"Buenos días / tardes profesor(a) y compañeros. El día de hoy les presentamos **StreetVulkan**, un proyecto de simulación urbana y gemelo digital tridimensional de la ciudad de Aguascalientes. El reto que abordamos fue: ¿Cómo podemos renderizar cientos de miles de entidades urbanas reales con máxima eficiencia computacional, tanto en una computadora de escritorio con Vulkan como en cualquier navegador web moderno sin necesidad de instalar programas?"*

### Diapositiva 2: Datos y Pipeline Geoespacial (1.5 minutos)
- **Ponente 2**:  
  *"Para construir el gemelo digital utilizamos datos reales: más de 325 mil edificios de Aguascalientes, topografía DEM de elevación, una red vial completa y las 27 sucursales de Rolcar en el estado. Desarrollamos herramientas en Python que procesan estos datos y calculan proceduralmente las alturas de edificios, los semáforos inteligentes y el tendido de cables de CFE con física de catenarias hiperbólicas, organizando la ciudad en 401 sectores modulares para carga eficiente."*

### Diapositiva 3: Arquitectura Gráfica C11 / Vulkan & WASM (1.5 minutos)
- **Ponente 3**:  
  *"En la parte de ingeniería de bajo nivel, el proyecto cuenta con dos motores:  
  1. **Motor Nativo**: Desarrollado en **C11 puro y Vulkan 1.2**, con iluminación basada en física (PBR), shaders GLSL SPIR-V y memoria optimizada con *memory pooling*.  
  2. **Cliente Web Universal**: Trasladamos el núcleo matemático a **Ensamblador WebAssembly (`.wat`)** ensamblado sin librerías externas, y lo conectamos a **WebGPU** con shaders WGSL para correr a 60 cuadros por segundo en cualquier navegador."*

### Diapositiva 4: Demostración en Vivo (1.5 minutos)
- **Ponente 1 o 2 (Compartir pantalla o proyector)**:  
  *(Abrir la URL: https://jefazo-isc.github.io/aguascavulkan/)*  
  *"Aquí pueden ver la aplicación en vivo en GitHub Pages. Estamos viendo el sector de **Paseo de la Cruz y José María Chávez**. Noten cómo el modelo 3D carga con fluidez. Con las teclas W, A, S, D nos desplazamos por las calles, el ratón nos permite orientar la cámara, y si damos clic en 'Verificar WASM' podemos comprobar que los cálculos matemáticos de matrices y frustum culling los está resolviendo el kernel WebAssembly en tiempo real."*

### Diapositiva 5: Calidad de Software, Metodologías y Conclusión (1 minuto)
- **Ponente 3**:  
  *"Finalmente, el desarrollo no fue improvisado. Cumplimos con un marco riguroso de ingeniería de software:  
  - Metodologías **OpenUP/TSP** y **Scrum/XP**.  
  - Batería de **841 pruebas automatizadas** que corren en cada commit mediante GitHub Actions.  
  - Auditoría de calidad bajo la familia **ISO/IEC 25000 (SQuaRE)**, seguridad ISO 27001 y pruebas ISO 29119.  
  El código está abierto y disponible en nuestro repositorio de GitHub. Muchas gracias, quedamos abiertos a sus preguntas."*

---

## ❓ 6. Preguntas Difíciles que el Profesor / Jurado Podría Hacer y Cómo Responder

1. **Pregunta:** *¿Por qué no usaron Three.js o Unity?*  
   - **Respuesta:** *«El objetivo pedagógico y de ingeniería era dominar las capas fundamentales de la computación gráfica. Usar un motor comercial oculta la gestión de buffers de GPU, la sincronización de comandos y el cálculo matricial. Al implementarlo en C11/Vulkan y WebAssembly/WebGPU, logramos un entendimiento profundo del hardware y un rendimiento determinístico con una huella de memoria mínima.»*

2. **Pregunta:** *¿Cómo garantizan que la aplicación no tenga fugas de memoria (memory leaks)?*  
   - **Respuesta:** *«Implementamos sanitizadores de memoria en tiempo de compilación con GCC: AddressSanitizer (ASan) y UndefinedBehaviorSanitizer (UBSan). Además, contamos con una compuerta automatizada (`make asan-test`) que valida todas las reservas dinámicas y garantiza cero memory leaks en cada ejecución.»*

3. **Pregunta:** *¿Cómo resolvieron el límite de 100 MB por archivo de GitHub al subir los modelos 3D?*  
   - **Respuesta:** *«Diseñamos un algoritmo de particionamiento espacial en celdas o macro-sectores (`split_glb_to_sectors.py`). Cada sector de la ciudad se exporta como un archivo glTF/GLB independiente de menos de 70 MB, permitiendo el streaming modular y cumpliendo con las políticas de GitHub sin requerir almacenamiento externo.»*

4. **Pregunta:** *¿Qué hace exactamente el archivo `.wat` en el cliente web?*  
   - **Respuesta:** *«Es el código fuente en formato de texto de WebAssembly. En él programamos funciones para multiplicar matrices 4x4, calcular el vector dirección a partir de los ángulos Pitch y Yaw de la cámara, extraer los 6 planos del frustum de visión (algoritmo Gribb-Hartmann) y realizar frustum culling sobre cajas envolventes (AABB) de los objetos para descartar geometría fuera de pantalla antes de pasarla a la GPU.»*

---

## 💻 7. Comandos de Emergencia en la Presentación

Si están en la computadora del laboratorio o laptop del equipo:

- **Para correr la versión web en local (si se cae el internet):**
  ```bash
  python3 -m http.server 8080
  # Abrir navegador en: http://localhost:8080/web/
  ```
- **Para compilar y correr el motor nativo en Linux:**
  ```bash
  make clean && make
  ./street_vulkan
  ```
- **Para demostrar la suite de pruebas al evaluador:**
  ```bash
  make test
  ```
- **Para mostrar el reporte de calidad ISO:**
  ```bash
  make metrics
  ```
