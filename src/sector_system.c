/* sector_system.c - Implementación del Gestor de Macro-Sectores Modulares (<99MB)
 * StreetVulkan Engine
 */
#include "sector_system.h"
#include "vulkan_types.h"
#include "vulkan_swapchain.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Helper para parsing JSON mínimo y robusto sin dependencias */
static char* read_entire_file(const char *path, long *outSize) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    long fsize = ftell(f);
    if (fsize < 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    char *buf = (char*)malloc((size_t)fsize + 1);
    if (!buf) { fclose(f); return NULL; }
    size_t nread = fread(buf, 1, (size_t)fsize, f);
    fclose(f);
    if (nread != (size_t)fsize) {
        free(buf);
        return NULL;
    }
    buf[fsize] = '\0';
    if (outSize) *outSize = fsize;
    return buf;
}

static void parse_sector_chunks(MacroSector *sec, char *secObj, char *secEnd) {
    char *chArray = strstr(secObj, "\"chunks\"");
    if (!chArray || chArray >= secEnd) return;

    char *cCur = strchr(chArray, '[');
    int cCount = 0;
    while (cCur && cCur < secEnd && cCount < MAX_CHUNKS_PER_SECTOR) {
        char *cxPtr = strstr(cCur, "\"cx\"");
        if (!cxPtr || cxPtr >= secEnd) break;
        char *cObjEnd = strchr(cxPtr, '}');
        if (!cObjEnd || cObjEnd >= secEnd) break;

        char savedChunk = *cObjEnd;
        *cObjEnd = '\0';

        Chunk *chk = &sec->chunks[cCount];
        memset(chk, 0, sizeof(Chunk));

        #define P_CHK_I(f, n) do { char *_x = strstr(cxPtr, "\"" n "\""); if (_x) { _x = strchr(_x, ':'); if (_x) chk->f = atoi(_x+1); } } while(0)
        #define P_CHK_F(f, n) do { char *_x = strstr(cxPtr, "\"" n "\""); if (_x) { _x = strchr(_x, ':'); if (_x) chk->f = (float)atof(_x+1); } } while(0)

        P_CHK_I(cx, "cx");
        P_CHK_I(cz, "cz");
        P_CHK_I(start, "start");
        P_CHK_I(count, "count");
        P_CHK_F(aabb.min_x, "min_x");
        P_CHK_F(aabb.min_y, "min_y");
        P_CHK_F(aabb.min_z, "min_z");
        P_CHK_F(aabb.max_x, "max_x");
        P_CHK_F(aabb.max_y, "max_y");
        P_CHK_F(aabb.max_z, "max_z");

        #undef P_CHK_I
        #undef P_CHK_F

        *cObjEnd = savedChunk;
        if (chk->count > 0) cCount++;
        cCur = cObjEnd + 1;
    }
    sec->chunkCount = cCount;
}

static void parse_sector_filepath(MacroSector *sec, char *secObj, char *secEnd) {
    char *fPtr = strstr(secObj, "\"file\"");
    if (!fPtr || fPtr >= secEnd) return;
    fPtr = strchr(fPtr, ':');
    if (!fPtr) return;
    char *startQ = strchr(fPtr, '\"');
    if (!startQ) return;
    char *endQ = strchr(startQ + 1, '\"');
    if (!endQ) return;

    size_t flen = (size_t)(endQ - (startQ + 1));
    if (flen < sizeof(sec->filepath) - 1) {
        strncpy(sec->filepath, startQ + 1, flen);
        sec->filepath[flen] = '\0';
    }
}

static void parse_sector_entry(MacroSector *sec, char *secObj, char *secEnd) {
    char saved = *secEnd;
    *secEnd = '\0';

    memset(sec, 0, sizeof(MacroSector));

    #define PARSE_INT(src, field, name) do { \
        char *_p = strstr(src, "\"" name "\""); \
        if (_p && _p < secEnd) { _p = strchr(_p, ':'); if (_p) sec->field = atoi(_p + 1); } \
    } while(0)
    #define PARSE_FLOAT(src, field, name) do { \
        char *_p = strstr(src, "\"" name "\""); \
        if (_p && _p < secEnd) { _p = strchr(_p, ':'); if (_p) sec->field = (float)atof(_p + 1); } \
    } while(0)

    PARSE_INT(secObj, mx, "mx");
    PARSE_INT(secObj, mz, "mz");
    PARSE_INT(secObj, vertexCount, "vert_count");
    PARSE_FLOAT(secObj, sizeMb, "size_mb");

    parse_sector_filepath(sec, secObj, secEnd);

    /* Sector AABB */
    char *aabbPtr = strstr(secObj, "\"aabb\"");
    if (aabbPtr && aabbPtr < secEnd) {
        char *pAABB;
        #define P_AABB(f, name) do { \
            pAABB = strstr(aabbPtr, "\"" name "\""); \
            if (pAABB && pAABB < secEnd) { pAABB = strchr(pAABB, ':'); if (pAABB) sec->aabb.f = (float)atof(pAABB + 1); } \
        } while(0)
        P_AABB(min_x, "min_x");
        P_AABB(min_y, "min_y");
        P_AABB(min_z, "min_z");
        P_AABB(max_x, "max_x");
        P_AABB(max_y, "max_y");
        P_AABB(max_z, "max_z");
        #undef P_AABB
    }

    /* Chunks dentro de este macro-sector */
    parse_sector_chunks(sec, secObj, secEnd);

    #undef PARSE_INT
    #undef PARSE_FLOAT

    *secEnd = saved;
}

