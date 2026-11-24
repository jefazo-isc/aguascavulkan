#ifndef ROAD_GRAPH_H
#define ROAD_GRAPH_H

#include <stdint.h>
#include <stddef.h>
#include "obj_loader.h"

#pragma pack(push, 1)
typedef struct {
    float x, y, z;
    int32_t signal_group;
    uint8_t degree;
    uint8_t pad[3];
} RoadNode;

typedef struct {
    uint32_t a, b;
    uint32_t pt_off, pt_count;
    float speed_ms, width;
    uint8_t lanes_fwd, lanes_rev, oneway, pad;
} RoadEdge;

typedef struct {
    float x, y, z;
} RoadPoint;
#pragma pack(pop)

typedef struct {
    uint32_t n_nodes;
    uint32_t n_edges;
    uint32_t n_points;
    RoadNode* nodes;
    RoadEdge* edges;
    RoadPoint* points;
    float* edge_lengths;
    uint32_t* node_edge_offsets;
    uint32_t* node_edge_indices;
    uint8_t* node_edge_dirs;
    uint32_t total_incidences;
} RoadGraph;

// Carga el grafo vial desde un archivo binario en formato RGP1
RoadGraph* road_graph_load(const char* filepath);

// Libera los recursos del grafo vial
void road_graph_free(RoadGraph* graph);

// Genera una malla de depuración con triángulos delgados sobre las aristas (+0.25m Y)
// Verde = doble sentido, Azul = sentido único (oneway), Rojo = nodo con semáforo
Mesh* road_graph_build_debug_mesh(const RoadGraph* graph);

#endif // ROAD_GRAPH_H
