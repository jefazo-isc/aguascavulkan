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

#define MAX_CHUNKS 4096

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
static inline int chunk_system_load(ChunkSystem *cs, const char *filepath) {
    memset(cs, 0, sizeof(ChunkSystem));
    FILE *f = fopen(filepath, "r");
    if (!f) {
        fprintf(stderr, "[Chunks] No se pudo abrir: %s\n", filepath);
        return 0;
    }

    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *json = (char*)malloc(fsize + 1);
    if (!json) { fclose(f); return 0; }
    fread(json, 1, fsize, f);
    json[fsize] = '\0';
    fclose(f);

    /* Parse chunk_size */
    char *p = strstr(json, "\"chunk_size\"");
    if (p) {
        p = strchr(p, ':');
        if (p) cs->chunkSize = (float)atof(p + 1);
    }
    if (cs->chunkSize < 1.0f) cs->chunkSize = 128.0f;

    /* Parse chunks array */
    p = strstr(json, "\"chunks\"");
    if (!p) { free(json); return 0; }
    p = strchr(p, '[');
    if (!p) { free(json); return 0; }

    int count = 0;
    char *cursor = p + 1;
    while (count < MAX_CHUNKS) {
        char *obj = strchr(cursor, '{');
        if (!obj) break;
        char *obj_end = strchr(obj, '}');
        if (!obj_end) break;

        Chunk *c = &cs->chunks[count];
        memset(c, 0, sizeof(Chunk));

        /* Helper macro to parse a field */
        #define PARSE_INT(field, name) do { \
            char *_p = strstr(obj, "\"" name "\""); \
            if (_p && _p < obj_end) { _p = strchr(_p, ':'); if (_p) c->field = atoi(_p + 1); } \
        } while(0)
        #define PARSE_FLOAT(field, name) do { \
            char *_p = strstr(obj, "\"" name "\""); \
            if (_p && _p < obj_end) { _p = strchr(_p, ':'); if (_p) c->field = (float)atof(_p + 1); } \
        } while(0)

        PARSE_INT(cx, "cx");
        PARSE_INT(cz, "cz");
        PARSE_INT(start, "start");
        PARSE_INT(count, "count");
        PARSE_FLOAT(aabb.min_x, "min_x");
        PARSE_FLOAT(aabb.min_y, "min_y");
        PARSE_FLOAT(aabb.min_z, "min_z");
        PARSE_FLOAT(aabb.max_x, "max_x");
        PARSE_FLOAT(aabb.max_y, "max_y");
        PARSE_FLOAT(aabb.max_z, "max_z");

        #undef PARSE_INT
        #undef PARSE_FLOAT

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