static int ensure_sync_init(SectorSystem *ss) {
    if (!ss) return 0;
    if (ss->syncInitialized) return 1;
    if (pthread_mutex_init(&ss->mutex, NULL) != 0) return 0;
    if (pthread_cond_init(&ss->cond, NULL) != 0) {
        pthread_mutex_destroy(&ss->mutex);
        return 0;
    }
    ss->syncInitialized = 1;
    return 1;
}

int sector_system_init(SectorSystem *ss, const char *manifestPath) {
    if (!ss || !manifestPath) return 0;
    memset(ss, 0, sizeof(SectorSystem));

    long jsonLen = 0;
    char *json = read_entire_file(manifestPath, &jsonLen);
    if (!json) {
        printf("[SectorSystem] Manifiesto no encontrado: %s (utilizando fallback monolítico)\n", manifestPath);
        return 0;
    }

    char *p = strstr(json, "\"macro_size\"");
    if (p) {
        p = strchr(p, ':');
        if (p) ss->macroSize = (float)atof(p + 1);
    }
    if (ss->macroSize < 100.0f) ss->macroSize = 1024.0f;

    p = strstr(json, "\"chunk_size\"");
    if (p) {
        p = strchr(p, ':');
        if (p) ss->chunkSize = (float)atof(p + 1);
    }
    if (ss->chunkSize < 10.0f) ss->chunkSize = 128.0f;

    p = strstr(json, "\"sectors\"");
    if (!p) { free(json); return 0; }
    p = strchr(p, '[');
    if (!p) { free(json); return 0; }

    char *cursor = p + 1;
    int sCount = 0;

    while (sCount < MAX_MACRO_SECTORS) {
        char *secObj = strstr(cursor, "\"mx\"");
        if (!secObj) break;

        char *nextSec = strstr(secObj + 4, "\"mx\"");
        char *secEnd = nextSec ? nextSec : strchr(secObj, ']');
        if (!secEnd) secEnd = secObj + strlen(secObj);

        MacroSector *sec = &ss->sectors[sCount];
        parse_sector_entry(sec, secObj, secEnd);

        if (sec->vertexCount > 0 && sec->filepath[0] != '\0') {
            sCount++;
        }
        cursor = secEnd;
    }

    ss->sectorCount = sCount;
    free(json);

    if (!ensure_sync_init(ss)) {
        ss->sectorCount = 0;
        return 0;
    }

    printf("[SectorSystem] ✅ Manifiesto cargado: %d macro-sectores (%.0fm, chunks %.0fm)\n",
           ss->sectorCount, ss->macroSize, ss->chunkSize);
    return 1;
}

static uint8_t* read_sector_glb_attributes(const char *filepath, uint32_t expectedVcount, uint32_t *outVcount) {
    if (!filepath || !outVcount) return NULL;

    FILE *f = fopen(filepath, "rb");
    if (!f) {
        fprintf(stderr, "[SectorSystem] No se pudo abrir sector: %s\n", filepath);
        return NULL;
    }

    /* Leer encabezado glTF 2.0 binario */
    uint32_t header[3];
    if (fread(header, sizeof(uint32_t), 3, f) != 3 || header[0] != 0x46546C67) {
        fprintf(stderr, "[SectorSystem] Cabecera GLB inválida en %s\n", filepath);
        fclose(f);
        return NULL;
    }

    /* Chunk 0: JSON */
    uint32_t c0_hdr[2];
    if (fread(c0_hdr, sizeof(uint32_t), 2, f) != 2 ||
        fseek(f, (long)c0_hdr[0], SEEK_CUR) != 0) {
        fclose(f);
        return NULL;
    }

    /* Chunk 1: BIN */
    uint32_t c1_hdr[2];
    if (fread(c1_hdr, sizeof(uint32_t), 2, f) != 2 || c1_hdr[1] != 0x004E4942) {
        fclose(f);
        return NULL;
    }

    uint32_t vcount = expectedVcount;
    uint32_t glb_vcount = c1_hdr[0] / 56;
    if (glb_vcount > 0 && vcount != glb_vcount) {
        printf("[SectorSystem] Auto-sincronizando %s: manifiesto=%u -> glb=%u\n",
               filepath, vcount, glb_vcount);
        vcount = glb_vcount;
    }

    if (vcount == 0) {
        fclose(f);
        return NULL;
    }

    /* Leer los 5 bloques de atributos (pos, norm, uv, col, em = 52 bytes/vértice) en un solo malloc + fread */
    size_t rawBytes = (size_t)vcount * 52;
    uint8_t *rawBuf = (uint8_t*)malloc(rawBytes);
    if (!rawBuf) {
        fprintf(stderr, "[SectorSystem] Error de memoria leyendo buffers de %s\n", filepath);
        fclose(f);
        return NULL;
    }

    size_t bytesRead = fread(rawBuf, 1, rawBytes, f);
    fclose(f);
    if (bytesRead != rawBytes) {
        fprintf(stderr, "[SectorSystem] Lectura incompleta de %s (%zu/%zu bytes)\n",
                filepath, bytesRead, rawBytes);
        free(rawBuf);
        return NULL;
    }

    *outVcount = vcount;
    return rawBuf;
}

