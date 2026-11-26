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
    const char* slash1 = strchr(str, '/');
    if (!slash1) {
        ref.v = atoi(str);
        return ref;
    }
    ref.v = atoi(str);
    const char* slash2 = strchr(slash1 + 1, '/');
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

/* Construye la ruta del archivo .mtl relativa al directorio del .obj. */
static void build_mtl_path(const char* objFilename, const char* mtlFilename,
                           char* outPath, size_t outSize) {
    const char* lastSlash = strrchr(objFilename, '/');
    if (!lastSlash) {
        snprintf(outPath, outSize, "%s", mtlFilename);
        return;
    }
    size_t dirLen = (size_t)(lastSlash - objFilename + 1);
    if (dirLen > outSize - 1) dirLen = outSize - 1;
    strncpy(outPath, objFilename, dirLen);
    outPath[dirLen] = '\0';
    strncat(outPath, mtlFilename, outSize - dirLen - 1);
}

/* Procesa una directiva individual (newmtl, Kd, map_Kd, d) de un .mtl. */
static void parse_mtl_line(const char* p, ObjMaterial* materials, int* matCount, ObjMaterial** curMat) {
    if (strncmp(p, "newmtl ", 7) == 0) {
        if (*matCount < MAX_OBJ_MATERIALS) {
            ObjMaterial* mat = &materials[(*matCount)++];
            memset(mat, 0, sizeof(ObjMaterial));
            sscanf(p + 7, "%127s", mat->name);
            mat->r = 0.8f; mat->g = 0.8f; mat->b = 0.8f;
            mat->a = 1.0f;
            *curMat = mat;
        } else {
            *curMat = NULL;
        }
        return;
    }
    if (!*curMat) return;
    if (strncmp(p, "Kd ", 3) == 0) {
        sscanf(p + 3, "%f %f %f", &(*curMat)->r, &(*curMat)->g, &(*curMat)->b);
    } else if (strncmp(p, "map_Kd ", 7) == 0) {
        sscanf(p + 7, "%255s", (*curMat)->mapKd);
        if ((*curMat)->a <= 1.01f) {
            (*curMat)->a = 0.0f;
        }
    } else if (strncmp(p, "d ", 2) == 0) {
        float dVal = 1.0f;
        if (sscanf(p + 2, "%f", &dVal) == 1 && dVal > 1.01f) {
            (*curMat)->a = dVal;
        }
    }
}

static void load_mtl_file(const char* objFilename, const char* mtlFilename,
                          ObjMaterial* materials, int* matCount) {
    char mtlPath[512];
    build_mtl_path(objFilename, mtlFilename, mtlPath, sizeof(mtlPath));

    FILE* f = fopen(mtlPath, "r");
    if (!f) return;

    char line[1024];
    ObjMaterial* curMat = NULL;
    while (fgets(line, sizeof(line), f)) {
        char* p = line;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == '\n' || *p == '\r' || !*p) continue;
        parse_mtl_line(p, materials, matCount, &curMat);
    }
    fclose(f);
}

// ====================================
// Carga Principal
// ====================================

typedef struct {
    Vertex* vertices;
    size_t count;
    size_t capacity;
} ObjOutBuffer;

typedef struct {
    float r, g, b, a;
} ObjMaterialState;

static int obj_resolve_index(int rawIdx, size_t count) {
    return rawIdx > 0 ? (rawIdx - 1) : ((int)count + rawIdx);
}

static void obj_push_out_vertex(ObjOutBuffer* out, Vertex vert) {
    if (out->count >= out->capacity) {
        size_t newCap = out->capacity == 0 ? 4096 : out->capacity * 2;
        Vertex* newVerts = realloc(out->vertices, newCap * sizeof(Vertex));
        if (!newVerts) return;
        out->vertices = newVerts;
        out->capacity = newCap;
    }
    out->vertices[out->count++] = vert;
}

/* Calcula la normal geométrica de una cara triangular a partir de sus 3 vértices. */
static Vec3 obj_compute_face_normal(const ObjData* raw, const ObjVertexRef* faceRefs, const int triIndices[3]) {
    Vec3 autoNormal = {0.0f, 1.0f, 0.0f};
    int idx0 = obj_resolve_index(faceRefs[triIndices[0]].v, raw->positionCount);
    int idx1 = obj_resolve_index(faceRefs[triIndices[1]].v, raw->positionCount);
    int idx2 = obj_resolve_index(faceRefs[triIndices[2]].v, raw->positionCount);
    if (idx0 < 0 || idx1 < 0 || idx2 < 0 ||
        (size_t)idx0 >= raw->positionCount ||
        (size_t)idx1 >= raw->positionCount ||
        (size_t)idx2 >= raw->positionCount) {
        return autoNormal;
    }

    float ax = raw->positions[idx1].x - raw->positions[idx0].x;
    float ay = raw->positions[idx1].y - raw->positions[idx0].y;
    float az = raw->positions[idx1].z - raw->positions[idx0].z;
    float bx = raw->positions[idx2].x - raw->positions[idx0].x;
    float by = raw->positions[idx2].y - raw->positions[idx0].y;
    float bz = raw->positions[idx2].z - raw->positions[idx0].z;
    autoNormal.x = ay * bz - az * by;
    autoNormal.y = az * bx - ax * bz;
    autoNormal.z = ax * by - ay * bx;
    vec3_normalize(&autoNormal);
    return autoNormal;
}

