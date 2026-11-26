#include "vulkan.h"
#include "logger.h"
#include <SDL2/SDL_vulkan.h>
#include "vulkan_device.h"
#include "vulkan_swapchain.h"
#include "vulkan_pipeline.h"
#include "vulkan_texture.h"
#include "vulkan_gltf.h"
#include "obj_loader.h"
#include "math_camera.h"
#include "terrain_dem_data.h"
#include "frustum_cull.h"
#include "pause_menu.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <dirent.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

float vulkan_get_ground_elevation(VulkanEngine *eng, float x, float z) {
    (void)eng; // Puede usarse para consultar buffers adicionales si fuera necesario
    return terrain_dem_get_elevation(x, z);
}

static int is_direct_host_visible_uma(const VulkanEngine *eng) {
    VkPhysicalDeviceMemoryProperties memProperties;
    vkGetPhysicalDeviceMemoryProperties(eng->physicalDevice, &memProperties);
    uint32_t hostMemType = eng->hostVisiblePool.memoryTypeIndex;
    if (hostMemType >= memProperties.memoryTypeCount) return 0;
    VkMemoryPropertyFlags flags = memProperties.memoryTypes[hostMemType].propertyFlags;
    return ((flags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) != 0) &&
           ((flags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) != 0);
}

static int create_pool_buffer(VulkanEngine *eng, VulkanMemoryPool *pool, VkDeviceSize size,
                              VkBufferUsageFlags usage, VkBuffer *outBuffer, VulkanSuballocation *outSub) {
    VkBufferCreateInfo info = {0};
    info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    info.size = size;
    info.usage = usage;
    info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    if (vkCreateBuffer(eng->device, &info, NULL, outBuffer) != VK_SUCCESS) {
        *outBuffer = VK_NULL_HANDLE;
        return 0;
    }
    if (!vulkan_memory_pool_bind_buffer(pool, *outBuffer, outSub)) {
        vkDestroyBuffer(eng->device, *outBuffer, NULL);
        *outBuffer = VK_NULL_HANDLE;
        return 0;
    }
    return 1;
}


typedef struct {
    VkBuffer src;
    VkBuffer dst;
    VkDeviceSize size;
} BufferCopyJob;

static int execute_buffer_copy_jobs(VulkanEngine *eng, const BufferCopyJob *jobs, uint32_t jobCount) {
    if (jobCount == 0) return 1;
    VkCommandBufferAllocateInfo cmdAlloc = {0};
    cmdAlloc.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    cmdAlloc.commandPool = eng->commandPool;
    cmdAlloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    cmdAlloc.commandBufferCount = 1;

    VkCommandBuffer uploadCmd = VK_NULL_HANDLE;
    if (vkAllocateCommandBuffers(eng->device, &cmdAlloc, &uploadCmd) != VK_SUCCESS) {
        return 0;
    }

    VkCommandBufferBeginInfo bbi = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
    };
    vkBeginCommandBuffer(uploadCmd, &bbi);
    for (uint32_t i = 0; i < jobCount; ++i) {
        VkBufferCopy copyRegion = { .srcOffset = 0, .dstOffset = 0, .size = jobs[i].size };
        vkCmdCopyBuffer(uploadCmd, jobs[i].src, jobs[i].dst, 1, &copyRegion);
    }
    vkEndCommandBuffer(uploadCmd);

    VkSubmitInfo submitInfo = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &uploadCmd
    };
    vkQueueSubmit(eng->graphicsQueue, 1, &submitInfo, VK_NULL_HANDLE);
    vkQueueWaitIdle(eng->graphicsQueue);
    vkFreeCommandBuffers(eng->device, eng->commandPool, 1, &uploadCmd);
    return 1;
}

/* Sube datos CPU a un VkBuffer (UMA directo o staging -> vramBufferPool) y libera cpuData */
static int upload_buffer_to_gpu(VulkanEngine *eng, void *cpuData, size_t byteSize,
                                VkBufferUsageFlags usage, VkBuffer *outBuffer, const char *label) {
    if (!cpuData || byteSize == 0 || !outBuffer) {
        free(cpuData);
        return 0;
    }

    if (is_direct_host_visible_uma(eng)) {
        VulkanSuballocation sub = {0};
        if (!create_pool_buffer(eng, &eng->hostVisiblePool, byteSize, usage, outBuffer, &sub) || !sub.mappedPtr) {
            LOG_ERROR("VRAM", "Error creando %s directo UMA", label);
            if (*outBuffer != VK_NULL_HANDLE) {
                vkDestroyBuffer(eng->device, *outBuffer, NULL);
                *outBuffer = VK_NULL_HANDLE;
            }
            free(cpuData);
            return 0;
        }
        memcpy(sub.mappedPtr, cpuData, byteSize);
        free(cpuData);
        return 1;
    }

    VkBuffer stagingBuffer = VK_NULL_HANDLE;
    VulkanSuballocation stagingSub = {0};
    if (!create_pool_buffer(eng, &eng->hostVisiblePool, byteSize,
                            VK_BUFFER_USAGE_TRANSFER_SRC_BIT, &stagingBuffer, &stagingSub) || !stagingSub.mappedPtr) {
        LOG_ERROR("VRAM", "Error creando Staging Buffer para %s", label);
        if (stagingBuffer != VK_NULL_HANDLE) {
            vkDestroyBuffer(eng->device, stagingBuffer, NULL);
        }
        free(cpuData);
        return 0;
    }
    memcpy(stagingSub.mappedPtr, cpuData, byteSize);
    free(cpuData);

    VkMemoryRequirements stagingReqs;
    vkGetBufferMemoryRequirements(eng->device, stagingBuffer, &stagingReqs);

    if (!create_pool_buffer(eng, &eng->vramBufferPool, byteSize,
                            usage | VK_BUFFER_USAGE_TRANSFER_DST_BIT, outBuffer, NULL)) {
        LOG_ERROR("VRAM", "Error creando %s DEVICE_LOCAL", label);
        vkDestroyBuffer(eng->device, stagingBuffer, NULL);
        vulkan_memory_pool_free_suballocation(&eng->hostVisiblePool, stagingSub, stagingReqs.size);
        return 0;
    }

    BufferCopyJob job = { .src = stagingBuffer, .dst = *outBuffer, .size = byteSize };
    int copied = execute_buffer_copy_jobs(eng, &job, 1);
    vkDestroyBuffer(eng->device, stagingBuffer, NULL);
    vulkan_memory_pool_free_suballocation(&eng->hostVisiblePool, stagingSub, stagingReqs.size);
    if (!copied) {
        vkDestroyBuffer(eng->device, *outBuffer, NULL);
        *outBuffer = VK_NULL_HANDLE;
        return 0;
    }
    return 1;
}