static void interleave_sector_vertices(Vertex *outV, const uint8_t *rawBuf, uint32_t vcount) {
    const float *posBuf  = (const float *)(rawBuf);
    const float *normBuf = (const float *)(rawBuf + (size_t)vcount * 12);
    const float *uvBuf   = (const float *)(rawBuf + (size_t)vcount * 24);
    const float *colBuf  = (const float *)(rawBuf + (size_t)vcount * 32);
    const float *emBuf   = (const float *)(rawBuf + (size_t)vcount * 48);

    for (uint32_t i = 0; i < vcount; i++) {
        outV[i].x = posBuf[i * 3 + 0];
        outV[i].y = posBuf[i * 3 + 1];
        outV[i].z = posBuf[i * 3 + 2];

        outV[i].nx = normBuf[i * 3 + 0];
        outV[i].ny = normBuf[i * 3 + 1];
        outV[i].nz = normBuf[i * 3 + 2];

        outV[i].u = uvBuf[i * 2 + 0];
        outV[i].v = uvBuf[i * 2 + 1];

        outV[i].r = colBuf[i * 4 + 0];
        outV[i].g = colBuf[i * 4 + 1];
        outV[i].b = colBuf[i * 4 + 2];
        outV[i].a = colBuf[i * 4 + 3];

        outV[i].emission = emBuf[i];
    }
}

static void write_sector_vertices(void *dst, const Vertex *staged, const uint8_t *rawBuf, uint32_t vcount) {
    if (staged) {
        memcpy(dst, staged, (size_t)vcount * sizeof(Vertex));
    } else if (rawBuf) {
        interleave_sector_vertices((Vertex*)dst, rawBuf, vcount);
    }
}

static void clear_sector_gpu_handles(MacroSector *sec) {
    sec->vertexBuffer = VK_NULL_HANDLE;
    sec->vertexMemory = VK_NULL_HANDLE;
    sec->mappedVertices = NULL;
    memset(&sec->vertexSub, 0, sizeof(sec->vertexSub));
    sec->vertexAllocSize = 0;
    sec->vertexInVramPool = 0;

    sec->indexBuffer = VK_NULL_HANDLE;
    sec->indexMemory = VK_NULL_HANDLE;
    sec->mappedIndices = NULL;
}

static int is_direct_uma(const struct VulkanEngine *eng) {
    if (!eng) return 0;
    if (eng->hostVisiblePool.propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) {
        return 1;
    }
    if (eng->physicalDevice != VK_NULL_HANDLE && eng->hostVisiblePool.device != VK_NULL_HANDLE) {
        VkPhysicalDeviceMemoryProperties memProps;
        vkGetPhysicalDeviceMemoryProperties(eng->physicalDevice, &memProps);
        uint32_t idx = eng->hostVisiblePool.memoryTypeIndex;
        if (idx < memProps.memoryTypeCount) {
            VkMemoryPropertyFlags flags = memProps.memoryTypes[idx].propertyFlags;
            if ((flags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) &&
                (flags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) {
                return 1;
            }
        }
    }
    return 0;
}

static int copy_buffer_one_time(struct VulkanEngine *eng, VkBuffer src, VkBuffer dst, VkDeviceSize size) {
    VkCommandBufferAllocateInfo cmdAlloc = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = eng->commandPool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1
    };
    VkCommandBuffer cmd = VK_NULL_HANDLE;
    if (vkAllocateCommandBuffers(eng->device, &cmdAlloc, &cmd) != VK_SUCCESS) {
        return 0;
    }

    VkCommandBufferBeginInfo beginInfo = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
    };
    if (vkBeginCommandBuffer(cmd, &beginInfo) != VK_SUCCESS) {
        vkFreeCommandBuffers(eng->device, eng->commandPool, 1, &cmd);
        return 0;
    }

    VkBufferCopy region = { .srcOffset = 0, .dstOffset = 0, .size = size };
    vkCmdCopyBuffer(cmd, src, dst, 1, &region);

    if (vkEndCommandBuffer(cmd) != VK_SUCCESS) {
        vkFreeCommandBuffers(eng->device, eng->commandPool, 1, &cmd);
        return 0;
    }

    VkFence fence = VK_NULL_HANDLE;
    VkFenceCreateInfo fenceInfo = {
        .sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,
        .pNext = NULL,
        .flags = 0
    };
    if (vkCreateFence(eng->device, &fenceInfo, NULL, &fence) != VK_SUCCESS) {
        vkFreeCommandBuffers(eng->device, eng->commandPool, 1, &cmd);
        return 0;
    }

    VkSubmitInfo submitInfo = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &cmd
    };
    VkResult res = vkQueueSubmit(eng->graphicsQueue, 1, &submitInfo, fence);
    if (res == VK_SUCCESS) {
        vkWaitForFences(eng->device, 1, &fence, VK_TRUE, UINT64_MAX);
    }
    vkDestroyFence(eng->device, fence, NULL);
    vkFreeCommandBuffers(eng->device, eng->commandPool, 1, &cmd);
    return (res == VK_SUCCESS);
}

typedef struct {
    VkBuffer buffer;
    VkDeviceMemory dedicatedMem;
    VulkanSuballocation sub;
    VkDeviceSize allocSize;
    int inPool;
} SectorStagingBuffer;

static void destroy_sector_staging(struct VulkanEngine *eng, SectorStagingBuffer *stg) {
    if (stg->buffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, stg->buffer, NULL);
        stg->buffer = VK_NULL_HANDLE;
    }
    if (stg->inPool && stg->sub.memory != VK_NULL_HANDLE) {
        vulkan_memory_pool_free_suballocation(&eng->hostVisiblePool, stg->sub, stg->allocSize);
        memset(&stg->sub, 0, sizeof(stg->sub));
        stg->allocSize = 0;
        stg->inPool = 0;
    }
    if (stg->dedicatedMem != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, stg->dedicatedMem, NULL);
        stg->dedicatedMem = VK_NULL_HANDLE;
    }
}

