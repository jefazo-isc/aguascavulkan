/*
 * car_system.c - TAREA 5
 * Sistema cinemático de 200 coches instanciados en GPU.
 * Spawn en anillo 50-400m de cámara, respawn >450m.
 * Movimiento sobre polilíneas del road_network.bin.
 * 6 draw calls instanciados (uno por tipo de coche).
 */
#include "car_system.h"
#include "vulkan_gltf.h"
#include "vulkan_swapchain.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static inline int maxi(int a, int b) { return a > b ? a : b; }

static const char* CAR_GLB_FILES[NUM_CAR_TYPES] = {
    "models/cars/car_sedan.glb",
    "models/cars/car_compacto.glb",
    "models/cars/car_pickup.glb",
    "models/cars/car_van.glb",
    "models/cars/car_taxi.glb",
    "models/cars/car_bus.glb"
};

/* Velocidad deseada base en m/s (se modula ±15%) */
static const float CAR_BASE_SPEEDS[NUM_CAR_TYPES] = {
    13.9f, 12.5f, 15.0f, 11.1f, 13.9f, 8.3f
};

/* Paleta de tints para coches (tint.a=1.0 marca coche instanciado) */
static const float CAR_TINTS[8][4] = {
    {0.90f, 0.15f, 0.15f, 1.0f},  /* rojo */
    {0.20f, 0.45f, 0.90f, 1.0f},  /* azul */
    {0.90f, 0.90f, 0.90f, 1.0f},  /* plata */
    {0.95f, 0.75f, 0.05f, 1.0f},  /* amarillo */
    {0.20f, 0.20f, 0.25f, 1.0f},  /* oscuro */
    {0.10f, 0.60f, 0.30f, 1.0f},  /* verde */
    {0.50f, 0.30f, 0.10f, 1.0f},  /* marrón */
    {0.80f, 0.50f, 0.80f, 1.0f},  /* morado */
};

/* ---------- utilidades matemáticas ---------- */

static float randf(float lo, float hi) {
    return lo + (float)rand() / (float)RAND_MAX * (hi - lo);
}

/* Construye mat4 col-mayor: Ry(heading) * Translate(pos) */
static void mat4_car(float m[16], float px, float py, float pz, float heading) {
    float ch = cosf(heading), sh = sinf(heading);
    /* col 0 */ m[0]=ch;   m[1]=0.f;  m[2]=-sh;  m[3]=0.f;
    /* col 1 */ m[4]=0.f;  m[5]=1.f;  m[6]=0.f;  m[7]=0.f;
    /* col 2 */ m[8]=sh;   m[9]=0.f;  m[10]=ch;  m[11]=0.f;
    /* col 3 */ m[12]=px;  m[13]=py;  m[14]=pz;  m[15]=1.f;
}

/* ---------- GPU buffer helper ---------- */

static int create_gpu_buffer(VkDevice device, VkPhysicalDevice phys,
                              VkDeviceSize size,
                              VkBufferUsageFlags usage,
                              VkMemoryPropertyFlags props,
                              VkBuffer* buf, VkDeviceMemory* mem)
{
    VkBufferCreateInfo bi = {
        .sType       = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size        = size,
        .usage       = usage,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE
    };
    if (vkCreateBuffer(device, &bi, NULL, buf) != VK_SUCCESS) return 0;

    VkMemoryRequirements mr;
    vkGetBufferMemoryRequirements(device, *buf, &mr);
    uint32_t mt = find_memory_type(phys, mr.memoryTypeBits, props);
    if (mt == UINT32_MAX) return 0;

    VkMemoryAllocateInfo ai = {
        .sType           = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize  = mr.size,
        .memoryTypeIndex = mt
    };
    if (vkAllocateMemory(device, &ai, NULL, mem) != VK_SUCCESS) return 0;
    vkBindBufferMemory(device, *buf, *mem, 0);
    return 1;
}

/* ---------- helpers de arista, muestreo y spawn / respawn ---------- */

#define CAR_GRID_SIZE 1024
#define CAR_GRID_CELL_SIZE 28.0f
#define CAR_EDGE_HASH_SIZE 512
#define MIN_FOLLOW_DIST 5.0f
#define SAFE_TIME_HEADWAY 1.2f

typedef struct {
    int cell_head[CAR_GRID_SIZE];
    int car_next[NUM_CARS];
    int edge_head[CAR_EDGE_HASH_SIZE];
    int edge_next[NUM_CARS];
} CarSpatialHash;

static inline uint32_t hash_grid_cell(int gx, int gz) {
    return (((uint32_t)gx * 73856093u) ^ ((uint32_t)gz * 19349663u)) & (CAR_GRID_SIZE - 1);
}

static inline uint32_t hash_edge_idx(uint32_t edge_idx) {
    return (edge_idx * 2654435761u) & (CAR_EDGE_HASH_SIZE - 1);
}