static void emit_cyan_beacon(Vertex outVerts[12], float cx, float baseY, float cz) {
    const float beaconHeight = 200.0f;
    const float beaconHalfW = 0.4f;
    float topY = baseY + beaconHeight;

    Vertex bv = {0};
    bv.r = 0.0f; bv.g = 0.9f; bv.b = 1.0f; bv.a = 1.0f;
    bv.emission = 1.5f;
    bv.nx = 0.0f; bv.ny = 0.0f; bv.nz = 1.0f;

    size_t bi = 0;
    // Quad 1 (plano XY)
    bv.x = cx - beaconHalfW; bv.y = baseY; bv.z = cz; outVerts[bi++] = bv;
    bv.x = cx + beaconHalfW; bv.y = baseY; bv.z = cz; outVerts[bi++] = bv;
    bv.x = cx + beaconHalfW; bv.y = topY;  bv.z = cz; outVerts[bi++] = bv;
    bv.x = cx - beaconHalfW; bv.y = baseY; bv.z = cz; outVerts[bi++] = bv;
    bv.x = cx + beaconHalfW; bv.y = topY;  bv.z = cz; outVerts[bi++] = bv;
    bv.x = cx - beaconHalfW; bv.y = topY;  bv.z = cz; outVerts[bi++] = bv;

    // Quad 2 (plano ZY)
    bv.nx = 1.0f; bv.nz = 0.0f;
    bv.x = cx; bv.y = baseY; bv.z = cz - beaconHalfW; outVerts[bi++] = bv;
    bv.x = cx; bv.y = baseY; bv.z = cz + beaconHalfW; outVerts[bi++] = bv;
    bv.x = cx; bv.y = topY;  bv.z = cz + beaconHalfW; outVerts[bi++] = bv;
    bv.x = cx; bv.y = baseY; bv.z = cz - beaconHalfW; outVerts[bi++] = bv;
    bv.x = cx; bv.y = topY;  bv.z = cz + beaconHalfW; outVerts[bi++] = bv;
    bv.x = cx; bv.y = topY;  bv.z = cz - beaconHalfW; outVerts[bi++] = bv;
}

static size_t append_gemini_obj_file(VulkanEngine *eng, const char *fullPath, const char *fileName) {
    Mesh* geminiMesh = obj_load(fullPath);
    if (!geminiMesh) return 0;
    if (geminiMesh->vertexCount == 0) {
        obj_free(geminiMesh);
        return 0;
    }

    float minX = 1e9f, maxX = -1e9f;
    float minY = 1e9f, maxY = -1e9f;
    float minZ = 1e9f, maxZ = -1e9f;
    for (size_t v = 0; v < geminiMesh->vertexCount; v++) {
        const Vertex *gv = &geminiMesh->vertices[v];
        if (gv->x < minX) minX = gv->x;
        if (gv->x > maxX) maxX = gv->x;
        if (gv->y < minY) minY = gv->y;
        if (gv->y > maxY) maxY = gv->y;
        if (gv->z < minZ) minZ = gv->z;
        if (gv->z > maxZ) maxZ = gv->z;
    }
    float cx = (minX + maxX) * 0.5f;
    float cz = (minZ + maxZ) * 0.5f;
    float groundY = vulkan_get_ground_elevation(eng, cx, cz);

    float yAdjustment = 0.0f;
    if (minY < groundY - 0.5f || (fabsf(minY) < 0.2f && groundY > 0.5f)) {
        yAdjustment = (groundY + 0.05f) - minY;
    }
    float baseY = minY + yAdjustment;

    int isPhotoPlane = (strncmp(fileName, "photo_", 6) == 0);
    size_t beaconCount = isPhotoPlane ? 0 : 12;
    size_t addedVerts = geminiMesh->vertexCount + beaconCount;
    size_t newCount = eng->auxVertexCount + addedVerts;

    Vertex* newData = realloc(eng->auxVertexData, newCount * sizeof(Vertex));
    if (!newData) {
        obj_free(geminiMesh);
        return 0;
    }

    size_t baseIdx = eng->auxVertexCount;
    for (size_t v = 0; v < geminiMesh->vertexCount; v++) {
        Vertex vert = geminiMesh->vertices[v];
        vert.y += yAdjustment;
        if (vert.emission == 0.0f) {
            vert.emission = 0.04f;
        }
        newData[baseIdx + v] = vert;
    }

    if (beaconCount > 0) {
        emit_cyan_beacon(&newData[baseIdx + geminiMesh->vertexCount], cx, baseY, cz);
    }

    eng->auxVertexData = newData;
    eng->auxVertexCount = newCount;
    printf("[Motor] +Gemini AI: %s (%zu vértices + beacon en X:%.1f, Y:%.2f, Z:%.1f)\n",
           fileName, geminiMesh->vertexCount, cx, baseY, cz);

    obj_free(geminiMesh);
    return addedVerts;
}

static void append_road_graph_debug_aux(VulkanEngine *eng) {
    if (!eng->roadGraph || !getenv("STREET_DEBUG_ROAD_GRAPH")) return;

    Mesh* debugMesh = road_graph_build_debug_mesh(eng->roadGraph);
    if (!debugMesh) return;

    if (debugMesh->vertexCount > 0) {
        size_t newCount = eng->auxVertexCount + debugMesh->vertexCount;
        Vertex* newData = realloc(eng->auxVertexData, newCount * sizeof(Vertex));
        if (newData) {
            memcpy(newData + eng->auxVertexCount, debugMesh->vertices,
                   debugMesh->vertexCount * sizeof(Vertex));
            eng->auxVertexData = newData;
            eng->auxVertexCount = newCount;
            printf("[Motor] 🚦 Malla de depuración del Grafo Vial agregada (%zu vértices)\n",
                   debugMesh->vertexCount);
        }
    }
    obj_free(debugMesh);
}

static void load_auxiliary_geometry(VulkanEngine *eng) {
    if (!eng) return;

    // 1. Escanear models/generated/*.obj (edificios/monumentos Gemini AI y photo planes)
    const char* genDir = "models/generated";
    DIR* dir = opendir(genDir);
    if (dir) {
        struct dirent* entry;
        size_t geminiTotal = 0;
        while ((entry = readdir(dir)) != NULL) {
            size_t nameLen = strlen(entry->d_name);
            if (nameLen < 5 || strcmp(entry->d_name + nameLen - 4, ".obj") != 0) continue;

            char fullPath[512];
            snprintf(fullPath, sizeof(fullPath), "%s/%s", genDir, entry->d_name);
            geminiTotal += append_gemini_obj_file(eng, fullPath, entry->d_name);
        }
        closedir(dir);
        if (geminiTotal > 0) {
            printf("[Motor] 🤖 Props Gemini colocados sobre terreno: %zu vértices totales\n", geminiTotal);
        }
    }

    // 2. Malla de depuración del grafo vial si STREET_DEBUG_ROAD_GRAPH está definido
    append_road_graph_debug_aux(eng);

    if (!eng->auxVertexData || eng->auxVertexCount == 0) {
        free(eng->auxVertexData);
        eng->auxVertexData = NULL;
        eng->auxVertexCount = 0;
        return;
    }

    size_t auxBytes = eng->auxVertexCount * sizeof(Vertex);
    void *rawAux = eng->auxVertexData;
    eng->auxVertexData = NULL;

    if (!upload_buffer_to_gpu(eng, rawAux, auxBytes, VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
                              &eng->auxVertexBuffer, "Aux Vertex Buffer")) {
        eng->auxVertexCount = 0;
        return;
    }
    printf("[Motor VRAM] 🚀 Aux Vertex Buffer (%zu vértices, %.2f MB) cargado.\n",
           eng->auxVertexCount, (double)auxBytes / (1024.0 * 1024.0));
}

