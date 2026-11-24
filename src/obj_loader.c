#include "obj_loader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// ====================================
// Definiciones Locales para Parser
// ====================================

typedef struct {
    float x, y, z;
    float u, v;
} PositionUV;

typedef struct {
    float x, y, z;
} Vec3;

typedef struct {
    float u, v;
} Vec2;

typedef struct {
    PositionUV* positions;
    Vec2* texCoords;
    Vec3* normals;
    size_t positionCount;
    size_t texCoordCount;
    size_t normalCount;
    size_t positionsCapacity;
    size_t texCoordsCapacity;
    size_t normalsCapacity;
} ObjData;

// ====================================
// Funciones de Utilidad
// ====================================

static void vec3_normalize(Vec3* v) {
    float len = sqrtf(v->x * v->x + v->y * v->y + v->z * v->z);
    if (len > 0.0f) {
        v->x /= len;
        v->y /= len;
        v->z /= len;
    }
}

static void obj_data_init(ObjData* data) {
    data->positions = NULL;
    data->texCoords = NULL;
    data->normals = NULL;
    data->positionCount = 0;
    data->texCoordCount = 0;
    data->normalCount = 0;
    data->positionsCapacity = 0;
    data->texCoordsCapacity = 0;
    data->normalsCapacity = 0;
}

static void obj_data_free(ObjData* data) {
    free(data->positions);
    free(data->texCoords);
    free(data->normals);
    obj_data_init(data);
}

static void obj_push_position(ObjData* data, PositionUV pos) {
    if (data->positionCount >= data->positionsCapacity) {
        size_t newCap = data->positionsCapacity == 0 ? 1024 : data->positionsCapacity * 2;
        PositionUV* newPos = realloc(data->positions, newCap * sizeof(PositionUV));
        if (!newPos) return;
        data->positions = newPos;
        data->positionsCapacity = newCap;
    }
    data->positions[data->positionCount++] = pos;
}

static void obj_push_texcoord(ObjData* data, Vec2 tc) {
    if (data->texCoordCount >= data->texCoordsCapacity) {
        size_t newCap = data->texCoordsCapacity == 0 ? 1024 : data->texCoordsCapacity * 2;
        Vec2* newTC = realloc(data->texCoords, newCap * sizeof(Vec2));
        if (!newTC) return;
        data->texCoords = newTC;
        data->texCoordsCapacity = newCap;
    }
    data->texCoords[data->texCoordCount++] = tc;
}

static void obj_push_normal(ObjData* data, Vec3 norm) {
    if (data->normalCount >= data->normalsCapacity) {
        size_t newCap = data->normalsCapacity == 0 ? 1024 : data->normalsCapacity * 2;
        Vec3* newN = realloc(data->normals, newCap * sizeof(Vec3));
        if (!newN) return;
        data->normals = newN;
        data->normalsCapacity = newCap;
    }
    data->normals[data->normalCount++] = norm;
}

// ====================================
// Parseo de Referencias (v/vt/vn)
// ====================================

typedef struct {
    int v;
    int vt;
    int vn;
} ObjVertexRef;

static ObjVertexRef parse_vertex_ref(const char* str) {
    ObjVertexRef ref = {0, 0, 0};
    char* slash1 = strchr(str, '/');
    if (!slash1) {
        ref.v = atoi(str);
        return ref;
    }
    ref.v = atoi(str);
    char* slash2 = strchr(slash1 + 1, '/');
    if (!slash2) {
        ref.vt = atoi(slash1 + 1);
        return ref;
    }
    if (slash2 > slash1 + 1) {
        ref.vt = atoi(slash1 + 1);
    }
    ref.vn = atoi(slash2 + 1);
    return ref;
}

typedef struct {
    char name[128];
    float r, g, b, a;
    char mapKd[256];
} ObjMaterial;

#define MAX_OBJ_MATERIALS 128

