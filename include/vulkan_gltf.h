#ifndef VULKAN_GLTF_H
#define VULKAN_GLTF_H

#include "obj_loader.h" // Proporciona la estructura Mesh y Vertex

// Carga un archivo binario glTF (.glb) y genera una malla con vértices unificados
// (Posición, normal, UVs, colores RGBA y emisión de semáforos)
// Devuelve NULL en caso de error. Liberar con mesh_free() / obj_free()
Mesh* gltf_load(const char* filepath);

#endif // VULKAN_GLTF_H