static float edge_length(const RoadGraph* graph, uint32_t eidx) {
    if (graph->edge_lengths && eidx < graph->n_edges) {
        return graph->edge_lengths[eidx];
    }
    const RoadEdge* edge = &graph->edges[eidx];
    float elen = 0.f;
    if (edge->pt_count >= 2 &&
        (uint64_t)edge->pt_off + (uint64_t)edge->pt_count <= (uint64_t)graph->n_points) {
        for (uint32_t i = 0; i < edge->pt_count - 1; i++) {
            RoadPoint a = graph->points[edge->pt_off + i];
            RoadPoint b = graph->points[edge->pt_off + i + 1];
            float dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
            elen += sqrtf(dx*dx + dy*dy + dz*dz);
        }
    }
    return (elen < 0.1f) ? 0.1f : elen;
}

static float edge_approx_heading(const RoadGraph* graph, const RoadEdge* e,
                                 uint8_t direction, float fallback)
{
    if (e->pt_count < 2 ||
        (uint64_t)e->pt_off + (uint64_t)e->pt_count > (uint64_t)graph->n_points) {
        return fallback;
    }
    RoadPoint p0 = (direction == 0)
        ? graph->points[e->pt_off]
        : graph->points[e->pt_off + e->pt_count - 1];
    RoadPoint p1 = (direction == 0)
        ? graph->points[e->pt_off + e->pt_count - 1]
        : graph->points[e->pt_off];
    float dx = p1.x - p0.x, dz = p1.z - p0.z;
    if (dx * dx + dz * dz <= 1e-6f) {
        p0 = (direction == 0)
            ? graph->points[e->pt_off + e->pt_count - 2]
            : graph->points[e->pt_off + 1];
        dx = p1.x - p0.x;
        dz = p1.z - p0.z;
    }
    return (dx * dx + dz * dz > 1e-6f) ? atan2f(dx, dz) : fallback;
}

/* ---------- elección de siguiente arista en O(1) via CSR ---------- */

static int collect_next_edge_candidates(const RoadGraph* graph, uint32_t curr_eidx,
                                        uint32_t reach_node, uint32_t cands[64], uint8_t dirs[64]) {
    int n = 0;
    if (graph->node_edge_offsets && graph->node_edge_indices && graph->node_edge_dirs) {
        if (reach_node >= graph->n_nodes) return 0;
        uint32_t start = graph->node_edge_offsets[reach_node];
        uint32_t end   = graph->node_edge_offsets[reach_node + 1];
        for (uint32_t idx = start; idx < end && n < 64; idx++) {
            uint32_t eidx = graph->node_edge_indices[idx];
            if (eidx == curr_eidx || eidx >= graph->n_edges) continue;
            if (graph->edges[eidx].pt_count < 2) continue;
            cands[n] = eidx;
            dirs[n]  = graph->node_edge_dirs[idx];
            n++;
        }
        return n;
    }

    for (uint32_t i = 0; i < graph->n_edges && n < 64; i++) {
        if (i == curr_eidx) continue;
        const RoadEdge* e = &graph->edges[i];
        if (e->pt_count < 2) continue;
        if (e->a == reach_node) { cands[n] = i; dirs[n] = 0; n++; }
        else if (!e->oneway && e->b == reach_node) { cands[n] = i; dirs[n] = 1; n++; }
    }
    return n;
}

static uint32_t pick_straightest_candidate(const RoadGraph* graph, const uint32_t cands[64],
                                           const uint8_t dirs[64], int n, float cur_heading) {
    int best = 0;
    float best_diff = 1e9f;
    for (int i = 0; i < n; i++) {
        const RoadEdge* e = &graph->edges[cands[i]];
        if ((uint64_t)e->pt_off + (uint64_t)e->pt_count > (uint64_t)graph->n_points) continue;
        uint32_t p0i = e->pt_off + (dirs[i] ? (e->pt_count - 1) : 0);
        uint32_t p1i = e->pt_off + (dirs[i] ? (e->pt_count - 2) : 1);
        RoadPoint p0 = graph->points[p0i], p1 = graph->points[p1i];
        float ang = atan2f(p1.x - p0.x, p1.z - p0.z);
        float diff = fabsf(ang - cur_heading);
        while (diff > (float)M_PI) diff -= 2.f * (float)M_PI;
        diff = fabsf(diff);
        if (diff < best_diff) { best_diff = diff; best = i; }
    }
    return cands[best];
}

static uint32_t pick_next_edge(const RoadGraph* graph,
                               uint32_t curr_eidx, uint32_t reach_node,
                               float cur_heading)
{
    if (!graph || graph->n_edges == 0) return curr_eidx;

    uint32_t cands[64];
    uint8_t  dirs[64];
    int n = collect_next_edge_candidates(graph, curr_eidx, reach_node, cands, dirs);
    if (n == 0) return curr_eidx;

    if (rand() % 100 < 70) {
        return pick_straightest_candidate(graph, cands, dirs, n, cur_heading);
    }
    return cands[rand() % n];
}

/* ---------- interpolar posición en polilínea ---------- */

