#ifndef VULKAN_GLTF_H
#define VULKAN_GLTF_H

#include "obj_loader.h" // Proporciona la estructura Mesh y Vertex

struct VulkanEngine;

// Carga un archivo binario glTF (.glb) y genera una malla con vértices unificados
// (Posición, normal, UVs, colores RGBA y emisión de semáforos)
// Devuelve NULL en caso de error. Liberar con mesh_free() / obj_free()
Mesh* gltf_load(const char* filepath);

// Carga directa Zero-Copy de alta fidelidad: parsea directo del mmap a los búferes
// Vulkan en memoria unificada (UMA) sin duplicación en CPU ni staging buffers (-5.3 GB RAM).
int gltf_load_direct_vulkan(const char* filepath, struct VulkanEngine* eng);

#endif // VULKAN_GLTF_H