/* Construye un Vertex completo combinando posición, UV, normal y material activo. */
static Vertex obj_build_face_vertex(const ObjData* raw, ObjVertexRef ref,
                                    const ObjMaterialState* mat, Vec3 autoNormal) {
    Vertex vert = {0};
    vert.r = mat->r;
    vert.g = mat->g;
    vert.b = mat->b;
    vert.a = mat->a;
    vert.nx = autoNormal.x;
    vert.ny = autoNormal.y;
    vert.nz = autoNormal.z;

    int posIdx = obj_resolve_index(ref.v, raw->positionCount);
    if (posIdx >= 0 && (size_t)posIdx < raw->positionCount) {
        vert.x = raw->positions[posIdx].x;
        vert.y = raw->positions[posIdx].y;
        vert.z = raw->positions[posIdx].z;
        vert.u = raw->positions[posIdx].u;
        vert.v = raw->positions[posIdx].v;
    }

    if (ref.vt != 0) {
        int tcIdx = obj_resolve_index(ref.vt, raw->texCoordCount);
        if (tcIdx >= 0 && (size_t)tcIdx < raw->texCoordCount) {
            vert.u = raw->texCoords[tcIdx].u;
            vert.v = raw->texCoords[tcIdx].v;
        }
    }

    if (ref.vn != 0) {
        int normIdx = obj_resolve_index(ref.vn, raw->normalCount);
        if (normIdx >= 0 && (size_t)normIdx < raw->normalCount) {
            vert.nx = raw->normals[normIdx].x;
            vert.ny = raw->normals[normIdx].y;
            vert.nz = raw->normals[normIdx].z;
        }
    }
    return vert;
}

/* Triangula una línea de cara ('f ...') en abanico y emite sus vértices. */
static void obj_process_face_line(const char* ptr, const ObjData* raw,
                                  const ObjMaterialState* mat, ObjOutBuffer* out) {
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
    if (refCount < 3) return;

    for (int i = 1; i < refCount - 1; i++) {
        int triIndices[3] = { 0, i, i + 1 };
        Vec3 autoNormal = obj_compute_face_normal(raw, faceRefs, triIndices);
        for (int t = 0; t < 3; t++) {
            Vertex vert = obj_build_face_vertex(raw, faceRefs[triIndices[t]], mat, autoNormal);
            obj_push_out_vertex(out, vert);
        }
    }
}

static void obj_select_material(const char* matName, const ObjMaterial* materials,
                                int materialCount, ObjMaterialState* mat) {
    for (int m = 0; m < materialCount; ++m) {
        if (strcmp(materials[m].name, matName) == 0) {
            mat->r = materials[m].r;
            mat->g = materials[m].g;
            mat->b = materials[m].b;
            mat->a = materials[m].a;
            return;
        }
    }
}

/* Despacha una línea ya recortada del archivo OBJ según su directiva. */
static void obj_process_line(const char* filename, const char* line, ObjData* raw,
                             ObjMaterial* materials, int* materialCount,
                             ObjMaterialState* mat, ObjOutBuffer* out) {
    if (strncmp(line, "mtllib ", 7) == 0) {
        char mtlName[256];
        if (sscanf(line + 7, "%255s", mtlName) == 1) {
            load_mtl_file(filename, mtlName, materials, materialCount);
        }
    } else if (strncmp(line, "usemtl ", 7) == 0) {
        char matName[128];
        if (sscanf(line + 7, "%127s", matName) == 1) {
            obj_select_material(matName, materials, *materialCount, mat);
        }
    } else if (strncmp(line, "v ", 2) == 0) {
        PositionUV pv = {0};
        if (sscanf(line + 2, "%f %f %f %f %f", &pv.x, &pv.y, &pv.z, &pv.u, &pv.v) >= 3) {
            obj_push_position(raw, pv);
        }
    } else if (strncmp(line, "vn ", 3) == 0) {
        Vec3 norm = {0};
        if (sscanf(line + 3, "%f %f %f", &norm.x, &norm.y, &norm.z) >= 3) {
            vec3_normalize(&norm);
            obj_push_normal(raw, norm);
        }
    } else if (strncmp(line, "vt ", 3) == 0) {
        Vec2 tc = {0};
        if (sscanf(line + 3, "%f %f", &tc.u, &tc.v) >= 2) {
            obj_push_texcoord(raw, tc);
        }
    } else if (strncmp(line, "f ", 2) == 0) {
        obj_process_face_line(line + 2, raw, mat, out);
    }
}

static void obj_trim_line_end(char* line) {
    size_t len = strlen(line);
    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r' ||
                       line[len - 1] == ' ' || line[len - 1] == '\t')) {
        line[--len] = '\0';
    }
}

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
    ObjMaterialState mat = { 0.85f, 0.82f, 0.78f, 1.0f };
    ObjOutBuffer out = { NULL, 0, 0 };

    char line[4096];
    while (fgets(line, sizeof(line), f)) {
        obj_trim_line_end(line);
        if (line[0] == '\0' || line[0] == '#') continue;
        obj_process_line(filename, line, &raw, materials, &materialCount, &mat, &out);
    }

    fclose(f);
    obj_data_free(&raw);

    if (out.count == 0) {
        fprintf(stderr, "No se pudieron generar vértices a partir del archivo OBJ\n");
        free(out.vertices);
        return NULL;
    }

    Mesh* mesh = calloc(1, sizeof(Mesh));
    if (!mesh) {
        free(out.vertices);
        return NULL;
    }

    mesh->vertices = out.vertices;
    mesh->vertexCount = out.count;
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
