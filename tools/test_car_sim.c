#include "road_graph.h"
#include "car_system.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>

int main(void) {
    RoadGraph* graph = road_graph_load("models/road_network.bin");
    assert(graph != NULL);
    assert(graph->n_edges > 0);

    CarSystem sys;
    memset(&sys, 0, sizeof(CarSystem));
    sys.mappedInstanceDatas[0] = (CarInstanceData*)calloc(NUM_CARS, sizeof(CarInstanceData));

    // Inicializar 200 coches simulados
    float cam_x = 0.0f, cam_z = 0.0f;
    for (int i = 0; i < NUM_CARS; i++) {
        sys.cars[i].mesh_type = i % NUM_CAR_TYPES;
    }

    printf("[SimTest] Ejecutando simulación cinemática de 200 coches durante 120s (7200 frames @ 60FPS)...\n");

    float dt = 1.0f / 60.0f;
    int nan_detected = 0;

    for (int frame = 0; frame < 7200; frame++) {
        car_system_update(&sys, graph, NULL, dt, cam_x, cam_z);

        for (int i = 0; i < NUM_CARS; i++) {
            Car* c = &sys.cars[i];
            if (isnan(c->pos[0]) || isnan(c->pos[1]) || isnan(c->pos[2]) || isnan(c->heading)) {
                fprintf(stderr, "[SimTest] ERROR: NaN detectado en coche %d en frame %d\n", i, frame);
                nan_detected = 1;
                break;
            }
            if (isinf(c->pos[0]) || isinf(c->pos[1]) || isinf(c->pos[2])) {
                fprintf(stderr, "[SimTest] ERROR: Inf detectado en coche %d en frame %d\n", i, frame);
                nan_detected = 1;
                break;
            }
        }
        if (nan_detected) break;
    }

    free(sys.mappedInstanceDatas[0]);
    road_graph_free(graph);

    if (nan_detected) {
        printf("[SimTest] ❌ PRUEBA FALLIDA: Se encontraron NaNs/Infs.\n");
        return 1;
    } else {
        printf("[SimTest] ✅ PRUEBA EXITOSA: 7200 frames simulados (120s @ 60FPS) con CERO NaNs y 200 coches circulando.\n");
        return 0;
    }
}
