#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <string.h>

#include "logger.h"
#include "math_camera.h"
#include "frustum_cull.h"
#include "traffic_system.h"
#include "road_graph.h"
#include "ped_system.h"
#include "telemetry.h"
#include "vulkan_memory_pool.h"
#include "obj_loader.h"
#include "sector_system.h"
#include "car_system.h"
#include "terrain_dem_data.h"

static int g_tests_run = 0;
static int g_tests_failed = 0;

#define ASSERT_TRUE(cond, msg) do { \
    g_tests_run++; \
    if (!(cond)) { \
        fprintf(stderr, "[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        g_tests_failed++; \
    } \
} while (0)

#define ASSERT_NEAR(a, b, eps, msg) ASSERT_TRUE(fabsf((a) - (b)) <= (eps), msg)

static void test_math_camera(void) {
    Mat4 id = mat4_identity();
    ASSERT_NEAR(id.m[0], 1.0f, 1e-6f, "mat4_identity diagonal [0]");
    ASSERT_NEAR(id.m[5], 1.0f, 1e-6f, "mat4_identity diagonal [5]");
    ASSERT_NEAR(id.m[10], 1.0f, 1e-6f, "mat4_identity diagonal [10]");
    ASSERT_NEAR(id.m[15], 1.0f, 1e-6f, "mat4_identity diagonal [15]");

    Mat4 prod = mat4_multiply(id, id);
    for (int i = 0; i < 16; i++) {
        ASSERT_NEAR(prod.m[i], id.m[i], 1e-6f, "mat4_multiply identity");
    }

    Mat4 proj = mat4_perspective_vk(DEG2RAD(60.0f), 16.0f / 9.0f, 0.1f, 1000.0f);
    ASSERT_TRUE(proj.m[5] < 0.0f, "mat4_perspective_vk inverts Y for Vulkan clip space");
    ASSERT_NEAR(proj.m[11], -1.0f, 1e-6f, "mat4_perspective_vk perspective divide");

    Mat4 view = mat4_lookat(0.0f, 0.0f, 5.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f, 0.0f);
    ASSERT_NEAR(view.m[14], -5.0f, 1e-5f, "mat4_lookat Z translation");
}

static void test_frustum_culling(void) {
    Mat4 proj = mat4_perspective_vk(DEG2RAD(60.0f), 1.0f, 0.5f, 100.0f);
    Mat4 view = mat4_lookat(0.0f, 0.0f, 0.0f, 0.0f, 0.0f, -1.0f, 0.0f, 1.0f, 0.0f);
    Mat4 mvp = mat4_multiply(proj, view);
    Frustum f = frustum_extract(mvp.m);

    AABB inside = { -1.0f, -1.0f, -12.0f, 1.0f, 1.0f, -8.0f };
    AABB behind = { -1.0f, -1.0f, 5.0f, 1.0f, 1.0f, 10.0f };
    AABB far_right = { 200.0f, -1.0f, -12.0f, 210.0f, 1.0f, -8.0f };

    ASSERT_TRUE(frustum_test_aabb(&f, &inside) == 1, "AABB in front of camera is visible");
    ASSERT_TRUE(frustum_test_aabb(&f, &behind) == 0, "AABB behind camera is culled");
    ASSERT_TRUE(frustum_test_aabb(&f, &far_right) == 0, "AABB far right is culled");
}

static void test_traffic_system_fsm(void) {
    TrafficSystem ts;
    traffic_system_init(&ts);

    TrafficIntersection* inter = traffic_system_get_or_create_intersection(&ts, 1);
    ASSERT_TRUE(inter != NULL, "Created traffic intersection");
    inter->greenDuration = 10.0f;
    inter->amberDuration = 3.0f;
    inter->allRedDuration = 2.0f;
    inter->currentPhase = 0;
    inter->timer = 0.0f;

    TrafficSignal sig = {0};
    sig.id = 101;
    sig.intersectionId = 1;
    sig.phaseGroup = 0; /* Eje Norte-Sur */
    sig.x = 10.0f;
    sig.y = 0.0f;
    sig.z = 20.0f;
    traffic_system_add_signal(&ts, sig);

    /* Fase 0: NS Verde */
    traffic_system_update_simulation(&ts, 1.0f);
    ASSERT_TRUE(ts.signals[0].currentState == TRAFFIC_LIGHT_GREEN, "Phase 0 -> GREEN");

    /* Avanzar a Fase 1: NS Ambar */
    traffic_system_update_simulation(&ts, 10.0f);
    ASSERT_TRUE(ts.signals[0].currentState == TRAFFIC_LIGHT_AMBER, "Phase 1 -> AMBER");

    /* Avanzar a Fase 2: Todo Rojo */
    traffic_system_update_simulation(&ts, 3.5f);
    ASSERT_TRUE(ts.signals[0].currentState == TRAFFIC_LIGHT_RED, "Phase 2 -> RED");

    TrafficLightState queried = traffic_system_get_light_state_at(&ts, 11.0f, 20.0f, 5.0f);
    ASSERT_TRUE(queried == TRAFFIC_LIGHT_RED, "Spatial query returns RED");

    traffic_system_free(&ts);
}

static void test_road_graph_binary(void) {
    RoadGraph* g = road_graph_load("models/road_network.bin");
    ASSERT_TRUE(g != NULL, "road_graph_load loads models/road_network.bin");
    if (g) {
        ASSERT_TRUE(g->n_nodes > 0, "RoadGraph has nodes > 0");
        ASSERT_TRUE(g->n_edges > 0, "RoadGraph has edges > 0");
        ASSERT_TRUE(g->edge_lengths != NULL, "RoadGraph edge_lengths != NULL");
        ASSERT_TRUE(g->node_edge_offsets != NULL, "RoadGraph node_edge_offsets != NULL");
        ASSERT_TRUE(g->node_edge_indices != NULL, "RoadGraph node_edge_indices != NULL");
        ASSERT_TRUE(g->node_edge_dirs != NULL, "RoadGraph node_edge_dirs != NULL");
        ASSERT_TRUE(g->total_incidences >= g->n_edges, "RoadGraph total_incidences >= n_edges");
        ASSERT_TRUE(g->edge_lengths[0] > 0.0f, "RoadGraph edge_lengths[0] > 0.0f");
        ASSERT_TRUE(g->node_edge_offsets[0] == 0, "CSR offsets[0] == 0");
        ASSERT_TRUE(g->node_edge_offsets[g->n_nodes] == g->total_incidences,
                    "CSR offsets[n_nodes] == total_incidences");

        uint32_t bad_len = 0;
        for (uint32_t e = 0; e < g->n_edges; e++) {
            if (!(g->edge_lengths[e] >= 0.1f) || !isfinite(g->edge_lengths[e])) {
                bad_len++;
            }
        }
        ASSERT_TRUE(bad_len == 0, "All RoadGraph precomputed edge_lengths are finite and >= 0.1f");

        uint32_t bad_csr = 0;
        for (uint32_t n = 0; n < g->n_nodes; n++) {
            uint32_t start = g->node_edge_offsets[n];
            uint32_t end = g->node_edge_offsets[n + 1];
            if (start > end || end > g->total_incidences) {
                bad_csr++;
                break;
            }
            for (uint32_t k = start; k < end; k++) {
                uint32_t eidx = g->node_edge_indices[k];
                uint8_t dir = g->node_edge_dirs[k];
                if (eidx >= g->n_edges || dir > 1) {
                    bad_csr++;
                    continue;
                }
                const RoadEdge* edge = &g->edges[eidx];
                if (dir == 0 && edge->a != n) bad_csr++;
                if (dir == 1 && (edge->oneway || edge->b != n)) bad_csr++;
            }
        }
        ASSERT_TRUE(bad_csr == 0, "All RoadGraph CSR incidences match edge endpoints and directions");

        road_graph_free(g);
    }
}

static void test_vulkan_memory_pool(void) {
    ASSERT_TRUE(VK_POOL_MAX_BLOCKS == 128, "VK_POOL_MAX_BLOCKS == 128");
    ASSERT_TRUE(VK_POOL_MAX_FREE_REGIONS == 256, "VK_POOL_MAX_FREE_REGIONS == 256");

    VulkanMemoryPool pool;
    memset(&pool, 0, sizeof(pool));
    ASSERT_TRUE(vulkan_memory_pool_init(NULL, VK_NULL_HANDLE, VK_NULL_HANDLE, 0, 0, 4096) == 0,
                "vulkan_memory_pool_init(NULL) returns 0");
    ASSERT_TRUE(vulkan_memory_pool_init(&pool, VK_NULL_HANDLE, VK_NULL_HANDLE, 0, 0, 4096) == 0,
                "vulkan_memory_pool_init(VK_NULL_HANDLE) returns 0");

    VulkanSuballocation emptySub = { VK_NULL_HANDLE, 0, NULL };
    vulkan_memory_pool_free_suballocation(NULL, emptySub, 64);
    vulkan_memory_pool_free_suballocation(&pool, emptySub, 64);
    vulkan_memory_pool_destroy(NULL);
    ASSERT_TRUE(vulkan_memory_pool_suballocate(NULL, 64, 16).memory == VK_NULL_HANDLE,
                "vulkan_memory_pool_suballocate(NULL) returns VK_NULL_HANDLE");

    /* Simulación CPU-side sin dispositivo Vulkan vivo (no llamar vulkan_memory_pool_destroy) */
    uint8_t backing[4096];
    memset(backing, 0, sizeof(backing));
    int dummy_dev = 1;
    int dummy_mem = 2;
    int dummy_other_mem = 3;
    VkDevice fake_dev = (VkDevice)(uintptr_t)&dummy_dev;
    VkDeviceMemory fake_mem = (VkDeviceMemory)(uintptr_t)&dummy_mem;
    VkDeviceMemory other_mem = (VkDeviceMemory)(uintptr_t)&dummy_other_mem;

    ASSERT_TRUE(vulkan_memory_pool_init(&pool, fake_dev, VK_NULL_HANDLE, 0,
                                        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT, sizeof(backing)) == 1,
                "vulkan_memory_pool_init succeeds with valid handle");
    ASSERT_TRUE(vulkan_memory_pool_suballocate(&pool, 0, 16).memory == VK_NULL_HANDLE,
                "vulkan_memory_pool_suballocate(size=0) returns VK_NULL_HANDLE");

    pool.blocks[0].memory = fake_mem;
    pool.blocks[0].size = sizeof(backing);
    pool.blocks[0].allocatedOffset = 0;
    pool.blocks[0].mappedBase = backing;
    pool.blockCount = 1;

    /* Boundary / invalid free checks */
    vulkan_memory_pool_free_suballocation(&pool, (VulkanSuballocation){ fake_mem, 0, backing }, 0);
    vulkan_memory_pool_free_suballocation(&pool, (VulkanSuballocation){ fake_mem, 128, backing }, 64);
    vulkan_memory_pool_free_suballocation(&pool, (VulkanSuballocation){ other_mem, 0, NULL }, 64);
    ASSERT_TRUE(pool.freeRegionCount == 0, "Invalid/out-of-bounds free_suballocation leaves freeRegionCount == 0");

    /* Subasignar A(128), B(512), C(128) */
    VulkanSuballocation subA = vulkan_memory_pool_suballocate(&pool, 128, 64);
    VulkanSuballocation subB = vulkan_memory_pool_suballocate(&pool, 512, 64);
    VulkanSuballocation subC = vulkan_memory_pool_suballocate(&pool, 128, 64);
    ASSERT_TRUE(subA.memory == fake_mem && subA.offset == 0 && subA.mappedPtr == backing + 0,
                "Suballocation A at offset 0 with mappedPtr");
    ASSERT_TRUE(subB.memory == fake_mem && subB.offset == 128 && subB.mappedPtr == backing + 128,
                "Suballocation B at offset 128 with mappedPtr");
    ASSERT_TRUE(subC.memory == fake_mem && subC.offset == 640 && subC.mappedPtr == backing + 640,
                "Suballocation C at offset 640 with mappedPtr");
    ASSERT_TRUE(pool.blocks[0].allocatedOffset == 768, "Block allocatedOffset == 768");

    /* Liberar región intermedia B -> se registra como región libre */
    vulkan_memory_pool_free_suballocation(&pool, subB, 512);
    ASSERT_TRUE(pool.freeRegionCount == 1, "Freeing middle block adds 1 free region");
    ASSERT_TRUE(pool.freeRegions[0].offset == 128 && pool.freeRegions[0].size == 512,
                "Free region tracks [128, 640)");
    ASSERT_TRUE(pool.blocks[0].allocatedOffset == 768, "Middle free does not rewind allocatedOffset");

    /* Reutilizar con alineación mayor (256) -> genera prefijo [128,256) y sufijo [384,640) */
    VulkanSuballocation subD = vulkan_memory_pool_suballocate(&pool, 128, 256);
    ASSERT_TRUE(subD.memory == fake_mem && subD.offset == 256 && subD.mappedPtr == backing + 256,
                "Reused free region aligned to 256 with mappedPtr");
    ASSERT_TRUE(pool.blocks[0].allocatedOffset == 768, "Reused free region does not grow allocatedOffset");
    ASSERT_TRUE(pool.freeRegionCount == 2, "Alignment split leaves prefix + suffix free regions");
    ((uint8_t*)subD.mappedPtr)[0] = 0xAB;
    ASSERT_TRUE(backing[256] == 0xAB, "mappedPtr writes into backing buffer at alignedOffset");

    /* Coalescencia + rebobinado completo de allocatedOffset al liberar A, D y C */
    vulkan_memory_pool_free_suballocation(&pool, subA, 128);
    ASSERT_TRUE(pool.freeRegionCount == 2, "Freeing A coalesces with prefix [128, 256)");
    vulkan_memory_pool_free_suballocation(&pool, subD, 128);
    ASSERT_TRUE(pool.freeRegionCount == 1 && pool.freeRegions[0].offset == 0 && pool.freeRegions[0].size == 640,
                "Freeing D coalesces left+right into [0, 640)");
    vulkan_memory_pool_free_suballocation(&pool, subC, 128);
    ASSERT_TRUE(pool.freeRegionCount == 0 && pool.blocks[0].allocatedOffset == 0,
                "Freeing tail C coalesces and rewinds allocatedOffset to 0");
}

static void test_traffic_system_o1_intersection_resolution(void) {
    TrafficSystem ts;
    traffic_system_init(&ts);

    TrafficIntersection* i10 = traffic_system_get_or_create_intersection(&ts, 10);
    TrafficIntersection* i20 = traffic_system_get_or_create_intersection(&ts, 20);
    TrafficIntersection* i30 = traffic_system_get_or_create_intersection(&ts, 30);
    ASSERT_TRUE(i10 != NULL && i20 != NULL && i30 != NULL, "Created 3 traffic intersections");

    i10->currentPhase = 0; i10->greenDuration = 10.0f; i10->amberDuration = 3.0f; i10->allRedDuration = 2.0f;
    i20->currentPhase = 3; i20->greenDuration = 10.0f; i20->amberDuration = 3.0f; i20->allRedDuration = 2.0f;
    i30->currentPhase = 1; i30->greenDuration = 10.0f; i30->amberDuration = 3.0f; i30->allRedDuration = 2.0f;

    /* Semáforos inicializados con {0} (intersectionIndex == 0) apuntando a intersecciones != 0 */
    TrafficSignal s0 = {0}; s0.id = 1; s0.intersectionId = 20; s0.phaseGroup = 0;
    TrafficSignal s1 = {0}; s1.id = 2; s1.intersectionId = 20; s1.phaseGroup = 1;
    TrafficSignal s2 = {0}; s2.id = 3; s2.intersectionId = 30; s2.phaseGroup = 0;
    TrafficSignal s3 = {0}; s3.id = 4; s3.intersectionId = 10; s3.phaseGroup = 0;
    /* Semáforo añadido antes de crear su intersección -> resolución diferida */
    TrafficSignal sLazy = {0}; sLazy.id = 5; sLazy.intersectionId = 999; sLazy.phaseGroup = 1;

    traffic_system_add_signal(&ts, s0);
    traffic_system_add_signal(&ts, s1);
    traffic_system_add_signal(&ts, s2);
    traffic_system_add_signal(&ts, s3);
    traffic_system_add_signal(&ts, sLazy);

    TrafficIntersection* i999 = traffic_system_get_or_create_intersection(&ts, 999);
    ASSERT_TRUE(i999 != NULL, "Created deferred intersection 999");
    i999->currentPhase = 3; i999->greenDuration = 10.0f; i999->amberDuration = 3.0f; i999->allRedDuration = 2.0f;

    /* Forzar realloc de sys->intersections (>64 elementos) para verificar estabilidad por índice */
    for (int id = 1000; id < 1070; id++) {
        TrafficIntersection* extra = traffic_system_get_or_create_intersection(&ts, id);
        if (extra && id == 1069) {
            extra->currentPhase = 4; /* EO Ambar */
            extra->greenDuration = 10.0f; extra->amberDuration = 3.0f; extra->allRedDuration = 2.0f;
        }
    }
    TrafficSignal sPostRealloc = {0};
    sPostRealloc.id = 6;
    sPostRealloc.intersectionId = 1069;
    sPostRealloc.phaseGroup = 1;
    traffic_system_add_signal(&ts, sPostRealloc);

    traffic_system_update_simulation(&ts, 0.1f);

    ASSERT_TRUE(ts.signals[0].intersectionIndex == 1 && ts.intersections[ts.signals[0].intersectionIndex].id == 20,
                "Signal 0 cached intersectionIndex points to intersection 20");
    ASSERT_TRUE(ts.signals[0].currentState == TRAFFIC_LIGHT_RED, "Inter 20 (phase 3) NS -> RED");
    ASSERT_TRUE(ts.signals[1].currentState == TRAFFIC_LIGHT_GREEN, "Inter 20 (phase 3) EW -> GREEN");

    ASSERT_TRUE(ts.signals[2].intersectionIndex == 2 && ts.intersections[ts.signals[2].intersectionIndex].id == 30,
                "Signal 2 cached intersectionIndex points to intersection 30");
    ASSERT_TRUE(ts.signals[2].currentState == TRAFFIC_LIGHT_AMBER, "Inter 30 (phase 1) NS -> AMBER");

    ASSERT_TRUE(ts.signals[3].intersectionIndex == 0 && ts.intersections[ts.signals[3].intersectionIndex].id == 10,
                "Signal 3 cached intersectionIndex points to intersection 10");
    ASSERT_TRUE(ts.signals[3].currentState == TRAFFIC_LIGHT_GREEN, "Inter 10 (phase 0) NS -> GREEN");

    ASSERT_TRUE(ts.signals[4].intersectionIndex >= 0 &&
                (size_t)ts.signals[4].intersectionIndex < ts.intersectionCount &&
                ts.intersections[ts.signals[4].intersectionIndex].id == 999,
                "Lazy signal 4 resolved intersectionIndex to 999");
    ASSERT_TRUE(ts.signals[4].currentState == TRAFFIC_LIGHT_GREEN, "Inter 999 (phase 3) EW -> GREEN");

    ASSERT_TRUE(ts.signals[5].intersectionIndex >= 0 &&
                (size_t)ts.signals[5].intersectionIndex < ts.intersectionCount &&
                ts.intersections[ts.signals[5].intersectionIndex].id == 1069,
                "Post-realloc signal 5 resolved intersectionIndex to 1069");
    ASSERT_TRUE(ts.signals[5].currentState == TRAFFIC_LIGHT_AMBER, "Inter 1069 (phase 4) EW -> AMBER");

    traffic_system_free(&ts);
}

static void test_obj_loader_and_sector_bounds(void) {
    ASSERT_TRUE(obj_load(NULL) == NULL, "obj_load(NULL) returns NULL safely");
    ASSERT_TRUE(obj_load("models/archivo_inexistente.obj") == NULL,
                "obj_load(missing) returns NULL safely");
    obj_free(NULL);

    Mesh* cube = obj_load("models/test.obj");
    ASSERT_TRUE(cube != NULL, "obj_load loads models/test.obj");
    if (cube) {
        ASSERT_TRUE(cube->vertices != NULL && cube->vertexCount == 36,
                    "models/test.obj has 36 triangulated vertices");
        ASSERT_TRUE(cube->indices == NULL && cube->indexCount == 0,
                    "obj_load omits identity index buffer (indices == NULL, indexCount == 0)");
        obj_free(cube);
    }

    ASSERT_TRUE(MAX_MACRO_SECTORS == 512, "MAX_MACRO_SECTORS == 512");
    ASSERT_TRUE(MAX_CHUNKS_PER_SECTOR == 256, "MAX_CHUNKS_PER_SECTOR == 256");
    ASSERT_TRUE(MAX_DEFERRED_SECTOR_FREES == 128, "MAX_DEFERRED_SECTOR_FREES == 128");
    ASSERT_TRUE(sizeof(DeferredSectorFree) > 0 && sizeof(SectorSystem) > 0,
                "SectorSystem & DeferredSectorFree structs valid");
}

static void test_ped_system(void) {
    TrafficSystem ts;
    traffic_system_init(&ts);
    TrafficIntersection* inter = traffic_system_get_or_create_intersection(&ts, 1);
    inter->greenDuration = 10.0f;
    inter->amberDuration = 3.0f;
    inter->allRedDuration = 2.0f;
    inter->currentPhase = 0;

    TrafficSignal sig = {0};
    sig.id = 1;
    sig.intersectionId = 1;
    sig.phaseGroup = 0;
    sig.x = 5.0f;
    sig.z = 0.0f;
    traffic_system_add_signal(&ts, sig);
    traffic_system_update_simulation(&ts, 0.1f); /* GREEN */

    PedestrianSystem ps;
    ped_system_init(&ps, 4);

    Pedestrian p1 = { .pos = {0.0f, 0.0f, 0.0f}, .heading = 0.0f, .speed = 2.0f,
                      .current_sidewalk_idx = 0, .state = PED_WALKING, .tint = {1,1,1,1} };
    Pedestrian p2 = { .pos = {5.0f, 0.0f, 1.0f}, .heading = 0.0f, .speed = 2.0f,
                      .current_sidewalk_idx = 1, .state = PED_CROSSING, .tint = {1,1,1,1} };

    ASSERT_TRUE(ped_system_spawn(&ps, &p1) == 1, "Spawn walking pedestrian");
    ASSERT_TRUE(ped_system_spawn(&ps, &p2) == 1, "Spawn crossing pedestrian");

    ped_system_update(&ps, &ts, 1.0f);
    ASSERT_NEAR(ps.peds[0].pos[0], 2.0f, 1e-5f, "Walking pedestrian advances along +X");
    ASSERT_TRUE(ps.peds[1].state == PED_WAITING_RED, "Crossing pedestrian waits on GREEN vehicular light");
    ASSERT_NEAR(ps.peds[1].pos[0], 5.0f, 1e-5f, "Waiting pedestrian does not move");

    /* Cambiar semaforo vehicular a rojo -> peaton cruza */
    traffic_system_force_mode(&ts, 2);
    ped_system_update(&ps, &ts, 1.0f);
    ASSERT_TRUE(ps.peds[1].state == PED_CROSSING, "Pedestrian crosses on RED vehicular light");
    ASSERT_NEAR(ps.peds[1].pos[0], 7.0f, 1e-5f, "Crossing pedestrian advances");

    ped_system_free(&ps);
    traffic_system_free(&ts);
}

static void test_recoverability_and_iso25022(void) {
    /* ISO/IEC 25045 & 25051: tolerancia a fallos y entradas invalidas */
    ASSERT_TRUE(road_graph_load(NULL) == NULL, "road_graph_load(NULL) returns NULL");
    ASSERT_TRUE(road_graph_load("models/archivo_inexistente.bin") == NULL,
                "road_graph_load(missing) returns NULL");
    road_graph_free(NULL);

    ped_system_init(NULL, 0);
    ASSERT_TRUE(ped_system_spawn(NULL, NULL) == 0, "ped_system_spawn(NULL, NULL) returns 0");
    ped_system_update(NULL, NULL, 0.016f);
    ped_system_free(NULL);

    traffic_system_update_simulation(NULL, 0.016f);
    ASSERT_TRUE(traffic_system_get_light_state_at(NULL, 0.0f, 0.0f, 10.0f) == TRAFFIC_LIGHT_GREEN,
                "traffic_system_get_light_state_at(NULL) returns GREEN safely");

    /* ISO/IEC 25022 & 25062: evaluacion de umbrales y exportacion JSON */
    TelemetrySystem tel;
    memset(&tel, 0, sizeof(tel));
    tel.fps = 75.0f;
    tel.frameTimeMs = 13.33f;
    tel.totalVerts = 1000000;
    tel.visibleVerts = 400000;
    tel.cullingEfficiencyPct = 60.0f;
    ASSERT_TRUE(telemetry_meets_iso25022(&tel) == 1, "Telemetry meets ISO 25022 thresholds");
    ASSERT_TRUE(telemetry_export_json(&tel, "build/telemetry_test.json") == 1,
                "Telemetry exports JSON");
    ASSERT_TRUE(telemetry_meets_iso25022(NULL) == 0, "Telemetry NULL fails check");
}

static void test_car_system_headless(void) {
    RoadNode nodes[2];
    memset(nodes, 0, sizeof(nodes));
    nodes[0].x = 0.0f;   nodes[0].y = 0.0f; nodes[0].z = 0.0f; nodes[0].signal_group = -1; nodes[0].degree = 1;
    nodes[1].x = 100.0f; nodes[1].y = 0.0f; nodes[1].z = 0.0f; nodes[1].signal_group =  0; nodes[1].degree = 1;

    RoadPoint points[2] = {
        { 0.0f, 0.0f, 0.0f },
        { 100.0f, 0.0f, 0.0f }
    };

    RoadEdge edges[1];
    memset(edges, 0, sizeof(edges));
    edges[0].a = 0;
    edges[0].b = 1;
    edges[0].pt_off = 0;
    edges[0].pt_count = 2;
    edges[0].speed_ms = 14.0f;
    edges[0].width = 7.0f;
    edges[0].lanes_fwd = 1;
    edges[0].lanes_rev = 1;
    edges[0].oneway = 1;

    float edge_lengths[1] = { 100.0f };

    RoadGraph graph;
    memset(&graph, 0, sizeof(graph));
    graph.n_nodes = 2;
    graph.n_edges = 1;
    graph.n_points = 2;
    graph.nodes = nodes;
    graph.edges = edges;
    graph.points = points;
    graph.edge_lengths = edge_lengths;

    TrafficSystem ts;
    traffic_system_init(&ts);
    TrafficIntersection* inter = traffic_system_get_or_create_intersection(&ts, 1);
    ASSERT_TRUE(inter != NULL, "CarSystem test intersection created");
    if (inter) {
        inter->greenDuration = 10.0f;
        inter->amberDuration = 3.0f;
        inter->allRedDuration = 2.0f;
        inter->currentPhase = 0;
    }
    TrafficSignal sig = {0};
    sig.id = 1;
    sig.intersectionId = 1;
    sig.phaseGroup = 0;
    sig.x = 100.0f;
    sig.y = 0.0f;
    sig.z = 0.0f;
    traffic_system_add_signal(&ts, sig);
    traffic_system_update_simulation(&ts, 0.1f); /* GREEN */

    CarSystem* sys = calloc(1, sizeof(CarSystem));
    ASSERT_TRUE(sys != NULL, "Allocated CarSystem for headless test");
    if (!sys) {
        traffic_system_free(&ts);
        return;
    }

    car_system_update(NULL, &graph, &ts, 0.016f, 0.0f, 0.0f);
    car_system_update(sys, NULL, &ts, 0.016f, 0.0f, 0.0f);

    /* 1. Spawn headless + stagedInstances population */
    car_system_update(sys, &graph, &ts, 0.016f, 0.0f, 0.0f);
    ASSERT_TRUE(sys->instancesStaged == 1, "car_system_update stages instances headless");

    uint32_t total_staged = 0;
    int offsets_ok = 1;
    for (int t = 0; t < NUM_CAR_TYPES; t++) {
        if (sys->typeOffsets[t] != total_staged) offsets_ok = 0;
        total_staged += sys->typeCounts[t];
    }
    ASSERT_TRUE(total_staged == NUM_CARS, "Sum of typeCounts == NUM_CARS");
    ASSERT_TRUE(offsets_ok == 1, "typeOffsets match cumulative typeCounts");

    int spawned_ok = 1;
    int staged_ok = 1;
    for (int i = 0; i < NUM_CARS; i++) {
        const Car* c = &sys->cars[i];
        if (c->edge_idx != 0 || c->v_desired <= 0.0f ||
            !isfinite(c->pos[0]) || !isfinite(c->pos[1]) || !isfinite(c->pos[2]) ||
            c->t < 0.0f || c->t > 1.0f) {
            spawned_ok = 0;
        }
        const CarInstanceData* inst = &sys->stagedInstances[i];
        if (fabsf(inst->tint[3] - 1.0f) > 1e-5f ||
            !isfinite(inst->model[12]) || !isfinite(inst->model[13]) || !isfinite(inst->model[14]) ||
            fabsf(inst->model[5] - 1.0f) > 1e-5f || fabsf(inst->model[15] - 1.0f) > 1e-5f) {
            staged_ok = 0;
        }
    }
    ASSERT_TRUE(spawned_ok == 1, "All cars spawn validly on synthetic RoadGraph");
    ASSERT_TRUE(staged_ok == 1, "All stagedInstances populated with valid matrices and alpha=1");

    /* 2. Forward progression along t under GREEN light */
    memset(sys, 0, sizeof(CarSystem));
    sys->cars[0].edge_idx = 0;
    sys->cars[0].t = 0.20f;
    sys->cars[0].direction = 0;
    sys->cars[0].lane = 0;
    sys->cars[0].mesh_type = 0;
    sys->cars[0].v_desired = 10.0f;
    sys->cars[0].v = 10.0f;
    sys->cars[0].pos[0] = 20.0f; sys->cars[0].pos[1] = 0.0f; sys->cars[0].pos[2] = 1.6f;
    sys->cars[0].tint[0] = 1.0f; sys->cars[0].tint[3] = 1.0f;
    for (int i = 1; i < NUM_CARS; i++) {
        sys->cars[i].edge_idx = 0;
        sys->cars[i].t = 0.01f;
        sys->cars[i].direction = 0;
        sys->cars[i].lane = 0;
        sys->cars[i].mesh_type = 1;
        sys->cars[i].v_desired = 10.0f;
        sys->cars[i].v = 0.0f;
        sys->cars[i].pos[0] = 1.0f; sys->cars[i].pos[1] = 0.0f; sys->cars[i].pos[2] = 1.6f;
        sys->cars[i].tint[1] = 1.0f; sys->cars[i].tint[3] = 1.0f;
    }

    car_system_update(sys, &graph, &ts, 0.5f, 0.0f, 0.0f);
    ASSERT_NEAR(sys->cars[0].t, 0.25f, 1e-4f, "Car advances t along edge under GREEN light");
    ASSERT_NEAR(sys->cars[0].pos[0], 25.0f, 1e-3f, "Car world X advances to 25m");
    ASSERT_NEAR(sys->cars[0].brake, 0.0f, 1e-5f, "Car does not brake under free cruise");
    ASSERT_TRUE(sys->typeCounts[0] == 1 && sys->typeOffsets[0] == 0,
                "Type 0 count/offset isolated for lead car");
    ASSERT_TRUE(sys->typeCounts[1] == NUM_CARS - 1 && sys->typeOffsets[1] == 1,
                "Type 1 count/offset isolated for trailing cars");
    ASSERT_NEAR(sys->stagedInstances[0].model[12], 25.0f, 1e-3f,
                "stagedInstances[0] translation X reflects updated car pos");
    ASSERT_NEAR(sys->stagedInstances[0].brake, 0.0f, 1e-5f,
                "stagedInstances[0] brake is 0 during cruise");

    /* 3. Braking when approaching TRAFFIC_LIGHT_RED node */
    traffic_system_force_mode(&ts, 2);
    sys->cars[0].t = 0.90f;
    sys->cars[0].pos[0] = 90.0f;
    sys->cars[0].v = 10.0f;
    sys->cars[0].v_desired = 10.0f;
    sys->cars[0].brake = 0.0f;
    for (int i = 1; i < NUM_CARS; i++) {
        sys->cars[i].t = 0.01f;
        sys->cars[i].v = 0.0f;
        sys->cars[i].pos[0] = 1.0f;
    }

    car_system_update(sys, &graph, &ts, 0.2f, 0.0f, 0.0f);
    ASSERT_TRUE(sys->cars[0].v < 10.0f, "Car decelerates when approaching TRAFFIC_LIGHT_RED");
    ASSERT_NEAR(sys->cars[0].brake, 1.0f, 1e-5f, "Car brake light turns on at RED node");
    ASSERT_NEAR(sys->stagedInstances[0].brake, 1.0f, 1e-5f,
                "stagedInstances[0] brake reflects braking state");

    for (int step = 0; step < 15; step++) {
        car_system_update(sys, &graph, &ts, 0.1f, 0.0f, 0.0f);
    }
    ASSERT_TRUE(sys->cars[0].t < 1.0f, "Car stops before crossing RED intersection");
    ASSERT_NEAR(sys->cars[0].v, 0.0f, 1e-4f, "Car reaches full stop at RED intersection");
    ASSERT_NEAR(sys->stagedInstances[0].brake, 1.0f, 1e-5f,
                "stagedInstances[0] keeps brake active when stopped at RED light");

    free(sys);
    traffic_system_free(&ts);
}

static void test_sector_system_manifest(void) {
    SectorSystem* ss = calloc(1, sizeof(SectorSystem));
    ASSERT_TRUE(ss != NULL, "Allocated SectorSystem on heap");
    if (!ss) return;

    ASSERT_TRUE(sector_system_init(NULL, "models/sectors.json") == 0,
                "sector_system_init(NULL) returns 0");
    ASSERT_TRUE(sector_system_init(ss, NULL) == 0,
                "sector_system_init(NULL path) returns 0");
    ASSERT_TRUE(sector_system_init(ss, "models/no_existe_sectors.json") == 0,
                "sector_system_init(missing) returns 0");

    int ok = sector_system_init(ss, "models/sectors.json");
    ASSERT_TRUE(ok == 1, "sector_system_init loads models/sectors.json");
    ASSERT_TRUE(ss->sectorCount > 0, "SectorSystem loaded sectorCount > 0");
    ASSERT_TRUE(ss->macroSize > 0.0f && ss->chunkSize > 0.0f,
                "SectorSystem macroSize and chunkSize > 0");

    int valid_aabbs = 1;
    int valid_meta = 1;
    for (int i = 0; i < ss->sectorCount; i++) {
        const MacroSector* sec = &ss->sectors[i];
        if (sec->vertexCount == 0 || sec->filepath[0] == '\0') {
            valid_meta = 0;
        }
        if (!isfinite(sec->aabb.min_x) || !isfinite(sec->aabb.min_y) || !isfinite(sec->aabb.min_z) ||
            !isfinite(sec->aabb.max_x) || !isfinite(sec->aabb.max_y) || !isfinite(sec->aabb.max_z) ||
            sec->aabb.min_x > sec->aabb.max_x ||
            sec->aabb.min_y > sec->aabb.max_y ||
            sec->aabb.min_z > sec->aabb.max_z) {
            valid_aabbs = 0;
        }
    }
    ASSERT_TRUE(valid_meta == 1, "All loaded sectors have vertexCount > 0 and filepath");
    ASSERT_TRUE(valid_aabbs == 1, "All loaded sectors have valid finite AABBs");

    sector_system_destroy(ss, NULL);
    ASSERT_TRUE(ss->sectorCount == 0 && ss->syncInitialized == 0,
                "sector_system_destroy(&ss, NULL) resets sectorCount and sync");
    sector_system_destroy(NULL, NULL);

    free(ss);
}

static void test_dem_topography_precision(void) {
    /* Valores de referencia exactos de geo_dem.py::TerrainElevation(21.800, 21.950, -102.370, -102.245, nx=64, ny=64).get_real_topography(x, z) */
    static const struct {
        float x;
        float z;
        float expected_y;
        const char *label;
    } cases[] = {
        { 0.0000f, 0.0000f, -1.012219f, "DEM Centro (Plaza Patria)" },
        { -3667.1753f, -1035.2760f, -22.108718f, "DEM Rio San Pedro (cauce)" },
        { -3627.1753f, -1035.2760f, -20.879939f, "DEM Rio San Pedro (valle +40m E)" },
        { 1704.4618f, 1191.1240f, 8.949041f, "DEM Arroyo El Cedazo (cauce)" },
        { 1187.9582f, -2705.0760f, 17.366889f, "DEM Arroyo Don Pascual" },
        { -361.5525f, -5710.7160f, 13.169970f, "DEM Arroyo El Molino" },
        { 1782.7625f, 77.9240f, 10.086849f, "DEM Falla Oriente (bloque Oeste)" },
        { 1832.7625f, 77.9240f, 9.910399f, "DEM Falla Oriente (bloque Este)" },
        { -2245.9653f, -478.6760f, -17.970488f, "DEM Falla Poniente (bloque Oeste)" },
        { -2195.9653f, -478.6760f, -16.741881f, "DEM Falla Poniente (bloque Este)" },
        { 0.0000f, -7157.8760f, 18.726944f, "DEM Borde Tercer Anillo Norte" },
        { 0.0000f, 7870.3240f, -1.716160f, "DEM Borde Tercer Anillo Sur" },
        { -7076.0988f, 0.0000f, 11.269441f, "DEM Borde Tercer Anillo Oeste" },
        { 4803.4831f, 0.0000f, 62.296246f, "DEM Borde Tercer Anillo Este" },
    };

    float max_diff = 0.0f;
    size_t count = sizeof(cases) / sizeof(cases[0]);
    for (size_t i = 0; i < count; i++) {
        float got = terrain_dem_get_elevation(cases[i].x, cases[i].z);
        float diff = fabsf(got - cases[i].expected_y);
        if (diff > max_diff) max_diff = diff;
        ASSERT_NEAR(got, cases[i].expected_y, 0.05f, cases[i].label);
    }
    ASSERT_TRUE(max_diff < 0.005f, "Max DEM error vs geo_dem.py is < 0.005m");

    float clamped = terrain_dem_get_elevation(-25000.0f, 25000.0f);
    ASSERT_TRUE(isfinite(clamped), "Out-of-bounds terrain_dem_get_elevation clamps cleanly");
}

static void test_vulkan_memory_pool_tier_a(void) {
    VulkanMemoryPool pool;
    memset(&pool, 0, sizeof(pool));
    int dummy_dev = 1;
    VkDevice fake_dev = (VkDevice)(uintptr_t)&dummy_dev;
    ASSERT_TRUE(vulkan_memory_pool_init(&pool, fake_dev, VK_NULL_HANDLE, 0, 0, 65536) == 1,
                "Pool init succeeds");

    /* 1. Validación de memoryTypeIndex >= 32 */
    pool.memoryTypeIndex = 32;
    VulkanSuballocation subOut;
    ASSERT_TRUE(vulkan_memory_pool_bind_buffer(&pool, (VkBuffer)(uintptr_t)0x1, &subOut) == 0,
                "bind_buffer rejects memoryTypeIndex == 32 without UB");
    ASSERT_TRUE(vulkan_memory_pool_bind_image(&pool, (VkImage)(uintptr_t)0x1, &subOut) == 0,
                "bind_image rejects memoryTypeIndex == 32 without UB");
    pool.memoryTypeIndex = UINT32_MAX;
    ASSERT_TRUE(vulkan_memory_pool_bind_buffer(&pool, (VkBuffer)(uintptr_t)0x1, &subOut) == 0,
                "bind_buffer rejects memoryTypeIndex == UINT32_MAX without UB");
    pool.memoryTypeIndex = 0;

    /* 2. Overflow sin fugas (> 256 regiones libres con extraFreeRegions) */
    uint8_t backing[65536];
    int dummy_mem = 2;
    VkDeviceMemory fake_mem = (VkDeviceMemory)(uintptr_t)&dummy_mem;
    pool.blocks[0].memory = fake_mem;
    pool.blocks[0].size = sizeof(backing);
    pool.blocks[0].allocatedOffset = 0;
    pool.blocks[0].mappedBase = backing;
    pool.blockCount = 1;

    /* Subasignar 600 regiones de 16 bytes intercaladas */
    VulkanSuballocation subs[600];
    for (int i = 0; i < 600; i++) {
        subs[i] = vulkan_memory_pool_suballocate(&pool, 16, 16);
        ASSERT_TRUE(subs[i].memory == fake_mem, "Suballocated region from pool");
    }

    /* Liberar regiones pares (300 regiones libres no adyacentes) */
    for (int i = 0; i < 600; i += 2) {
        vulkan_memory_pool_free_suballocation(&pool, subs[i], 16);
    }
    ASSERT_TRUE(pool.freeRegionCount == 256, "256 free regions stored in static array");
    ASSERT_TRUE(pool.extraFreeRegionCount == 44, "44 overflow free regions stored in extraFreeRegions");

    /* Subasignar 44 regiones: deben ser servidas reutilizando memoria libre */
    for (int i = 0; i < 44; i++) {
        VulkanSuballocation re = vulkan_memory_pool_suballocate(&pool, 16, 16);
        ASSERT_TRUE(re.memory == fake_mem, "Suballocated from free/extra regions");
    }
    ASSERT_TRUE(pool.freeRegionCount + pool.extraFreeRegionCount == 256,
                "Free regions count decreased exactly by 44 after reuse");

    /* Limpieza de búfer dinámico en simulación CPU */
    if (pool.extraFreeRegions) {
        free(pool.extraFreeRegions);
        pool.extraFreeRegions = NULL;
    }
    pool.extraFreeRegionCount = 0;
    pool.extraFreeRegionCapacity = 0;
}

static void test_defensive_tier_a(void) {
    /* Test null safe traffic_system_free */
    traffic_system_free(NULL);
    ASSERT_TRUE(1, "traffic_system_free(NULL) is crash-safe");

    /* Test bounds safe road_graph_build_debug_mesh */
    RoadGraph rg;
    memset(&rg, 0, sizeof(rg));
    RoadPoint pts[2] = { {0,0,0}, {1,0,1} };
    RoadEdge edges[2];
    memset(edges, 0, sizeof(edges));
    edges[0].pt_off = 100; // Fuera de rango
    edges[0].pt_count = 5;
    edges[1].pt_off = 0;
    edges[1].pt_count = 2;

    rg.points = pts;
    rg.n_points = 2;
    rg.edges = edges;
    rg.n_edges = 2;

    Mesh* m = road_graph_build_debug_mesh(&rg);
    ASSERT_TRUE(m != NULL, "road_graph_build_debug_mesh handles out-of-bounds pt_off safely");
    if (m) {
        free(m->vertices);
        free(m);
    }
}

static void test_logger_system(void) {
    const char *log_dir = "build/test_logs";
    const char *text_path = "build/test_logs/street_vulkan.log";
    const char *jsonl_path = "build/test_logs/street_vulkan.jsonl";

    remove(text_path);
    remove(jsonl_path);

    ASSERT_TRUE(logger_init(log_dir, LOG_LEVEL_INFO) == 1, "logger_init creates dir and opens log files");
    ASSERT_TRUE(logger_get_level() == LOG_LEVEL_INFO, "logger_get_level returns initial INFO level");

    /* Level filtering: set to WARN, INFO/DEBUG/TRACE must be suppressed */
    logger_set_level(LOG_LEVEL_WARN);
    ASSERT_TRUE(logger_get_level() == LOG_LEVEL_WARN, "logger_set_level updates level to WARN");

    LOG_TRACE("TestMod", "filtered_trace_msg");
    LOG_DEBUG("TestMod", "filtered_debug_msg");
    LOG_INFO("TestMod", "filtered_info_msg");
    LOG_WARN("TestMod", "visible_warn_msg %d", 42);
    LOG_ERROR("TestMod", "visible_error_\"quoted\"");

    logger_shutdown();
    /* Double shutdown must be safe */
    logger_shutdown();

    /* Verify text log contents */
    FILE *tf = fopen(text_path, "r");
    ASSERT_TRUE(tf != NULL, "Text log file street_vulkan.log created");
    if (tf) {
        char buf[4096];
        size_t n = fread(buf, 1, sizeof(buf) - 1, tf);
        buf[n] = '\0';
        fclose(tf);

        ASSERT_TRUE(strstr(buf, "filtered_info_msg") == NULL, "Text log filters out INFO when level=WARN");
        ASSERT_TRUE(strstr(buf, "visible_warn_msg 42") != NULL, "Text log records WARN message");
        ASSERT_TRUE(strstr(buf, "visible_error_\"quoted\"") != NULL, "Text log records ERROR message");
        ASSERT_TRUE(strstr(buf, "test_c_modules.c:") != NULL, "Text log includes file:line on WARN/ERROR");
    }

    /* Verify JSONL log contents */
    FILE *jf = fopen(jsonl_path, "r");
    ASSERT_TRUE(jf != NULL, "JSONL log file street_vulkan.jsonl created");
    if (jf) {
        char buf[4096];
        size_t n = fread(buf, 1, sizeof(buf) - 1, jf);
        buf[n] = '\0';
        fclose(jf);

        ASSERT_TRUE(strstr(buf, "filtered_info_msg") == NULL, "JSONL log filters out INFO when level=WARN");
        ASSERT_TRUE(strstr(buf, "\"level\":\"WARN\"") != NULL, "JSONL log has WARN level field");
        ASSERT_TRUE(strstr(buf, "\"tag\":\"TestMod\"") != NULL, "JSONL log has tag field");
        ASSERT_TRUE(strstr(buf, "visible_error_\\\"quoted\\\"") != NULL, "JSONL log escapes quotes properly");
        ASSERT_TRUE(strstr(buf, "\"line\":") != NULL, "JSONL log includes line field on WARN/ERROR");
    }

    remove(text_path);
    remove(jsonl_path);
}

int main(void) {
    test_math_camera();
    test_frustum_culling();
    test_traffic_system_fsm();
    test_road_graph_binary();
    test_vulkan_memory_pool();
    test_vulkan_memory_pool_tier_a();
    test_defensive_tier_a();
    test_traffic_system_o1_intersection_resolution();
    test_obj_loader_and_sector_bounds();
    test_ped_system();
    test_recoverability_and_iso25022();
    test_car_system_headless();
    test_sector_system_manifest();
    test_dem_topography_precision();
    test_logger_system();

    printf("[XP Unit Tests C] Ejecutados: %d | Fallidos: %d\n", g_tests_run, g_tests_failed);
    return (g_tests_failed == 0) ? 0 : 1;
}