static int create_sector_staging(struct VulkanEngine *eng, VkDeviceSize vBufferSize,
                                 const Vertex *staged, const uint8_t *rawBuf, uint32_t vcount,
                                 SectorStagingBuffer *outStg) {
    memset(outStg, 0, sizeof(*outStg));
    VkBufferCreateInfo stgInfo = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = vBufferSize,
        .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE
    };
    if (vkCreateBuffer(eng->device, &stgInfo, NULL, &outStg->buffer) != VK_SUCCESS) {
        return 0;
    }

    VkMemoryRequirements stgReq;
    vkGetBufferMemoryRequirements(eng->device, outStg->buffer, &stgReq);

    int tryPool = (eng->hostVisiblePool.device != VK_NULL_HANDLE &&
                   (eng->hostVisiblePool.defaultBlockSize == 0 ||
                    stgReq.size <= eng->hostVisiblePool.defaultBlockSize));
    if (tryPool && vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, outStg->buffer, &outStg->sub)) {
        outStg->allocSize = stgReq.size;
        outStg->inPool = 1;
        if (outStg->sub.mappedPtr != NULL) {
            write_sector_vertices(outStg->sub.mappedPtr, staged, rawBuf, vcount);
            return 1;
        }
        void *tmpMapped = NULL;
        if (vkMapMemory(eng->device, outStg->sub.memory, outStg->sub.offset,
                        vBufferSize, 0, &tmpMapped) == VK_SUCCESS) {
            write_sector_vertices(tmpMapped, staged, rawBuf, vcount);
            vkUnmapMemory(eng->device, outStg->sub.memory);
            return 1;
        }
        destroy_sector_staging(eng, outStg);
        return 0;
    }

    uint32_t hostMemType = find_memory_type(eng->physicalDevice, stgReq.memoryTypeBits,
                                            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (hostMemType == UINT32_MAX) {
        destroy_sector_staging(eng, outStg);
        return 0;
    }

    VkMemoryAllocateInfo stgAlloc = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = stgReq.size,
        .memoryTypeIndex = hostMemType
    };
    if (vkAllocateMemory(eng->device, &stgAlloc, NULL, &outStg->dedicatedMem) != VK_SUCCESS) {
        destroy_sector_staging(eng, outStg);
        return 0;
    }

    void *mapped = NULL;
    if (vkBindBufferMemory(eng->device, outStg->buffer, outStg->dedicatedMem, 0) != VK_SUCCESS ||
        vkMapMemory(eng->device, outStg->dedicatedMem, 0, vBufferSize, 0, &mapped) != VK_SUCCESS) {
        destroy_sector_staging(eng, outStg);
        return 0;
    }

    write_sector_vertices(mapped, staged, rawBuf, vcount);
    vkUnmapMemory(eng->device, outStg->dedicatedMem);
    return 1;
}

static int upload_sector_vram_staged(struct VulkanEngine *eng, MacroSector *sec, VkDeviceSize vBufferSize,
                                     const Vertex *staged, const uint8_t *rawBuf, uint32_t vcount) {
    VkBufferCreateInfo vbInfo = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = vBufferSize,
        .usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE
    };
    if (vkCreateBuffer(eng->device, &vbInfo, NULL, &sec->vertexBuffer) != VK_SUCCESS) {
        clear_sector_gpu_handles(sec);
        return 0;
    }

    VkMemoryRequirements vMemReq;
    vkGetBufferMemoryRequirements(eng->device, sec->vertexBuffer, &vMemReq);

    if (!vulkan_memory_pool_bind_buffer(&eng->vramBufferPool, sec->vertexBuffer, &sec->vertexSub)) {
        vkDestroyBuffer(eng->device, sec->vertexBuffer, NULL);
        clear_sector_gpu_handles(sec);
        return 0;
    }
    sec->vertexAllocSize = vMemReq.size;
    sec->vertexInVramPool = 1;

    SectorStagingBuffer stg;
    int ok = create_sector_staging(eng, vBufferSize, staged, rawBuf, vcount, &stg);
    if (ok) {
        ok = copy_buffer_one_time(eng, stg.buffer, sec->vertexBuffer, vBufferSize);
    }
    destroy_sector_staging(eng, &stg);

    if (!ok) {
        vkDestroyBuffer(eng->device, sec->vertexBuffer, NULL);
        vulkan_memory_pool_free_suballocation(&eng->vramBufferPool, sec->vertexSub, sec->vertexAllocSize);
        clear_sector_gpu_handles(sec);
        return 0;
    }
    return 1;
}

static int upload_sector_dedicated(struct VulkanEngine *eng, MacroSector *sec,
                                   const VkMemoryRequirements *vMemReq, VkDeviceSize vBufferSize,
                                   const Vertex *staged, const uint8_t *rawBuf, uint32_t vcount) {
    uint32_t hostMemType = find_memory_type(eng->physicalDevice, vMemReq->memoryTypeBits,
                                            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (hostMemType == UINT32_MAX) return 0;

    VkMemoryAllocateInfo vAllocInfo = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = vMemReq->size,
        .memoryTypeIndex = hostMemType
    };
    if (vkAllocateMemory(eng->device, &vAllocInfo, NULL, &sec->vertexMemory) != VK_SUCCESS) {
        return 0;
    }
    if (vkBindBufferMemory(eng->device, sec->vertexBuffer, sec->vertexMemory, 0) != VK_SUCCESS ||
        vkMapMemory(eng->device, sec->vertexMemory, 0, vBufferSize, 0, &sec->mappedVertices) != VK_SUCCESS) {
        vkFreeMemory(eng->device, sec->vertexMemory, NULL);
        sec->vertexMemory = VK_NULL_HANDLE;
        sec->mappedVertices = NULL;
        return 0;
    }

    write_sector_vertices(sec->mappedVertices, staged, rawBuf, vcount);
    vkUnmapMemory(eng->device, sec->vertexMemory);
    sec->mappedVertices = NULL;
    return 1;
}

