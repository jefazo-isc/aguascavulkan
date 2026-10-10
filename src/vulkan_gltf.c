#include "vulkan_gltf.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CGLTF_IMPLEMENTATION
#include "cgltf.h"

Mesh* gltf_load(const char* filepath) {
    cgltf_options options = {0};
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
    for (cgltf_size m = 0; m < data->meshes_count; ++m) {
        cgltf_mesh* mesh = &data->meshes[m];
        for (cgltf_size p = 0; p < mesh->primitives_count; ++p) {
            cgltf_primitive* prim = &mesh->primitives[p];
            if (prim->type != cgltf_primitive_type_triangles) continue;
            if (prim->indices) totalVertices += prim->indices->count;
            else {
                for (cgltf_size a = 0; a < prim->attributes_count; ++a) {
                    if (prim->attributes[a].type == cgltf_attribute_type_position) {
                        totalVertices += prim->attributes[a].data->count;
                        break;
                    }
                }
            }
        }
    }
    if (totalVertices == 0) {
        fprintf(stderr, "[glTF] Sin geometría: %s\n", filepath);
        cgltf_free(data);
        return NULL;
    }

    Vertex* outVerts = malloc(totalVertices * sizeof(Vertex));
    if (!outVerts) {
        cgltf_free(data);
        return NULL;
    }

    size_t vertWriteIdx = 0;
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

            size_t primIndexCount = prim->indices ? prim->indices->count : posAcc->count;
            for (size_t i = 0; i < primIndexCount; ++i) {
                size_t srcIndex = prim->indices ? cgltf_accessor_read_index(prim->indices, i) : i;
                Vertex v;
                memset(&v, 0, sizeof(Vertex));

                float pos[3] = {0};
                cgltf_accessor_read_float(posAcc, srcIndex, pos, 3);
                v.x = pos[0]; v.y = pos[1]; v.z = pos[2];

                if (normAcc) {
                    float n[3] = {0,1,0};
                    cgltf_accessor_read_float(normAcc, srcIndex, n, 3);
                    v.nx = n[0]; v.ny = n[1]; v.nz = n[2];
                } else v.ny = 1.0f;

                if (uvAcc) {
                    float uv[2] = {0};
                    cgltf_accessor_read_float(uvAcc, srcIndex, uv, 2);
                    v.u = uv[0]; v.v = uv[1];
                }

                if (colAcc) {
                    float col[4] = {1,1,1,1};
                    cgltf_accessor_read_float(colAcc, srcIndex, col, 4);
                    v.r = col[0]; v.g = col[1]; v.b = col[2]; v.a = col[3];
                } else {
                    v.r = 1; v.g = 1; v.b = 1; v.a = (uvAcc != NULL) ? 0.0f : 1.0f;
                }

                if (emAcc) {
                    float em[1] = {0};
                    cgltf_accessor_read_float(emAcc, srcIndex, em, 1);
                    v.emission = em[0];
                } else {
                    v.emission = matEmission;
                }

                outVerts[vertWriteIdx++] = v;
            }
        }
    }

    cgltf_free(data);
    Mesh* mesh = calloc(1, sizeof(Mesh));
    if (!mesh) { free(outVerts); return NULL; }
    mesh->vertices = outVerts;
    mesh->vertexCount = vertWriteIdx;
    mesh->indices = NULL;
    mesh->indexCount = 0;
    printf("[glTF] Cargado '%s': %zu verts (emission per-vertex %s)\n", filepath, vertWriteIdx, "soportado");
    return mesh;
}
