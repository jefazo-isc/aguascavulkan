/* chunk_system.h - Sistema de chunks para StreetVulkan
 *
 * Carga metadatos de chunks desde JSON generado por generate_sector.py.
 * Cada chunk tiene un rango de vértices [start, start+count) en el VBO y un AABB.
 */
#ifndef CHUNK_SYSTEM_H
#define CHUNK_SYSTEM_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "frustum_cull.h"

#define MAX_CHUNKS 16384

typedef struct {
    int cx, cz;              /* Coordenadas de chunk (grid index) */
    uint32_t start;          /* Primer vértice en el VBO */
    uint32_t count;          /* Número de vértices */
    AABB aabb;               /* Bounding box del chunk */
} Chunk;

typedef struct {
    Chunk chunks[MAX_CHUNKS];
    int chunkCount;
    float chunkSize;         /* Tamaño del chunk en metros */
    /* Stats del último frame */
    int visibleChunks;
    uint32_t visibleVerts;
    uint32_t totalVerts;
} ChunkSystem;

/* Parsear un JSON simple de chunks.
 * Formato esperado: {"chunk_size":128,"chunks":[{"cx":0,"cz":0,"start":0,"count":1234,
 *   "min_x":...,"min_y":...,"min_z":...,"max_x":...,"max_y":...,"max_z":...}, ...]}
 * Usamos un parser manual mínimo para evitar dependencias. */
static inline float chunk_parse_float_field(const char *obj, const char *obj_end, const char *name) {
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", name);
    const char *p = strstr(obj, pattern);
    if (!p || p >= obj_end) return 0.0f;
    p = strchr(p, ':');
    return p ? (float)atof(p + 1) : 0.0f;
}

static inline int chunk_parse_int_field(const char *obj, const char *obj_end, const char *name) {
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", name);
    const char *p = strstr(obj, pattern);
    if (!p || p >= obj_end) return 0;
    p = strchr(p, ':');
    return p ? atoi(p + 1) : 0;
}

static inline char *chunk_read_file_alloc(const char *filepath) {
    FILE *f = fopen(filepath, "r");
    if (!f) {
        fprintf(stderr, "[Chunks] No se pudo abrir: %s\n", filepath);
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (fsize <= 0) { fclose(f); return NULL; }
    char *json = (char*)malloc((size_t)fsize + 1);
    if (!json) { fclose(f); return NULL; }
    size_t nread = fread(json, 1, (size_t)fsize, f);
    (void)nread;
    json[fsize] = '\0';
    fclose(f);
    return json;
}

static inline void chunk_parse_entry(Chunk *c, const char *obj, const char *obj_end) {
    memset(c, 0, sizeof(Chunk));
    c->cx = chunk_parse_int_field(obj, obj_end, "cx");
    c->cz = chunk_parse_int_field(obj, obj_end, "cz");
    c->start = chunk_parse_int_field(obj, obj_end, "start");
    c->count = chunk_parse_int_field(obj, obj_end, "count");
    c->aabb.min_x = chunk_parse_float_field(obj, obj_end, "min_x");
    c->aabb.min_y = chunk_parse_float_field(obj, obj_end, "min_y");
    c->aabb.min_z = chunk_parse_float_field(obj, obj_end, "min_z");
    c->aabb.max_x = chunk_parse_float_field(obj, obj_end, "max_x");
    c->aabb.max_y = chunk_parse_float_field(obj, obj_end, "max_y");
    c->aabb.max_z = chunk_parse_float_field(obj, obj_end, "max_z");
}

static inline int chunk_system_load(ChunkSystem *cs, const char *filepath) {
    memset(cs, 0, sizeof(ChunkSystem));
    char *json = chunk_read_file_alloc(filepath);
    if (!json) return 0;

    char *p = strstr(json, "\"chunk_size\"");
    if (p) {
        p = strchr(p, ':');
        if (p) cs->chunkSize = (float)atof(p + 1);
    }
    if (cs->chunkSize < 1.0f) cs->chunkSize = 128.0f;

    p = strstr(json, "\"chunks\"");
    p = p ? strchr(p, '[') : NULL;
    if (!p) { free(json); return 0; }

    int count = 0;
    char *cursor = p + 1;
    while (count < MAX_CHUNKS) {
        char *obj = strchr(cursor, '{');
        char *obj_end = obj ? strchr(obj, '}') : NULL;
        if (!obj || !obj_end) break;

        Chunk *c = &cs->chunks[count];
        chunk_parse_entry(c, obj, obj_end);
        if (c->count > 0) {
            cs->totalVerts += c->count;
            count++;
        }
        cursor = obj_end + 1;
    }
    cs->chunkCount = count;
    free(json);
    printf("[Chunks] Cargados %d chunks (%.0fm) con %u vértices totales\n",
           cs->chunkCount, cs->chunkSize, cs->totalVerts);
    return 1;
}

#endif /* CHUNK_SYSTEM_H */