static int upload_sector_to_gpu_buffer(SectorSystem *ss, struct VulkanEngine *eng, MacroSector *sec,
                                       const Vertex *staged, const uint8_t *rawBuf, uint32_t vcount) {
    if (!ss || !eng || !sec || eng->device == VK_NULL_HANDLE || vcount == 0) return 0;
    if (!staged && !rawBuf) return 0;
    if (sec->isLoaded) return 1;

    clear_sector_gpu_handles(sec);

    VkDeviceSize vBufferSize = (VkDeviceSize)vcount * sizeof(Vertex);

    int uploaded = 0;
    if (!is_direct_uma(eng) &&
        eng->vramBufferPool.device != VK_NULL_HANDLE &&
        eng->commandPool != VK_NULL_HANDLE &&
        eng->graphicsQueue != VK_NULL_HANDLE) {
        uploaded = upload_sector_vram_staged(eng, sec, vBufferSize, staged, rawBuf, vcount);
    }

    if (!uploaded) {
        VkBufferCreateInfo vbInfo = {
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = vBufferSize,
            .usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE
        };
        if (vkCreateBuffer(eng->device, &vbInfo, NULL, &sec->vertexBuffer) != VK_SUCCESS) {
            return 0;
        }

        VkMemoryRequirements vMemReq;
        vkGetBufferMemoryRequirements(eng->device, sec->vertexBuffer, &vMemReq);

        if (eng->hostVisiblePool.device != VK_NULL_HANDLE &&
            vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, sec->vertexBuffer, &sec->vertexSub)) {
            sec->vertexAllocSize = vMemReq.size;
            sec->vertexInVramPool = 0;
            if (sec->vertexSub.mappedPtr != NULL) {
                write_sector_vertices(sec->vertexSub.mappedPtr, staged, rawBuf, vcount);
            } else {
                void *tmpMapped = NULL;
                if (vkMapMemory(eng->device, sec->vertexSub.memory, sec->vertexSub.offset,
                                vBufferSize, 0, &tmpMapped) != VK_SUCCESS) {
                    vkDestroyBuffer(eng->device, sec->vertexBuffer, NULL);
                    vulkan_memory_pool_free_suballocation(&eng->hostVisiblePool, sec->vertexSub, sec->vertexAllocSize);
                    clear_sector_gpu_handles(sec);
                    return 0;
                }
                write_sector_vertices(tmpMapped, staged, rawBuf, vcount);
                vkUnmapMemory(eng->device, sec->vertexSub.memory);
            }
        } else if (!upload_sector_dedicated(eng, sec, &vMemReq, vBufferSize, staged, rawBuf, vcount)) {
            vkDestroyBuffer(eng->device, sec->vertexBuffer, NULL);
            clear_sector_gpu_handles(sec);
            return 0;
        }
    }

    if (ss->syncInitialized) pthread_mutex_lock(&ss->mutex);
    sec->vertexCount = vcount;
    sec->isLoaded = 1;
    ss->activeLoadedSectors++;
    ss->activeLoadedVerts += vcount;
    if (ss->syncInitialized) pthread_mutex_unlock(&ss->mutex);
    return 1;
}

int sector_system_load_gpu(SectorSystem *ss, struct VulkanEngine *eng, int sectorIdx) {
    if (!ss || !eng || sectorIdx < 0 || sectorIdx >= ss->sectorCount) return 0;
    MacroSector *sec = &ss->sectors[sectorIdx];
    if (sec->isLoaded) return 1;

    Vertex *staged = NULL;
    uint32_t stagedVcount = 0;
    if (ss->syncInitialized) {
        pthread_mutex_lock(&ss->mutex);
        if (sec->loadState == SECTOR_STATE_READY_CPU && sec->stagedVertices != NULL) {
            staged = sec->stagedVertices;
            stagedVcount = sec->stagedVertexCount;
            sec->stagedVertices = NULL;
            sec->stagedVertexCount = 0;
            sec->loadState = SECTOR_STATE_UNLOADED;
        } else if (sec->loadState == SECTOR_STATE_QUEUED_ASYNC) {
            sec->asyncGen++;
            sec->loadState = SECTOR_STATE_UNLOADED;
        }
        pthread_mutex_unlock(&ss->mutex);
    }

    if (eng->device == VK_NULL_HANDLE) {
        free(staged);
        return 0;
    }

    int ok = 0;
    if (staged && stagedVcount > 0) {
        ok = upload_sector_to_gpu_buffer(ss, eng, sec, staged, NULL, stagedVcount);
        free(staged);
    } else {
        free(staged);
        uint32_t vcount = sec->vertexCount;
        uint8_t *rawBuf = read_sector_glb_attributes(sec->filepath, sec->vertexCount, &vcount);
        if (!rawBuf) return 0;
        ok = upload_sector_to_gpu_buffer(ss, eng, sec, NULL, rawBuf, vcount);
        free(rawBuf);
    }

    if (ok) {
        if (ss->syncInitialized) pthread_mutex_lock(&ss->mutex);
        sec->loadState = SECTOR_STATE_LOADED_GPU;
        if (ss->syncInitialized) pthread_mutex_unlock(&ss->mutex);
    }
    return ok;
}