static void polyline_sample(const RoadGraph* graph, const RoadEdge* edge,
                            float total_len, float t, uint8_t direction,
                            float* out_x, float* out_y, float* out_z,
                            float* fwd_x_out, float* fwd_z_out)
{
    if (edge->pt_count < 2 ||
        (uint64_t)edge->pt_off + (uint64_t)edge->pt_count > (uint64_t)graph->n_points) {
        *out_x = 0.f; *out_y = 0.f; *out_z = 0.f;
        *fwd_x_out = 1.f; *fwd_z_out = 0.f;
        return;
    }

    float eff_t = direction ? (1.f - t) : t;
    eff_t = fmaxf(0.f, fminf(1.f, eff_t));

    if (total_len < 0.001f) total_len = 0.001f;

    float target = eff_t * total_len;
    float accum  = 0.f;

    for (uint32_t i = 0; i < edge->pt_count - 1; i++) {
        RoadPoint a = graph->points[edge->pt_off + i];
        RoadPoint b = graph->points[edge->pt_off + i + 1];
        float dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
        float seg = sqrtf(dx*dx + dy*dy + dz*dz);

        if (accum + seg >= target || i == edge->pt_count - 2) {
            float u = (seg > 1e-4f) ? (target - accum) / seg : 0.f;
            u = fmaxf(0.f, fminf(1.f, u));
            *out_x = a.x + u * dx;
            *out_y = a.y + u * dy;
            *out_z = a.z + u * dz;
            float len2 = sqrtf(dx*dx + dz*dz);
            if (len2 > 1e-4f) {
                float fx = dx / len2, fz = dz / len2;
                if (direction) { fx = -fx; fz = -fz; }
                *fwd_x_out = fx;
                *fwd_z_out = fz;
            } else {
                *fwd_x_out = 1.f;
                *fwd_z_out = 0.f;
            }
            return;
        }
        accum += seg;
    }
    /* fallback */
    RoadPoint p = graph->points[edge->pt_off];
    *out_x = p.x; *out_y = p.y; *out_z = p.z;
    *fwd_x_out = 1.f; *fwd_z_out = 0.f;
}

static void spawn_car(Car* car, const RoadGraph* graph, float cam_x, float cam_z) {
    if (!graph || graph->n_edges == 0) return;

    for (int attempt = 0; attempt < 64; attempt++) {
        uint32_t eidx = (uint32_t)(rand() % (int)graph->n_edges);
        const RoadEdge* e = &graph->edges[eidx];
        if (e->pt_count < 2 ||
            (uint64_t)e->pt_off + (uint64_t)e->pt_count > (uint64_t)graph->n_points) {
            continue;
        }

        RoadPoint mp = graph->points[e->pt_off + e->pt_count / 2];
        float dx = mp.x - cam_x, dz = mp.z - cam_z;
        float dist = sqrtf(dx*dx + dz*dz);
        if (dist < 30.f || dist > 700.f) continue;

        car->edge_idx  = eidx;
        car->t         = randf(0.05f, 0.90f);
        car->mesh_type = (uint8_t)(rand() % NUM_CAR_TYPES);
        car->direction = (e->oneway) ? 0 : (uint8_t)(rand() % 2);

        int max_lanes = (car->direction == 0) ? maxi(1, e->lanes_fwd)
                                              : maxi(1, e->lanes_rev);
        car->lane = (int8_t)(rand() % max_lanes);

        float base = (e->speed_ms > 0.f) ? e->speed_ms : CAR_BASE_SPEEDS[car->mesh_type];
        car->v_desired = base * randf(0.85f, 1.15f);
        car->v         = car->v_desired;

        int tidx = rand() % 8;
        memcpy(car->tint, CAR_TINTS[tidx], sizeof(float)*4);

        car->brake = 0.f;
        float elen = edge_length(graph, eidx);
        float wx, wy, wz, fwd_x, fwd_z;
        polyline_sample(graph, e, elen, car->t, car->direction,
                        &wx, &wy, &wz, &fwd_x, &fwd_z);
        float lane_off = (car->lane + 0.5f) * 3.2f;
        car->pos[0]  = wx + (-fwd_z) * lane_off;
        car->pos[1]  = wy;
        car->pos[2]  = wz + ( fwd_x) * lane_off;
        car->heading = atan2f(fwd_x, fwd_z);

        uint32_t reach     = (car->direction == 0) ? e->b : e->a;
        car->next_edge_idx = pick_next_edge(graph, eidx, reach, car->heading);
        return;
    }
    /* fallback: colocar en el primer nodo del primer edge */
    const RoadEdge* e0 = &graph->edges[0];
    car->edge_idx  = 0;
    car->t         = 0.5f;
    car->mesh_type = 0;
    car->direction = 0;
    car->lane      = 0;
    car->v_desired = CAR_BASE_SPEEDS[0];
    car->v         = car->v_desired;
    memcpy(car->tint, CAR_TINTS[0], sizeof(float)*4);
    car->brake         = 0.f;
    car->heading       = edge_approx_heading(graph, e0, car->direction, 0.f);
    car->next_edge_idx = pick_next_edge(graph, 0, e0->b, car->heading);
    car->pos[0] = cam_x; car->pos[1] = 0.f; car->pos[2] = cam_z;
}

