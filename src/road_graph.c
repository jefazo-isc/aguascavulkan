#include "road_graph.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static int road_graph_build_edge_lengths(RoadGraph* graph) {
    if (graph->n_edges == 0) {
        graph->edge_lengths = NULL;
        return 1;
    }

    graph->edge_lengths = (float*)malloc((size_t)graph->n_edges * sizeof(float));
    if (!graph->edge_lengths) {
        return 0;
    }

    for (uint32_t e = 0; e < graph->n_edges; e++) {
        const RoadEdge* edge = &graph->edges[e];
        float elen = 0.0f;
        if (edge->pt_count >= 2 &&
            (uint64_t)edge->pt_off + (uint64_t)edge->pt_count <= (uint64_t)graph->n_points) {
            for (uint32_t i = 0; i < edge->pt_count - 1; i++) {
                RoadPoint a = graph->points[edge->pt_off + i];
                RoadPoint b = graph->points[edge->pt_off + i + 1];
                float dx = b.x - a.x;
                float dy = b.y - a.y;
                float dz = b.z - a.z;
                elen += sqrtf(dx * dx + dy * dy + dz * dz);
            }
        }
        graph->edge_lengths[e] = (elen < 0.1f) ? 0.1f : elen;
    }
    return 1;
}

static int road_graph_build_csr(RoadGraph* graph) {
    uint32_t n_nodes = graph->n_nodes;
    uint32_t n_edges = graph->n_edges;

    graph->node_edge_offsets = (uint32_t*)calloc((size_t)n_nodes + 1, sizeof(uint32_t));
    if (!graph->node_edge_offsets) {
        return 0;
    }

    if (n_nodes == 0 || n_edges == 0) {
        graph->total_incidences = 0;
        return 1;
    }

    uint64_t total_inc = 0;
    for (uint32_t e = 0; e < n_edges; e++) {
        const RoadEdge* edge = &graph->edges[e];
        if (edge->pt_count < 2) continue;
        if ((uint64_t)edge->pt_off + (uint64_t)edge->pt_count > (uint64_t)graph->n_points) continue;
        if (edge->a < n_nodes) {
            if (graph->node_edge_offsets[edge->a + 1] == UINT32_MAX) return 0;
            graph->node_edge_offsets[edge->a + 1]++;
            total_inc++;
        }
        if (!edge->oneway && edge->b < n_nodes) {
            if (graph->node_edge_offsets[edge->b + 1] == UINT32_MAX) return 0;
            graph->node_edge_offsets[edge->b + 1]++;
            total_inc++;
        }
    }

    if (total_inc > UINT32_MAX) {
        return 0;
    }

    for (uint32_t n = 0; n < n_nodes; n++) {
        graph->node_edge_offsets[n + 1] += graph->node_edge_offsets[n];
    }
    graph->total_incidences = (uint32_t)total_inc;

    if (graph->total_incidences == 0) {
        return 1;
    }

    graph->node_edge_indices = (uint32_t*)malloc((size_t)graph->total_incidences * sizeof(uint32_t));
    graph->node_edge_dirs = (uint8_t*)malloc((size_t)graph->total_incidences * sizeof(uint8_t));
    uint32_t* cursor = (uint32_t*)malloc((size_t)n_nodes * sizeof(uint32_t));
    if (!graph->node_edge_indices || !graph->node_edge_dirs || !cursor) {
        free(cursor);
        return 0;
    }

    memcpy(cursor, graph->node_edge_offsets, (size_t)n_nodes * sizeof(uint32_t));

    for (uint32_t e = 0; e < n_edges; e++) {
        const RoadEdge* edge = &graph->edges[e];
        if (edge->pt_count < 2) continue;
        if ((uint64_t)edge->pt_off + (uint64_t)edge->pt_count > (uint64_t)graph->n_points) continue;
        if (edge->a < n_nodes) {
            uint32_t pos = cursor[edge->a]++;
            graph->node_edge_indices[pos] = e;
            graph->node_edge_dirs[pos] = 0;
        }
        if (!edge->oneway && edge->b < n_nodes) {
            uint32_t pos = cursor[edge->b]++;
            graph->node_edge_indices[pos] = e;
            graph->node_edge_dirs[pos] = 1;
        }
    }

    free(cursor);
    return 1;
}