static void free_deferred_sector_entry(struct VulkanEngine *eng, DeferredSectorFree *entry) {
    if (entry->vertexBuffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, entry->vertexBuffer, NULL);
        entry->vertexBuffer = VK_NULL_HANDLE;
    }
    if (entry->dedicatedVertexMemory != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, entry->dedicatedVertexMemory, NULL);
        entry->dedicatedVertexMemory = VK_NULL_HANDLE;
    }
    if (entry->vertexSub.memory != VK_NULL_HANDLE) {
        VulkanMemoryPool *pool = entry->vertexInVramPool ? &eng->vramBufferPool : &eng->hostVisiblePool;
        vulkan_memory_pool_free_suballocation(pool,
                                              entry->vertexSub,
                                              entry->vertexAllocSize);
        memset(&entry->vertexSub, 0, sizeof(entry->vertexSub));
        entry->vertexAllocSize = 0;
        entry->vertexInVramPool = 0;
    }
    if (entry->indexBuffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, entry->indexBuffer, NULL);
        entry->indexBuffer = VK_NULL_HANDLE;
    }
    if (entry->dedicatedIndexMemory != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, entry->dedicatedIndexMemory, NULL);
        entry->dedicatedIndexMemory = VK_NULL_HANDLE;
    }
}

void sector_system_process_deferred_frees(SectorSystem *ss, struct VulkanEngine *eng, int forceAll) {
    if (!ss || !eng) return;
    if (eng->device == VK_NULL_HANDLE) {
        if (forceAll) {
            memset(ss->deferredFrees, 0, sizeof(ss->deferredFrees));
            ss->deferredFreeCount = 0;
        }
        return;
    }

    int oldCount = ss->deferredFreeCount;
    if (oldCount < 0) oldCount = 0;
    if (oldCount > MAX_DEFERRED_SECTOR_FREES) oldCount = MAX_DEFERRED_SECTOR_FREES;

    int writeIdx = 0;
    for (int i = 0; i < oldCount; i++) {
        DeferredSectorFree entry = ss->deferredFrees[i];
        if (!forceAll) {
            entry.framesRemaining--;
        }
        if (forceAll || entry.framesRemaining <= 0) {
            free_deferred_sector_entry(eng, &entry);
        } else {
            ss->deferredFrees[writeIdx++] = entry;
        }
    }
    for (int i = writeIdx; i < oldCount; i++) {
        memset(&ss->deferredFrees[i], 0, sizeof(ss->deferredFrees[i]));
    }
    ss->deferredFreeCount = writeIdx;
}

static void cancel_sector_async_state(SectorSystem *ss, MacroSector *sec) {
    Vertex *pendingStaged = NULL;
    if (ss->syncInitialized) pthread_mutex_lock(&ss->mutex);
    if (sec->loadState == SECTOR_STATE_QUEUED_ASYNC) {
        sec->asyncGen++;
        sec->loadState = SECTOR_STATE_UNLOADED;
    } else if (sec->loadState == SECTOR_STATE_READY_CPU || sec->stagedVertices != NULL) {
        pendingStaged = sec->stagedVertices;
        sec->stagedVertices = NULL;
        sec->stagedVertexCount = 0;
        sec->loadState = SECTOR_STATE_UNLOADED;
    }
    if (ss->syncInitialized) pthread_mutex_unlock(&ss->mutex);
    free(pendingStaged);
}

static int sector_has_gpu_handles(const MacroSector *sec) {
    if (sec->vertexBuffer != VK_NULL_HANDLE) return 1;
    if (sec->vertexMemory != VK_NULL_HANDLE) return 1;
    if (sec->vertexSub.memory != VK_NULL_HANDLE) return 1;
    if (sec->indexBuffer != VK_NULL_HANDLE) return 1;
    if (sec->indexMemory != VK_NULL_HANDLE) return 1;
    return 0;
}

static void enqueue_sector_deferred_free(SectorSystem *ss, struct VulkanEngine *eng,
                                         const MacroSector *sec) {
    if (ss->deferredFreeCount >= MAX_DEFERRED_SECTOR_FREES) {
        if (eng->device != VK_NULL_HANDLE) {
            vkDeviceWaitIdle(eng->device);
        }
        sector_system_process_deferred_frees(ss, eng, 1);
    }

    if (ss->deferredFreeCount < MAX_DEFERRED_SECTOR_FREES && sector_has_gpu_handles(sec)) {
        DeferredSectorFree *entry = &ss->deferredFrees[ss->deferredFreeCount++];
        memset(entry, 0, sizeof(*entry));
        entry->vertexBuffer = sec->vertexBuffer;
        entry->dedicatedVertexMemory = sec->vertexMemory;
        entry->vertexSub = sec->vertexSub;
        entry->vertexAllocSize = sec->vertexAllocSize;
        entry->vertexInVramPool = sec->vertexInVramPool;
        entry->indexBuffer = sec->indexBuffer;
        entry->dedicatedIndexMemory = sec->indexMemory;
        entry->framesRemaining = MAX_FRAMES_IN_FLIGHT + 1;
    }
}