/* ---------- init / free ---------- */

int car_system_init(CarSystem* sys, VkDevice device, VkPhysicalDevice physDevice,
                    VkCommandPool commandPool, VkQueue graphicsQueue) {
    memset(sys, 0, sizeof(CarSystem));
    srand((unsigned)time(NULL));

    /* --- Cargar mallas de coches --- */
    size_t total_verts = 0;
    for (int i = 0; i < NUM_CAR_TYPES; i++) {
        Mesh* m = gltf_load(CAR_GLB_FILES[i]);
        if (!m || m->vertexCount == 0) {
            fprintf(stderr, "[CarSystem] Fallback procedural para tipo %d (%s)\n",
                    i, CAR_GLB_FILES[i]);
            if (!m) m = calloc(1, sizeof(Mesh));
            /* cubo mínimo de 6 vértices si falla la carga */
            if (!m->vertices) {
                m->vertexCount = 6;
                m->vertices = calloc(6, sizeof(Vertex));
            }
        }
        sys->car_meshes[i] = m;
        sys->mesh_vertex_offsets[i] = (uint32_t)total_verts;
        sys->mesh_vertex_counts[i]  = (uint32_t)m->vertexCount;
        total_verts += m->vertexCount;
    }
    sys->totalVertexCount = total_verts;

    /* --- Vertex buffer unificado para los 6 modelos en DEVICE_LOCAL --- */
    Vertex* combined = malloc(total_verts * sizeof(Vertex));
    if (!combined) {
        for (int i = 0; i < NUM_CAR_TYPES; i++) {
            if (sys->car_meshes[i]) {
                obj_free(sys->car_meshes[i]);
                sys->car_meshes[i] = NULL;
            }
        }
        return 0;
    }
    size_t off = 0;
    for (int i = 0; i < NUM_CAR_TYPES; i++) {
        memcpy(combined + off, sys->car_meshes[i]->vertices,
               sys->car_meshes[i]->vertexCount * sizeof(Vertex));
        off += sys->car_meshes[i]->vertexCount;
        obj_free(sys->car_meshes[i]);
        sys->car_meshes[i] = NULL;
    }

    VkDeviceSize vertexBufferSize = total_verts * sizeof(Vertex);
    VkMemoryPropertyFlags host_flags =
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;

    // 1. Buffer temporal Staging en HOST_VISIBLE | HOST_COHERENT
    VkBuffer stagingBuffer = VK_NULL_HANDLE;
    VkDeviceMemory stagingMemory = VK_NULL_HANDLE;
    if (!create_gpu_buffer(device, physDevice, vertexBufferSize,
                           VK_BUFFER_USAGE_TRANSFER_SRC_BIT, host_flags,
                           &stagingBuffer, &stagingMemory)) {
        free(combined);
        return 0;
    }

    void* p = NULL;
    vkMapMemory(device, stagingMemory, 0, vertexBufferSize, 0, &p);
    memcpy(p, combined, vertexBufferSize);
    vkUnmapMemory(device, stagingMemory);
    free(combined);

    // 2. Buffer destino definitivo en VRAM pura (DEVICE_LOCAL)
    if (!create_gpu_buffer(device, physDevice, vertexBufferSize,
                           VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                           VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
                           &sys->vertexBuffer, &sys->vertexBufferMemory)) {
        vkDestroyBuffer(device, stagingBuffer, NULL);
        vkFreeMemory(device, stagingMemory, NULL);
        return 0;
    }

    // 3. Copia Staging -> DEVICE_LOCAL vía Command Buffer
    VkCommandBufferAllocateInfo cmdAlloc = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = commandPool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1
    };
    VkCommandBuffer uploadCmd = VK_NULL_HANDLE;
    if (vkAllocateCommandBuffers(device, &cmdAlloc, &uploadCmd) == VK_SUCCESS) {
        VkCommandBufferBeginInfo bbi = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
        };
        vkBeginCommandBuffer(uploadCmd, &bbi);

        VkBufferCopy copyRegion = {
            .srcOffset = 0,
            .dstOffset = 0,
            .size = vertexBufferSize
        };
        vkCmdCopyBuffer(uploadCmd, stagingBuffer, sys->vertexBuffer, 1, &copyRegion);

        vkEndCommandBuffer(uploadCmd);

        VkSubmitInfo submitInfo = {
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .commandBufferCount = 1,
            .pCommandBuffers = &uploadCmd
        };
        vkQueueSubmit(graphicsQueue, 1, &submitInfo, VK_NULL_HANDLE);
        vkQueueWaitIdle(graphicsQueue);

        vkFreeCommandBuffers(device, commandPool, 1, &uploadCmd);
    }

    // 4. Liberación inmediata del staging buffer temporal
    vkDestroyBuffer(device, stagingBuffer, NULL);
    vkFreeMemory(device, stagingMemory, NULL);

    /* --- Instance buffers (NUM_CARS instancias × 96B por cada frame en vuelo) --- */
    size_t inst_sz = NUM_CARS * sizeof(CarInstanceData);
    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if (!create_gpu_buffer(device, physDevice, inst_sz,
                               VK_BUFFER_USAGE_VERTEX_BUFFER_BIT, host_flags,
                               &sys->instanceBuffers[i], &sys->instanceBufferMemories[i])) {
            return 0;
        }
        vkMapMemory(device, sys->instanceBufferMemories[i], 0, inst_sz, 0, (void**)&sys->mappedInstanceDatas[i]);
    }

    /* --- Static dummy buffer (1 instancia con tint.a=0) para terreno --- */
    if (!create_gpu_buffer(device, physDevice, sizeof(CarInstanceData),
                           VK_BUFFER_USAGE_VERTEX_BUFFER_BIT, host_flags,
                           &sys->staticDummyBuffer, &sys->staticDummyBufferMemory)) {
        return 0;
    }
    CarInstanceData dummy; memset(&dummy, 0, sizeof(dummy));
    /* matriz identidad */
    dummy.model[0]=1.f; dummy.model[5]=1.f; dummy.model[10]=1.f; dummy.model[15]=1.f;
    dummy.tint[0]=1.f; dummy.tint[1]=1.f; dummy.tint[2]=1.f; dummy.tint[3]=0.f; /* a=0 → estático */
    void* dp = NULL;
    vkMapMemory(device, sys->staticDummyBufferMemory, 0, sizeof(CarInstanceData), 0, &dp);
    memcpy(dp, &dummy, sizeof(dummy));
    vkUnmapMemory(device, sys->staticDummyBufferMemory);

    printf("[CarSystem] Listo: 6 tipos (%zu verts), %d instancias × %d buffers (96B/inst)\n",
           total_verts, NUM_CARS, MAX_FRAMES_IN_FLIGHT);
    return 1;
}

