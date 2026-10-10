# 🗺️ StreetVulkan - Roadmap de Funcionalidades Futuras

Este documento establece el plan técnico detallado para implementar las **3 características avanzadas pendientes** en el motor `StreetVulkan`.

---

## 🚗 1. Simulación Dinámica de Vehículos y Tráfico en C
**Objetivo:** Introducir vehículos low-poly animados que circulen por la red vial de la ciudad y respeten los estados de los semáforos (Verde/Amarillo/Rojo).

### Arquitectura Técnica:
1. **Estructuras de Datos (`include/traffic_system.h` & `src/traffic_system.c`):**
   ```c
   typedef enum { VEHICLE_DRIVING, VEHICLE_STOPPING, VEHICLE_WAITING_RED } VehicleState;

   typedef struct {
       float x, y, z;
       float speed;
       float maxSpeed;
       float dirAngle;
       int targetIntersectionId;
       VehicleState state;
       size_t vertexStartIndex;
   } Vehicle;
   ```
2. **Lógica de Navegación:**
   - Los vehículos siguen los nodos viales extraídos de OpenStreetMap (`highway_pts_m`).
   - En `traffic_system_update()`, cada vehículo consulta la intersección más cercana:
     - Si la fase actual es **Verde**, acelera hasta `maxSpeed`.
     - Si la fase es **Amarillo / Rojo**, calcula la distancia de frenado y se detiene antes del paso peatonal.
3. **Malla 3D Pixel-Art:**
   - Modelos de vehículos en 3D en estilo low-poly (sedán, autobús, camioneta) mapeados a baldosas de $16 \times 16$ px en el atlas.

---

## 🌙 2. Ciclo Día/Noche e Iluminación Dinámica
**Objetivo:** Transición continua del tiempo ($0.0 \to 24.0\text{ horas}$) modificando la luz solar, el color del cielo y activando la iluminación de ventanas y farolas al anochecer.

### Arquitectura Técnica:
1. **Controles en CPU (`src/main.c` / `src/vulkan.c`):**
   - Variable `timeOfDay` incrementada por `deltaTime`.
   - Cálculo de la posición del Sol:
     $$\vec{L} = (\cos(\theta), \sin(\theta), 0.3), \quad \theta = \frac{\text{timeOfDay}}{24.0} \times 2\pi$$
   - Interpolación de paleta de colores del cielo (Azul Día $\to$ Naranja Atardecer $\to$ Azul Marino Noche).
2. **Shaders GLSL (`shaders/vertex.vert` & `shaders/fragment.frag`):**
   - Enviar `timeOfDay` y $\vec{L}$ mediante *PushConstants* o *Uniform Buffers*.
   - Multiplicador de Emisión Nocturna:
     $$\text{FinalColor} = \text{Diffuse} \times \text{Ambient} + \text{Emission} \times \text{NightFactor}$$
     Durante la noche, las ventanas de edificios clasificados y los lentes de los semáforos destacan en la oscuridad.

---

## 🏛️ 3. Generación de Monumentos Únicos con la API de Gemini
**Objetivo:** Sustituir edificios históricos o icónicos por modelos 3D detallados generados automáticamente por la API de Gemini.

### Arquitectura Técnica:
1. **Detección Semántica (`tools/classify_buildings.py`):**
   - Filtrar en el mapa los edificios marcados con etiquetas especiales de OSM/DENUE (`historic=monument`, `amenity=place_of_worship`, `tourism=attraction`).
2. **Generador con IA Gemini (`tools/gemini_obj_generator.py`):**
   - Enviar el contexto geométrico (polígono de base, altura real y foto satelital) al modelo de Gemini para estructurar las caras y vértices del monumento en formato `.obj`.
3. **Carga en Tiempo de Ejecución en Vulkan (`src/vulkan.c` & `src/obj_loader.c`):**
   - Cargar dinámicamente los archivos `.obj` generados desde `models/gemini_cache/`.
   - Ajuste de cota topográfica (`vulkan_get_ground_elevation`) para asentar la base del monumento perfectamente sobre el terreno.

---

## 📌 Cronograma Sugerido de Implementación
1. **Paso 1:** Ciclo Día/Noche (requiere ajustes menores en shaders y PushConstants).
2. **Paso 2:** Simulación de Vehículos (aprovecha la infraestructura existente de `traffic_system.c`).
3. **Paso 3:** Monumentos con Gemini (requiere llamadas de red a la API de Gemini).
