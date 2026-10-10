#ifndef VERTEX_FORMAT_H
#define VERTEX_FORMAT_H

#include <vulkan/vulkan.h>
#include <stddef.h>

// Vértice completo para el motor StreetVulkan:
// Soporta geometría 3D, normales, UVs para ortofoto satelital,
// color por vértice (fachadas, azoteas, asfalto) y canal de emisión dinámico (semáforos)
typedef struct {
    float x, y, z;        // Ubicación 0: Posición en metros (espacio local / mundo)
    float nx, ny, nz;     // Ubicación 1: Normal unitaria
    float u, v;           // Ubicación 2: Coordenadas UV de textura
    float r, g, b, a;     // Ubicación 3: Color RGBA (A = factor de mezcla textura/color)
    float emission;       // Ubicación 4: Brillo emisivo (0.0 = mate, >0.0 = semáforo/luz encendida)
} Vertex;

static inline VkVertexInputBindingDescription vertex_get_binding_description(void) {
    VkVertexInputBindingDescription bindingDescription = {0};
    bindingDescription.binding = 0;
    bindingDescription.stride = sizeof(Vertex);
    bindingDescription.inputRate = VK_VERTEX_INPUT_RATE_VERTEX;
    return bindingDescription;
}

static inline void vertex_get_attribute_descriptions(VkVertexInputAttributeDescription attrs[5]) {
    // 0: inPosition (vec3)
    attrs[0].binding = 0;
    attrs[0].location = 0;
    attrs[0].format = VK_FORMAT_R32G32B32_SFLOAT;
    attrs[0].offset = offsetof(Vertex, x);

    // 1: inNormal (vec3)
    attrs[1].binding = 0;
    attrs[1].location = 1;
    attrs[1].format = VK_FORMAT_R32G32B32_SFLOAT;
    attrs[1].offset = offsetof(Vertex, nx);

    // 2: inTexCoord (vec2)
    attrs[2].binding = 0;
    attrs[2].location = 2;
    attrs[2].format = VK_FORMAT_R32G32_SFLOAT;
    attrs[2].offset = offsetof(Vertex, u);

    // 3: inColor (vec4)
    attrs[3].binding = 0;
    attrs[3].location = 3;
    attrs[3].format = VK_FORMAT_R32G32B32A32_SFLOAT;
    attrs[3].offset = offsetof(Vertex, r);

    // 4: inEmission (float)
    attrs[4].binding = 0;
    attrs[4].location = 4;
    attrs[4].format = VK_FORMAT_R32_SFLOAT;
    attrs[4].offset = offsetof(Vertex, emission);
}

#endif // VERTEX_FORMAT_H