static void load_mtl_file(const char* objFilename, const char* mtlFilename,
                          ObjMaterial* materials, int* matCount) {
    char mtlPath[512];
    const char* lastSlash = strrchr(objFilename, '/');
    if (lastSlash) {
        size_t dirLen = (size_t)(lastSlash - objFilename + 1);
        if (dirLen > sizeof(mtlPath) - 1) dirLen = sizeof(mtlPath) - 1;
        strncpy(mtlPath, objFilename, dirLen);
        mtlPath[dirLen] = '\0';
        strncat(mtlPath, mtlFilename, sizeof(mtlPath) - dirLen - 1);
    } else {
        snprintf(mtlPath, sizeof(mtlPath), "%s", mtlFilename);
    }

    FILE* f = fopen(mtlPath, "r");
    if (!f) return;

    char line[1024];
    ObjMaterial* curMat = NULL;

    while (fgets(line, sizeof(line), f)) {
        char* p = line;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == '\n' || *p == '\r' || !*p) continue;

        if (strncmp(p, "newmtl ", 7) == 0) {
            if (*matCount < MAX_OBJ_MATERIALS) {
                curMat = &materials[(*matCount)++];
                memset(curMat, 0, sizeof(ObjMaterial));
                sscanf(p + 7, "%127s", curMat->name);
                curMat->r = 0.8f; curMat->g = 0.8f; curMat->b = 0.8f;
                curMat->a = 1.0f; // 100% color de material por defecto
            } else {
                curMat = NULL; /* Prevenir sobreescritura fuera de límites */
            }
        } else if (curMat && strncmp(p, "Kd ", 3) == 0) {
            sscanf(p + 3, "%f %f %f", &curMat->r, &curMat->g, &curMat->b);
        } else if (curMat && strncmp(p, "map_Kd ", 7) == 0) {
            sscanf(p + 7, "%255s", curMat->mapKd);
            // Solo resetear alpha si no fue ya configurado como matID personalizado (d > 1.0)
            if (curMat->a <= 1.01f) {
                curMat->a = 0.0f; // Con mapa de textura estándar, mezclar con textura
            }
        } else if (curMat && strncmp(p, "d ", 2) == 0) {
            float dVal = 1.0f;
            if (sscanf(p + 2, "%f", &dVal) == 1) {
                // Extensión StreetVulkan: d > 1.0 se usa como matID directo (vertex alpha)
                // e.g. "d 1.3" en photo_mat → matID = 1.3 → photo plane en el shader
                if (dVal > 1.01f) {
                    curMat->a = dVal;
                }
                // d en rango normal 0..1 = opacidad estándar (reservado)
            }
        }
    }
    fclose(f);
}

// ====================================
// Carga Principal
// ====================================

