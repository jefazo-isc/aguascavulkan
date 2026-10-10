#include "vulkan.h"
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

#define DEM_ORIGIN_LAT 21.8807
#define DEM_ORIGIN_LON (-102.2965)
#define DEM_M_PER_LAT 111320.0
#define DEM_MIN_LON (-102.3110)
#define DEM_MAX_LON (-102.2815)
#define DEM_MIN_LAT 21.8690
#define DEM_MAX_LAT 21.8940
#define DEM_NX 40
#define DEM_NY 40
#define DEM_BASE_ELEVATION 1865.0f

float vulkan_get_ground_elevation(VulkanEngine *eng, float x, float z) {
    (void)eng; // Puede usarse para consultar buffers adicionales si fuera necesario

    double m_per_lon = DEM_M_PER_LAT * cos(DEM_ORIGIN_LAT * (M_PI / 180.0));
    double lon = DEM_ORIGIN_LON + (double)x / m_per_lon;
    double lat = DEM_ORIGIN_LAT - (double)z / DEM_M_PER_LAT;

    double u = (lon - DEM_MIN_LON) / (DEM_MAX_LON - DEM_MIN_LON) * (DEM_NX - 1);
    double v = (lat - DEM_MIN_LAT) / (DEM_MAX_LAT - DEM_MIN_LAT) * (DEM_NY - 1);

    if (u < 0.0) u = 0.0;
    if (u > (double)(DEM_NX - 1)) u = (double)(DEM_NX - 1);
    if (v < 0.0) v = 0.0;
    if (v > (double)(DEM_NY - 1)) v = (double)(DEM_NY - 1);

    int i = (int)u;
    int j = (int)v;
    if (i > DEM_NX - 2) i = DEM_NX - 2;
    if (j > DEM_NY - 2) j = DEM_NY - 2;

    float du = (float)(u - i);
    float dv = (float)(v - j);

    float h00 = s_demGrid[j][i];
    float h10 = s_demGrid[j][i + 1];
    float h01 = s_demGrid[j + 1][i];
    float h11 = s_demGrid[j + 1][i + 1];

    float h0 = h00 * (1.0f - du) + h10 * du;
    float h1 = h01 * (1.0f - du) + h11 * du;
    float dem_h = h0 * (1.0f - dv) + h1 * dv;

    float y = dem_h - DEM_BASE_ELEVATION;

    // Escarpes geológicos reales de Aguascalientes (Falla San Marcos y Falla Oriente)
    double fault_sm_x = (-102.3012 - DEM_ORIGIN_LON) * m_per_lon;
    double fault_or_x = (-102.2865 - DEM_ORIGIN_LON) * m_per_lon;

    float d_sm = (float)((x - fault_sm_x) / 12.0);
    float scarp_sm = -2.2f * (0.5f - 0.5f * tanhf(d_sm));

    float d_or = (float)((x - fault_or_x) / 12.0);
    float scarp_or = -1.8f * (0.5f + 0.5f * tanhf(d_or));

    return y + scarp_sm + scarp_or;
}