void car_system_free(CarSystem* sys, VkDevice device) {
    if (!sys || device == VK_NULL_HANDLE) return;
    vkDeviceWaitIdle(device);

    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if (sys->mappedInstanceDatas[i]) {
            vkUnmapMemory(device, sys->instanceBufferMemories[i]);
            sys->mappedInstanceDatas[i] = NULL;
        }
        if (sys->instanceBuffers[i]      != VK_NULL_HANDLE) vkDestroyBuffer(device, sys->instanceBuffers[i], NULL);
        if (sys->instanceBufferMemories[i]!= VK_NULL_HANDLE) vkFreeMemory(device, sys->instanceBufferMemories[i], NULL);
    }
    if (sys->vertexBuffer       != VK_NULL_HANDLE) vkDestroyBuffer(device, sys->vertexBuffer, NULL);
    if (sys->vertexBufferMemory != VK_NULL_HANDLE) vkFreeMemory(device, sys->vertexBufferMemory, NULL);
    if (sys->staticDummyBuffer  != VK_NULL_HANDLE) vkDestroyBuffer(device, sys->staticDummyBuffer, NULL);
    if (sys->staticDummyBufferMemory != VK_NULL_HANDLE) vkFreeMemory(device, sys->staticDummyBufferMemory, NULL);

    for (int i = 0; i < NUM_CAR_TYPES; i++) {
        if (sys->car_meshes[i]) { obj_free(sys->car_meshes[i]); sys->car_meshes[i]=NULL; }
    }
}

VkBuffer car_system_get_static_dummy(const CarSystem* sys) {
    return sys->staticDummyBuffer;
}

/* ---------- update ---------- */

static void build_car_spatial_hash(CarSpatialHash* grid, const Car cars[NUM_CARS]) {
    for (int i = 0; i < CAR_GRID_SIZE; i++) grid->cell_head[i] = -1;
    for (int i = 0; i < CAR_EDGE_HASH_SIZE; i++) grid->edge_head[i] = -1;

    for (int ci = 0; ci < NUM_CARS; ci++) {
        const Car* car = &cars[ci];
        if (!isfinite(car->pos[0]) || !isfinite(car->pos[2]) ||
            fabsf(car->pos[0]) > 1e7f || fabsf(car->pos[2]) > 1e7f) {
            grid->car_next[ci] = -1;
            grid->edge_next[ci] = -1;
            continue;
        }
        int gx = (int)floorf(car->pos[0] / CAR_GRID_CELL_SIZE);
        int gz = (int)floorf(car->pos[2] / CAR_GRID_CELL_SIZE);
        uint32_t ch = hash_grid_cell(gx, gz);
        grid->car_next[ci] = grid->cell_head[ch];
        grid->cell_head[ch] = ci;

        uint32_t eh = hash_edge_idx(car->edge_idx);
        grid->edge_next[ci] = grid->edge_head[eh];
        grid->edge_head[eh] = ci;
    }
}