void sector_system_unload_gpu(SectorSystem *ss, struct VulkanEngine *eng, int sectorIdx) {
    if (!ss || sectorIdx < 0 || sectorIdx >= ss->sectorCount) return;
    MacroSector *sec = &ss->sectors[sectorIdx];

    cancel_sector_async_state(ss, sec);

    if (!sec->isLoaded || !eng) return;

    enqueue_sector_deferred_free(ss, eng, sec);
    clear_sector_gpu_handles(sec);

    if (ss->syncInitialized) pthread_mutex_lock(&ss->mutex);
    sec->isLoaded = 0;
    sec->loadState = SECTOR_STATE_UNLOADED;
    if (ss->activeLoadedSectors > 0) ss->activeLoadedSectors--;
    if (ss->activeLoadedVerts >= sec->vertexCount) {
        ss->activeLoadedVerts -= sec->vertexCount;
    } else {
        ss->activeLoadedVerts = 0;
    }
    if (ss->syncInitialized) pthread_mutex_unlock(&ss->mutex);
}

static float point_dist_to_aabb_xz(float px, float pz, const AABB *aabb) {
    float dx = 0.0f;
    if (px < aabb->min_x) dx = aabb->min_x - px;
    else if (px > aabb->max_x) dx = px - aabb->max_x;

    float dz = 0.0f;
    if (pz < aabb->min_z) dz = aabb->min_z - pz;
    else if (pz > aabb->max_z) dz = pz - aabb->max_z;

    return sqrtf(dx * dx + dz * dz);
}

static int find_next_queued_sector_locked(const SectorSystem *ss) {
    int bestIdx = -1;
    float bestDist = 0.0f;
    for (int i = 0; i < ss->sectorCount; i++) {
        if (ss->sectors[i].loadState == SECTOR_STATE_QUEUED_ASYNC) {
            float d = point_dist_to_aabb_xz(ss->lastCamX, ss->lastCamZ, &ss->sectors[i].aabb);
            if (bestIdx < 0 || d < bestDist) {
                bestDist = d;
                bestIdx = i;
            }
        }
    }
    return bestIdx;
}

static void* sector_worker_thread(void *arg) {
    SectorSystem *ss = (SectorSystem *)arg;
    for (;;) {
        pthread_mutex_lock(&ss->mutex);
        int idx = -1;
        while (!ss->shutdownWorker && (idx = find_next_queued_sector_locked(ss)) < 0) {
            pthread_cond_wait(&ss->cond, &ss->mutex);
        }
        if (ss->shutdownWorker) {
            pthread_mutex_unlock(&ss->mutex);
            break;
        }

        MacroSector *sec = &ss->sectors[idx];
        char filepath[128];
        memcpy(filepath, sec->filepath, sizeof(filepath));
        filepath[sizeof(filepath) - 1] = '\0';
        uint32_t expectedVcount = sec->vertexCount;
        uint32_t token = sec->asyncGen;
        pthread_mutex_unlock(&ss->mutex);

        /* Lectura GLB e interleaving fuera del hilo principal */
        uint32_t actualVcount = expectedVcount;
        uint8_t *rawBuf = read_sector_glb_attributes(filepath, expectedVcount, &actualVcount);
        Vertex *staged = NULL;
        if (rawBuf && actualVcount > 0) {
            staged = (Vertex *)malloc((size_t)actualVcount * sizeof(Vertex));
            if (staged) {
                interleave_sector_vertices(staged, rawBuf, actualVcount);
            }
        }
        free(rawBuf);

        pthread_mutex_lock(&ss->mutex);
        int stillValid = (!ss->shutdownWorker &&
                          sec->loadState == SECTOR_STATE_QUEUED_ASYNC &&
                          sec->asyncGen == token);
        if (stillValid && staged) {
            free(sec->stagedVertices);
            sec->stagedVertices = staged;
            sec->stagedVertexCount = actualVcount;
            sec->loadState = SECTOR_STATE_READY_CPU;
            staged = NULL;
        } else if (stillValid) {
            sec->loadState = SECTOR_STATE_UNLOADED;
        }
        pthread_mutex_unlock(&ss->mutex);

        free(staged);
    }
    return NULL;
}

static int start_sector_worker(SectorSystem *ss) {
    if (ss->workerRunning) return 1;
    if (!ensure_sync_init(ss)) return 0;
    ss->shutdownWorker = 0;
    if (pthread_create(&ss->workerThread, NULL, sector_worker_thread, ss) != 0) {
        return 0;
    }
    ss->workerRunning = 1;
    return 1;
}

static void stop_sector_worker(SectorSystem *ss) {
    if (!ss || !ss->workerRunning) return;
    if (ss->syncInitialized) {
        pthread_mutex_lock(&ss->mutex);
        ss->shutdownWorker = 1;
        pthread_cond_broadcast(&ss->cond);
        pthread_mutex_unlock(&ss->mutex);
    } else {
        ss->shutdownWorker = 1;
    }
    pthread_join(ss->workerThread, NULL);
    ss->workerRunning = 0;
}

static void process_ready_cpu_sectors(SectorSystem *ss, struct VulkanEngine *eng,
                                      float camX, float camZ, float unloadRadius) {
    int uploadedThisFrame = 0;

    for (int i = 0; i < ss->sectorCount; i++) {
        MacroSector *sec = &ss->sectors[i];

        pthread_mutex_lock(&ss->mutex);
        int isReady = (sec->loadState == SECTOR_STATE_READY_CPU);
        pthread_mutex_unlock(&ss->mutex);
        if (!isReady) continue;

        float dist = point_dist_to_aabb_xz(camX, camZ, &sec->aabb);
        int inRange = (dist <= unloadRadius);
        if (inRange && uploadedThisFrame >= 2) {
            continue;
        }

        pthread_mutex_lock(&ss->mutex);
        if (sec->loadState != SECTOR_STATE_READY_CPU) {
            pthread_mutex_unlock(&ss->mutex);
            continue;
        }
        Vertex *staged = sec->stagedVertices;
        uint32_t vcount = sec->stagedVertexCount;
        sec->stagedVertices = NULL;
        sec->stagedVertexCount = 0;
        sec->loadState = SECTOR_STATE_UNLOADED;
        pthread_mutex_unlock(&ss->mutex);

        if (inRange && staged && vcount > 0) {
            if (upload_sector_to_gpu_buffer(ss, eng, sec, staged, NULL, vcount)) {
                pthread_mutex_lock(&ss->mutex);
                sec->loadState = SECTOR_STATE_LOADED_GPU;
                pthread_mutex_unlock(&ss->mutex);
                uploadedThisFrame++;
            }
        }
        free(staged);
    }
}