RoadGraph* road_graph_load(const char* filepath) {
    if (!filepath) {
        fprintf(stderr, "[RoadGraph] Error: Ruta NULL\n");
        return NULL;
    }

    FILE* f = fopen(filepath, "rb");
    if (!f) {
        fprintf(stderr, "[RoadGraph] Error: No se pudo abrir %s\n", filepath);
        return NULL;
    }

    char magic[4];
    uint32_t n_nodes = 0, n_edges = 0, n_points = 0;
    if (fread(magic, 1, 4, f) != 4 || memcmp(magic, "RGP1", 4) != 0) {
        fprintf(stderr, "[RoadGraph] Error: Formato invalido en %s (magic no es RGP1)\n", filepath);
        fclose(f);
        return NULL;
    }

    if (fread(&n_nodes, sizeof(uint32_t), 1, f) != 1 ||
        fread(&n_edges, sizeof(uint32_t), 1, f) != 1 ||
        fread(&n_points, sizeof(uint32_t), 1, f) != 1) {
        fprintf(stderr, "[RoadGraph] Error leyendo header de %s\n", filepath);
        fclose(f);
        return NULL;
    }

    RoadGraph* graph = (RoadGraph*)calloc(1, sizeof(RoadGraph));
    if (!graph) {
        fclose(f);
        return NULL;
    }

    graph->n_nodes = n_nodes;
    graph->n_edges = n_edges;
    graph->n_points = n_points;

    if (n_nodes > 0) graph->nodes = (RoadNode*)malloc((size_t)n_nodes * sizeof(RoadNode));
    if (n_edges > 0) graph->edges = (RoadEdge*)malloc((size_t)n_edges * sizeof(RoadEdge));
    if (n_points > 0) graph->points = (RoadPoint*)malloc((size_t)n_points * sizeof(RoadPoint));

    if ((n_nodes > 0 && !graph->nodes) ||
        (n_edges > 0 && !graph->edges) ||
        (n_points > 0 && !graph->points)) {
        fprintf(stderr, "[RoadGraph] Error de memoria asignando buffers\n");
        road_graph_free(graph);
        fclose(f);
        return NULL;
    }

    if ((n_nodes > 0 && fread(graph->nodes, sizeof(RoadNode), n_nodes, f) != n_nodes) ||
        (n_edges > 0 && fread(graph->edges, sizeof(RoadEdge), n_edges, f) != n_edges) ||
        (n_points > 0 && fread(graph->points, sizeof(RoadPoint), n_points, f) != n_points)) {
        fprintf(stderr, "[RoadGraph] Error leyendo datos binarios de %s\n", filepath);
        road_graph_free(graph);
        fclose(f);
        return NULL;
    }

    fclose(f);

    if (!road_graph_build_edge_lengths(graph) || !road_graph_build_csr(graph)) {
        fprintf(stderr, "[RoadGraph] Error de memoria construyendo CSR/longitudes\n");
        road_graph_free(graph);
        return NULL;
    }

    printf("[RoadGraph] Cargado '%s': %u nodos, %u aristas, %u puntos\n",
           filepath, n_nodes, n_edges, n_points);
    return graph;
}

void road_graph_free(RoadGraph* graph) {
    if (!graph) return;
    free(graph->nodes);
    free(graph->edges);
    free(graph->points);
    free(graph->edge_lengths);
    free(graph->node_edge_offsets);
    free(graph->node_edge_indices);
    free(graph->node_edge_dirs);
    free(graph);
}