static int upload_primary_mesh_buffers(VulkanEngine *eng) {
    if (eng->vertexCount == 0 || !eng->vertexData) {
        free(eng->vertexData);
        eng->vertexData = NULL;
        free(eng->indexData);
        eng->indexData = NULL;
        eng->indexCount = 0;
        return 0;
    }

    size_t bufferSize = eng->vertexCount * sizeof(Vertex);
    void *rawVerts = eng->vertexData;
    eng->vertexData = NULL;

    if (!upload_buffer_to_gpu(eng, rawVerts, bufferSize, VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
                              &eng->vertexBuffer, "Vertex Buffer")) {
        free(eng->indexData);
        eng->indexData = NULL;
        eng->indexCount = 0;
        return 0;
    }

    if (eng->indexCount > 0 && eng->indexData) {
        size_t indexBufferSize = eng->indexCount * sizeof(uint32_t);
        void *rawIndices = eng->indexData;
        eng->indexData = NULL;
        if (!upload_buffer_to_gpu(eng, rawIndices, indexBufferSize, VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
                                  &eng->indexBuffer, "Index Buffer")) {
            eng->indexCount = 0;
        }
    }

    printf("[Motor VRAM] 🚀 Vertex Buffer (%.2f MB) %s cargado exitosamente.\n",
           (double)bufferSize / (1024.0 * 1024.0),
           (eng->indexCount > 0 && eng->indexBuffer != VK_NULL_HANDLE) ? "+ Index Buffer" : "");
    return 1;
}

static int load_primary_geometry(VulkanEngine *eng) {
    // 0. Modo Modular (<99MB por archivo): Macro-Sectores Espaciales con Streaming Dinámico
    const char* sectorsManifest = "models/sectors.json";
    FILE* checkManifest = fopen(sectorsManifest, "r");
    if (checkManifest) {
        fclose(checkManifest);
        if (sector_system_init(&eng->sectorSystem, sectorsManifest)) {
            eng->useSectorSystem = 1;
            extern Camera g_camera;
            LOG_INFO("Motor", "Modo Modular Activado: %d macro-sectores (<99MB) listos para streaming",
                     eng->sectorSystem.sectorCount);
            // Cargar sectores iniciales en radio de 2.0 km
            sector_system_update(&eng->sectorSystem, eng, g_camera.pos.x, g_camera.pos.z, 2000.0f);

            eng->vertexCount = eng->sectorSystem.activeLoadedVerts;
            eng->baseVertexCount = eng->vertexCount;
            eng->indexCount = 0;

            eng->roadGraph = road_graph_load("models/road_network.bin");
            load_auxiliary_geometry(eng);
            if (eng->trafficSystem.signalCount > 0) {
                traffic_system_init_gpu(&eng->trafficSystem, eng, NULL, 0);
            }
            return 1;
        }
    }
    eng->useSectorSystem = 0;

    // 1. Intentar cargar modelo binario glTF (.glb) con Direct VRAM Streaming Zero-Copy
    const char* glbFile = "models/aguascalientes_sector1.glb";
    FILE* checkGLB = fopen(glbFile, "rb");
    if (checkGLB) {
        fclose(checkGLB);
        LOG_INFO("Motor", "Cargando geometría glTF con Direct VRAM Streaming: %s...", glbFile);
        if (gltf_load_direct_vulkan(glbFile, eng)) {
            eng->roadGraph = road_graph_load("models/road_network.bin");
            load_auxiliary_geometry(eng);
            return 1;
        }
    }

    // 2. Si no hay .glb, cargar el modelo .obj existente
    const char* objFile = "models/aguascalientes_sector1.obj";
    FILE* checkOBJ = fopen(objFile, "r");
    if (checkOBJ) {
        fclose(checkOBJ);
    } else {
        objFile = "models/test.obj";
    }
    LOG_INFO("Motor", "Cargando geometría OBJ: %s...", objFile);
    Mesh* mesh = obj_load(objFile);
    if (!mesh) {
        LOG_ERROR("Motor", "No se pudo cargar ningún modelo 3D inicial");
        return 0;
    }

    if (mesh->indices && mesh->indexCount > 0) {
        eng->indexData = malloc(mesh->indexCount * sizeof(uint32_t));
        if (eng->indexData) {
            eng->indexCount = mesh->indexCount;
            for (size_t i = 0; i < mesh->indexCount; ++i) {
                eng->indexData[i] = (uint32_t)mesh->indices[i];
            }
        } else {
            eng->indexCount = 0;
        }
    } else {
        eng->indexCount = 0;
        eng->indexData = NULL;
    }

    eng->vertexCount = mesh->vertexCount;
    eng->baseVertexCount = mesh->vertexCount;
    eng->vertexData = mesh->vertices;
    mesh->vertices = NULL; // Traspasar la propiedad para que obj_free no lo libere
    obj_free(mesh);

    // Extraer vértices de lentes de semáforos antes de liberar el búfer CPU
    if (eng->trafficSystem.signalCount > 0) {
        traffic_system_init_gpu(&eng->trafficSystem, eng, eng->vertexData, eng->vertexCount);
    }

    if (!upload_primary_mesh_buffers(eng)) {
        return 0;
    }

    eng->roadGraph = road_graph_load("models/road_network.bin");
    load_auxiliary_geometry(eng);
    return 1;
}

static void init_timestamp_query_pool(VulkanEngine *eng) {
    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(eng->physicalDevice, &props);
    eng->timestampPeriodNs = props.limits.timestampPeriod;
    eng->timestampQueryPool = VK_NULL_HANDLE;
    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        eng->timestampValid[i] = 0;
    }

    if (props.limits.timestampComputeAndGraphics && eng->timestampPeriodNs > 0.0f) {
        VkQueryPoolCreateInfo qpi = {0};
        qpi.sType = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO;
        qpi.queryType = VK_QUERY_TYPE_TIMESTAMP;
        qpi.queryCount = MAX_FRAMES_IN_FLIGHT * 2;
        if (vkCreateQueryPool(eng->device, &qpi, NULL, &eng->timestampQueryPool) != VK_SUCCESS) {
            eng->timestampQueryPool = VK_NULL_HANDLE;
        }
    }
}

/* Reserva y mapea persistentemente los buffers de vértices del HUD por frame. */
static void init_hud_vertex_buffers(VulkanEngine *eng) {
    VkDeviceSize hudBufSize = DEBUG_MAX_VERTS * sizeof(Vertex);
    VkBufferCreateInfo bi = {0};
    bi.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    bi.size = hudBufSize;
    bi.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
    bi.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if (vkCreateBuffer(eng->device, &bi, NULL, &eng->hudVertexBuffers[i]) != VK_SUCCESS) continue;
        VkMemoryRequirements mr;
        vkGetBufferMemoryRequirements(eng->device, eng->hudVertexBuffers[i], &mr);
        VulkanSuballocation sub = vulkan_memory_pool_suballocate(&eng->hostVisiblePool, mr.size, mr.alignment);
        if (sub.memory != VK_NULL_HANDLE) {
            eng->hudVertexBufferMemories[i] = VK_NULL_HANDLE;
            vkBindBufferMemory(eng->device, eng->hudVertexBuffers[i], sub.memory, sub.offset);
            eng->hudMappedDatas[i] = (Vertex*)sub.mappedPtr;
        }
    }
}

