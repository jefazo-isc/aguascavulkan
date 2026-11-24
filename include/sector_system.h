/* sector_system.h - Sistema de Macro-Sectores Modulares (<99MB) para StreetVulkan
 *
 * Divide la zona metropolitana de Aguascalientes en cuadrantes espaciales de 1 km x 1 km,
 * cargando en VRAM únicamente los sectores dentro del radio de visión (<= 2.0 km).
 */
#ifndef SECTOR_SYSTEM_H
#define SECTOR_SYSTEM_H

#include <stdint.h>
#include <pthread.h>
#include <vulkan/vulkan.h>
#include "vertex_format.h"
#include "frustum_cull.h"
#include "chunk_system.h"
#include "vulkan_memory_pool.h"

#ifndef MAX_FRAMES_IN_FLIGHT
#define MAX_FRAMES_IN_FLIGHT 2
#endif

#define MAX_MACRO_SECTORS 512
#define MAX_CHUNKS_PER_SECTOR 256
#define MAX_DEFERRED_SECTOR_FREES 128

#define SECTOR_STATE_UNLOADED     0
#define SECTOR_STATE_QUEUED_ASYNC 1
#define SECTOR_STATE_READY_CPU    2
#define SECTOR_STATE_LOADED_GPU   3

typedef struct {
    int mx, mz;
    char filepath[128];
    uint32_t vertexCount;
    float sizeMb;
    AABB aabb;

    int isLoaded;
    int loadState;
    Vertex *stagedVertices;
    uint32_t stagedVertexCount;
    uint32_t asyncGen;

    VkBuffer vertexBuffer;
    VkDeviceMemory vertexMemory;
    void *mappedVertices;
    VulkanSuballocation vertexSub;
    VkDeviceSize vertexAllocSize;
    int vertexInVramPool;

    VkBuffer indexBuffer;
    VkDeviceMemory indexMemory;
    void *mappedIndices;

    Chunk chunks[MAX_CHUNKS_PER_SECTOR];
    int chunkCount;
} MacroSector;

typedef struct {
    VkBuffer vertexBuffer;
    VkDeviceMemory dedicatedVertexMemory;
    VulkanSuballocation vertexSub;
    VkDeviceSize vertexAllocSize;
    int vertexInVramPool;
    VkBuffer indexBuffer;
    VkDeviceMemory dedicatedIndexMemory;
    int framesRemaining;
} DeferredSectorFree;

typedef struct {
    MacroSector sectors[MAX_MACRO_SECTORS];
    int sectorCount;
    float macroSize;
    float chunkSize;

    int activeLoadedSectors;
    uint32_t activeLoadedVerts;
    float lastCamX, lastCamZ;
    uint64_t updateTick;

    DeferredSectorFree deferredFrees[MAX_DEFERRED_SECTOR_FREES];
    int deferredFreeCount;

    pthread_t workerThread;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int workerRunning;
    int shutdownWorker;
    int syncInitialized;
} SectorSystem;

// Forward declaration para evitar dependencias circulares
struct VulkanEngine;

/**
 * Inicializa el sistema de macro-sectores desde models/sectors.json.
 * Retorna 1 si tuvo éxito, 0 si no existe el manifiesto (activando fallback monolítico).
 */
int sector_system_init(SectorSystem *ss, const char *manifestPath);

/**
 * Carga un macro-sector individual en VRAM directamente desde su archivo .glb (<99MB).
 */
int sector_system_load_gpu(SectorSystem *ss, struct VulkanEngine *eng, int sectorIdx);

/**
 * Descarga un macro-sector de VRAM encolando la liberación diferida de recursos GPU.
 */
void sector_system_unload_gpu(SectorSystem *ss, struct VulkanEngine *eng, int sectorIdx);

/**
 * Procesa la cola de liberaciones diferidas de sectores cuando expira su ventana de frames en vuelo.
 */
void sector_system_process_deferred_frees(SectorSystem *ss, struct VulkanEngine *eng, int forceAll);

/**
 * Actualiza los sectores activos según la posición de la cámara (radio en metros).
 */
void sector_system_update(SectorSystem *ss, struct VulkanEngine *eng, float camX, float camZ, float loadRadius);

/**
 * Libera todos los recursos de macro-sectores en VRAM.
 */
void sector_system_destroy(SectorSystem *ss, struct VulkanEngine *eng);

#endif /* SECTOR_SYSTEM_H */
