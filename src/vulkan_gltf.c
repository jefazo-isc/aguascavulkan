#include "vulkan_gltf.h"
#include "vulkan_types.h"
#include "vulkan_memory_pool.h"
#include "traffic_system.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

extern void SDL_PumpEvents(void);

#pragma GCC push_options
#pragma GCC optimize("O0")
#define CGLTF_IMPLEMENTATION
#include "cgltf.h"
#pragma GCC pop_options

static cgltf_result mmap_file_read(const struct cgltf_memory_options* mem, const struct cgltf_file_options* file_opt, const char* path, cgltf_size* size, void** data) {
    (void)mem; (void)file_opt;
    int fd = open(path, O_RDONLY);
    if (fd < 0) return cgltf_result_file_not_found;
    struct stat st;
    if (fstat(fd, &st) != 0) { close(fd); return cgltf_result_io_error; }
    void* ptr = mmap(NULL, st.st_size, PROT_READ, MAP_SHARED, fd, 0);
    close(fd);
    if (ptr == MAP_FAILED) return cgltf_result_out_of_memory;
    madvise(ptr, st.st_size, MADV_SEQUENTIAL);
    *size = (cgltf_size)st.st_size;
    *data = ptr;
    return cgltf_result_success;
}

static void mmap_file_release(const struct cgltf_memory_options* mem, const struct cgltf_file_options* file_opt, void* data, cgltf_size size) {
    (void)mem; (void)file_opt;
    if (data && size > 0) {
        munmap(data, size);
    }
}

typedef struct {
    cgltf_accessor* pos;
    cgltf_accessor* norm;
    cgltf_accessor* uv;
    cgltf_accessor* col;
    cgltf_accessor* em;
    float matEmission;
} GltfPrimAccessors;

/* Abre y carga en memoria mapeada los buffers de un archivo glTF/GLB. */
static cgltf_data* gltf_open_and_load(const char* filepath, const char* tag) {
    cgltf_options options = {0};
    options.file.read = mmap_file_read;
    options.file.release = mmap_file_release;
    cgltf_data* data = NULL;
    cgltf_result result = cgltf_parse_file(&options, filepath, &data);
    if (result != cgltf_result_success) {
        fprintf(stderr, "[%s] Error al parsear: %s (%d)\n", tag, filepath, (int)result);
        return NULL;
    }
    result = cgltf_load_buffers(&options, data, filepath);
    if (result != cgltf_result_success) {
        fprintf(stderr, "[%s] Error buffers: %s (%d)\n", tag, filepath, (int)result);
        cgltf_free(data);
        return NULL;
    }
    return data;
}

static size_t gltf_prim_vertex_count(const cgltf_primitive* prim) {
    for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
        if (prim->attributes[a].type == cgltf_attribute_type_position) {
            return prim->attributes[a].data->count;
        }
    }
    return 0;
}

/* Cuenta el total de vértices e índices triangulares de la escena glTF. */
static void gltf_count_geometry(const cgltf_data* data, size_t* outVerts, size_t* outIndices) {
    size_t totalVertices = 0;
    size_t totalIndices = 0;
    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        const cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            const cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;
            size_t vertCount = gltf_prim_vertex_count(prim);
            totalVertices += vertCount;
            totalIndices += prim->indices ? prim->indices->count : vertCount;
        }
    }
    *outVerts = totalVertices;
    *outIndices = totalIndices;
}

static int gltf_is_emission_attr(const char* name) {
    if (!name) return 0;
    return strcmp(name, "_EMISSION") == 0 ||
           strcmp(name, "EMISSION") == 0 ||
           strcmp(name, "_EMISSION_FACTOR") == 0;
}

static float gltf_compute_mat_emission(const cgltf_material* mat) {
    if (!mat) return 0.0f;
    float er = mat->emissive_factor[0];
    float eg = mat->emissive_factor[1];
    float eb = mat->emissive_factor[2];
    if (er > 0.01f || eg > 0.01f || eb > 0.01f) {
        return (er + eg + eb) / 3.0f * 3.0f;
    }
    return 0.0f;
}

