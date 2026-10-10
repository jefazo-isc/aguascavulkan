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
#include <SDL2/SDL.h>
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

/* ---------- spawn / respawn ---------- */

static void spawn_car(Car* car, const RoadGraph* graph, float cam_x, float cam_z) {
    if (!graph || graph->n_edges == 0) return;

    for (int attempt = 0; attempt < 64; attempt++) {
        uint32_t eidx = (uint32_t)(rand() % (int)graph->n_edges);
        const RoadEdge* e = &graph->edges[eidx];
        if (e->pt_count < 2) continue;

        RoadPoint mp = graph->points[e->pt_off + e->pt_count / 2];
        float dx = mp.x - cam_x, dz = mp.z - cam_z;
        float dist = sqrtf(dx*dx + dz*dz);
        if (dist < 50.f || dist > 400.f) continue;

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

        car->next_edge_idx = eidx;
        car->brake         = 0.f;
        car->pos[0]        = mp.x;
        car->pos[1]        = mp.y;
        car->pos[2]        = mp.z;
        car->heading       = 0.f;
        return;
    }
    /* fallback: colocar en el primer nodo del primer edge */
    car->edge_idx  = 0;
    car->t         = 0.5f;
    car->mesh_type = 0;
    car->direction = 0;
    car->lane      = 0;
    car->v_desired = CAR_BASE_SPEEDS[0];
    car->v         = car->v_desired;
    memcpy(car->tint, CAR_TINTS[0], sizeof(float)*4);
    car->pos[0] = cam_x; car->pos[1] = 0.f; car->pos[2] = cam_z;
}

/* ---------- elección de siguiente arista ---------- */

static uint32_t pick_next_edge(const RoadGraph* graph,
                               uint32_t curr_eidx, uint32_t reach_node,
                               float cur_heading)
{
    uint32_t cands[64];
    int     dirs[64];
    int     n = 0;

    for (uint32_t i = 0; i < graph->n_edges && n < 64; i++) {
        if (i == curr_eidx) continue;
        const RoadEdge* e = &graph->edges[i];
        if (e->a == reach_node) { cands[n]=i; dirs[n]=0; n++; }
        else if (!e->oneway && e->b == reach_node) { cands[n]=i; dirs[n]=1; n++; }
    }
    if (n == 0) return curr_eidx;

    /* 70% elegir "todo recto" (menor cambio de ángulo) */
    if (rand() % 100 < 70) {
        int best = 0;
        float best_diff = 1e9f;
        for (int i = 0; i < n; i++) {
            const RoadEdge* e = &graph->edges[cands[i]];
            uint32_t p0i = e->pt_off + (dirs[i] ? (e->pt_count-1) : 0);
            uint32_t p1i = e->pt_off + (dirs[i] ? (e->pt_count-2) : 1);
            RoadPoint p0 = graph->points[p0i], p1 = graph->points[p1i];
            float ang = atan2f(p1.x-p0.x, p1.z-p0.z);
            float diff = fabsf(ang - cur_heading);
            while (diff >  M_PI) diff -= 2.f*(float)M_PI;
            diff = fabsf(diff);
            if (diff < best_diff) { best_diff=diff; best=i; }
        }
        return cands[best];
    }
    return cands[rand() % n];
}

/* ---------- interpolar posición en polilínea ---------- */