static void find_lead_same_lane(const CarSpatialHash* grid, const Car cars[NUM_CARS],
                                int ci, float elen, float* dist_to_lead, float* lead_v) {
    const Car* car = &cars[ci];
    uint32_t eh = hash_edge_idx(car->edge_idx);
    for (int other_i = grid->edge_head[eh]; other_i >= 0; other_i = grid->edge_next[other_i]) {
        if (other_i == ci) continue;
        const Car* other = &cars[other_i];
        if (other->edge_idx == car->edge_idx &&
            other->direction == car->direction &&
            other->lane == car->lane &&
            other->t > car->t) {
            float d = (other->t - car->t) * elen;
            if (d < *dist_to_lead) {
                *dist_to_lead = d;
                *lead_v = other->v;
            }
        }
    }
}

static void find_lead_in_cell(const CarSpatialHash* grid, const Car cars[NUM_CARS],
                              int ci, uint32_t ch, float fwd_dx, float fwd_dz,
                              float* dist_to_lead, float* lead_v) {
    const Car* car = &cars[ci];
    for (int other_i = grid->cell_head[ch]; other_i >= 0; other_i = grid->car_next[other_i]) {
        if (other_i == ci) continue;
        const Car* other = &cars[other_i];
        if (other->edge_idx == car->edge_idx &&
            other->direction == car->direction &&
            other->lane == car->lane) {
            continue;
        }
        float cdx = other->pos[0] - car->pos[0];
        float cdz = other->pos[2] - car->pos[2];
        float distSq = cdx * cdx + cdz * cdz;
        if (distSq < 49.0f && (cdx * fwd_dx + cdz * fwd_dz) > 0.5f) {
            float d = sqrtf(distSq);
            if (d < *dist_to_lead) {
                *dist_to_lead = d;
                *lead_v = other->v;
            }
        }
    }
}

static void find_lead_car(const CarSpatialHash* grid, const Car cars[NUM_CARS],
                          int ci, float elen, float* out_dist_to_lead, float* out_lead_v)
{
    const Car* car = &cars[ci];
    float dist_to_lead = 999.0f;
    float lead_v = car->v_desired;

    find_lead_same_lane(grid, cars, ci, elen, &dist_to_lead, &lead_v);

    if (isfinite(car->pos[0]) && isfinite(car->pos[2]) &&
        fabsf(car->pos[0]) <= 1e7f && fabsf(car->pos[2]) <= 1e7f) {
        int gx = (int)floorf(car->pos[0] / CAR_GRID_CELL_SIZE);
        int gz = (int)floorf(car->pos[2] / CAR_GRID_CELL_SIZE);
        float fwd_dx = sinf(car->heading);
        float fwd_dz = cosf(car->heading);

        for (int oz = -1; oz <= 1; oz++) {
            for (int ox = -1; ox <= 1; ox++) {
                uint32_t ch = hash_grid_cell(gx + ox, gz + oz);
                find_lead_in_cell(grid, cars, ci, ch, fwd_dx, fwd_dz, &dist_to_lead, &lead_v);
            }
        }
    }

    *out_dist_to_lead = dist_to_lead;
    *out_lead_v = lead_v;
}

static void car_system_stage_instances(CarSystem* sys);

/* Respawnea vehículos fuera de radio (800m) o con aristas inválidas. */
static void respawn_invalid_cars(CarSystem* sys, const RoadGraph* graph, float cam_x, float cam_z) {
    for (int ci = 0; ci < NUM_CARS; ci++) {
        Car* car = &sys->cars[ci];
        float dx = car->pos[0] - cam_x, dz = car->pos[2] - cam_z;
        float dist = sqrtf(dx * dx + dz * dz);
        if (dist > 800.f || car->v_desired <= 0.f || isnan(car->pos[0]) || isnan(car->pos[2])) {
            spawn_car(car, graph, cam_x, cam_z);
        }
        if (car->edge_idx >= graph->n_edges) {
            car->edge_idx = 0;
            car->next_edge_idx = 0;
        }
        if (graph->edges[car->edge_idx].pt_count < 2) {
            spawn_car(car, graph, cam_x, cam_z);
        }
    }
}

/* Calcula velocidad objetivo considerando semáforos próximos en el nodo destino. */
static float compute_traffic_target_speed(const Car* car, const RoadEdge* edge, const RoadGraph* graph,
                                          const TrafficSystem* traffic, float elen) {
    float target_speed = car->v_desired;
    if (!traffic) return target_speed;

    uint32_t target_node_idx = (car->direction == 0) ? edge->b : edge->a;
    if (target_node_idx >= graph->n_nodes) return target_speed;

    const RoadNode* target_node = &graph->nodes[target_node_idx];
    float dist_to_node = (1.0f - car->t) * elen;
    if (target_node->signal_group < 0 || dist_to_node > 35.0f) return target_speed;

    TrafficLightState light = traffic_system_get_light_state_at(
        traffic, target_node->x, target_node->z, 18.0f);
    if (light != TRAFFIC_LIGHT_RED && light != TRAFFIC_LIGHT_AMBER) return target_speed;

    if (dist_to_node <= 5.0f) return 0.0f;
    float ratio = (dist_to_node - 5.0f) / 30.0f;
    return car->v_desired * ratio * ratio;
}

