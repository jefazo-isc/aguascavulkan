#ifndef TRAFFIC_SYSTEM_H
#define TRAFFIC_SYSTEM_H

#include "vertex_format.h"
#include <stdint.h>
#include <stddef.h>

#include <vulkan/vulkan.h>

#ifndef MAX_FRAMES_IN_FLIGHT
#define MAX_FRAMES_IN_FLIGHT 2
#endif

// Estados posibles de una luz de semáforo
typedef enum {
    TRAFFIC_LIGHT_OFF = 0,
    TRAFFIC_LIGHT_GREEN = 1,
    TRAFFIC_LIGHT_AMBER = 2,
    TRAFFIC_LIGHT_RED = 3
} TrafficLightState;

// Representa un lente lumínico individual
typedef struct {
    size_t vertexStartIndex;
    size_t vertexCount;
    TrafficLightState type; // Qué color es este lente (GREEN, AMBER o RED)
    size_t localOffset;     // Offset dentro del buffer dinámico de lentes desacoplado
} TrafficLens;

// Semáforo con sus 3 lentes (Rojo, Ámbar, Verde) y su orientación/fase
typedef struct {
    int id;
    int intersectionId;
    int intersectionIndex; // Índice cacheado en sys->intersections (-1 si no resuelto)
    int phaseGroup; // 0 = Eje Norte-Sur, 1 = Eje Este-Oeste
    float x, y, z;  // Coordenadas mundiales
    float dirAngle;
    int hasDirAngle;
    TrafficLightState currentState; // Estado activo actual (RED, AMBER o GREEN)
    TrafficLens redLens;
    TrafficLens amberLens;
    TrafficLens greenLens;
} TrafficSignal;

// Intersección que coordina los semáforos
typedef struct {
    int id;
    float timer;
    int currentPhase; // 0: NS Verde, 1: NS Ámbar, 2: Todo Rojo, 3: EO Verde, 4: EO Ámbar, 5: Todo Rojo
    float greenDuration;
    float amberDuration;
    float allRedDuration;
} TrafficIntersection;

typedef struct {
    TrafficSignal* signals;
    size_t signalCount;
    size_t signalCapacity;

    TrafficIntersection* intersections;
    size_t intersectionCount;
    size_t intersectionCapacity;

    // --- Buffer GPU Desacoplado de Lentes de Semáforos (~75 KB) ---
    Vertex* lensTemplateVertices; // Malla base de todos los lentes
    size_t totalLensVertices;

    VkBuffer lensBuffers[MAX_FRAMES_IN_FLIGHT];
    Vertex* mappedLensDatas[MAX_FRAMES_IN_FLIGHT];
} TrafficSystem;

void traffic_system_init(TrafficSystem* sys);
void traffic_system_free(TrafficSystem* sys);

// Registra una nueva intersección o busca existente
TrafficIntersection* traffic_system_get_or_create_intersection(TrafficSystem* sys, int intersectionId);

// Registra un semáforo 3D
void traffic_system_add_signal(TrafficSystem* sys, TrafficSignal signal);

// Carga configuración de tráfico desde archivo JSON complementario
int traffic_system_load_json(TrafficSystem* sys, const char* jsonPath);

// Inicializa el buffer GPU desacoplado de lentes (solo ~75 KB en hostVisiblePool)
typedef struct VulkanEngine VulkanEngine;
int traffic_system_init_gpu(TrafficSystem* sys, VulkanEngine* eng, const Vertex* initialVertexData, size_t totalVertices);
void traffic_system_free_gpu(TrafficSystem* sys, VkDevice device);

// Actualiza los temporizadores y lógica determinista de intersecciones a paso fijo
void traffic_system_update_simulation(TrafficSystem* sys, float deltaTime);

// Fuerza todas las luces a un estado de prueba (0: normal, 1: todo verde, 2: todo rojo)
void traffic_system_force_mode(TrafficSystem* sys, int mode);

// Actualiza los vértices lumínicos mapeados para el fotograma en vuelo actual (<5 microsegundos)
void traffic_system_update_gpu_frame(TrafficSystem* sys, uint32_t frameIdx);

// Renderiza todos los lentes activos en 1 solo draw call instanciado/dinámico
void traffic_system_render(TrafficSystem* sys, VkCommandBuffer cmd, uint32_t frameIdx, VkBuffer staticDummy);

// Funciones de compatibilidad legacy
void traffic_system_update(TrafficSystem* sys, float deltaTime, Vertex* vertexBufferMapped, size_t maxVertices);
void traffic_system_apply_visuals(TrafficSystem* sys, Vertex* vertexBufferMapped, size_t maxVertices);

// Consulta el estado del semáforo más cercano a las coordenadas (x, z) dentro de un radio dado.
TrafficLightState traffic_system_get_light_state_at(const TrafficSystem* sys, float x, float z, float maxRadius);

#endif // TRAFFIC_SYSTEM_H