/* Extrae los accessors de atributos y emisión de una primitiva triangular. */
static int gltf_extract_prim_accessors(const cgltf_primitive* prim, GltfPrimAccessors* out) {
    memset(out, 0, sizeof(*out));
    for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
        const cgltf_attribute* attr = &prim->attributes[a];
        if (attr->type == cgltf_attribute_type_position) out->pos = attr->data;
        else if (attr->type == cgltf_attribute_type_normal) out->norm = attr->data;
        else if (attr->type == cgltf_attribute_type_texcoord) out->uv = attr->data;
        else if (attr->type == cgltf_attribute_type_color) out->col = attr->data;
        else if (attr->type == cgltf_attribute_type_custom && gltf_is_emission_attr(attr->name)) {
            out->em = attr->data;
        }
    }
    if (!out->pos) return 0;
    out->matEmission = gltf_compute_mat_emission(prim->material);
    return 1;
}

static void gltf_write_prim_vertices_accessor(const GltfPrimAccessors* acc, Vertex* outVerts, size_t* vertWriteIdx) {
    size_t count = acc->pos->count;
    for (size_t vIdx = 0; vIdx < count; ++vIdx) {
        Vertex v;
        memset(&v, 0, sizeof(Vertex));

        float pos[3] = {0};
        cgltf_accessor_read_float(acc->pos, vIdx, pos, 3);
        v.x = pos[0]; v.y = pos[1]; v.z = pos[2];

        if (acc->norm) {
            float n[3] = {0, 1, 0};
            cgltf_accessor_read_float(acc->norm, vIdx, n, 3);
            v.nx = n[0]; v.ny = n[1]; v.nz = n[2];
        } else {
            v.ny = 1.0f;
        }

        if (acc->uv) {
            float uv[2] = {0};
            cgltf_accessor_read_float(acc->uv, vIdx, uv, 2);
            v.u = uv[0]; v.v = uv[1];
        }

        if (acc->col) {
            float col[4] = {1, 1, 1, 1};
            cgltf_accessor_read_float(acc->col, vIdx, col, 4);
            v.r = col[0]; v.g = col[1]; v.b = col[2]; v.a = col[3];
        } else {
            v.r = 1; v.g = 1; v.b = 1;
            v.a = (acc->uv != NULL) ? 0.0f : 1.0f;
        }

        if (acc->em) {
            float em[1] = {0};
            cgltf_accessor_read_float(acc->em, vIdx, em, 1);
            v.emission = em[0];
        } else {
            v.emission = acc->matEmission;
        }

        outVerts[(*vertWriteIdx)++] = v;
    }
}

static void gltf_write_prim_indices_size(const cgltf_primitive* prim, size_t primVertexOffset,
                                         size_t primVertexCount, size_t* outIndices, size_t* indexWriteIdx) {
    if (prim->indices) {
        for (size_t i = 0; i < prim->indices->count; ++i) {
            outIndices[(*indexWriteIdx)++] = primVertexOffset + cgltf_accessor_read_index(prim->indices, i);
        }
        return;
    }
    for (size_t i = 0; i < primVertexCount; ++i) {
        outIndices[(*indexWriteIdx)++] = primVertexOffset + i;
    }
}

static const uint8_t* gltf_accessor_data_ptr(const cgltf_accessor* acc) {
    if (!acc || !acc->buffer_view) return NULL;
    return cgltf_buffer_view_data(acc->buffer_view) + acc->offset;
}

static void gltf_write_prim_vertices_direct(const GltfPrimAccessors* acc, Vertex* outVerts, size_t* vertWriteIdx) {
    size_t count = acc->pos->count;
    const uint8_t* posBase = gltf_accessor_data_ptr(acc->pos);
    const uint8_t* normBase = gltf_accessor_data_ptr(acc->norm);
    const uint8_t* uvBase = gltf_accessor_data_ptr(acc->uv);
    const uint8_t* colBase = gltf_accessor_data_ptr(acc->col);
    const uint8_t* emBase = gltf_accessor_data_ptr(acc->em);

    size_t posStride = acc->pos->stride ? acc->pos->stride : sizeof(float) * 3;
    size_t normStride = (acc->norm && acc->norm->stride) ? acc->norm->stride : sizeof(float) * 3;
    size_t uvStride = (acc->uv && acc->uv->stride) ? acc->uv->stride : sizeof(float) * 2;
    size_t colStride = (acc->col && acc->col->stride) ? acc->col->stride : sizeof(float) * 4;
    size_t emStride = (acc->em && acc->em->stride) ? acc->em->stride : sizeof(float);

    for (size_t vIdx = 0; vIdx < count; ++vIdx) {
        if ((vIdx & 0x7FFFF) == 0) {
            SDL_PumpEvents();
        }
        const float* pos = (const float*)(posBase + vIdx * posStride);
        Vertex* v = &outVerts[(*vertWriteIdx)++];
        v->x = pos[0]; v->y = pos[1]; v->z = pos[2];

        if (normBase) {
            const float* norm = (const float*)(normBase + vIdx * normStride);
            v->nx = norm[0]; v->ny = norm[1]; v->nz = norm[2];
        } else {
            v->nx = 0.0f; v->ny = 1.0f; v->nz = 0.0f;
        }

        if (uvBase) {
            const float* uv = (const float*)(uvBase + vIdx * uvStride);
            v->u = uv[0]; v->v = uv[1];
        } else {
            v->u = 0.0f; v->v = 0.0f;
        }

        if (colBase) {
            const float* col = (const float*)(colBase + vIdx * colStride);
            v->r = col[0]; v->g = col[1]; v->b = col[2]; v->a = col[3];
        } else {
            v->r = 1.0f; v->g = 1.0f; v->b = 1.0f;
            v->a = (uvBase != NULL) ? 0.0f : 1.0f;
        }

        if (emBase) {
            const float* em = (const float*)(emBase + vIdx * emStride);
            v->emission = em[0];
        } else {
            v->emission = acc->matEmission;
        }
    }
}

