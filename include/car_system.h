#ifndef CAR_SYSTEM_H
#define CAR_SYSTEM_H

#include <stdint.h>
#include <vulkan/vulkan.h>
#include "road_graph.h"
#include "obj_loader.h"

#define NUM_CARS 200
#define NUM_CAR_TYPES 6

#ifndef MAX_FRAMES_IN_FLIGHT
#define MAX_FRAMES_IN_FLIGHT 2
#endif

typedef struct {
    uint32_t edge_idx;      // Índice de la arista actual
    float t;                // Parámetro [0.0, 1.0] sobre la arista
    uint32_t next_edge_idx; // Siguiente arista elegida
    int8_t lane;            // Índice de carril (0, 1, ...)
    uint8_t direction;      // 0 = a->b (fwd), 1 = b->a (rev)
    float v;                // Velocidad actual m/s
    float v_desired;        // Velocidad deseada m/s
    uint8_t mesh_type;      // 0=sedan, 1=compacto, 2=pickup, 3=van, 4=taxi, 5=bus
    float tint[4];          // Color tint

    // Estado calculado para física y render
    float pos[3];           // (x, y, z)
    float heading;          // Ángulo de orientación en radianes
    float brake;            // 0.0 o 1.0
} Car;

#pragma pack(push, 1)
typedef struct {
    float model[16];   // Matriz 4x4 (64B)
    float tint[4];     // Color RGBA (16B)
    float brake;       // Factor de freno (4B)
    float pad[3];      // Padding (12B) -> Total 96B
} CarInstanceData;
#pragma pack(pop)

typedef struct {
    Car cars[NUM_CARS];
    
    // Mallas de los 6 tipos de coches
    Mesh* car_meshes[NUM_CAR_TYPES];
    uint32_t mesh_vertex_offsets[NUM_CAR_TYPES];
    uint32_t mesh_vertex_counts[NUM_CAR_TYPES];
    
    // Buffer unificado de vértices de coches en GPU
    VkBuffer vertexBuffer;
    VkDeviceMemory vertexBufferMemory;
    size_t totalVertexCount;
    
    // Buffer de instancias de coches en GPU (NUM_CARS instancias × MAX_FRAMES_IN_FLIGHT)
    VkBuffer instanceBuffers[MAX_FRAMES_IN_FLIGHT];
    VkDeviceMemory instanceBufferMemories[MAX_FRAMES_IN_FLIGHT];
    CarInstanceData* mappedInstanceDatas[MAX_FRAMES_IN_FLIGHT];

    // Buffer precalculado en CPU para desacoplar la preparación de instancias del renderpass
    CarInstanceData stagedInstances[NUM_CARS];
    uint32_t typeCounts[NUM_CAR_TYPES];
    uint32_t typeOffsets[NUM_CAR_TYPES];
    int instancesStaged;

    // Buffer dummy de una sola instancia con tint.a=0 para geometría estática
    // Cuando dibujamos el terreno en binding 1 apuntamos aquí
    VkBuffer staticDummyBuffer;
    VkDeviceMemory staticDummyBufferMemory;
} CarSystem;

// Inicializa el sistema de coches (sube mallas a VRAM DEVICE_LOCAL)
int car_system_init(CarSystem* sys, VkDevice device, VkPhysicalDevice physDevice,
                    VkCommandPool commandPool, VkQueue graphicsQueue);

#include "traffic_system.h"

// Libera los recursos del sistema de coches
void car_system_free(CarSystem* sys, VkDevice device);

// Actualiza simulación cinemática de los 200 coches (con navegación e interacción con semáforos)
void car_system_update(CarSystem* sys, const RoadGraph* graph, const TrafficSystem* traffic, float dt, float cam_x, float cam_z);

// Dibuja instanciadamente los 200 coches (≈6 draw calls)
void car_system_render(CarSystem* sys, VkCommandBuffer cmdBuffer, uint32_t frameIdx);

// Devuelve el buffer dummy para usar cuando se dibuja geometría estática (binding 1)
VkBuffer car_system_get_static_dummy(const CarSystem* sys);

#endif // CAR_SYSTEM_H