/* Registra en el log el total de chunks activos para frustum culling. */
static void log_active_chunks(const VulkanEngine *eng) {
    if (!eng->chunksEnabled) return;
    if (!eng->useSectorSystem) {
        LOG_INFO("Motor", "Frustum culling ACTIVO (%d chunks de %.0fm)",
                 eng->chunkSystem.chunkCount, eng->chunkSystem.chunkSize);
        return;
    }
    int activeChunks = 0;
    for (int s = 0; s < eng->sectorSystem.sectorCount; s++) {
        const MacroSector *sec = &eng->sectorSystem.sectors[s];
        if (!sec->isLoaded) continue;
        activeChunks += (sec->chunkCount > 0) ? sec->chunkCount : 1;
    }
    LOG_INFO("Motor", "Frustum culling ACTIVO (%d chunks de %.0fm)",
             activeChunks, eng->sectorSystem.chunkSize);
}

int vulkan_init(VulkanEngine *eng, SDL_Window *window) {
    memset(eng, 0, sizeof(VulkanEngine));
    eng->window = window;

    if (!init_vulkan_instance_and_device(eng, window)) return 0;

    uint32_t vramType = find_memory_type(eng->physicalDevice, UINT32_MAX, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    uint32_t hostType = find_memory_type(eng->physicalDevice, UINT32_MAX,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);

    vulkan_memory_pool_init(&eng->vramBufferPool, eng->device, eng->physicalDevice, vramType,
                            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 64 * 1024 * 1024);
    vulkan_memory_pool_init(&eng->vramImagePool, eng->device, eng->physicalDevice, vramType,
                            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 64 * 1024 * 1024);
    vulkan_memory_pool_init(&eng->hostVisiblePool, eng->device, eng->physicalDevice, hostType,
                            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, 16 * 1024 * 1024);

    if (!create_swapchain_and_depth(eng)) goto fail_cleanup;
    if (!create_render_pass(eng)) goto fail_cleanup;
    if (!create_framebuffers(eng)) goto fail_cleanup;
    if (!create_sync_objects(eng)) goto fail_cleanup;
    if (!create_pipeline_and_descriptors(eng)) goto fail_cleanup;
    init_timestamp_query_pool(eng);
    SDL_PumpEvents();

    const char* texFile = "assets/satellite.png";
    if (!init_satellite_texture(eng, texFile)) {
        LOG_ERROR("Motor", "Fallo inicializando textura satelital y descriptores (%s).", texFile);
        goto fail_cleanup;
    }
    SDL_PumpEvents();

    traffic_system_init(&eng->trafficSystem);
    traffic_system_load_json(&eng->trafficSystem, "models/traffic_signals.json");
    SDL_PumpEvents();

    if (!load_primary_geometry(eng)) goto fail_cleanup;
    SDL_PumpEvents();

    lighting_system_init(&eng->lightingSystem, &eng->trafficSystem);
    car_system_init(&eng->carSystem, eng->device, eng->physicalDevice, eng->commandPool, eng->graphicsQueue);
    SDL_PumpEvents();

    if (eng->useSectorSystem) {
        eng->chunksEnabled = 1;
    } else {
        eng->chunksEnabled = chunk_system_load(&eng->chunkSystem, "models/chunks.json");
        SDL_PumpEvents();
        if (eng->chunksEnabled && eng->indexCount > 0 && eng->chunkSystem.totalVerts > eng->indexCount) {
            LOG_WARN("Motor", "chunks.json tiene %u vertices pero GLB tiene %zu. Desactivando chunks para prevenir corrupcion.",
                     eng->chunkSystem.totalVerts, eng->indexCount);
            eng->chunksEnabled = 0;
        }
    }

    init_hud_vertex_buffers(eng);
    eng->currentFps = 60.0f;
    eng->simHour = 14.0f;
    eng->timeScale = 1.0f;
    eng->showTelemetry = 1;
    eng->cullingEnabled = eng->chunksEnabled;
    eng->camSpeedIndex = 1;

    LOG_INFO("Motor", "StreetVulkan inicializado con éxito. Vértices activos: %zu", eng->vertexCount);
    log_active_chunks(eng);
    return 1;

fail_cleanup:
    LOG_ERROR("Motor", "Error en inicialización; ejecutando rollback y limpieza de recursos.");
    vulkan_destroy(eng);
    return 0;
}

void vulkan_update_simulation(VulkanEngine *eng, float fixedDeltaTime) {
    if (eng->isPaused) return;
    Uint64 simStart = SDL_GetPerformanceCounter();

    float simDelta = fixedDeltaTime * eng->timeScale;

    // 1. Ciclo Día/Noche (72 minutos reales = 24 horas simuladas con timeScale y pausa)
    if (!eng->timeFrozen) {
        eng->simHour += simDelta / 180.0f;
        if (eng->simHour >= 24.0f) eng->simHour = fmodf(eng->simHour, 24.0f);
        if (eng->simHour < 0.0f)  eng->simHour += 24.0f;
    }

    // 2. Semáforos a paso fijo (actualización lógica determinista)
    if (eng->trafficSignalMode != 0) {
        traffic_system_force_mode(&eng->trafficSystem, eng->trafficSignalMode);
    } else {
        if (simDelta > 0.0f) {
            traffic_system_update_simulation(&eng->trafficSystem, simDelta);
        }
    }

    // 3. Cinemática y trayectoria de coches determinista a paso fijo
    if (eng->roadGraph) {
        car_system_update(&eng->carSystem, eng->roadGraph, &eng->trafficSystem, simDelta, g_camera.pos.x, g_camera.pos.z);
    }

    Uint64 simEnd = SDL_GetPerformanceCounter();
    Uint64 perfFreq = SDL_GetPerformanceFrequency();
    if (perfFreq > 0) {
        eng->simCpuAccumMs += (float)((double)(simEnd - simStart) * 1000.0 / (double)perfFreq);
    }
}

static int ensure_render_finished_semaphores(VulkanEngine *eng, uint32_t neededCount) {
    if (neededCount <= eng->renderFinishedSemaphoreCount) return 1;
    VkSemaphore *newSems = realloc(eng->renderFinishedSemaphores, neededCount * sizeof(VkSemaphore));
    if (!newSems) {
        LOG_ERROR("Vulkan", "Error realojando renderFinishedSemaphores");
        return 0;
    }
    eng->renderFinishedSemaphores = newSems;
    VkSemaphoreCreateInfo si = { VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO, NULL, 0 };
    for (uint32_t i = eng->renderFinishedSemaphoreCount; i < neededCount; i++) {
        eng->renderFinishedSemaphores[i] = VK_NULL_HANDLE;
        if (vkCreateSemaphore(eng->device, &si, NULL, &eng->renderFinishedSemaphores[i]) != VK_SUCCESS) {
            LOG_ERROR("Vulkan", "Error creando renderFinishedSemaphore %u", i);
            eng->renderFinishedSemaphoreCount = i;
            return 0;
        }
    }
    eng->renderFinishedSemaphoreCount = neededCount;
    return 1;
}

static void compute_sun_and_sky(float simHour, float outSunDir[4], float outSkyColor[4], float *outSkyR, float *outSkyG, float *outSkyB) {
    float sunAngle = ((simHour - 6.0f) / 24.0f) * 2.0f * (float)M_PI;
    float sunY = sinf(sunAngle);
    float sunX = cosf(sunAngle);

    outSunDir[0] = sunX;
    outSunDir[1] = (sunY > 0.05f) ? sunY : 0.05f;
    outSunDir[2] = 0.35f;
    outSunDir[3] = 0.16f + 0.22f * fmaxf(0.0f, sunY);

    float nightFactor = fmaxf(0.0f, -sunY * 1.5f);
    if (nightFactor > 1.0f) nightFactor = 1.0f;

    float skyR, skyG, skyB;
    if (simHour >= 6.0f && simHour < 18.0f) {
        if (simHour < 8.0f) { // Amanecer (06:00 - 08:00)
            float t = (simHour - 6.0f) / 2.0f;
            skyR = 0.90f * (1.0f - t) + 0.52f * t;
            skyG = 0.50f * (1.0f - t) + 0.68f * t;
            skyB = 0.30f * (1.0f - t) + 0.88f * t;
        } else if (simHour > 16.0f) { // Atardecer (16:00 - 18:00)
            float t = (simHour - 16.0f) / 2.0f;
            skyR = 0.52f * (1.0f - t) + 0.95f * t;
            skyG = 0.68f * (1.0f - t) + 0.45f * t;
            skyB = 0.88f * (1.0f - t) + 0.25f * t;
        } else { // Día pleno (08:00 - 16:00)
            skyR = 0.52f; skyG = 0.68f; skyB = 0.88f;
        }
    } else { // Noche (18:00 - 06:00)
        float t = (simHour >= 18.0f) ? (simHour - 18.0f) / 2.0f : (simHour < 6.0f) ? (6.0f - simHour) / 2.0f : 0.0f;
        if (t > 1.0f) t = 1.0f;
        skyR = 0.95f * (1.0f - t) + 0.02f * t;
        skyG = 0.45f * (1.0f - t) + 0.03f * t;
        skyB = 0.25f * (1.0f - t) + 0.08f * t;
    }

    outSkyColor[0] = skyR;
    outSkyColor[1] = skyG;
    outSkyColor[2] = skyB;
    outSkyColor[3] = nightFactor;
    *outSkyR = skyR;
    *outSkyG = skyG;
    *outSkyB = skyB;
}

static void draw_single_sector(const MacroSector *sec, VkCommandBuffer cmd, VkBuffer staticDummy,
                               const Frustum *frustum, int cullingEnabled,
                               int *visibleChunks, uint32_t *visibleVerts) {
    if (sec->vertexBuffer == VK_NULL_HANDLE) return;

    VkBuffer secVertexBuffers[] = { sec->vertexBuffer, staticDummy };
    VkDeviceSize secOffsets[] = { 0, 0 };
    vkCmdBindVertexBuffers(cmd, 0, 2, secVertexBuffers, secOffsets);

    int useIndexed = (sec->indexBuffer != VK_NULL_HANDLE);
    if (useIndexed) {
        vkCmdBindIndexBuffer(cmd, sec->indexBuffer, 0, VK_INDEX_TYPE_UINT32);
    }

    if (sec->chunkCount > 0) {
        for (int i = 0; i < sec->chunkCount; i++) {
            const Chunk *c = &sec->chunks[i];
            if (!cullingEnabled || frustum_test_aabb(frustum, &c->aabb)) {
                if (useIndexed) {
                    vkCmdDrawIndexed(cmd, c->count, 1, c->start, 0, 0);
                } else {
                    vkCmdDraw(cmd, c->count, 1, c->start, 0);
                }
                (*visibleChunks)++;
                (*visibleVerts) += c->count;
            }
        }
    } else {
        if (useIndexed) {
            vkCmdDrawIndexed(cmd, sec->vertexCount, 1, 0, 0, 0);
        } else {
            vkCmdDraw(cmd, sec->vertexCount, 1, 0, 0);
        }
        (*visibleChunks)++;
        (*visibleVerts) += sec->vertexCount;
    }
}

static void draw_sector_geometry(const VulkanEngine *eng, VkCommandBuffer cmd, VkBuffer staticDummy,
                                 const Frustum *frustum, int *totalActiveChunks,
                                 int *visibleChunks, uint32_t *visibleVerts) {
    for (int s = 0; s < eng->sectorSystem.sectorCount; s++) {
        const MacroSector *sec = &eng->sectorSystem.sectors[s];
        if (!sec->isLoaded) continue;

        (*totalActiveChunks) += (sec->chunkCount > 0) ? sec->chunkCount : 1;
        if (eng->cullingEnabled && !frustum_test_aabb(frustum, &sec->aabb)) continue;

        draw_single_sector(sec, cmd, staticDummy, frustum, eng->cullingEnabled,
                           visibleChunks, visibleVerts);
    }
}

static void draw_monolithic_geometry(const VulkanEngine *eng, VkCommandBuffer cmd,
                                     const Frustum *frustum, int *visibleChunks,
                                     uint32_t *visibleVerts) {
    if (eng->vertexBuffer == VK_NULL_HANDLE) return;

    if (eng->cullingEnabled && eng->chunksEnabled && eng->chunkSystem.chunkCount > 0) {
        const float maxDistSq = 2000.0f * 2000.0f; // 2.0 km de alcance visual en 3D
        for (int i = 0; i < eng->chunkSystem.chunkCount; i++) {
            const Chunk *c = &eng->chunkSystem.chunks[i];
            float midX = (c->aabb.min_x + c->aabb.max_x) * 0.5f;
            float midZ = (c->aabb.min_z + c->aabb.max_z) * 0.5f;
            float cdx = midX - g_camera.pos.x;
            float cdz = midZ - g_camera.pos.z;
            if ((cdx * cdx + cdz * cdz) > maxDistSq) continue;
            if (!frustum_test_aabb(frustum, &c->aabb)) continue;

            if (eng->indexBuffer != VK_NULL_HANDLE && eng->indexCount > 0) {
                if ((c->start + c->count) <= eng->indexCount) {
                    vkCmdDrawIndexed(cmd, c->count, 1, c->start, 0, 0);
                    (*visibleChunks)++;
                    (*visibleVerts) += c->count;
                }
            } else if ((c->start + c->count) <= (uint32_t)eng->baseVertexCount) {
                vkCmdDraw(cmd, c->count, 1, c->start, 0);
                (*visibleChunks)++;
                (*visibleVerts) += c->count;
            }
        }
        if (eng->vertexCount > eng->baseVertexCount) {
            uint32_t extraCount = (uint32_t)(eng->vertexCount - eng->baseVertexCount);
            vkCmdDraw(cmd, extraCount, 1, (uint32_t)eng->baseVertexCount, 0);
            (*visibleVerts) += extraCount;
        }
        return;
    }

    /* Fallback o Culling desactivado por opción de testing: dibujar todo */
    if (eng->indexBuffer != VK_NULL_HANDLE && eng->indexCount > 0) {
        vkCmdDrawIndexed(cmd, (uint32_t)eng->indexCount, 1, 0, 0, 0);
        if (eng->vertexCount > eng->baseVertexCount) {
            uint32_t extraCount = (uint32_t)(eng->vertexCount - eng->baseVertexCount);
            vkCmdDraw(cmd, extraCount, 1, (uint32_t)eng->baseVertexCount, 0);
        }
    } else {
        vkCmdDraw(cmd, (uint32_t)eng->vertexCount, 1, 0, 0);
    }
    *visibleChunks = (int)(eng->chunksEnabled ? eng->chunkSystem.chunkCount : 1);
    *visibleVerts = (uint32_t)eng->vertexCount;
}

static uint32_t draw_auxiliary_geometry(const VulkanEngine *eng, VkCommandBuffer cmd,
                                        VkBuffer staticDummy, uint32_t *visibleVerts) {
    if (eng->auxVertexBuffer == VK_NULL_HANDLE || eng->auxVertexCount == 0) {
        return 0;
    }
    VkBuffer auxBuffers[] = { eng->auxVertexBuffer, staticDummy };
    VkDeviceSize auxOffsets[] = { 0, 0 };
    vkCmdBindVertexBuffers(cmd, 0, 2, auxBuffers, auxOffsets);
    vkCmdDraw(cmd, (uint32_t)eng->auxVertexCount, 1, 0, 0);
    *visibleVerts += (uint32_t)eng->auxVertexCount;
    return 1;
}

static Uint64 render_hud_overlay(VulkanEngine *eng, VkCommandBuffer cmd, VkBuffer staticDummy,
                                 uint32_t frameIdx, float deltaTime, float simHour,
                                 int visibleChunks, int totalActiveChunks,
                                 uint32_t visibleVerts, uint32_t auxDrawCalls) {
    if (!eng->hudMappedDatas[frameIdx]) return 0;

    Uint64 hudStart = SDL_GetPerformanceCounter();
    debug_overlay_begin(&eng->debugOverlay,
        (float)eng->swapchainExtent.width,
        (float)eng->swapchainExtent.height);

    if (eng->showTelemetry) {
        TelemetrySystem t = {0};
        snprintf(t.gpuName, sizeof(t.gpuName), "%s", eng->gpuName);
        t.screenWidth = eng->swapchainExtent.width;
        t.screenHeight = eng->swapchainExtent.height;
        t.simHour = simHour;
        t.fps = eng->currentFps;
        t.frameTimeMs = (eng->currentFps > 0.1f) ? (1000.0f / eng->currentFps) : 0.0f;
        t.cpuTimeMs = eng->lastCpuTimeMs;
        t.gpuTimeMs = eng->lastGpuTimeMs;
        t.trafficSignalsCount = (uint32_t)eng->trafficSystem.signalCount;
        t.trafficIntersectionsCount = (uint32_t)eng->trafficSystem.intersectionCount;
        t.visibleChunks = (uint32_t)visibleChunks;
        t.totalChunks = (uint32_t)(eng->useSectorSystem ? totalActiveChunks :
                                   (eng->chunksEnabled ? eng->chunkSystem.chunkCount : 1));
        t.visibleVerts = visibleVerts;
        t.totalVerts = (uint32_t)((eng->useSectorSystem ? eng->sectorSystem.activeLoadedVerts : eng->vertexCount) +
                                  eng->auxVertexCount);
        t.drawCalls = (uint32_t)visibleChunks + auxDrawCalls;
        if (t.totalVerts > 0) {
            t.cullingEfficiencyPct = (1.0f - ((float)visibleVerts / (float)t.totalVerts)) * 100.0f;
        }

        debug_overlay_build_telemetry(&eng->debugOverlay, &t,
            g_camera.pos.x, g_camera.pos.y, g_camera.pos.z);
    }

    if (eng->isPaused) {
        pause_menu_render(&eng->debugOverlay, eng);
    }
    if (eng->notificationTimer > 0.0f) {
        eng->notificationTimer -= deltaTime;
        pause_menu_render_notification(&eng->debugOverlay, eng);
    }

    if (eng->debugOverlay.vertCount > 0) {
        memcpy(eng->hudMappedDatas[frameIdx], eng->debugOverlay.verts,
               eng->debugOverlay.vertCount * sizeof(Vertex));
    }
    Uint64 hudCpuTicks = SDL_GetPerformanceCounter() - hudStart;

    if (eng->debugOverlay.vertCount > 0) {
        PushConstants hudPc = {0};
        Mat4 identity = mat4_identity();
        memcpy(hudPc.mvp, identity.m, sizeof(hudPc.mvp));
        memcpy(hudPc.model, identity.m, sizeof(hudPc.model));
        vkCmdPushConstants(cmd, eng->pipelineLayout,
            VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
            0, sizeof(PushConstants), &hudPc);

        VkBuffer hudBufs[] = { eng->hudVertexBuffers[frameIdx], staticDummy };
        VkDeviceSize hudOff[] = { 0, 0 };
        vkCmdBindVertexBuffers(cmd, 0, 2, hudBufs, hudOff);
        vkCmdDraw(cmd, (uint32_t)eng->debugOverlay.vertCount, 1, 0, 0);
    }
    return hudCpuTicks;
}

static void update_draw_timing_stats(VulkanEngine *eng, Uint64 cpuPrepStart, Uint64 cpuPrepEnd,
                                     Uint64 gpuStart, Uint64 gpuEnd, Uint64 hudCpuTicks) {
    Uint64 perfFreq = SDL_GetPerformanceFrequency();
    if (perfFreq == 0) return;

    double ticksToMs = 1000.0 / (double)perfFreq;
    Uint64 prepTicks = (cpuPrepEnd > cpuPrepStart) ? (cpuPrepEnd - cpuPrepStart) : 0;
    float prepCpuMs = (float)((double)(prepTicks + hudCpuTicks) * ticksToMs);

    Uint64 gpuTicks = (gpuEnd > gpuStart) ? (gpuEnd - gpuStart) : 0;
    if (gpuTicks >= hudCpuTicks) gpuTicks -= hudCpuTicks;
    float cmdRecordCpuMs = (float)((double)gpuTicks * ticksToMs);

    eng->lastCpuTimeMs = eng->simCpuAccumMs + prepCpuMs + cmdRecordCpuMs;
    eng->simCpuAccumMs = 0.0f;

    if (eng->timestampQueryPool == VK_NULL_HANDLE) {
        eng->lastGpuTimeMs = cmdRecordCpuMs;
    }
}

static void read_frame_gpu_timestamp(VulkanEngine *eng, uint32_t frameIdx) {
    if (eng->timestampQueryPool == VK_NULL_HANDLE || !eng->timestampValid[frameIdx]) {
        return;
    }
    uint64_t ts[2] = {0, 0};
    VkResult res = vkGetQueryPoolResults(
        eng->device, eng->timestampQueryPool, frameIdx * 2, 2,
        sizeof(ts), ts, sizeof(uint64_t), VK_QUERY_RESULT_64_BIT);
    if (res == VK_SUCCESS && ts[1] >= ts[0]) {
        eng->lastGpuTimeMs = (float)((double)(ts[1] - ts[0]) * (double)eng->timestampPeriodNs / 1000000.0);
    }
}

static void cmd_begin_frame_timestamp(const VulkanEngine *eng, VkCommandBuffer cmd, uint32_t frameIdx) {
    if (eng->timestampQueryPool == VK_NULL_HANDLE) return;
    vkCmdResetQueryPool(cmd, eng->timestampQueryPool, frameIdx * 2, 2);
    vkCmdWriteTimestamp(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                        eng->timestampQueryPool, frameIdx * 2);
}

static void cmd_end_frame_timestamp(const VulkanEngine *eng, VkCommandBuffer cmd, uint32_t frameIdx) {
    if (eng->timestampQueryPool == VK_NULL_HANDLE) return;
    vkCmdWriteTimestamp(cmd, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,
                        eng->timestampQueryPool, frameIdx * 2 + 1);
}

static int acquire_frame_image(VulkanEngine *eng, uint32_t frameIdx, uint32_t *outImageIndex) {
    vkWaitForFences(eng->device, 1, &eng->inFlightFences[frameIdx], VK_TRUE, UINT64_MAX);
    if (!ensure_render_finished_semaphores(eng, eng->imageCount)) return 0;

    traffic_system_update_gpu_frame(&eng->trafficSystem, frameIdx);

    VkResult result = vkAcquireNextImageKHR(eng->device, eng->swapchain, UINT64_MAX,
                                           eng->imageAvailableSemaphores[frameIdx], VK_NULL_HANDLE, outImageIndex);
    if (result == VK_ERROR_OUT_OF_DATE_KHR) {
        recreate_swapchain(eng);
        return 0;
    }
    if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
        fprintf(stderr, "Error adquiriendo imagen de swapchain: %d\n", result);
        return 0;
    }
    if (*outImageIndex >= eng->renderFinishedSemaphoreCount &&
        !ensure_render_finished_semaphores(eng, *outImageIndex + 1)) {
        return 0;
    }
    return 1;
}