static void gltf_write_prim_indices_u32(const cgltf_primitive* prim, size_t primVertexOffset,
                                        size_t primVertexCount, uint32_t* outIndices, size_t* indexWriteIdx) {
    if (!outIndices) return;
    if (!prim->indices || !prim->indices->buffer_view) {
        for (size_t i = 0; i < primVertexCount; ++i) {
            outIndices[(*indexWriteIdx)++] = (uint32_t)(primVertexOffset + i);
        }
        return;
    }

    const uint8_t* idxBase = cgltf_buffer_view_data(prim->indices->buffer_view) + prim->indices->offset;
    size_t count = prim->indices->count;
    if (prim->indices->component_type == cgltf_component_type_r_32u) {
        const uint32_t* pIdx = (const uint32_t*)idxBase;
        if (primVertexOffset == 0) {
            memcpy(outIndices + *indexWriteIdx, pIdx, count * sizeof(uint32_t));
            *indexWriteIdx += count;
            return;
        }
        for (size_t i = 0; i < count; ++i) {
            outIndices[(*indexWriteIdx)++] = (uint32_t)(primVertexOffset + pIdx[i]);
        }
    } else if (prim->indices->component_type == cgltf_component_type_r_16u) {
        const uint16_t* pIdx = (const uint16_t*)idxBase;
        for (size_t i = 0; i < count; ++i) {
            outIndices[(*indexWriteIdx)++] = (uint32_t)(primVertexOffset + pIdx[i]);
        }
    } else {
        for (size_t i = 0; i < count; ++i) {
            outIndices[(*indexWriteIdx)++] = (uint32_t)(primVertexOffset + cgltf_accessor_read_index(prim->indices, i));
        }
    }
}

/* Crea y vincula vertex/index buffers directamente en hostVisiblePool (zero-copy). */
static int gltf_create_direct_buffers(struct VulkanEngine* eng, size_t bufferSize, size_t indexBufferSize,
                                      size_t totalIndices, VulkanSuballocation* vertexSub, VulkanSuballocation* indexSub) {
    VkBufferCreateInfo vertexInfo = {0};
    vertexInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    vertexInfo.size = bufferSize;
    vertexInfo.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
    vertexInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    if (vkCreateBuffer(eng->device, &vertexInfo, NULL, &eng->vertexBuffer) != VK_SUCCESS) {
        fprintf(stderr, "[glTF Direct] Error creando Vertex Buffer directo\n");
        return 0;
    }
    if (!vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, eng->vertexBuffer, vertexSub) || !vertexSub->mappedPtr) {
        fprintf(stderr, "[glTF Direct] Error vinculando Vertex Buffer directo al pool\n");
        vkDestroyBuffer(eng->device, eng->vertexBuffer, NULL);
        return 0;
    }

    if (totalIndices > 0) {
        VkBufferCreateInfo indexInfo = {0};
        indexInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        indexInfo.size = indexBufferSize;
        indexInfo.usage = VK_BUFFER_USAGE_INDEX_BUFFER_BIT;
        indexInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

        if (vkCreateBuffer(eng->device, &indexInfo, NULL, &eng->indexBuffer) == VK_SUCCESS) {
            vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, eng->indexBuffer, indexSub);
        }
    }
    return 1;
}