static void polyline_sample(const RoadGraph* graph, const RoadEdge* edge,
                            float t, uint8_t direction,
                            float* out_x, float* out_y, float* out_z,
                            float* fwd_x_out, float* fwd_z_out)
{
    float eff_t = direction ? (1.f - t) : t;
    eff_t = fmaxf(0.f, fminf(1.f, eff_t));

    /* calcular longitud total */
    float total_len = 0.f;
    for (uint32_t i = 0; i < edge->pt_count - 1; i++) {
        RoadPoint a = graph->points[edge->pt_off + i];
        RoadPoint b = graph->points[edge->pt_off + i + 1];
        float dx=b.x-a.x, dy=b.y-a.y, dz=b.z-a.z;
        total_len += sqrtf(dx*dx+dy*dy+dz*dz);
    }
    if (total_len < 0.001f) total_len = 0.001f;

    float target = eff_t * total_len;
    float accum  = 0.f;

    for (uint32_t i = 0; i < edge->pt_count - 1; i++) {
        RoadPoint a = graph->points[edge->pt_off + i];
        RoadPoint b = graph->points[edge->pt_off + i + 1];
        float dx=b.x-a.x, dy=b.y-a.y, dz=b.z-a.z;
        float seg = sqrtf(dx*dx+dy*dy+dz*dz);

        if (accum + seg >= target || i == edge->pt_count - 2) {
            float u = (seg > 1e-4f) ? (target - accum) / seg : 0.f;
            u = fmaxf(0.f, fminf(1.f, u));
            *out_x = a.x + u*dx;
            *out_y = a.y + u*dy;
            *out_z = a.z + u*dz;
            float len2 = sqrtf(dx*dx+dz*dz);
            if (len2 > 1e-4f) {
                float fx = dx/len2, fz = dz/len2;
                if (direction) { fx=-fx; fz=-fz; }
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

/* ---------- init / free ---------- */

int car_system_init(CarSystem* sys, VkDevice device, VkPhysicalDevice physDevice) {
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

    /* --- Vertex buffer unificado para los 6 modelos --- */
    Vertex* combined = malloc(total_verts * sizeof(Vertex));
    if (!combined) return 0;
    size_t off = 0;
    for (int i = 0; i < NUM_CAR_TYPES; i++) {
        memcpy(combined + off, sys->car_meshes[i]->vertices,
               sys->car_meshes[i]->vertexCount * sizeof(Vertex));
        off += sys->car_meshes[i]->vertexCount;
    }

    VkMemoryPropertyFlags host_flags =
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;

    if (!create_gpu_buffer(device, physDevice, total_verts * sizeof(Vertex),
                           VK_BUFFER_USAGE_VERTEX_BUFFER_BIT, host_flags,
                           &sys->vertexBuffer, &sys->vertexBufferMemory)) {
        free(combined);
        return 0;
    }
    void* p = NULL;
    vkMapMemory(device, sys->vertexBufferMemory, 0, total_verts*sizeof(Vertex), 0, &p);
    memcpy(p, combined, total_verts * sizeof(Vertex));
    vkUnmapMemory(device, sys->vertexBufferMemory);
    free(combined);

    /* --- Instance buffer (NUM_CARS instancias × 96B) --- */
    size_t inst_sz = NUM_CARS * sizeof(CarInstanceData);
    if (!create_gpu_buffer(device, physDevice, inst_sz,
                           VK_BUFFER_USAGE_VERTEX_BUFFER_BIT, host_flags,
                           &sys->instanceBuffer, &sys->instanceBufferMemory)) {
        return 0;
    }
    vkMapMemory(device, sys->instanceBufferMemory, 0, inst_sz, 0, (void**)&sys->mappedInstanceData);

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

    printf("[CarSystem] Listo: 6 tipos (%zu verts), %d instancias (96B/inst)\n",
           total_verts, NUM_CARS);
    return 1;
}

void car_system_free(CarSystem* sys, VkDevice device) {
    if (!sys || device == VK_NULL_HANDLE) return;
    vkDeviceWaitIdle(device);

    if (sys->mappedInstanceData) {
        vkUnmapMemory(device, sys->instanceBufferMemory);
        sys->mappedInstanceData = NULL;
    }
    if (sys->instanceBuffer     != VK_NULL_HANDLE) vkDestroyBuffer(device, sys->instanceBuffer, NULL);
    if (sys->instanceBufferMemory!= VK_NULL_HANDLE) vkFreeMemory(device, sys->instanceBufferMemory, NULL);
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

void car_system_update(CarSystem* sys, const RoadGraph* graph,
                       float dt, float cam_x, float cam_z)
{
    if (!graph || graph->n_edges == 0 || !sys->mappedInstanceData) return;

    for (int ci = 0; ci < NUM_CARS; ci++) {
        Car* car = &sys->cars[ci];

        /* Respawn si fuera del anillo o nunca inicializado */
        float dx = car->pos[0]-cam_x, dz = car->pos[2]-cam_z;
        float dist = sqrtf(dx*dx + dz*dz);
        if (dist > 450.f || car->v_desired <= 0.f || isnan(car->pos[0])) {
            spawn_car(car, graph, cam_x, cam_z);
        }

        if (car->edge_idx >= graph->n_edges) car->edge_idx = 0;
        const RoadEdge* edge = &graph->edges[car->edge_idx];
        if (edge->pt_count < 2) { spawn_car(car, graph, cam_x, cam_z); continue; }

        /* ---- calcular longitud del edge para avanzar t ---- */
        float elen = 0.f;
        for (uint32_t i = 0; i < edge->pt_count-1; i++) {
            RoadPoint a = graph->points[edge->pt_off+i];
            RoadPoint b = graph->points[edge->pt_off+i+1];
            elen += sqrtf((b.x-a.x)*(b.x-a.x)+(b.y-a.y)*(b.y-a.y)+(b.z-a.z)*(b.z-a.z));
        }
        if (elen < 0.1f) elen = 0.1f;

        car->v = car->v_desired;
        car->t += (car->v * dt) / elen;

        /* ---- llegó al nodo destino → elegir siguiente arista ---- */
        if (car->t >= 1.0f) {
            car->t = 0.f;
            uint32_t reach = (car->direction == 0) ? edge->b : edge->a;
            uint32_t nxt   = pick_next_edge(graph, car->edge_idx, reach, car->heading);
            car->edge_idx  = nxt;
            const RoadEdge* ne = &graph->edges[nxt];
            car->direction = (ne->a == reach) ? 0 : 1;
            car->lane      = 0;
            edge = ne;
        }

        /* ---- interpolar posición y dirección ---- */
        float wx, wy, wz, fwd_x, fwd_z;
        polyline_sample(graph, edge, car->t, car->direction,
                        &wx, &wy, &wz, &fwd_x, &fwd_z);

        /* offset de carril: right = (-fwd_z, 0, fwd_x) */
        float lane_off = (car->lane + 0.5f) * 3.2f;
        wx += (-fwd_z) * lane_off;
        wz += ( fwd_x) * lane_off;

        car->pos[0] = wx;
        car->pos[1] = wy;
        car->pos[2] = wz;
        car->heading = atan2f(fwd_x, fwd_z);

        /* ---- heading suave a <8m del nodo destino ---- */
        if (car->t >= 1.f - 8.f/elen && car->next_edge_idx != car->edge_idx) {
            const RoadEdge* ne = &graph->edges[car->next_edge_idx];
            RoadPoint p0 = graph->points[ne->pt_off];
            RoadPoint p1 = graph->points[ne->pt_off + 1];
            float ndx = p1.x-p0.x, ndz = p1.z-p0.z;
            float nlen = sqrtf(ndx*ndx+ndz*ndz);
            if (nlen > 0.001f) {
                float target_h = atan2f(ndx/nlen, ndz/nlen);
                float alpha = (car->t - (1.f-8.f/elen)) / (8.f/elen);
                alpha = fmaxf(0.f, fminf(1.f, alpha));
                /* interpolación angular */
                float dh = target_h - car->heading;
                while (dh >  (float)M_PI) dh -= 2.f*(float)M_PI;
                while (dh < -(float)M_PI) dh += 2.f*(float)M_PI;
                car->heading += alpha * dh;
            }
        }

        /* ---- sanity check NaN ---- */
        if (isnan(car->pos[0]) || isnan(car->pos[1]) || isnan(car->pos[2]) || isnan(car->heading)) {
            car->pos[0]=cam_x; car->pos[1]=0.f; car->pos[2]=cam_z; car->heading=0.f;
        }
    }
}

/* ---------- render ---------- */

void car_system_render(CarSystem* sys, VkCommandBuffer cmdBuffer) {
    if (!sys || sys->totalVertexCount == 0 || sys->vertexBuffer == VK_NULL_HANDLE) return;

    /* Bind 0=vertex buffer del coche, 1=instance buffer */
    VkBuffer   bufs[2] = { sys->vertexBuffer, sys->instanceBuffer };
    VkDeviceSize offs[2] = { 0, 0 };
    vkCmdBindVertexBuffers(cmdBuffer, 0, 2, bufs, offs);

    /* Contar instancias por tipo y calcular offsets en el buffer */
    uint32_t type_count[NUM_CAR_TYPES]  = {0};
    uint32_t type_offset[NUM_CAR_TYPES] = {0};

    for (int ci = 0; ci < NUM_CARS; ci++) {
        uint8_t t = sys->cars[ci].mesh_type;
        if (t < NUM_CAR_TYPES) type_count[t]++;
    }
    uint32_t running = 0;
    for (int t = 0; t < NUM_CAR_TYPES; t++) {
        type_offset[t] = running;
        running += type_count[t];
    }

    /* Re-ordenar el buffer de instancias por tipo de malla
       (escritura directa sobre la memoria mapeada ya existente) */
    uint32_t write_idx[NUM_CAR_TYPES];
    memcpy(write_idx, type_offset, sizeof(write_idx));

    /* Buffer temporal en stack para no alocar heap cada frame */
    CarInstanceData tmp[NUM_CARS];
    for (int ci = 0; ci < NUM_CARS; ci++) {
        const Car* car = &sys->cars[ci];
        uint8_t t = car->mesh_type < NUM_CAR_TYPES ? car->mesh_type : 0;
        CarInstanceData* dst = &tmp[write_idx[t]++];
        mat4_car(dst->model, car->pos[0], car->pos[1], car->pos[2], car->heading);
        memcpy(dst->tint,  car->tint, sizeof(float)*4);
        dst->brake  = car->brake;
        dst->pad[0] = 0.f; dst->pad[1] = 0.f; dst->pad[2] = 0.f;
    }
    memcpy(sys->mappedInstanceData, tmp, NUM_CARS * sizeof(CarInstanceData));

    /* Un draw call por tipo, usando sólo el slice correcto */
    for (int t = 0; t < NUM_CAR_TYPES; t++) {
        if (sys->mesh_vertex_counts[t] == 0 || type_count[t] == 0) continue;
        vkCmdDraw(cmdBuffer,
                  sys->mesh_vertex_counts[t],   /* vertex count del modelo */
                  type_count[t],                 /* sólo las instancias de este tipo */
                  sys->mesh_vertex_offsets[t],   /* first vertex */
                  type_offset[t]);               /* first instance */
    }
}
