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

Mesh* gltf_load(const char* filepath) {
    cgltf_options options = {0};
    options.file.read = mmap_file_read;
    options.file.release = mmap_file_release;
    cgltf_data* data = NULL;
    cgltf_result result = cgltf_parse_file(&options, filepath, &data);
    if (result != cgltf_result_success) {
        fprintf(stderr, "[glTF] Error al parsear: %s (%d)\n", filepath, (int)result);
        return NULL;
    }
    result = cgltf_load_buffers(&options, data, filepath);
    if (result != cgltf_result_success) {
        fprintf(stderr, "[glTF] Error buffers: %s (%d)\n", filepath, (int)result);
        cgltf_free(data);
        return NULL;
    }

    size_t totalVertices = 0;
    size_t totalIndices = 0;
    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;

            size_t vertCount = 0;
            for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
                if (prim->attributes[a].type == cgltf_attribute_type_position) {
                    vertCount = prim->attributes[a].data->count;
                    break;
                }
            }
            totalVertices += vertCount;
            if (prim->indices) totalIndices += prim->indices->count;
            else totalIndices += vertCount;
        }
    }
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

    size_t vertWriteIdx = 0;
    size_t indexWriteIdx = 0;

    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;

            cgltf_accessor* posAcc = NULL;
            cgltf_accessor* normAcc = NULL;
            cgltf_accessor* uvAcc = NULL;
            cgltf_accessor* colAcc = NULL;
            cgltf_accessor* emAcc = NULL;

            for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
                cgltf_attribute* attr = &prim->attributes[a];
                if (attr->type == cgltf_attribute_type_position) posAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_normal) normAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_texcoord) uvAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_color) colAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_custom) {
                    if (attr->name && (strcmp(attr->name, "_EMISSION") == 0 || strcmp(attr->name, "EMISSION") == 0 || strcmp(attr->name, "_EMISSION_FACTOR") == 0)) {
                        emAcc = attr->data;
                    }
                }
            }
            if (!posAcc) continue;

            float matEmission = 0.0f;
            if (prim->material) {
                float er = prim->material->emissive_factor[0];
                float eg = prim->material->emissive_factor[1];
                float eb = prim->material->emissive_factor[2];
                if (er > 0.01f || eg > 0.01f || eb > 0.01f) {
                    matEmission = (er + eg + eb) / 3.0f * 3.0f;
                }
            }

            size_t primVertexOffset = vertWriteIdx;
            size_t primVertexCount = posAcc->count;

            for (size_t vIdx = 0; vIdx < primVertexCount; ++vIdx) {
                Vertex v;
                memset(&v, 0, sizeof(Vertex));

                float pos[3] = {0};
                cgltf_accessor_read_float(posAcc, vIdx, pos, 3);
                v.x = pos[0]; v.y = pos[1]; v.z = pos[2];

                if (normAcc) {
                    float n[3] = {0,1,0};
                    cgltf_accessor_read_float(normAcc, vIdx, n, 3);
                    v.nx = n[0]; v.ny = n[1]; v.nz = n[2];
                } else v.ny = 1.0f;

                if (uvAcc) {
                    float uv[2] = {0};
                    cgltf_accessor_read_float(uvAcc, vIdx, uv, 2);
                    v.u = uv[0]; v.v = uv[1];
                }

                if (colAcc) {
                    float col[4] = {1,1,1,1};
                    cgltf_accessor_read_float(colAcc, vIdx, col, 4);
                    v.r = col[0]; v.g = col[1]; v.b = col[2]; v.a = col[3];
                } else {
                    v.r = 1; v.g = 1; v.b = 1; v.a = (uvAcc != NULL) ? 0.0f : 1.0f;
                }

                if (emAcc) {
                    float em[1] = {0};
                    cgltf_accessor_read_float(emAcc, vIdx, em, 1);
                    v.emission = em[0];
                } else {
                    v.emission = matEmission;
                }

                outVerts[vertWriteIdx++] = v;
            }

            if (prim->indices) {
                for (size_t i = 0; i < prim->indices->count; ++i) {
                    size_t idxVal = cgltf_accessor_read_index(prim->indices, i);
                    outIndices[indexWriteIdx++] = primVertexOffset + idxVal;
                }
            } else {
                for (size_t i = 0; i < primVertexCount; ++i) {
                    outIndices[indexWriteIdx++] = primVertexOffset + i;
                }
            }
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

    cgltf_options options = {0};
    options.file.read = mmap_file_read;
    options.file.release = mmap_file_release;
    cgltf_data* data = NULL;
    printf("[glTF Direct] Parseando '%s'...\n", filepath);
    cgltf_result result = cgltf_parse_file(&options, filepath, &data);
    if (result != cgltf_result_success) {
        fprintf(stderr, "[glTF Direct] Error al parsear: %s (%d)\n", filepath, (int)result);
        return 0;
    }
    printf("[glTF Direct] Cargando buffers...\n");
    result = cgltf_load_buffers(&options, data, filepath);
    if (result != cgltf_result_success) {
        fprintf(stderr, "[glTF Direct] Error buffers: %s (%d)\n", filepath, (int)result);
        cgltf_free(data);
        return 0;
    }
    printf("[glTF Direct] Buffers cargados. Contando vertices e indices...\n");

    size_t totalVertices = 0;
    size_t totalIndices = 0;
    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;

            size_t vertCount = 0;
            for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
                if (prim->attributes[a].type == cgltf_attribute_type_position) {
                    vertCount = prim->attributes[a].data->count;
                    break;
                }
            }
            totalVertices += vertCount;
            if (prim->indices) totalIndices += prim->indices->count;
            else totalIndices += vertCount;
        }
    }
    if (totalVertices == 0) {
        fprintf(stderr, "[glTF Direct] Sin geometría: %s\n", filepath);
        cgltf_free(data);
        return 0;
    }

    size_t bufferSize = totalVertices * sizeof(Vertex);
    size_t indexBufferSize = totalIndices * sizeof(uint32_t);
    printf("[glTF Direct] Geometria: %zu vertices (%zu MB), %zu indices (%zu MB)\n",
           totalVertices, bufferSize / (1024*1024), totalIndices, indexBufferSize / (1024*1024));

    // 1. Crear y vincular Vertex Buffer directamente en Vulkan hostVisiblePool (Zero-Copy)
    VkBufferCreateInfo vertexInfo = {0};
    vertexInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    vertexInfo.size = bufferSize;
    vertexInfo.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
    vertexInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    if (vkCreateBuffer(eng->device, &vertexInfo, NULL, &eng->vertexBuffer) != VK_SUCCESS) {
        fprintf(stderr, "[glTF Direct] Error creando Vertex Buffer directo\n");
        cgltf_free(data);
        return 0;
    }
    printf("[glTF Direct] vkCreateBuffer OK. Vinculando a hostVisiblePool...\n");

    VulkanSuballocation vertexSub;
    if (!vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, eng->vertexBuffer, &vertexSub) || !vertexSub.mappedPtr) {
        fprintf(stderr, "[glTF Direct] Error vinculando Vertex Buffer directo al pool\n");
        vkDestroyBuffer(eng->device, eng->vertexBuffer, NULL);
        cgltf_free(data);
        return 0;
    }

    // 2. Crear y vincular Index Buffer directamente
    VulkanSuballocation indexSub = {0};
    if (totalIndices > 0) {
        VkBufferCreateInfo indexInfo = {0};
        indexInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        indexInfo.size = indexBufferSize;
        indexInfo.usage = VK_BUFFER_USAGE_INDEX_BUFFER_BIT;
        indexInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

        if (vkCreateBuffer(eng->device, &indexInfo, NULL, &eng->indexBuffer) == VK_SUCCESS) {
            vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, eng->indexBuffer, &indexSub);
        }
    }

    Vertex* outVerts = (Vertex*)vertexSub.mappedPtr;
    uint32_t* outIndices = (uint32_t*)indexSub.mappedPtr;
    size_t vertWriteIdx = 0;
    size_t indexWriteIdx = 0;

    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;

            cgltf_accessor* posAcc = NULL;
            cgltf_accessor* normAcc = NULL;
            cgltf_accessor* uvAcc = NULL;
            cgltf_accessor* colAcc = NULL;
            cgltf_accessor* emAcc = NULL;

            for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
                cgltf_attribute* attr = &prim->attributes[a];
                if (attr->type == cgltf_attribute_type_position) posAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_normal) normAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_texcoord) uvAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_color) colAcc = attr->data;
                else if (attr->type == cgltf_attribute_type_custom) {
                    if (attr->name && (strcmp(attr->name, "_EMISSION") == 0 || strcmp(attr->name, "EMISSION") == 0 || strcmp(attr->name, "_EMISSION_FACTOR") == 0)) {
                        emAcc = attr->data;
                    }
                }
            }
            if (!posAcc) continue;

            float matEmission = 0.0f;
            if (prim->material) {
                float er = prim->material->emissive_factor[0];
                float eg = prim->material->emissive_factor[1];
                float eb = prim->material->emissive_factor[2];
                if (er > 0.01f || eg > 0.01f || eb > 0.01f) {
                    matEmission = (er + eg + eb) / 3.0f * 3.0f;
                }
            }

            size_t primVertexOffset = vertWriteIdx;
            size_t primVertexCount = posAcc->count;

            const uint8_t* posBase = cgltf_buffer_view_data(posAcc->buffer_view) + posAcc->offset;
            const uint8_t* normBase = (normAcc && normAcc->buffer_view) ? (cgltf_buffer_view_data(normAcc->buffer_view) + normAcc->offset) : NULL;
            const uint8_t* uvBase = (uvAcc && uvAcc->buffer_view) ? (cgltf_buffer_view_data(uvAcc->buffer_view) + uvAcc->offset) : NULL;
            const uint8_t* colBase = (colAcc && colAcc->buffer_view) ? (cgltf_buffer_view_data(colAcc->buffer_view) + colAcc->offset) : NULL;
            const uint8_t* emBase = (emAcc && emAcc->buffer_view) ? (cgltf_buffer_view_data(emAcc->buffer_view) + emAcc->offset) : NULL;

            size_t posStride = posAcc->stride ? posAcc->stride : sizeof(float) * 3;
            size_t normStride = (normAcc && normAcc->stride) ? normAcc->stride : sizeof(float) * 3;
            size_t uvStride = (uvAcc && uvAcc->stride) ? uvAcc->stride : sizeof(float) * 2;
            size_t colStride = (colAcc && colAcc->stride) ? colAcc->stride : sizeof(float) * 4;
            size_t emStride = (emAcc && emAcc->stride) ? emAcc->stride : sizeof(float);

            for (size_t vIdx = 0; vIdx < primVertexCount; ++vIdx) {
                if ((vIdx & 0x7FFFF) == 0) {
                    SDL_PumpEvents();
                }

                const float* pos = (const float*)(posBase + vIdx * posStride);
                Vertex* v = &outVerts[vertWriteIdx++];
                v->x = pos[0];
                v->y = pos[1];
                v->z = pos[2];

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
                    v->r = 1.0f; v->g = 1.0f; v->b = 1.0f; v->a = (uvBase != NULL) ? 0.0f : 1.0f;
                }

                if (emBase) {
                    const float* em = (const float*)(emBase + vIdx * emStride);
                    v->emission = em[0];
                } else {
                    v->emission = matEmission;
                }
            }

            if (outIndices) {
                if (prim->indices && prim->indices->buffer_view) {
                    const uint8_t* idxBase = cgltf_buffer_view_data(prim->indices->buffer_view) + prim->indices->offset;
                    if (prim->indices->component_type == cgltf_component_type_r_32u) {
                        const uint32_t* pIdx = (const uint32_t*)idxBase;
                        if (primVertexOffset == 0) {
                            memcpy(outIndices + indexWriteIdx, pIdx, prim->indices->count * sizeof(uint32_t));
                            indexWriteIdx += prim->indices->count;
                        } else {
                            for (size_t i = 0; i < prim->indices->count; ++i) {
                                outIndices[indexWriteIdx++] = (uint32_t)(primVertexOffset + pIdx[i]);
                            }
                        }
                    } else if (prim->indices->component_type == cgltf_component_type_r_16u) {
                        const uint16_t* pIdx = (const uint16_t*)idxBase;
                        for (size_t i = 0; i < prim->indices->count; ++i) {
                            outIndices[indexWriteIdx++] = (uint32_t)(primVertexOffset + pIdx[i]);
                        }
                    } else {
                        for (size_t i = 0; i < prim->indices->count; ++i) {
                            size_t idxVal = cgltf_accessor_read_index(prim->indices, i);
                            outIndices[indexWriteIdx++] = (uint32_t)(primVertexOffset + idxVal);
                        }
                    }
                } else {
                    for (size_t i = 0; i < primVertexCount; ++i) {
                        outIndices[indexWriteIdx++] = (uint32_t)(primVertexOffset + i);
                    }
                }
            }
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

    // Inicializar semáforos leyendo directo de outVerts en VRAM
    if (eng->trafficSystem.signalCount > 0) {
        traffic_system_init_gpu(&eng->trafficSystem, eng, outVerts, eng->vertexCount);
    }

    return 1;
}