Mesh* road_graph_build_debug_mesh(const RoadGraph* graph) {
    if (!graph || graph->n_edges == 0) return NULL;

    // Estimar vértices requeridos:
    // Cada tramo de arista (p1 -> p2) genera 2 triángulos (6 vértices) de 0.15m ancho.
    // Cada nodo de semáforo genera 1 caja/quad (12 vértices).
    size_t segment_count = 0;
    for (uint32_t i = 0; i < graph->n_edges; i++) {
        if (graph->edges[i].pt_count >= 2) {
            segment_count += (graph->edges[i].pt_count - 1);
        }
    }

    size_t signal_count = 0;
    for (uint32_t i = 0; i < graph->n_nodes; i++) {
        if (graph->nodes[i].signal_group >= 0) {
            signal_count++;
        }
    }

    size_t max_verts = segment_count * 6 + signal_count * 36;
    Vertex* verts = (Vertex*)malloc(max_verts * sizeof(Vertex));
    if (!verts) return NULL;

    size_t v_idx = 0;
    const float line_hw = 0.075f; // 0.15m ancho total (mitad = 0.075m)
    const float y_offset = 0.25f; // +0.25m sobre Y del grafo

    for (uint32_t e = 0; e < graph->n_edges; e++) {
        const RoadEdge* edge = &graph->edges[e];
        if (edge->pt_count < 2) continue;

        // Color por tipo: Verde (doble sentido), Azul (one-way)
        float r = edge->oneway ? 0.0f : 0.0f;
        float g = edge->oneway ? 0.4f : 0.9f;
        float b = edge->oneway ? 1.0f : 0.1f;
        float a = 1.0f;
        float em = 1.5f;

        for (uint32_t i = 0; i < edge->pt_count - 1; i++) {
            uint32_t p_idx1 = edge->pt_off + i;
            uint32_t p_idx2 = edge->pt_off + i + 1;
            if (p_idx1 >= graph->n_points || p_idx2 >= graph->n_points) {
                continue;
            }
            RoadPoint p1 = graph->points[p_idx1];
            RoadPoint p2 = graph->points[p_idx2];

            float dx = p2.x - p1.x;
            float dz = p2.z - p1.z;
            float len = sqrtf(dx * dx + dz * dz);
            if (len < 0.001f) continue;

            float nx = -dz / len;
            float nz = dx / len;

            float p1x = p1.x, p1y = p1.y + y_offset, p1z = p1.z;
            float p2x = p2.x, p2y = p2.y + y_offset, p2z = p2.z;

            // 4 esquinas de la cinta
            float ax = p1x - nx * line_hw, ay = p1y, az = p1z - nz * line_hw;
            float bx = p1x + nx * line_hw, by = p1y, bz = p1z + nz * line_hw;
            float cx = p2x + nx * line_hw, cy = p2y, cz = p2z + nz * line_hw;
            float dx_c = p2x - nx * line_hw, dy_c = p2y, dz_c = p2z - nz * line_hw;

            // Triángulo 1: A, B, C
            verts[v_idx++] = (Vertex){ax, ay, az, 0, 1, 0, 0, 0, r, g, b, a, em};
            verts[v_idx++] = (Vertex){bx, by, bz, 0, 1, 0, 0, 0, r, g, b, a, em};
            verts[v_idx++] = (Vertex){cx, cy, cz, 0, 1, 0, 0, 0, r, g, b, a, em};

            // Triángulo 2: A, C, D
            verts[v_idx++] = (Vertex){ax, ay, az, 0, 1, 0, 0, 0, r, g, b, a, em};
            verts[v_idx++] = (Vertex){cx, cy, cz, 0, 1, 0, 0, 0, r, g, b, a, em};
            verts[v_idx++] = (Vertex){dx_c, dy_c, dz_c, 0, 1, 0, 0, 0, r, g, b, a, em};
        }
    }

    // Dibujar semáforos como cubos rojos en nodos de semáforo
    const float box_size = 0.6f;
    const float half_b = box_size * 0.5f;

    for (uint32_t i = 0; i < graph->n_nodes; i++) {
        const RoadNode* node = &graph->nodes[i];
        if (node->signal_group < 0) continue;

        float nx_pos = node->x;
        float ny_pos = node->y + 0.5f;
        float nz_pos = node->z;
        float sr = 1.0f, sg = 0.0f, sb = 0.0f, sa = 1.0f;
        float sem = 2.0f;

        // Caja superior/cubo rojo de semáforo
        float x0 = nx_pos - half_b, x1 = nx_pos + half_b;
        float y1 = ny_pos + box_size;
        float z0 = nz_pos - half_b, z1 = nz_pos + half_b;

        // Cara superior (+Y)
        verts[v_idx++] = (Vertex){x0, y1, z1, 0, 1, 0, 0, 0, sr, sg, sb, sa, sem};
        verts[v_idx++] = (Vertex){x1, y1, z1, 0, 1, 0, 0, 0, sr, sg, sb, sa, sem};
        verts[v_idx++] = (Vertex){x1, y1, z0, 0, 1, 0, 0, 0, sr, sg, sb, sa, sem};

        verts[v_idx++] = (Vertex){x0, y1, z1, 0, 1, 0, 0, 0, sr, sg, sb, sa, sem};
        verts[v_idx++] = (Vertex){x1, y1, z0, 0, 1, 0, 0, 0, sr, sg, sb, sa, sem};
        verts[v_idx++] = (Vertex){x0, y1, z0, 0, 1, 0, 0, 0, sr, sg, sb, sa, sem};
    }

    Mesh* mesh = (Mesh*)calloc(1, sizeof(Mesh));
    if (!mesh) {
        free(verts);
        return NULL;
    }

    mesh->vertices = verts;
    mesh->vertexCount = v_idx;
    printf("[RoadGraph] Malla de debug construida: %zu vértices\n", v_idx);
    return mesh;
}