/* Aplica seguimiento vehicular tipo IDM usando el hash espacial. */
static float apply_following_idm(const CarSpatialHash* grid, const Car cars[NUM_CARS],
                                 int ci, float elen, float target_speed) {
    float dist_to_lead = 999.0f;
    float lead_v = cars[ci].v_desired;
    find_lead_car(grid, cars, ci, elen, &dist_to_lead, &lead_v);

    float desired_gap = MIN_FOLLOW_DIST + cars[ci].v * SAFE_TIME_HEADWAY;
    if (dist_to_lead >= desired_gap) return target_speed;
    if (dist_to_lead <= MIN_FOLLOW_DIST) return 0.0f;

    float ratio = (dist_to_lead - MIN_FOLLOW_DIST) / (desired_gap - MIN_FOLLOW_DIST);
    float safe_v = lead_v * (ratio * ratio);
    return (safe_v < target_speed) ? safe_v : target_speed;
}

static void update_car_velocity(Car* car, float target_speed, float dt, float elen) {
    if (car->v > target_speed) {
        car->v -= 8.5f * dt;
        if (car->v < target_speed) car->v = target_speed;
        car->brake = 1.0f;
    } else if (car->v < target_speed) {
        car->v += 4.0f * dt;
        if (car->v > target_speed) car->v = target_speed;
        car->brake = 0.0f;
    } else {
        car->brake = (car->v < 0.1f) ? 1.0f : 0.0f;
    }

    if (car->v > 0.001f) {
        car->t += (car->v * dt) / elen;
    }
}

static void advance_car_to_next_edge(Car* car, const RoadGraph* graph,
                                     const RoadEdge** edge_io, float* elen_io) {
    if (car->t < 1.0f) return;
    const RoadEdge* edge = *edge_io;
    car->t = 0.f;

    uint32_t reach = (car->direction == 0) ? edge->b : edge->a;
    uint32_t nxt = car->next_edge_idx;
    if (nxt >= graph->n_edges || nxt == car->edge_idx ||
        graph->edges[nxt].pt_count < 2 ||
        (graph->edges[nxt].a != reach &&
         (graph->edges[nxt].oneway || graph->edges[nxt].b != reach))) {
        nxt = pick_next_edge(graph, car->edge_idx, reach, car->heading);
    }

    car->edge_idx = nxt;
    const RoadEdge* ne = &graph->edges[nxt];
    car->direction = (ne->a == reach) ? 0 : 1;

    int max_l = (car->direction == 0) ? maxi(1, ne->lanes_fwd) : maxi(1, ne->lanes_rev);
    if (car->lane >= max_l) car->lane = (int8_t)(max_l - 1);
    if (car->lane < 0) car->lane = 0;

    uint32_t next_reach = (car->direction == 0) ? ne->b : ne->a;
    float next_heading = edge_approx_heading(graph, ne, car->direction, car->heading);
    car->next_edge_idx = pick_next_edge(graph, nxt, next_reach, next_heading);

    *edge_io = ne;
    *elen_io = edge_length(graph, car->edge_idx);
}

static void apply_smooth_corner_heading(Car* car, const RoadGraph* graph,
                                        const RoadEdge* edge, float elen) {
    if (car->t < 1.f - 8.f / elen ||
        car->next_edge_idx == car->edge_idx ||
        car->next_edge_idx >= graph->n_edges) {
        return;
    }
    const RoadEdge* ne = &graph->edges[car->next_edge_idx];
    if (ne->pt_count < 2 ||
        (uint64_t)ne->pt_off + (uint64_t)ne->pt_count > (uint64_t)graph->n_points) {
        return;
    }

    uint32_t reach = (car->direction == 0) ? edge->b : edge->a;
    RoadPoint p0 = (ne->a == reach) ? graph->points[ne->pt_off]
                                    : graph->points[ne->pt_off + ne->pt_count - 1];
    RoadPoint p1 = (ne->a == reach) ? graph->points[ne->pt_off + 1]
                                    : graph->points[ne->pt_off + ne->pt_count - 2];
    float ndx = p1.x - p0.x, ndz = p1.z - p0.z;
    float nlen = sqrtf(ndx * ndx + ndz * ndz);
    if (nlen <= 0.001f) return;

    float target_h = atan2f(ndx / nlen, ndz / nlen);
    float alpha = fmaxf(0.f, fminf(1.f, (car->t - (1.f - 8.f / elen)) / (8.f / elen)));
    float dh = target_h - car->heading;
    while (dh >  (float)M_PI) dh -= 2.f * (float)M_PI;
    while (dh < -(float)M_PI) dh += 2.f * (float)M_PI;
    car->heading += alpha * dh;
}

