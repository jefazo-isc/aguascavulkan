#ifndef OBJ_LOADER_H
#define OBJ_LOADER_H

#include <stdlib.h>
#include "vertex_format.h"

// Estructura de resultados de carga de mallas
typedef struct {
    Vertex* vertices;       // Array de vértices finales
    size_t vertexCount;     // Número de vértices
    size_t* indices;        // Indices (3 por triángulo)
    size_t indexCount;      // Número de indices
} Mesh;

// Carga un archivo OBJ compatible con el formato Vertex unificado
// Devuelve NULL en caso de error
// El caller debe liberar con obj_free()
Mesh* obj_load(const char* filename);

// Libera la memoria de un Mesh
void obj_free(Mesh* mesh);

#endif // OBJ_LOADER_H