static void update_sectors_sync(SectorSystem *ss, struct VulkanEngine *eng,
                                float camX, float camZ, float loadRadius, float unloadRadius) {
    for (int i = 0; i < ss->sectorCount; i++) {
        MacroSector *sec = &ss->sectors[i];
        float dist = point_dist_to_aabb_xz(camX, camZ, &sec->aabb);
        if (dist <= loadRadius) {
            if (!sec->isLoaded) {
                sector_system_load_gpu(ss, eng, i);
            }
        } else if (dist > unloadRadius) {
            pthread_mutex_lock(&ss->mutex);
            int state = sec->loadState;
            pthread_mutex_unlock(&ss->mutex);
            if (sec->isLoaded || state != SECTOR_STATE_UNLOADED) {
                sector_system_unload_gpu(ss, eng, i);
            }
        }
    }
}

static void update_sectors_streaming(SectorSystem *ss, struct VulkanEngine *eng,
                                     float camX, float camZ, float loadRadius, float unloadRadius) {
    int queuedAny = 0;

    for (int i = 0; i < ss->sectorCount; i++) {
        MacroSector *sec = &ss->sectors[i];
        float dist = point_dist_to_aabb_xz(camX, camZ, &sec->aabb);

        if (dist <= loadRadius) {
            if (!sec->isLoaded) {
                pthread_mutex_lock(&ss->mutex);
                if (sec->loadState == SECTOR_STATE_UNLOADED) {
                    sec->loadState = SECTOR_STATE_QUEUED_ASYNC;
                    queuedAny = 1;
                }
                pthread_mutex_unlock(&ss->mutex);
            }
        } else if (dist > unloadRadius) {
            if (sec->isLoaded) {
                sector_system_unload_gpu(ss, eng, i);
            } else {
                pthread_mutex_lock(&ss->mutex);
                int needCancel = (sec->loadState == SECTOR_STATE_QUEUED_ASYNC ||
                                  sec->loadState == SECTOR_STATE_READY_CPU);
                pthread_mutex_unlock(&ss->mutex);
                if (needCancel) {
                    sector_system_unload_gpu(ss, eng, i);
                }
            }
        }
    }

    if (queuedAny) {
        pthread_mutex_lock(&ss->mutex);
        pthread_cond_signal(&ss->cond);
        pthread_mutex_unlock(&ss->mutex);
    }
}

void sector_system_update(SectorSystem *ss, struct VulkanEngine *eng, float camX, float camZ, float loadRadius) {
    if (!ss || !eng) return;

    ss->updateTick++;
    sector_system_process_deferred_frees(ss, eng, 0);
    if (ss->sectorCount == 0) return;
    if (!ensure_sync_init(ss)) return;

    pthread_mutex_lock(&ss->mutex);
    ss->lastCamX = camX;
    ss->lastCamZ = camZ;
    pthread_mutex_unlock(&ss->mutex);

    /* Distancia con histeresis para evitar oscilación de carga/descarga */
    float unloadRadius = loadRadius + 400.0f;

    if (ss->workerRunning || ss->activeLoadedSectors > 0) {
        process_ready_cpu_sectors(ss, eng, camX, camZ, unloadRadius);
    }

    if (ss->activeLoadedSectors == 0) {
        update_sectors_sync(ss, eng, camX, camZ, loadRadius, unloadRadius);
    } else if (start_sector_worker(ss)) {
        update_sectors_streaming(ss, eng, camX, camZ, loadRadius, unloadRadius);
    } else {
        update_sectors_sync(ss, eng, camX, camZ, loadRadius, unloadRadius);
    }
}

void sector_system_destroy(SectorSystem *ss, struct VulkanEngine *eng) {
    if (!ss) return;

    stop_sector_worker(ss);

    if (eng && eng->device != VK_NULL_HANDLE) {
        vkDeviceWaitIdle(eng->device);
    }

    int count = (ss->sectorCount > MAX_MACRO_SECTORS) ? MAX_MACRO_SECTORS : ss->sectorCount;
    for (int i = 0; i < count; i++) {
        MacroSector *sec = &ss->sectors[i];
        free(sec->stagedVertices);
        sec->stagedVertices = NULL;
        sec->stagedVertexCount = 0;
        if (sec->isLoaded && eng) {
            sector_system_unload_gpu(ss, eng, i);
        } else {
            sec->loadState = SECTOR_STATE_UNLOADED;
        }
    }

    if (eng) {
        sector_system_process_deferred_frees(ss, eng, 1);
    }

    if (ss->syncInitialized) {
        pthread_cond_destroy(&ss->cond);
        pthread_mutex_destroy(&ss->mutex);
        ss->syncInitialized = 0;
    }
    ss->shutdownWorker = 0;
    ss->sectorCount = 0;
}