static int load_primary_geometry(VulkanEngine *eng) {
    Mesh* mesh = NULL;

    // 1. Intentar cargar modelo binario glTF (.glb)
    const char* glbFile = "models/aguascalientes_sector1.glb";
    FILE* checkGLB = fopen(glbFile, "rb");
    if (checkGLB) {
        fclose(checkGLB);
        printf("[Motor] Cargando geometría glTF: %s...\n", glbFile);
        mesh = gltf_load(glbFile);
    }

    // 2. Si no hay .glb, cargar el modelo .obj existente
    if (!mesh) {
        const char* objFile = "models/aguascalientes_sector1.obj";
        FILE* checkOBJ = fopen(objFile, "r");
        if (checkOBJ) {
            fclose(checkOBJ);
        } else {
            objFile = "models/test.obj";
        }
        printf("[Motor] Cargando geometría OBJ: %s...\n", objFile);
        mesh = obj_load(objFile);
    }

    if (!mesh) {
        fprintf(stderr, "[Motor] No se pudo cargar ningún modelo 3D inicial\n");
        return 0;
    }

    eng->vertexCount = mesh->vertexCount;
    eng->vertexData = mesh->vertices;
    mesh->vertices = NULL; // Traspasar la propiedad para que obj_free no lo libere
    obj_free(mesh);

    // ============================================================
    // 3. Cargar edificios y props generados por Gemini AI desde disco
    //    Escanea models/generated/*.obj y los agrega al buffer unificado.
    //    Alinea la cota Y con la elevación topográfica real (cero subsuelo).
    //    Marca visual: rayo vertical cyan brillante (beacon).
    // ============================================================
    {
        const char* genDir = "models/generated";
        DIR* dir = opendir(genDir);
        if (dir) {
            struct dirent* entry;
            size_t geminiTotal = 0;
            while ((entry = readdir(dir)) != NULL) {
                // Solo archivos .obj
                size_t nameLen = strlen(entry->d_name);
                if (nameLen < 5) continue;
                if (strcmp(entry->d_name + nameLen - 4, ".obj") != 0) continue;

                char fullPath[512];
                snprintf(fullPath, sizeof(fullPath), "%s/%s", genDir, entry->d_name);

                Mesh* geminiMesh = obj_load(fullPath);
                if (geminiMesh) {
                    if (geminiMesh->vertexCount > 0) {
                    // Calcular centro X, Z y bounding box del objeto
                    float minX = 1e9f, maxX = -1e9f;
                    float minY = 1e9f, maxY = -1e9f;
                    float minZ = 1e9f, maxZ = -1e9f;
                    for (size_t v = 0; v < geminiMesh->vertexCount; v++) {
                        if (geminiMesh->vertices[v].x < minX) minX = geminiMesh->vertices[v].x;
                        if (geminiMesh->vertices[v].x > maxX) maxX = geminiMesh->vertices[v].x;
                        if (geminiMesh->vertices[v].y < minY) minY = geminiMesh->vertices[v].y;
                        if (geminiMesh->vertices[v].y > maxY) maxY = geminiMesh->vertices[v].y;
                        if (geminiMesh->vertices[v].z < minZ) minZ = geminiMesh->vertices[v].z;
                        if (geminiMesh->vertices[v].z > maxZ) maxZ = geminiMesh->vertices[v].z;
                    }
                    float cx = (minX + maxX) * 0.5f;
                    float cz = (minZ + maxZ) * 0.5f;

                    // Obtener la cota topográfica real en las coordenadas del objeto
                    float groundY = vulkan_get_ground_elevation(eng, cx, cz);

                    // Si el modelo viene con origen local en Y=0 (o por debajo de la cota),
                    // ajustar automáticamente para que la base descanse sobre la superficie
                    float yAdjustment = 0.0f;
                    if (minY < groundY - 0.5f || (fabsf(minY) < 0.2f && groundY > 0.5f)) {
                        yAdjustment = (groundY + 0.05f) - minY;
                    }

                    float baseY = minY + yAdjustment;

                    // ── Beacon: rayo vertical brillante (2 quads en cruz, 200m de alto) ──
                    #define BEACON_HEIGHT 200.0f
                    #define BEACON_HALF_W 0.4f
                    #define BEACON_VERTS 12  // 2 quads × 2 triángulos × 3 vértices
                    size_t beaconCount = BEACON_VERTS;

                    // Necesitamos espacio para el edificio + beacon
                    size_t newCount = eng->vertexCount + geminiMesh->vertexCount + beaconCount;
                    Vertex* newData = realloc(eng->vertexData, newCount * sizeof(Vertex));
                    if (newData) {
                        // Copiar vértices del edificio aplicando corrección de altura
                        size_t baseIdx = eng->vertexCount;
                        for (size_t v = 0; v < geminiMesh->vertexCount; v++) {
                            Vertex vert = geminiMesh->vertices[v];
                            vert.y += yAdjustment;
                            // Mantener un sutil brillo ambiental para visibilidad nocturna
                            if (vert.emission == 0.0f) {
                                vert.emission = 0.04f;
                            }
                            newData[baseIdx + v] = vert;
                        }

                        // ── Generar beacon (rayo vertical) desde la base real ──
                        size_t bi = baseIdx + geminiMesh->vertexCount;
                        float topY = baseY + BEACON_HEIGHT;

                        // Color del rayo: cyan brillante con emisión máxima
                        Vertex bv = {0};
                        bv.r = 0.0f; bv.g = 0.9f; bv.b = 1.0f; bv.a = 1.0f;
                        bv.emission = 1.5f; // Muy brillante
                        bv.nx = 0.0f; bv.ny = 0.0f; bv.nz = 1.0f;

                        // Quad 1 (plano XY) — triángulo A
                        bv.x = cx - BEACON_HALF_W; bv.y = baseY; bv.z = cz; newData[bi++] = bv;
                        bv.x = cx + BEACON_HALF_W; bv.y = baseY; bv.z = cz; newData[bi++] = bv;
                        bv.x = cx + BEACON_HALF_W; bv.y = topY;  bv.z = cz; newData[bi++] = bv;
                        // Quad 1 — triángulo B
                        bv.x = cx - BEACON_HALF_W; bv.y = baseY; bv.z = cz; newData[bi++] = bv;
                        bv.x = cx + BEACON_HALF_W; bv.y = topY;  bv.z = cz; newData[bi++] = bv;
                        bv.x = cx - BEACON_HALF_W; bv.y = topY;  bv.z = cz; newData[bi++] = bv;

                        // Quad 2 (plano ZY) — triángulo A
                        bv.nx = 1.0f; bv.nz = 0.0f;
                        bv.x = cx; bv.y = baseY; bv.z = cz - BEACON_HALF_W; newData[bi++] = bv;
                        bv.x = cx; bv.y = baseY; bv.z = cz + BEACON_HALF_W; newData[bi++] = bv;
                        bv.x = cx; bv.y = topY;  bv.z = cz + BEACON_HALF_W; newData[bi++] = bv;
                        // Quad 2 — triángulo B
                        bv.x = cx; bv.y = baseY; bv.z = cz - BEACON_HALF_W; newData[bi++] = bv;
                        bv.x = cx; bv.y = topY;  bv.z = cz + BEACON_HALF_W; newData[bi++] = bv;
                        bv.x = cx; bv.y = topY;  bv.z = cz - BEACON_HALF_W; newData[bi++] = bv;

                        eng->vertexData = newData;
                        eng->vertexCount = newCount;
                        geminiTotal += geminiMesh->vertexCount + beaconCount;
                        printf("[Motor] +Gemini AI: %s (%zu vértices + beacon en X:%.1f, Y:%.2f, Z:%.1f)\n",
                               entry->d_name, geminiMesh->vertexCount, cx, baseY, cz);
                    }
                }
                obj_free(geminiMesh);
            }
            }
            closedir(dir);
            if (geminiTotal > 0) {
                printf("[Motor] 🤖 Props Gemini colocados sobre terreno: %zu vértices totales\n", geminiTotal);
            }
        }
    }

    // ============================================================
    // 4. Cargar Grafo Vial y generar malla de depuración
    // ============================================================
    const char* roadBin = "models/road_network.bin";
    eng->roadGraph = road_graph_load(roadBin);
    if (eng->roadGraph) {
        Mesh* debugMesh = road_graph_build_debug_mesh(eng->roadGraph);
        if (debugMesh && debugMesh->vertexCount > 0) {
            size_t newCount = eng->vertexCount + debugMesh->vertexCount;
            Vertex* newData = realloc(eng->vertexData, newCount * sizeof(Vertex));
            if (newData) {
                memcpy(newData + eng->vertexCount, debugMesh->vertices, debugMesh->vertexCount * sizeof(Vertex));
                eng->vertexData = newData;
                eng->vertexCount = newCount;
                printf("[Motor] 🚦 Malla de depuración del Grafo Vial agregada (%zu vértices)\n", debugMesh->vertexCount);
            }
            obj_free(debugMesh);
        }
    }

    // Crear Vertex Buffer en GPU
    size_t bufferSize = eng->vertexCount * sizeof(Vertex);
    VkBufferCreateInfo bufferInfo = {0};
    bufferInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    bufferInfo.size = bufferSize;
    bufferInfo.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
    bufferInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    if (vkCreateBuffer(eng->device, &bufferInfo, NULL, &eng->vertexBuffer) != VK_SUCCESS) {
        return 0;
    }

    VkMemoryRequirements memReqs;
    vkGetBufferMemoryRequirements(eng->device, eng->vertexBuffer, &memReqs);

    uint32_t memoryType = find_memory_type(eng->physicalDevice, memReqs.memoryTypeBits,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (memoryType == UINT32_MAX) return 0;

    VkMemoryAllocateInfo memAllocInfo = {0};
    memAllocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    memAllocInfo.allocationSize = memReqs.size;
    memAllocInfo.memoryTypeIndex = memoryType;

    if (vkAllocateMemory(eng->device, &memAllocInfo, NULL, &eng->vertexBufferMemory) != VK_SUCCESS) {
        return 0;
    }
    vkBindBufferMemory(eng->device, eng->vertexBuffer, eng->vertexBufferMemory, 0);

    // Mapear persistentemente para permitir actualizaciones en vivo de semáforos
    vkMapMemory(eng->device, eng->vertexBufferMemory, 0, bufferSize, 0, (void**)&eng->mappedVertexData);
    memcpy(eng->mappedVertexData, eng->vertexData, bufferSize);

    return 1;
}

int vulkan_init(VulkanEngine *eng, SDL_Window *window) {
    memset(eng, 0, sizeof(VulkanEngine));
    eng->window = window;

    if (!init_vulkan_instance_and_device(eng, window)) return 0;
    if (!create_swapchain_and_depth(eng)) return 0;
    if (!create_render_pass(eng)) return 0;
    if (!create_framebuffers(eng)) return 0;
    if (!create_sync_objects(eng)) return 0;
    if (!create_pipeline_and_descriptors(eng)) return 0;

    // Cargar satélite
    const char* texFile = "assets/satellite.png";
    if (!init_satellite_texture(eng, texFile)) {
        printf("[Motor] Textura %s no disponible, inicializando modo color.\n", texFile);
    }

    // Cargar geometría
    if (!load_primary_geometry(eng)) return 0;

    // Iniciar sistema de tráfico dinámico
    traffic_system_init(&eng->trafficSystem);
    traffic_system_load_json(&eng->trafficSystem, "models/traffic_signals.json");
    if (eng->mappedVertexData) {
        traffic_system_update(&eng->trafficSystem, 0.0f, eng->mappedVertexData, eng->vertexCount);
    }

    // Iniciar sistema de iluminación dinámica (farolas viales, semáforos, linterna)
    lighting_system_init(&eng->lightingSystem, &eng->trafficSystem);

    // Iniciar sistema cinemático de coches
    car_system_init(&eng->carSystem, eng->device, eng->physicalDevice);

    // Cargar sistema de chunks para frustum culling
    eng->chunksEnabled = chunk_system_load(&eng->chunkSystem, "models/chunks.json");

    // Crear HUD vertex buffer para debug overlay (mapeado persistentemente)
    {
        VkDeviceSize hudBufSize = DEBUG_MAX_VERTS * sizeof(Vertex);
        VkBufferCreateInfo bi = {0};
        bi.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        bi.size = hudBufSize;
        bi.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
        bi.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        if (vkCreateBuffer(eng->device, &bi, NULL, &eng->hudVertexBuffer) == VK_SUCCESS) {
            VkMemoryRequirements mr;
            vkGetBufferMemoryRequirements(eng->device, eng->hudVertexBuffer, &mr);
            uint32_t mt = find_memory_type(eng->physicalDevice, mr.memoryTypeBits,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
            if (mt != UINT32_MAX) {
                VkMemoryAllocateInfo mai = {0};
                mai.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
                mai.allocationSize = mr.size;
                mai.memoryTypeIndex = mt;
                vkAllocateMemory(eng->device, &mai, NULL, &eng->hudVertexBufferMemory);
                vkBindBufferMemory(eng->device, eng->hudVertexBuffer, eng->hudVertexBufferMemory, 0);
                vkMapMemory(eng->device, eng->hudVertexBufferMemory, 0, hudBufSize, 0, (void**)&eng->hudMappedData);
            }
        }
    }
    eng->currentFps = 60.0f;

    // Inicializar estado de pausa y testing
    eng->isPaused = 0;
    eng->pauseMenuIndex = 0;
    eng->timeScale = 1.0f;
    eng->timeScaleIndex = 0;
    eng->simHour = 14.0f; /* 14:00 hrs: luz diurna plena por defecto */
    eng->timeFrozen = 0;
    eng->showTelemetry = 1;
    eng->cullingEnabled = eng->chunksEnabled;
    eng->timePresetIndex = 0;
    eng->camSpeedIndex = 1;
    eng->trafficSignalMode = 0;
    eng->notificationTimer = 0.0f;

    printf("[Motor] StreetVulkan inicializado con éxito. Vértices activos: %zu\n", eng->vertexCount);
    if (eng->chunksEnabled)
        printf("[Motor] Frustum culling ACTIVO (%d chunks de %.0fm)\n",
               eng->chunkSystem.chunkCount, eng->chunkSystem.chunkSize);
    return 1;
}

void vulkan_draw(VulkanEngine *eng, float deltaTime) {
    // 0. Comprobar si la ventana está minimizada (ancho o alto = 0)
    int w = 0, h = 0;
    if (eng->window) {
        SDL_Vulkan_GetDrawableSize(eng->window, &w, &h);
        if (w == 0 || h == 0) {
            return;
        }
    }

    // 1. Actualizar luces dinámicas de semáforos (respeta pausa y velocidad de simulación)
    if (eng->trafficSignalMode != 0) {
        traffic_system_force_mode(&eng->trafficSystem, eng->trafficSignalMode, eng->mappedVertexData, eng->vertexCount);
    } else {
        float trafficDelta = eng->isPaused ? 0.0f : (deltaTime * eng->timeScale);
        traffic_system_update(&eng->trafficSystem, trafficDelta, eng->mappedVertexData, eng->vertexCount);
    }

    // FPS counter
    eng->fpsAccum += deltaTime;
    eng->fpsFrameCount++;
    if (eng->fpsAccum >= 0.5f) {
        eng->currentFps = (float)eng->fpsFrameCount / eng->fpsAccum;
        eng->fpsFrameCount = 0;
        eng->fpsAccum = 0.0f;
    }

    // 2. Sincronización de fotograma
    vkWaitForFences(eng->device, 1, &eng->inFlightFence, VK_TRUE, UINT64_MAX);

    uint32_t imageIndex;
    VkResult result = vkAcquireNextImageKHR(eng->device, eng->swapchain, UINT64_MAX,
                                           eng->imageAvailableSemaphore, VK_NULL_HANDLE, &imageIndex);
    if (result == VK_ERROR_OUT_OF_DATE_KHR) {
        recreate_swapchain(eng);
        return;
    } else if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
        fprintf(stderr, "Error adquiriendo imagen de swapchain: %d\n", result);
        return;
    }

    vkResetFences(eng->device, 1, &eng->inFlightFence);
    vkResetCommandBuffer(eng->commandBuffer, 0);

    // 3. Matrices de Cámara (MVP)
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
    Mat4 proj = mat4_perspective_vk(DEG2RAD(60.0f), aspect, 1.0f, 10000.0f);
    Mat4 model = mat4_identity();
    Mat4 vp = mat4_multiply(proj, view);
    Mat4 mvp = mat4_multiply(vp, model);

    // 3a. Ciclo Día/Noche (72 minutos reales = 24 horas simuladas con timeScale y pausa)
    if (!eng->isPaused && !eng->timeFrozen) {
        eng->simHour += (deltaTime * eng->timeScale) / 180.0f;
        if (eng->simHour >= 24.0f) eng->simHour = fmodf(eng->simHour, 24.0f);
        if (eng->simHour < 0.0f) eng->simHour += 24.0f;
    }
    float simHour = eng->simHour;

    float sunAngle = ((simHour - 6.0f) / 24.0f) * 2.0f * (float)M_PI;
    float sunY = sinf(sunAngle);
    float sunX = cosf(sunAngle);

    PushConstants pc;
    memcpy(pc.mvp, mvp.m, sizeof(pc.mvp));
    memcpy(pc.model, model.m, sizeof(pc.model));

    pc.sunDir[0] = sunX;
    pc.sunDir[1] = (sunY > 0.05f) ? sunY : 0.05f;
    pc.sunDir[2] = 0.35f;

    float ambient = 0.22f + 0.68f * fmaxf(0.0f, sunY);
    pc.sunDir[3] = ambient;

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

    pc.skyColor[0] = skyR;
    pc.skyColor[1] = skyG;
    pc.skyColor[2] = skyB;
    pc.skyColor[3] = nightFactor;

    pc.timeParams[0] = simHour;

    // 3b. Actualizar UBO de luces dinámicas (Semáforos, Farolas, Beacons, Linterna)
    if (eng->lightingUboMapped) {
        Vec3 camPos = g_camera.pos;
        Vec3 camFwd = forward;
        lighting_system_update(&eng->lightingSystem,
                               &eng->trafficSystem,
                               simHour,
                               &camPos,
                               &camFwd,
                               eng->lightingUboMapped);
    }

    // Actualizar movimiento cinemático de los 200 coches
    if (eng->roadGraph) {
        car_system_update(&eng->carSystem, eng->roadGraph, deltaTime, g_camera.pos.x, g_camera.pos.z);
    }

    // 3c. Frustum culling
    Frustum frustum = frustum_extract(mvp.m);
    int visibleChunks = 0;
    uint32_t visibleVerts = 0;

    // 4. Grabar comandos de renderizado
    VkCommandBufferBeginInfo beginInfo = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO, NULL, 0, NULL};
    vkBeginCommandBuffer(eng->commandBuffer, &beginInfo);

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

    vkCmdBeginRenderPass(eng->commandBuffer, &passInfo, VK_SUBPASS_CONTENTS_INLINE);
    vkCmdBindPipeline(eng->commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, eng->graphicsPipeline);

    VkViewport viewport = {
        .x = 0.0f,
        .y = 0.0f,
        .width = (float)eng->swapchainExtent.width,
        .height = (float)eng->swapchainExtent.height,
        .minDepth = 0.0f,
        .maxDepth = 1.0f
    };
    vkCmdSetViewport(eng->commandBuffer, 0, 1, &viewport);

    VkRect2D scissor = {
        .offset = {0, 0},
        .extent = eng->swapchainExtent
    };
    vkCmdSetScissor(eng->commandBuffer, 0, 1, &scissor);

    vkCmdPushConstants(eng->commandBuffer, eng->pipelineLayout,
                       VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
                       0, sizeof(PushConstants), &pc);

    // Geometría estática: binding 1 apunta al dummy (tint.a=0 → shader ignora transform de instancia)
    VkBuffer staticDummy = car_system_get_static_dummy(&eng->carSystem);
    VkBuffer vertexBuffers[] = { eng->vertexBuffer, staticDummy };
    VkDeviceSize offsets[] = { 0, 0 };
    vkCmdBindVertexBuffers(eng->commandBuffer, 0, 2, vertexBuffers, offsets);

    if (eng->textureSampler != VK_NULL_HANDLE) {
        vkCmdBindDescriptorSets(eng->commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS,
                                eng->pipelineLayout, 0, 1, &eng->descriptorSet, 0, NULL);
    }

    // === RENDER: Per-chunk frustum-culled draw calls ===
    if (eng->cullingEnabled && eng->chunksEnabled && eng->chunkSystem.chunkCount > 0) {
        for (int i = 0; i < eng->chunkSystem.chunkCount; i++) {
            Chunk *c = &eng->chunkSystem.chunks[i];
            if (frustum_test_aabb(&frustum, &c->aabb)) {
                vkCmdDraw(eng->commandBuffer, c->count, 1, c->start, 0);
                visibleChunks++;
                visibleVerts += c->count;
            }
        }
    } else {
        /* Fallback o Culling desactivado por opción de testing: dibujar todo */
        vkCmdDraw(eng->commandBuffer, (uint32_t)eng->vertexCount, 1, 0, 0);
        visibleChunks = (int)(eng->chunksEnabled ? eng->chunkSystem.chunkCount : 1);
        visibleVerts = (uint32_t)eng->vertexCount;
    }

    // === RENDER: Instanced Cars (200 coches en ≈6 draw calls) ===
    car_system_render(&eng->carSystem, eng->commandBuffer);

    // === RENDER: HUD Debug Overlay & Menú de Pausa ===
    if (eng->hudMappedData) {
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
            t.cpuTimeMs = 0.5f; /* Estimado de actualización física/tráfico */
            t.gpuTimeMs = (t.frameTimeMs > 0.5f) ? (t.frameTimeMs - 0.5f) : 0.1f;
            t.trafficSignalsCount = (uint32_t)eng->trafficSystem.signalCount;
            t.trafficIntersectionsCount = (uint32_t)eng->trafficSystem.intersectionCount;
            t.visibleChunks = (uint32_t)visibleChunks;
            t.totalChunks = (uint32_t)(eng->chunksEnabled ? eng->chunkSystem.chunkCount : 1);
            t.visibleVerts = visibleVerts;
            t.totalVerts = (uint32_t)eng->vertexCount;
            t.drawCalls = (uint32_t)visibleChunks;
            if (t.totalVerts > 0) {
                t.cullingEfficiencyPct = (1.0f - ((float)visibleVerts / (float)t.totalVerts)) * 100.0f;
            }

            debug_overlay_build_telemetry(&eng->debugOverlay, &t,
                g_camera.pos.x, g_camera.pos.y, g_camera.pos.z);
        }

        // Renderizar Menú de Pausa si el simulador está en pausa
        if (eng->isPaused) {
            pause_menu_render(&eng->debugOverlay, eng);
        }

        // Renderizar notificación flotante de testing si está activa
        if (eng->notificationTimer > 0.0f) {
            eng->notificationTimer -= deltaTime;
            pause_menu_render_notification(&eng->debugOverlay, eng);
        }

        if (eng->debugOverlay.vertCount > 0) {
            /* Copiar vértices HUD al buffer mapeado */
            memcpy(eng->hudMappedData, eng->debugOverlay.verts,
                   eng->debugOverlay.vertCount * sizeof(Vertex));

            /* Push constants con MVP identidad para espacio de pantalla */
            PushConstants hudPc = {0};
            Mat4 identity = mat4_identity();
            memcpy(hudPc.mvp, identity.m, sizeof(hudPc.mvp));
            memcpy(hudPc.model, identity.m, sizeof(hudPc.model));
            vkCmdPushConstants(eng->commandBuffer, eng->pipelineLayout,
                VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
                0, sizeof(PushConstants), &hudPc);

            /* Bind HUD vertex buffer + dummy de instancia y dibujar */
            VkBuffer hudBufs[] = { eng->hudVertexBuffer, staticDummy };
            VkDeviceSize hudOff[] = { 0, 0 };
            vkCmdBindVertexBuffers(eng->commandBuffer, 0, 2, hudBufs, hudOff);
            vkCmdDraw(eng->commandBuffer, (uint32_t)eng->debugOverlay.vertCount, 1, 0, 0);
        }
    }

    // Guardar stats
    eng->chunkSystem.visibleChunks = visibleChunks;
    eng->chunkSystem.visibleVerts = visibleVerts;

    vkCmdEndRenderPass(eng->commandBuffer);
    vkEndCommandBuffer(eng->commandBuffer);

    // 5. Envío y presentación a la pantalla
    VkSemaphore waitSemaphores[] = { eng->imageAvailableSemaphore };
    VkPipelineStageFlags waitStages[] = { VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT };
    VkSemaphore signalSemaphores[] = { eng->renderFinishedSemaphore };

    VkSubmitInfo submitInfo = {0};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.waitSemaphoreCount = 1;
    submitInfo.pWaitSemaphores = waitSemaphores;
    submitInfo.pWaitDstStageMask = waitStages;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &eng->commandBuffer;
    submitInfo.signalSemaphoreCount = 1;
    submitInfo.pSignalSemaphores = signalSemaphores;

    vkQueueSubmit(eng->graphicsQueue, 1, &submitInfo, eng->inFlightFence);

    VkPresentInfoKHR presentInfo = {0};
    presentInfo.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
    presentInfo.waitSemaphoreCount = 1;
    presentInfo.pWaitSemaphores = signalSemaphores;
    presentInfo.swapchainCount = 1;
    presentInfo.pSwapchains = &eng->swapchain;
    presentInfo.pImageIndices = &imageIndex;
    
    result = vkQueuePresentKHR(eng->graphicsQueue, &presentInfo);
    if (result == VK_ERROR_OUT_OF_DATE_KHR || result == VK_SUBOPTIMAL_KHR || eng->framebufferResized) {
        eng->framebufferResized = 0;
        recreate_swapchain(eng);
    } else if (result != VK_SUCCESS) {
        fprintf(stderr, "Error al presentar swapchain: %d\n", result);
    }
}

