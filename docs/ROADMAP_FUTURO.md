# 🗺️ StreetVulkan - Roadmap de Funcionalidades Futuras

Este documento establece el plan técnico detallado para implementar las características avanzadas pendientes en el motor `StreetVulkan`.

---

## 🚶 1. Integración Visual de Peatones en GPU
**Objetivo:** Conectar al renderizado los peatones cuya lógica de movimiento y estados semafóricos ya existen en C, y mostrarlos caminando por banquetas y cruces.

### Arquitectura Técnica:
1. **Lógica existente:** [ped_system.h](../include/ped_system.h) y [ped_system.c](../src/ped_system.c) definen los estados y la actualización CPU; conservar las pruebas unitarias al integrarlos.
2. **Malla 3D e instancing GPU:**
   - Carga del modelo low-poly `models/peds/ped.glb`.
   - Renderizado instanciado masivo en GPU con buffer dinámico mapeado por frame en vuelo (`MAX_FRAMES_IN_FLIGHT = 2`).
3. **Integración y validación:** actualizar la escena/bucle de render y comprobar sincronización con semáforos, límites del buffer y comportamiento al no haber modelos disponibles.

---

## 🎨 2. Pipeline 2D Separado, Alpha Blending y Font Atlas
**Objetivo:** Soportar transparencias reales en la escena 3D y renderizar la interfaz de usuario/telemetría mediante texturas tipográficas eficientes.

### Arquitectura Técnica:
1. **Pipeline 2D con Mezcla Alfa (`src/vulkan_pipeline.c`):**
   - Configuración de un pipeline secundario con `blendEnable = VK_TRUE` (`VK_BLEND_FACTOR_SRC_ALPHA`, `VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA`) y `depthTestEnable = VK_FALSE`.
2. **Font Atlas (`include/debug_overlay.h`):**
   - Sustituir la generación por CPU de ~30,000 micro-vértices geométricos por frame por un atlas de texturas tipográficas (reducción a ~600 vértices de quads texturizados).
3. **Transparencias Reales:**
   - Soporte para vidrios de vehículos, agua/fuentes y follaje con mezcla alfa.

---

## ☀️ 3. Sombras Dinámicas (Shadow Mapping) y Control Horario
**Objetivo:** Proyectar sombras direccionales nítidas de edificios y farolas en tiempo real y coordinar el encendido/apagado horario de farolas.

### Arquitectura Técnica:
1. **Render Pass de Profundidad (Shadow Map):**
   - Pase previo de renderizado a un attachment de solo profundidad desde la perspectiva ortográfica de la luz solar direccional (`pc.sunDir`).
   - Muestreo con `sampler2DShadow` / `textureProj` en `shaders/fragment.frag` para atenuar la iluminación solar directa en zonas en sombra.
2. **Encendido Reactivo de Alumbrado Público:**
   - Activación gradual de las 64 luces puntuales viales y de la emisión en ventanas entre las 18:30 y las 06:30 de la simulación horaria.

---

## 🏛️ 4. Integración en Runtime de Monumentos Generados
**Objetivo:** Integrar en el runtime Vulkan los modelos OBJ que ya puede producir el pipeline de Gemini para sustituir edificios históricos o icónicos seleccionados.

### Arquitectura Técnica:
1. **Detección Semántica (`tools/classify_buildings.py`):**
   - Filtrar en el mapa los edificios marcados con etiquetas especiales de OSM/DENUE (`historic=monument`, `amenity=place_of_worship`, `tourism=attraction`).
2. **Generación existente:** [gemini_obj_generator.py](../tools/gemini_obj_generator.py) y las herramientas relacionadas producen modelos OBJ; documentar y validar entradas, salidas y credenciales antes de ejecutar el servicio externo.
3. **Carga en Tiempo de Ejecución en Vulkan (`src/vulkan.c` & `src/obj_loader.c`):**
   - Cargar dinámicamente los archivos `.obj` generados desde `models/gemini_cache/`.
   - Ajuste de cota topográfica (`vulkan_get_ground_elevation`) para asentar la base del monumento perfectamente sobre el terreno.

---

## 📌 Cronograma Sugerido de Implementación
1. **Paso 1:** Integración visual de peatones en GPU (aprovecha la lógica CPU y los modelos existentes en `models/peds/`).
2. **Paso 2:** Pipeline 2D con Alpha Blending y Font Atlas (optimiza el HUD y habilita cristales transparentes).
3. **Paso 3:** Sombras Dinámicas Direccionales (Shadow Mapping).
4. **Paso 4:** Integración en runtime de monumentos generados con Gemini.
