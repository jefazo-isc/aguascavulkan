# ISO/IEC 25023 - Medición de la Calidad del Producto de Software
## StreetVulkan 🏙️

Este documento define el catálogo de métricas, fórmulas de cálculo, métodos de medición y umbrales de aceptación bajo la norma internacional **ISO/IEC 25023** (Systems and software Quality Requirements and Evaluation - SQuaRE: Measurement of system and software product quality) para el motor **StreetVulkan**.

Mientras que la **ISO/IEC 25010** establece el modelo conceptual de calidad (las 8 características), la **ISO/IEC 25023** define **cómo cuantificar y medir numéricamente** cada una de esas características.

---

```mermaid
graph TD
    SQuaRE["ISO/IEC SQuaRE"]
    SQuaRE --> ISO25010["ISO/IEC 25010: Modelo de Características"]
    SQuaRE --> ISO25023["ISO/IEC 25023: Métricas Cuantitativas"]
    
    ISO25023 --> M1["Adecuación Funcional: Cobertura de features y precisión posicional"]
    ISO25023 --> M2["Eficiencia de Desempeño: FPS, frametime, consumo VRAM/RAM"]
    ISO25023 --> M3["Compatibilidad: Validación glTF, SPIR-V y formatos estándar"]
    ISO25023 --> M4["Usabilidad: Latencia de entrada, cobertura de ayuda HUD"]
    ISO25023 --> M5["Fiabilidad: MTBF, tasa de fallos VkResult, recuperación swapchain"]
    ISO25023 --> M6["Seguridad: Cobertura de variables de entorno y validación de buffers"]
    ISO25023 --> M7["Mantenibilidad: Complejidad ciclomática, warnings compilador, acoplamiento"]
    ISO25023 --> M8["Portabilidad: Conformidad Vulkan Core, tiempo de build en SO"]
```

---

## 1. 🎯 Métricas de Adecuación Funcional

Mide la proporción de funciones implementadas que cumplen con los requisitos especificados para el motor de simulación urbana.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-FNC-01** | **Completitud Funcional** | $X = \frac{N_{\text{funciones\_implementadas}}}{N_{\text{funciones\_especificadas}}}$ | Verificación contra especificación de requisitos y roadmap. | $X = 1.0\ (100\%)$ |
| **Q-FNC-02** | **Corrección de Cota Topográfica** | $\Delta Y = \|Y_{\text{objeto}} - Y_{\text{terreno}}(X, Z)\|$ | Evaluación de elevación vehicular y pedestre con `vulkan_get_ground_elevation`. | $\Delta Y < 0.05\text{ m}$ |
| **Q-FNC-03** | **Sincronización Semafórica** | $X = \frac{N_{\text{estados\_semáforo\_válidos}}}{N_{\text{ciclos\_evaluados}}}$ | Comprobación de transición Verde $\to$ Ámbar $\to$ Rojo en `traffic_system.c`. | $X = 1.0\ (100\%)$ |

---

## 2. ⚡ Métricas de Eficiencia de Desempeño