Mesh* obj_load(const char* filename) {
    if (!filename) {
        fprintf(stderr, "No se pudo abrir el archivo OBJ: ruta NULL\n");
        return NULL;
    }
    FILE* f = fopen(filename, "r");
    if (!f) {
        fprintf(stderr, "No se pudo abrir el archivo OBJ: %s\n", filename);
        return NULL;
    }

    ObjData raw;
    obj_data_init(&raw);

    ObjMaterial materials[MAX_OBJ_MATERIALS];
    int materialCount = 0;
    float curR = 0.85f, curG = 0.82f, curB = 0.78f, curA = 1.0f;

    Vertex* outVertices = NULL;
    size_t outVertexCount = 0;
    size_t outVertexCapacity = 0;

    char line[4096];
    while (fgets(line, sizeof(line), f)) {
        size_t len = strlen(line);
        while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r' || line[len-1] == ' ' || line[len-1] == '\t')) {
            line[--len] = '\0';
        }
        if (len == 0 || line[0] == '#') continue;

        // Directiva mtllib: cargar librería de materiales
        if (strncmp(line, "mtllib ", 7) == 0) {
            char mtlName[256];
            if (sscanf(line + 7, "%255s", mtlName) == 1) {
                load_mtl_file(filename, mtlName, materials, &materialCount);
            }
        }
        // Directiva usemtl: activar material actual
        else if (strncmp(line, "usemtl ", 7) == 0) {
            char matName[128];
            if (sscanf(line + 7, "%127s", matName) == 1) {
                for (int m = 0; m < materialCount; ++m) {
                    if (strcmp(materials[m].name, matName) == 0) {
                        curR = materials[m].r;
                        curG = materials[m].g;
                        curB = materials[m].b;
                        curA = materials[m].a;
                        break;
                    }
                }
            }
        }
        // Línea v: Posición + UV (x y z u v)
        else if (strncmp(line, "v ", 2) == 0) {
            PositionUV pv = {0};
            int matched = sscanf(line + 2, "%f %f %f %f %f", &pv.x, &pv.y, &pv.z, &pv.u, &pv.v);
            
            if (matched >= 3) {
                if (matched < 5) {
                    pv.u = 0.0f; 
                    pv.v = 0.0f;
                }
                obj_push_position(&raw, pv);
            }
        }
        // Línea vn: Normal
        else if (strncmp(line, "vn ", 3) == 0) {
            Vec3 norm = {0};
            if (sscanf(line + 3, "%f %f %f", &norm.x, &norm.y, &norm.z) >= 3) {
                vec3_normalize(&norm);
                obj_push_normal(&raw, norm);
            }
        }
        // Línea vt: Coordenadas de textura UV
        else if (strncmp(line, "vt ", 3) == 0) {
            Vec2 tc = {0};
            if (sscanf(line + 3, "%f %f", &tc.u, &tc.v) >= 2) {
                obj_push_texcoord(&raw, tc);
            }
        }
        // Línea f: Caras
        else if (strncmp(line, "f ", 2) == 0) {
            char* ptr = line + 2;
            ObjVertexRef faceRefs[64];
            int refCount = 0;

            while (*ptr && refCount < 64) {
                while (*ptr == ' ' || *ptr == '\t') ptr++;
                if (!*ptr) break;

                char token[128];
                int tokenLen = 0;
                while (*ptr && *ptr != ' ' && *ptr != '\t' && tokenLen < 127) {
                    token[tokenLen++] = *ptr++;
                }
                token[tokenLen] = '\0';

                faceRefs[refCount++] = parse_vertex_ref(token);
            }

            if (refCount < 3) continue;

            // Triangular caras con abanico: (0, i, i+1)
            for (int i = 1; i < refCount - 1; i++) {
                int triIndices[3] = { 0, i, i + 1 };

                // Calcular normal geométrica de la cara si el modelo no trae vn
                Vec3 autoNormal = {0.0f, 1.0f, 0.0f};
                int idx0 = faceRefs[triIndices[0]].v > 0 ? (faceRefs[triIndices[0]].v - 1) : ((int)raw.positionCount + faceRefs[triIndices[0]].v);
                int idx1 = faceRefs[triIndices[1]].v > 0 ? (faceRefs[triIndices[1]].v - 1) : ((int)raw.positionCount + faceRefs[triIndices[1]].v);
                int idx2 = faceRefs[triIndices[2]].v > 0 ? (faceRefs[triIndices[2]].v - 1) : ((int)raw.positionCount + faceRefs[triIndices[2]].v);
                if (idx0 >= 0 && idx1 >= 0 && idx2 >= 0 &&
                    (size_t)idx0 < raw.positionCount && (size_t)idx1 < raw.positionCount && (size_t)idx2 < raw.positionCount) {
                    float ax = raw.positions[idx1].x - raw.positions[idx0].x;
                    float ay = raw.positions[idx1].y - raw.positions[idx0].y;
                    float az = raw.positions[idx1].z - raw.positions[idx0].z;
                    float bx = raw.positions[idx2].x - raw.positions[idx0].x;
                    float by = raw.positions[idx2].y - raw.positions[idx0].y;
                    float bz = raw.positions[idx2].z - raw.positions[idx0].z;
                    autoNormal.x = ay * bz - az * by;
                    autoNormal.y = az * bx - ax * bz;
                    autoNormal.z = ax * by - ay * bx;
                    vec3_normalize(&autoNormal);
                }

                for (int t = 0; t < 3; t++) {
                    ObjVertexRef ref = faceRefs[triIndices[t]];
                    Vertex vert = {0};
                    vert.r = curR;
                    vert.g = curG;
                    vert.b = curB;
                    vert.a = curA;
                    vert.emission = 0.0f;

                    // Posición
                    int posIdx = ref.v > 0 ? (ref.v - 1) : ((int)raw.positionCount + ref.v);
                    if (posIdx >= 0 && (size_t)posIdx < raw.positionCount) {
                        vert.x = raw.positions[posIdx].x;
                        vert.y = raw.positions[posIdx].y;
                        vert.z = raw.positions[posIdx].z;
                        vert.u = raw.positions[posIdx].u;
                        vert.v = raw.positions[posIdx].v;
                    }

                    // Coordenadas UV desde vt (si se especificaron en f v/vt/vn)
                    if (ref.vt != 0) {
                        int tcIdx = ref.vt > 0 ? (ref.vt - 1) : ((int)raw.texCoordCount + ref.vt);
                        if (tcIdx >= 0 && (size_t)tcIdx < raw.texCoordCount) {
                            vert.u = raw.texCoords[tcIdx].u;
                            vert.v = raw.texCoords[tcIdx].v;
                        }
                    }

                    // Normal (usar vn si existe, o autoNormal calculado)
                    if (ref.vn != 0) {
                        int normIdx = ref.vn > 0 ? (ref.vn - 1) : ((int)raw.normalCount + ref.vn);
                        if (normIdx >= 0 && (size_t)normIdx < raw.normalCount) {
                            vert.nx = raw.normals[normIdx].x;
                            vert.ny = raw.normals[normIdx].y;
                            vert.nz = raw.normals[normIdx].z;
                        } else {
                            vert.nx = autoNormal.x;
                            vert.ny = autoNormal.y;
                            vert.nz = autoNormal.z;
                        }
                    } else {
                        vert.nx = autoNormal.x;
                        vert.ny = autoNormal.y;
                        vert.nz = autoNormal.z;
                    }

                    // Expansión de buffer
                    if (outVertexCount >= outVertexCapacity) {
                        size_t newCap = outVertexCapacity == 0 ? 4096 : outVertexCapacity * 2;
                        Vertex* newVerts = realloc(outVertices, newCap * sizeof(Vertex));
                        if (!newVerts) {
                            break;
                        }
                        outVertices = newVerts;
                        outVertexCapacity = newCap;
                    }

                    outVertices[outVertexCount++] = vert;
                }
            }
        }
    }

    fclose(f);
    obj_data_free(&raw);

    if (outVertexCount == 0) {
        fprintf(stderr, "No se pudieron generar vértices a partir del archivo OBJ\n");
        free(outVertices);
        return NULL;
    }

    Mesh* mesh = calloc(1, sizeof(Mesh));
    if (!mesh) {
        free(outVertices);
        return NULL;
    }

    mesh->vertices = outVertices;
    mesh->vertexCount = outVertexCount;
    mesh->indices = NULL;
    mesh->indexCount = 0;

    fprintf(stderr, "Modelo cargado exitosamente: %zu vértices\n", mesh->vertexCount);
    return mesh;
}

void obj_free(Mesh* mesh) {
    if (!mesh) return;
    free(mesh->vertices);
    free(mesh->indices);
    free(mesh);
}