void vulkan_destroy(VulkanEngine *eng) {
    vkDeviceWaitIdle(eng->device);

    traffic_system_free(&eng->trafficSystem);
    car_system_free(&eng->carSystem, eng->device);
    if (eng->roadGraph) {
        road_graph_free(eng->roadGraph);
        eng->roadGraph = NULL;
    }

    if (eng->mappedVertexData) {
        vkUnmapMemory(eng->device, eng->vertexBufferMemory);
        eng->mappedVertexData = NULL;
    }
    if (eng->vertexBuffer != VK_NULL_HANDLE) vkDestroyBuffer(eng->device, eng->vertexBuffer, NULL);
    if (eng->vertexBufferMemory != VK_NULL_HANDLE) vkFreeMemory(eng->device, eng->vertexBufferMemory, NULL);
    free(eng->vertexData);

    // Limpiar HUD buffer
    if (eng->hudMappedData) {
        vkUnmapMemory(eng->device, eng->hudVertexBufferMemory);
        eng->hudMappedData = NULL;
    }
    if (eng->hudVertexBuffer != VK_NULL_HANDLE) vkDestroyBuffer(eng->device, eng->hudVertexBuffer, NULL);
    if (eng->hudVertexBufferMemory != VK_NULL_HANDLE) vkFreeMemory(eng->device, eng->hudVertexBufferMemory, NULL);

    cleanup_texture_resources(eng);
    cleanup_pipeline_and_sync(eng);
    cleanup_swapchain_and_depth(eng);
    cleanup_vulkan_instance_and_device(eng);
}