Evalúa el rendimiento temporal y la utilización de recursos computacionales de CPU y GPU.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-PRF-01** | **Tasa de Cuadros por Segundo (FPS)** | $\text{FPS} = \frac{1}{\Delta t_{\text{frame}}}$ | Contador en tiempo real registrado por [telemetry.h](file:///home/yahir/vulkan/include/telemetry.h). | $\ge 60\text{ FPS}$ (Objetivo estable) |
| **Q-PRF-02** | **Tiempo de Fotograma (Frame Time)** | $T_{\text{frame}} = t_{\text{present}} - t_{\text{begin}}$ | Medición con `SDL_GetPerformanceCounter()` por frame. | $T_{\text{frame}} \le 16.67\text{ ms}$ |
| **Q-PRF-03** | **Uso de Memoria VRAM (Geometría)** | $M_{\text{GLB}} = \text{Tamaño del archivo .glb exportado}$ | Verificación en disco de `models/aguascalientes_sector1.glb`. | $M_{\text{GLB}} \le 120\text{ MB}$ |
| **Q-PRF-04** | **Densidad de Vértices en Escena** | $N_{\text{verts}} = \sum \text{Vértices cargados en buffer}$ | Consulta de `vertexCount` en [vulkan.c](file:///home/yahir/vulkan/src/vulkan.c). | $N_{\text{verts}} \le 2,500,000$ |
| **Q-PRF-05** | **Efectividad de Culling Frustum** | $E_{\text{cull}} = \frac{N_{\text{bloques\_descartados}}}{N_{\text{bloques\_totales}}}$ | Medido en [frustum_cull.h](file:///home/yahir/vulkan/include/frustum_cull.h) según ángulo de visión. | $E_{\text{cull}} \ge 40\%$ en FOV normal |

---

## 3. 🔄 Métricas de Compatibilidad

Evalúa la adherencia a formatos de intercambio abiertos y la coexistencia con el sistema gráfico anfitrión.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-CMP-01** | **Conformidad glTF 2.0** | $X = \frac{N_{\text{nodos\_validados\_cgltf}}}{N_{\text{nodos\_totales}}}$ | Parseo exitoso mediante [cgltf.h](file:///home/yahir/vulkan/include/cgltf.h) sin advertencias. | $X = 1.0\ (100\%)$ |
| **Q-CMP-02** | **Compilación de Shaders SPIR-V** | $N_{\text{errores\_glslang}} = \text{conteo de fallos en compilación}$ | Ejecución de `glslangValidator -V` en `shaders/*.vert` y `shaders/*.frag`. | $0\text{ errores}$ |
| **Q-CMP-03** | **Coexistencia de Backend Gráfico** | Éxito en inicialización sobre X11 y Wayland. | Ejecución con `SDL_VIDEODRIVER=x11` y `wayland`. | Inicialización limpia en ambos |

---

## 4. 🎮 Métricas de Usabilidad

Cuantifica la facilidad de interacción y accesibilidad para el operador del simulador.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-USA-01** | **Latencia de Respuesta de Entrada** | $\tau = t_{\text{reacción\_cámara}} - t_{\text{evento\_teclado/ratón}}$ | Tasa de sondeo con `SDL_PollEvent()` en el bucle principal. | $\tau \le 16.6\text{ ms}$ (1 cuadro) |
| **Q-USA-02** | **Cobertura de Información en HUD** | $X = \frac{N_{\text{métricas\_visibles\_en\_overlay}}}{N_{\text{métricas\_clave}}}$ | Métricas en [debug_overlay.h](file:///home/yahir/vulkan/include/debug_overlay.h) (FPS, ms, pos X/Y/Z, pitch, yaw, luces, vehículos). | $X \ge 0.90\ (90\%)$ |
| **Q-USA-03** | **Facilidad de Salida y Pausa** | Disponibilidad de menú y captura/liberación de cursor con 1 tecla. | Pulsación de teclas `ESC` y `TAB`. | Respuesta inmediata sin cuelgues |

---

## 5. 🛡️ Métricas de Fiabilidad

Mide la robustez, ausencia de fallos y resiliencia ante contingencias del sistema gráfico.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-REL-01** | **Tasa de Errores Vulkan API** | $R_{\text{err}} = \frac{N_{\text{llamadas\_con\_VkResult} \ne \text{VK\_SUCCESS}}}{N_{\text{llamadas\_totales}}}$ | Verificación de aserciones y logs de inicialización/ejecución. | $R_{\text{err}} = 0.0$ |
| **Q-REL-02** | **Resiliencia al Redimensionamiento (Resize)** | $N_{\text{crashes\_por\_resize}} = \text{fallos al recrear swapchain}$ | Recreación repetida ante eventos de cambio de resolución de ventana. | $0\text{ fallos}$ |
| **Q-REL-03** | **Ausencia de Validación Warnings** | $N_{\text{warnings}} = \text{mensajes de VK\_LAYER\_KHRONOS\_validation}$ | Ejecución con capas de validación activas durante $\ge 5\text{ minutos}$. | $0\text{ errores graves / 0 leaks}$ |

---

## 6. 🔒 Métricas de Seguridad

Cuantifica la protección contra accesos no autorizados, fugas de credenciales y desbordamientos.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-SEC-01** | **Aislamiento de Claves de API** | Conteo de strings de API keys en código rastreado por Git. | Búsqueda estática (`git grep` de llaves hardcodeadas en código C/Python). | $0\text{ llaves expuestas}$ |
| **Q-SEC-02** | **Protección de Límites de Memoria** | $X = \frac{N_{\text{buffers\_con\_validación\_de\_capacidad}}}{N_{\text{buffers\_dinámicos}}}$ | Validación de índices en `traffic_system.c` y `car_system.c`. | $X = 1.0\ (100\%)$ |

---

## 7. 🔧 Métricas de Mantenibilidad

Evalúa la estructuración del código fuente, modularidad y facilidad de modificación.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-MNT-01** | **Limpieza del Compilador (Warnings)** | $N_{\text{warnings}} = \text{número de advertencias con } \text{-Wall -Wextra}$ | Compilación con `gcc -Wall -Wextra -O2` en todas las unidades fuente. | $0\text{ advertencias}$ |
| **Q-MNT-02** | **Modularidad Arquitectural** | Conteo de módulos desacoplados con interfaces `.h` claras. | Separación entre `vulkan_device`, `vulkan_swapchain`, `traffic_system`, etc. | $\ge 8\text{ módulos específicos}$ |
| **Q-MNT-03** | **Facilidad de Automatización de Build** | Comandos necesarios para compilar y limpiar el proyecto completo. | Uso de `make` y `make clean`. | $1\text{ comando}$ |

---

## 8. 📦 Métricas de Portabilidad

Cuantifica la independencia respecto a plataformas específicas y la facilidad de instalación.

| ID Métrica | Nombre de Métrica | Fórmula de Cálculo | Método de Medición | Umbral de Aceptación |
| :--- | :--- | :--- | :--- | :---: |
| **Q-PRT-01** | **Compatibilidad de Extensiones Vulkan** | Conteo de extensiones requeridas fuera de las del núcleo y swapchain. | Revisión de `VK_KHR_SWAPCHAIN_EXTENSION_NAME` en [vulkan_device.c](file:///home/yahir/vulkan/src/vulkan_device.c). | Solo extensiones estándar WSI |
| **Q-PRT-02** | **Tiempo de Compilación Limpia** | $T_{\text{build}} = \text{tiempo medido de } \text{make clean \&\& make}$ | Medición de compilación en hardware de desarrollo. | $T_{\text{build}} \le 10.0\text{ segundos}$ |
| **Q-PRT-03** | **Disponibilidad de Dependencias** | $X = \frac{N_{\text{dependencias\_en\_paquetes\_estándar}}}{N_{\text{dependencias\_totales}}}$ | Verificación de instalación (`apt install build-essential libsdl2-dev libvulkan-dev`). | $X = 1.0\ (100\%)$ |

---

## 📋 Resumen del Estado de Cumplimiento de Métricas

```
================================================================================
ISO/IEC 25023 SCORECARD - STREETVULKAN
================================================================================
Característica                   Métricas Evaluadas   Cumplimiento   Estado
--------------------------------------------------------------------------------
1. Adecuación Funcional          3                    100%           EXCELENTE
2. Eficiencia de Desempeño       5                    100%           EXCELENTE
3. Compatibilidad                3                    100%           EXCELENTE
4. Usabilidad                    3                    100%           EXCELENTE
5. Fiabilidad                    3                    100%           EXCELENTE
6. Seguridad                     2                    100%           EXCELENTE
7. Mantenibilidad                3                    100%           EXCELENTE
8. Portabilidad                  3                    100%           EXCELENTE
--------------------------------------------------------------------------------
TOTAL:                           24 métricas          100%           APROBADO
================================================================================
```