/* Avanza un vehículo individual: semáforos, IDM, cinemática y transición de arista. */
static void update_single_car(CarSystem* sys, const CarSpatialHash* grid,
                              const RoadGraph* graph, const TrafficSystem* traffic,
                              int ci, float dt, float cam_x, float cam_z) {
    Car* car = &sys->cars[ci];
    const RoadEdge* edge = &graph->edges[car->edge_idx];
    if (edge->pt_count < 2 ||
        (uint64_t)edge->pt_off + (uint64_t)edge->pt_count > (uint64_t)graph->n_points) {
        return;
    }

    float elen = edge_length(graph, car->edge_idx);
    float target_speed = compute_traffic_target_speed(car, edge, graph, traffic, elen);
    target_speed = apply_following_idm(grid, sys->cars, ci, elen, target_speed);

    update_car_velocity(car, target_speed, dt, elen);
    advance_car_to_next_edge(car, graph, &edge, &elen);

    float wx, wy, wz, fwd_x, fwd_z;
    polyline_sample(graph, edge, elen, car->t, car->direction,
                    &wx, &wy, &wz, &fwd_x, &fwd_z);
    float lane_off = (car->lane + 0.5f) * 3.2f;
    car->pos[0] = wx + (-fwd_z) * lane_off;
    car->pos[1] = wy;
    car->pos[2] = wz + fwd_x * lane_off;
    car->heading = atan2f(fwd_x, fwd_z);

    apply_smooth_corner_heading(car, graph, edge, elen);

    if (isnan(car->pos[0]) || isnan(car->pos[1]) || isnan(car->pos[2]) || isnan(car->heading)) {
        car->pos[0] = cam_x; car->pos[1] = 0.f; car->pos[2] = cam_z; car->heading = 0.f;
    }
}

void car_system_update(CarSystem* sys, const RoadGraph* graph,
                       const TrafficSystem* traffic,
                       float dt, float cam_x, float cam_z)
{
    if (!sys || !graph || graph->n_edges == 0) return;

    respawn_invalid_cars(sys, graph, cam_x, cam_z);

    CarSpatialHash grid;
    build_car_spatial_hash(&grid, sys->cars);

    for (int ci = 0; ci < NUM_CARS; ci++) {
        update_single_car(sys, &grid, graph, traffic, ci, dt, cam_x, cam_z);
    }

    car_system_stage_instances(sys);
}

/* ---------- staging y render ---------- */

static void car_system_stage_instances(CarSystem* sys) {
    if (!sys) return;

    memset(sys->typeCounts, 0, sizeof(sys->typeCounts));
    memset(sys->typeOffsets, 0, sizeof(sys->typeOffsets));

    for (int ci = 0; ci < NUM_CARS; ci++) {
        uint8_t t = sys->cars[ci].mesh_type;
        if (t >= NUM_CAR_TYPES) t = 0;
        sys->typeCounts[t]++;
    }

    uint32_t running = 0;
    for (int t = 0; t < NUM_CAR_TYPES; t++) {
        sys->typeOffsets[t] = running;
        running += sys->typeCounts[t];
    }

    uint32_t write_idx[NUM_CAR_TYPES];
    memcpy(write_idx, sys->typeOffsets, sizeof(write_idx));

    for (int ci = 0; ci < NUM_CARS; ci++) {
        const Car* car = &sys->cars[ci];
        uint8_t t = (car->mesh_type < NUM_CAR_TYPES) ? car->mesh_type : 0;
        CarInstanceData* dst = &sys->stagedInstances[write_idx[t]++];
        mat4_car(dst->model, car->pos[0], car->pos[1], car->pos[2], car->heading);
        memcpy(dst->tint, car->tint, sizeof(float) * 4);
        dst->brake = car->brake;
        dst->pad[0] = 0.f;
        dst->pad[1] = 0.f;
        dst->pad[2] = 0.f;
    }

    sys->instancesStaged = 1;
}

void car_system_render(CarSystem* sys, VkCommandBuffer cmdBuffer, uint32_t frameIdx) {
    if (!sys || sys->totalVertexCount == 0 || sys->vertexBuffer == VK_NULL_HANDLE) return;
    if (frameIdx >= MAX_FRAMES_IN_FLIGHT) frameIdx = 0;

    if (!sys->instancesStaged) {
        car_system_stage_instances(sys);
    }

    if (sys->mappedInstanceDatas[frameIdx]) {
        memcpy(sys->mappedInstanceDatas[frameIdx], sys->stagedInstances,
               NUM_CARS * sizeof(CarInstanceData));
    }

    /* Bind 0=vertex buffer del coche, 1=instance buffer del frame actual */
    VkBuffer   bufs[2] = { sys->vertexBuffer, sys->instanceBuffers[frameIdx] };
    VkDeviceSize offs[2] = { 0, 0 };
    vkCmdBindVertexBuffers(cmdBuffer, 0, 2, bufs, offs);

    /* Un draw call por tipo, usando sólo el slice correcto */
    for (int t = 0; t < NUM_CAR_TYPES; t++) {
        if (sys->mesh_vertex_counts[t] == 0 || sys->typeCounts[t] == 0) continue;
        vkCmdDraw(cmdBuffer,
                  sys->mesh_vertex_counts[t],   /* vertex count del modelo */
                  sys->typeCounts[t],           /* sólo las instancias de este tipo */
                  sys->mesh_vertex_offsets[t],  /* first vertex */
                  sys->typeOffsets[t]);         /* first instance */
    }
}