static void present_frame_image(VulkanEngine *eng, uint32_t imageIndex, VkSemaphore waitSem) {
    VkPresentInfoKHR presentInfo = {0};
    presentInfo.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
    presentInfo.waitSemaphoreCount = 1;
    presentInfo.pWaitSemaphores = &waitSem;
    presentInfo.swapchainCount = 1;
    presentInfo.pSwapchains = &eng->swapchain;
    presentInfo.pImageIndices = &imageIndex;

    VkResult result = vkQueuePresentKHR(eng->graphicsQueue, &presentInfo);
    if (result == VK_ERROR_OUT_OF_DATE_KHR || result == VK_SUBOPTIMAL_KHR || eng->framebufferResized) {
        eng->framebufferResized = 0;
        recreate_swapchain(eng);
    } else if (result != VK_SUCCESS) {
        fprintf(stderr, "Error al presentar swapchain: %d\n", result);
    }
}

void vulkan_draw(VulkanEngine *eng, float deltaTime) {
    // 0. Comprobar si la ventana está minimizada (ancho o alto = 0)
    int w = 0, h = 0;
    if (eng->window) {
        SDL_Vulkan_GetDrawableSize(eng->window, &w, &h);
        if (w == 0 || h == 0) return;
    }

    if (eng->isPaused && eng->trafficSignalMode != 0) {
        traffic_system_force_mode(&eng->trafficSystem, eng->trafficSignalMode);
    }

    eng->fpsAccum += deltaTime;
    eng->fpsFrameCount++;
    if (eng->fpsAccum >= 0.5f) {
        eng->currentFps = (float)eng->fpsFrameCount / eng->fpsAccum;
        eng->fpsFrameCount = 0;
        eng->fpsAccum = 0.0f;
    }

    // 2. Sincronización de fotograma (Doble Buffer Frames in Flight)
    uint32_t frameIdx = eng->currentFrame;
    uint32_t imageIndex = 0;
    if (!acquire_frame_image(eng, frameIdx, &imageIndex)) return;

    read_frame_gpu_timestamp(eng, frameIdx);

    // 3. Streaming de macro-sectores en VRAM (tras fence GPU) y matrices de Cámara (MVP)
    Uint64 cpuPrepStart = SDL_GetPerformanceCounter();
    if (eng->useSectorSystem) {
        sector_system_update(&eng->sectorSystem, eng, g_camera.pos.x, g_camera.pos.z, 2000.0f);
        eng->vertexCount = eng->sectorSystem.activeLoadedVerts;
    }

    vkResetCommandBuffer(eng->commandBuffers[frameIdx], 0);
    Vec3 forward, right, up;
    camera_get_vectors(&g_camera, &forward, &right, &up);
    Vec3 center = {
        g_camera.pos.x + forward.x,
        g_camera.pos.y + forward.y,
        g_camera.pos.z + forward.z
    };

    Mat4 view = mat4_lookat(g_camera.pos.x, g_camera.pos.y, g_camera.pos.z,
                            center.x, center.y, center.z,
                            up.x, up.y, up.z);
    float aspect = (float)eng->swapchainExtent.width / (float)eng->swapchainExtent.height;
    Mat4 proj = mat4_perspective_vk(DEG2RAD(60.0f), aspect, 1.0f, 15000.0f);
    Mat4 model = mat4_identity();
    Mat4 mvp = mat4_multiply(mat4_multiply(proj, view), model);

    PushConstants pc = {0};
    memcpy(pc.mvp, mvp.m, sizeof(pc.mvp));
    memcpy(pc.model, model.m, sizeof(pc.model));

    float simHour = eng->simHour;
    float skyR = 0.0f, skyG = 0.0f, skyB = 0.0f;
    float sunDir[4] = {0};
    float skyColor[4] = {0};
    compute_sun_and_sky(simHour, sunDir, skyColor, &skyR, &skyG, &skyB);

    if (eng->lightingUboMapped[frameIdx]) {
        LightingUBO *ubo = eng->lightingUboMapped[frameIdx];
        Vec3 camPos = g_camera.pos;
        Vec3 camFwd = forward;
        lighting_system_update(&eng->lightingSystem, &eng->trafficSystem,
                               simHour, &camPos, &camFwd, ubo);
        memcpy(ubo->sunDir, sunDir, sizeof(ubo->sunDir));
        memcpy(ubo->skyColor, skyColor, sizeof(ubo->skyColor));
        ubo->timeParams[0] = simHour;
        ubo->timeParams[1] = g_camera.pos.x;
        ubo->timeParams[2] = g_camera.pos.y;
        ubo->timeParams[3] = g_camera.pos.z;
    }

    Frustum frustum = frustum_extract(mvp.m);
    int visibleChunks = 0;
    int totalActiveChunks = 0;
    uint32_t visibleVerts = 0;
    Uint64 cpuPrepEnd = SDL_GetPerformanceCounter();

    // 4. Grabar comandos de renderizado
    Uint64 gpuStart = SDL_GetPerformanceCounter();
    VkCommandBuffer cmd = eng->commandBuffers[frameIdx];
    VkCommandBufferBeginInfo beginInfo = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO, NULL, 0, NULL};
    vkBeginCommandBuffer(cmd, &beginInfo);
    cmd_begin_frame_timestamp(eng, cmd, frameIdx);

    VkClearValue clearValues[2] = {
        {.color = {{skyR, skyG, skyB, 1.0f}}},
        {.depthStencil = {1.0f, 0}}
    };

    VkRenderPassBeginInfo passInfo = {0};
    passInfo.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
    passInfo.renderPass = eng->renderPass;
    passInfo.framebuffer = eng->framebuffers[imageIndex];
    passInfo.renderArea.extent = eng->swapchainExtent;
    passInfo.clearValueCount = 2;
    passInfo.pClearValues = clearValues;

    vkCmdBeginRenderPass(cmd, &passInfo, VK_SUBPASS_CONTENTS_INLINE);
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, eng->graphicsPipeline);

    VkViewport viewport = {
        .x = 0.0f, .y = 0.0f,
        .width = (float)eng->swapchainExtent.width,
        .height = (float)eng->swapchainExtent.height,
        .minDepth = 0.0f, .maxDepth = 1.0f
    };
    vkCmdSetViewport(cmd, 0, 1, &viewport);

    VkRect2D scissor = { .offset = {0, 0}, .extent = eng->swapchainExtent };
    vkCmdSetScissor(cmd, 0, 1, &scissor);

    vkCmdPushConstants(cmd, eng->pipelineLayout,
                       VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
                       0, sizeof(PushConstants), &pc);

    VkBuffer staticDummy = car_system_get_static_dummy(&eng->carSystem);
    if (!eng->useSectorSystem && eng->vertexBuffer != VK_NULL_HANDLE) {
        VkBuffer vertexBuffers[] = { eng->vertexBuffer, staticDummy };
        VkDeviceSize offsets[] = { 0, 0 };
        vkCmdBindVertexBuffers(cmd, 0, 2, vertexBuffers, offsets);
    }

    if (eng->textureSampler != VK_NULL_HANDLE) {
        vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS,
                                eng->pipelineLayout, 0, 1, &eng->descriptorSets[frameIdx], 0, NULL);
    }

    if (eng->indexBuffer != VK_NULL_HANDLE && eng->indexCount > 0) {
        vkCmdBindIndexBuffer(cmd, eng->indexBuffer, 0, VK_INDEX_TYPE_UINT32);
    }

    // === RENDER: Macro-Sectores Modulares (<99MB) o Chunks Monolíticos ===
    if (eng->useSectorSystem) {
        draw_sector_geometry(eng, cmd, staticDummy, &frustum,
                             &totalActiveChunks, &visibleChunks, &visibleVerts);
    } else {
        draw_monolithic_geometry(eng, cmd, &frustum, &visibleChunks, &visibleVerts);
    }

    // === RENDER: Geometría Auxiliar (Gemini AI OBJs, Photo Planes, Debug RoadGraph) ===
    uint32_t auxDrawCalls = draw_auxiliary_geometry(eng, cmd, staticDummy, &visibleVerts);

    // === RENDER: Instanced Cars (200 coches en ≈6 draw calls) ===
    car_system_render(&eng->carSystem, cmd, frameIdx);

    // === RENDER: Lentes Dinámicos de Semáforos (1 solo draw call desacoplado) ===
    traffic_system_render(&eng->trafficSystem, cmd, frameIdx, staticDummy);

    eng->lastDrawCalls = (uint32_t)visibleChunks + auxDrawCalls + 6 + 1;
    eng->lastVisibleVerts = visibleVerts;

    // === RENDER: HUD Debug Overlay & Menú de Pausa ===
    Uint64 hudCpuTicks = render_hud_overlay(eng, cmd, staticDummy, frameIdx, deltaTime, simHour,
                                            visibleChunks, totalActiveChunks, visibleVerts, auxDrawCalls);

    eng->chunkSystem.visibleChunks = visibleChunks;
    eng->chunkSystem.visibleVerts = visibleVerts;

    vkCmdEndRenderPass(cmd);
    cmd_end_frame_timestamp(eng, cmd, frameIdx);
    vkEndCommandBuffer(cmd);

    // 5. Envío y presentación a la pantalla
    VkSemaphore waitSemaphores[] = { eng->imageAvailableSemaphores[frameIdx] };
    VkPipelineStageFlags waitStages[] = { VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT };
    VkSemaphore signalSemaphores[] = { eng->renderFinishedSemaphores[imageIndex] };

    VkSubmitInfo submitInfo = {0};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.waitSemaphoreCount = 1;
    submitInfo.pWaitSemaphores = waitSemaphores;
    submitInfo.pWaitDstStageMask = waitStages;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &cmd;
    submitInfo.signalSemaphoreCount = 1;
    submitInfo.pSignalSemaphores = signalSemaphores;

    vkResetFences(eng->device, 1, &eng->inFlightFences[frameIdx]);
    VkResult submitRes = vkQueueSubmit(eng->graphicsQueue, 1, &submitInfo, eng->inFlightFences[frameIdx]);
    if (submitRes == VK_SUCCESS && eng->timestampQueryPool != VK_NULL_HANDLE) {
        eng->timestampValid[frameIdx] = 1;
    }
    Uint64 gpuEnd = SDL_GetPerformanceCounter();
    update_draw_timing_stats(eng, cpuPrepStart, cpuPrepEnd, gpuStart, gpuEnd, hudCpuTicks);

    present_frame_image(eng, imageIndex, signalSemaphores[0]);
    eng->currentFrame = (eng->currentFrame + 1) % MAX_FRAMES_IN_FLIGHT;
}

