#ifndef TRAFFIC_SYSTEM_H
#define TRAFFIC_SYSTEM_H

#include "vertex_format.h"
#include <stdint.h>
#include <stddef.h>

// Estados posibles de una luz de semáforo
typedef enum {
    TRAFFIC_LIGHT_OFF = 0,
    TRAFFIC_LIGHT_GREEN = 1,
    TRAFFIC_LIGHT_AMBER = 2,
    TRAFFIC_LIGHT_RED = 3
} TrafficLightState;

// Representa un lente lumínico individual en el vertex buffer
typedef struct {
    size_t vertexStartIndex;
    size_t vertexCount;
    TrafficLightState type; // Qué color es este lente (GREEN, AMBER o RED)
} TrafficLens;

// Semáforo con sus 3 lentes (Rojo, Ámbar, Verde) y su orientación/fase
typedef struct {
    int id;
    int intersectionId;
    int phaseGroup; // 0 = Eje Norte-Sur, 1 = Eje Este-Oeste
    float x, y, z;  // Coordenadas mundiales
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
} TrafficSystem;

void traffic_system_init(TrafficSystem* sys);
void traffic_system_free(TrafficSystem* sys);

// Registra una nueva intersección o busca existente
TrafficIntersection* traffic_system_get_or_create_intersection(TrafficSystem* sys, int intersectionId);

// Registra un semáforo 3D
void traffic_system_add_signal(TrafficSystem* sys, TrafficSignal signal);

// Carga configuración de tráfico desde archivo JSON complementario
int traffic_system_load_json(TrafficSystem* sys, const char* jsonPath);

// Actualiza los temporizadores y actualiza la emisión de los vértices de los lentes
void traffic_system_update(TrafficSystem* sys, float deltaTime, Vertex* vertexBufferMapped, size_t maxVertices);

// Fuerza todas las luces a un estado de prueba (0: normal, 1: todo verde, 2: todo rojo)
void traffic_system_force_mode(TrafficSystem* sys, int mode, Vertex* vertexBufferMapped, size_t maxVertices);

#endif // TRAFFIC_SYSTEM_H