Mesh* gltf_load(const char* filepath) {
    cgltf_data* data = gltf_open_and_load(filepath, "glTF");
    if (!data) return NULL;

    size_t totalVertices = 0, totalIndices = 0;
    gltf_count_geometry(data, &totalVertices, &totalIndices);
    if (totalVertices == 0) {
        fprintf(stderr, "[glTF] Sin geometría: %s\n", filepath);
        cgltf_free(data);
        return NULL;
    }

    Vertex* outVerts = malloc(totalVertices * sizeof(Vertex));
    size_t* outIndices = (totalIndices > 0) ? malloc(totalIndices * sizeof(size_t)) : NULL;
    if (!outVerts || (totalIndices > 0 && !outIndices)) {
        free(outVerts);
        free(outIndices);
        cgltf_free(data);
        return NULL;
    }

    size_t vertWriteIdx = 0, indexWriteIdx = 0;
    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;
            GltfPrimAccessors acc;
            if (!gltf_extract_prim_accessors(prim, &acc)) continue;

            size_t primVertexOffset = vertWriteIdx;
            gltf_write_prim_vertices_accessor(&acc, outVerts, &vertWriteIdx);
            gltf_write_prim_indices_size(prim, primVertexOffset, acc.pos->count, outIndices, &indexWriteIdx);
        }
    }

    cgltf_free(data);
    Mesh* mesh = calloc(1, sizeof(Mesh));
    if (!mesh) { free(outVerts); free(outIndices); return NULL; }
    mesh->vertices = outVerts;
    mesh->vertexCount = vertWriteIdx;
    mesh->indices = outIndices;
    mesh->indexCount = indexWriteIdx;
    printf("[glTF] Cargado '%s': %zu verts, %zu indices (Indexed Rendering Activo)\n", filepath, vertWriteIdx, indexWriteIdx);
    return mesh;
}

int gltf_load_direct_vulkan(const char* filepath, struct VulkanEngine* eng) {
    if (!filepath || !eng) return 0;

    printf("[glTF Direct] Parseando '%s'...\n", filepath);
    cgltf_data* data = gltf_open_and_load(filepath, "glTF Direct");
    if (!data) return 0;

    size_t totalVertices = 0, totalIndices = 0;
    gltf_count_geometry(data, &totalVertices, &totalIndices);
    if (totalVertices == 0) {
        fprintf(stderr, "[glTF Direct] Sin geometría: %s\n", filepath);
        cgltf_free(data);
        return 0;
    }

    size_t bufferSize = totalVertices * sizeof(Vertex);
    size_t indexBufferSize = totalIndices * sizeof(uint32_t);
    printf("[glTF Direct] Geometria: %zu vertices (%zu MB), %zu indices (%zu MB)\n",
           totalVertices, bufferSize / (1024 * 1024), totalIndices, indexBufferSize / (1024 * 1024));

    VulkanSuballocation vertexSub = {0}, indexSub = {0};
    if (!gltf_create_direct_buffers(eng, bufferSize, indexBufferSize, totalIndices, &vertexSub, &indexSub)) {
        cgltf_free(data);
        return 0;
    }

    Vertex* outVerts = (Vertex*)vertexSub.mappedPtr;
    uint32_t* outIndices = (uint32_t*)indexSub.mappedPtr;
    size_t vertWriteIdx = 0, indexWriteIdx = 0;

    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;
            GltfPrimAccessors acc;
            if (!gltf_extract_prim_accessors(prim, &acc)) continue;

            size_t primVertexOffset = vertWriteIdx;
            gltf_write_prim_vertices_direct(&acc, outVerts, &vertWriteIdx);
            gltf_write_prim_indices_u32(prim, primVertexOffset, acc.pos->count, outIndices, &indexWriteIdx);
        }
    }

    cgltf_free(data);
    eng->vertexCount = vertWriteIdx;
    eng->baseVertexCount = vertWriteIdx;
    eng->indexCount = indexWriteIdx;
    eng->vertexData = NULL;
    eng->indexData = NULL;

    printf("[glTF Direct] 🚀 Cargado '%s': %zu verts, %zu indices mapeados DIRECTAMENTE a VRAM sin buffers intermedios (-5.3 GB RAM)\n",
           filepath, vertWriteIdx, indexWriteIdx);

    if (eng->trafficSystem.signalCount > 0) {
        traffic_system_init_gpu(&eng->trafficSystem, eng, outVerts, eng->vertexCount);
    }
    return 1;
}