void vulkan_destroy(VulkanEngine *eng) {
    vkDeviceWaitIdle(eng->device);

    traffic_system_free_gpu(&eng->trafficSystem, eng->device);
    traffic_system_free(&eng->trafficSystem);
    car_system_free(&eng->carSystem, eng->device);
    if (eng->roadGraph) {
        road_graph_free(eng->roadGraph);
        eng->roadGraph = NULL;
    }

    if (eng->useSectorSystem) {
        sector_system_destroy(&eng->sectorSystem, eng);
    }

    if (eng->vertexBuffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, eng->vertexBuffer, NULL);
        eng->vertexBuffer = VK_NULL_HANDLE;
    }
    if (eng->indexBuffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, eng->indexBuffer, NULL);
        eng->indexBuffer = VK_NULL_HANDLE;
    }
    if (eng->auxVertexBuffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, eng->auxVertexBuffer, NULL);
        eng->auxVertexBuffer = VK_NULL_HANDLE;
    }
    free(eng->vertexData);
    eng->vertexData = NULL;
    free(eng->indexData);
    eng->indexData = NULL;
    free(eng->auxVertexData);
    eng->auxVertexData = NULL;
    eng->auxVertexCount = 0;

    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        eng->hudMappedDatas[i] = NULL;
        if (eng->hudVertexBuffers[i] != VK_NULL_HANDLE) {
            vkDestroyBuffer(eng->device, eng->hudVertexBuffers[i], NULL);
            eng->hudVertexBuffers[i] = VK_NULL_HANDLE;
        }
    }

    if (eng->timestampQueryPool != VK_NULL_HANDLE) {
        vkDestroyQueryPool(eng->device, eng->timestampQueryPool, NULL);
        eng->timestampQueryPool = VK_NULL_HANDLE;
    }

    cleanup_texture_resources(eng);
    cleanup_pipeline_and_sync(eng);
    cleanup_swapchain_and_depth(eng);

    // Destruir subasignadores centrales de memoria (Tier S #2)
    vulkan_memory_pool_destroy(&eng->vramBufferPool);
    vulkan_memory_pool_destroy(&eng->vramImagePool);
    vulkan_memory_pool_destroy(&eng->hostVisiblePool);

    cleanup_vulkan_instance_and_device(eng);
}
