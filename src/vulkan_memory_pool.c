#include "vulkan_memory_pool.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static VkDeviceSize align_up(VkDeviceSize value, VkDeviceSize alignment) {
    if (alignment <= 1) return value;
    if ((alignment & (alignment - 1)) == 0) {
        return (value + (alignment - 1)) & ~(alignment - 1);
    }
    VkDeviceSize rem = value % alignment;
    return (rem == 0) ? value : (value + (alignment - rem));
}

static VulkanMemoryBlock* find_block_by_memory(VulkanMemoryPool *pool, VkDeviceMemory memory) {
    for (uint32_t i = 0; i < pool->blockCount; i++) {
        if (pool->blocks[i].memory == memory) {
            return &pool->blocks[i];
        }
    }
    return NULL;
}

static void insert_free_region(VulkanMemoryPool *pool, VkDeviceMemory memory,
                               VkDeviceSize offset, VkDeviceSize size) {
    if (size == 0) return;
    if (pool->freeRegionCount < VK_POOL_MAX_FREE_REGIONS) {
        pool->freeRegions[pool->freeRegionCount++] = (VulkanFreeRegion){
            .memory = memory,
            .offset = offset,
            .size = size
        };
        return;
    }

    /* Búfer estático lleno: almacenar en el búfer dinámico de desbordamiento sin descartar */
    if (pool->extraFreeRegionCount >= pool->extraFreeRegionCapacity) {
        uint32_t newCap = (pool->extraFreeRegionCapacity == 0) ? 64 : pool->extraFreeRegionCapacity * 2;
        VulkanFreeRegion *newBuf = (VulkanFreeRegion*)realloc(pool->extraFreeRegions, newCap * sizeof(VulkanFreeRegion));
        if (!newBuf) {
            fprintf(stderr, "[MemoryPool] CRITICO: realloc fallo al expandir regiones libres\n");
            return;
        }
        pool->extraFreeRegions = newBuf;
        pool->extraFreeRegionCapacity = newCap;
    }
    pool->extraFreeRegions[pool->extraFreeRegionCount++] = (VulkanFreeRegion){
        .memory = memory,
        .offset = offset,
        .size = size
    };
}

/*
 * Recorre un arreglo de regiones libres buscando la de menor tamaño que cumpla
 * con el alineamiento y tamaño solicitados (estrategia best-fit).
 */
static void scan_free_region_array(const VulkanFreeRegion *regions, uint32_t count,
                                   VkDeviceSize size, VkDeviceSize alignment,
                                   uint32_t *bestIdx, int *bestInExtra, int isExtra,
                                   VkDeviceSize *bestSize, VkDeviceSize *bestAlignedOffset) {
    for (uint32_t i = 0; i < count; i++) {
        const VulkanFreeRegion *r = &regions[i];
        VkDeviceSize regionEnd = r->offset + r->size;
        VkDeviceSize alignedOffset = align_up(r->offset, alignment);
        if (alignedOffset < r->offset || alignedOffset > regionEnd) continue;
        if (size > regionEnd - alignedOffset) continue;

        if (*bestIdx == UINT32_MAX || r->size < *bestSize) {
            *bestIdx = i;
            *bestInExtra = isExtra;
            *bestSize = r->size;
            *bestAlignedOffset = alignedOffset;
        }
    }
}

/* Busca la mejor región libre entre el bloque principal y los bloques extra. */
static int suballocate_from_free_regions(VulkanMemoryPool *pool, VkDeviceSize size,
                                         VkDeviceSize alignment, VulkanSuballocation *outSub) {
    uint32_t bestIdx = UINT32_MAX;
    int bestInExtra = 0;
    VkDeviceSize bestSize = 0;
    VkDeviceSize bestAlignedOffset = 0;

    scan_free_region_array(pool->freeRegions, pool->freeRegionCount, size, alignment,
                           &bestIdx, &bestInExtra, 0, &bestSize, &bestAlignedOffset);
    scan_free_region_array(pool->extraFreeRegions, pool->extraFreeRegionCount, size, alignment,
                           &bestIdx, &bestInExtra, 1, &bestSize, &bestAlignedOffset);

    if (bestIdx == UINT32_MAX) return 0;

    VulkanFreeRegion chosen;
    if (bestInExtra) {
        chosen = pool->extraFreeRegions[bestIdx];
        pool->extraFreeRegions[bestIdx] = pool->extraFreeRegions[--pool->extraFreeRegionCount];
    } else {
        chosen = pool->freeRegions[bestIdx];
        pool->freeRegions[bestIdx] = pool->freeRegions[--pool->freeRegionCount];
    }

    VkDeviceSize regionEnd = chosen.offset + chosen.size;
    VkDeviceSize prefixSize = bestAlignedOffset - chosen.offset;
    VkDeviceSize suffixOffset = bestAlignedOffset + size;
    VkDeviceSize suffixSize = regionEnd - suffixOffset;

    if (prefixSize > 0) {
        insert_free_region(pool, chosen.memory, chosen.offset, prefixSize);
    }
    if (suffixSize > 0) {
        insert_free_region(pool, chosen.memory, suffixOffset, suffixSize);
    }

    VulkanMemoryBlock *block = find_block_by_memory(pool, chosen.memory);
    outSub->memory = chosen.memory;
    outSub->offset = bestAlignedOffset;
    outSub->mappedPtr = (block && block->mappedBase)
        ? (void*)((char*)block->mappedBase + bestAlignedOffset)
        : NULL;
    return 1;
}

int vulkan_memory_pool_init(VulkanMemoryPool *pool, VkDevice device, VkPhysicalDevice physicalDevice,
                            uint32_t memoryTypeIndex, VkMemoryPropertyFlags propertyFlags,
                            VkDeviceSize defaultBlockSize) {
    if (!pool || device == VK_NULL_HANDLE) return 0;
    memset(pool, 0, sizeof(VulkanMemoryPool));
    pool->device = device;
    pool->physicalDevice = physicalDevice;
    pool->memoryTypeIndex = memoryTypeIndex;
    pool->propertyFlags = propertyFlags;
    pool->defaultBlockSize = defaultBlockSize;
    pool->blockCount = 0;
    pool->freeRegionCount = 0;
    return 1;
}

VulkanSuballocation vulkan_memory_pool_suballocate(VulkanMemoryPool *pool, VkDeviceSize size, VkDeviceSize alignment) {
    VulkanSuballocation sub = { VK_NULL_HANDLE, 0, NULL };
    if (!pool || pool->device == VK_NULL_HANDLE || size == 0) return sub;

    if (alignment == 0) alignment = 1;

    // 1. Reutilizar regiones liberadas previamente (best-fit con respeto de alineamiento)
    if (suballocate_from_free_regions(pool, size, alignment, &sub)) {
        return sub;
    }

    // 2. Intentar ubicar al final de los bloques existentes
    for (uint32_t i = 0; i < pool->blockCount; i++) {
        VulkanMemoryBlock *b = &pool->blocks[i];
        VkDeviceSize alignedOffset = align_up(b->allocatedOffset, alignment);
        if (alignedOffset >= b->allocatedOffset && alignedOffset <= b->size && size <= b->size - alignedOffset) {
            sub.memory = b->memory;
            sub.offset = alignedOffset;
            if (b->mappedBase) {
                sub.mappedPtr = (char*)b->mappedBase + alignedOffset;
            }
            b->allocatedOffset = alignedOffset + size;
            return sub;
        }
    }

    // 3. Si no cabe en los bloques actuales, crear un nuevo bloque grande
    if (pool->blockCount >= VK_POOL_MAX_BLOCKS) {
        fprintf(stderr, "[MemoryPool] ERROR: Se ha alcanzado el límite máximo de bloques (%d)\n", VK_POOL_MAX_BLOCKS);
        return sub;
    }

    VkDeviceSize newBlockSize = pool->defaultBlockSize;
    if (newBlockSize == 0) {
        newBlockSize = size;
    } else if (size > newBlockSize) {
        newBlockSize = align_up(size, pool->defaultBlockSize);
    }

    VkMemoryAllocateInfo allocInfo = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .pNext = NULL,
        .allocationSize = newBlockSize,
        .memoryTypeIndex = pool->memoryTypeIndex
    };

    VkDeviceMemory newMem = VK_NULL_HANDLE;
    VkResult res = vkAllocateMemory(pool->device, &allocInfo, NULL, &newMem);
    if (res != VK_SUCCESS) {
        fprintf(stderr, "[MemoryPool] ERROR al asignar bloque grande de %zu bytes (VkResult=%d, memTypeIndex=%u)\n",
                (size_t)newBlockSize, res, pool->memoryTypeIndex);
        return sub;
    }

    VulkanMemoryBlock *newBlock = &pool->blocks[pool->blockCount++];
    newBlock->memory = newMem;
    newBlock->size = newBlockSize;
    newBlock->allocatedOffset = size;
    newBlock->mappedBase = NULL;

    // Si el tipo de memoria es accesible por CPU (HOST_VISIBLE), mapear el bloque persistentemente
    if (pool->propertyFlags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) {
        res = vkMapMemory(pool->device, newMem, 0, newBlockSize, 0, &newBlock->mappedBase);
        if (res == VK_SUCCESS) {
            sub.mappedPtr = newBlock->mappedBase;
        } else {
            fprintf(stderr, "[MemoryPool] ADVERTENCIA: Falló vkMapMemory en bloque host-visible (VkResult=%d)\n", res);
        }
    }

    sub.memory = newMem;
    sub.offset = 0;
    return sub;
}

int vulkan_memory_pool_bind_buffer(VulkanMemoryPool *pool, VkBuffer buffer, VulkanSuballocation *outSub) {
    if (!pool || buffer == VK_NULL_HANDLE) return 0;
    if (pool->memoryTypeIndex >= 32) {
        fprintf(stderr, "[MemoryPool] ERROR: memoryTypeIndex %u fuera de rango de 32 bits\n", pool->memoryTypeIndex);
        return 0;
    }
    VkMemoryRequirements memReqs;
    vkGetBufferMemoryRequirements(pool->device, buffer, &memReqs);

    // Validación crítica de compatibilidad de tipo de memoria de hardware
    if (!(memReqs.memoryTypeBits & (1u << pool->memoryTypeIndex))) {
        fprintf(stderr, "[MemoryPool] ERROR: Buffer requiere tipos de memoria 0x%x, incompatible con pool index %u\n",
                memReqs.memoryTypeBits, pool->memoryTypeIndex);
        return 0;
    }

    VulkanSuballocation sub = vulkan_memory_pool_suballocate(pool, memReqs.size, memReqs.alignment);
    if (sub.memory == VK_NULL_HANDLE) return 0;

    VkResult res = vkBindBufferMemory(pool->device, buffer, sub.memory, sub.offset);
    if (res != VK_SUCCESS) {
        vulkan_memory_pool_free_suballocation(pool, sub, memReqs.size);
        return 0;
    }

    if (outSub) *outSub = sub;
    return 1;
}

int vulkan_memory_pool_bind_image(VulkanMemoryPool *pool, VkImage image, VulkanSuballocation *outSub) {
    if (!pool || image == VK_NULL_HANDLE) return 0;
    if (pool->memoryTypeIndex >= 32) {
        fprintf(stderr, "[MemoryPool] ERROR: memoryTypeIndex %u fuera de rango de 32 bits\n", pool->memoryTypeIndex);
        return 0;
    }
    VkMemoryRequirements memReqs;
    vkGetImageMemoryRequirements(pool->device, image, &memReqs);

    // Validación crítica de compatibilidad de tipo de memoria de hardware
    if (!(memReqs.memoryTypeBits & (1u << pool->memoryTypeIndex))) {
        fprintf(stderr, "[MemoryPool] ERROR: Imagen requiere tipos de memoria 0x%x, incompatible con pool index %u\n",
                memReqs.memoryTypeBits, pool->memoryTypeIndex);
        return 0;
    }

    VulkanSuballocation sub = vulkan_memory_pool_suballocate(pool, memReqs.size, memReqs.alignment);
    if (sub.memory == VK_NULL_HANDLE) return 0;

    VkResult res = vkBindImageMemory(pool->device, image, sub.memory, sub.offset);
    if (res != VK_SUCCESS) {
        vulkan_memory_pool_free_suballocation(pool, sub, memReqs.size);
        return 0;
    }

    if (outSub) *outSub = sub;
    return 1;
}

void vulkan_memory_pool_free_suballocation(VulkanMemoryPool *pool, VulkanSuballocation sub, VkDeviceSize size) {
    if (!pool || sub.memory == VK_NULL_HANDLE || size == 0) return;

    VulkanMemoryBlock *block = find_block_by_memory(pool, sub.memory);
    if (!block) return;
    if (sub.offset > block->allocatedOffset || size > block->allocatedOffset - sub.offset) {
        return;
    }

    VkDeviceSize newOffset = sub.offset;
    VkDeviceSize newSize = size;

    // Coalescer regiones libres adyacentes dentro del mismo VkDeviceMemory (en búfer estático y extra)
    int merged = 1;
    while (merged) {
        merged = 0;
        for (uint32_t i = 0; i < pool->freeRegionCount; i++) {
            VulkanFreeRegion *r = &pool->freeRegions[i];
            if (r->memory != sub.memory) continue;

            if (r->offset + r->size == newOffset) {
                newOffset = r->offset;
                newSize += r->size;
                pool->freeRegions[i] = pool->freeRegions[--pool->freeRegionCount];
                merged = 1;
                break;
            }
            if (newOffset + newSize == r->offset) {
                newSize += r->size;
                pool->freeRegions[i] = pool->freeRegions[--pool->freeRegionCount];
                merged = 1;
                break;
            }
        }
        if (merged) continue;
        for (uint32_t i = 0; i < pool->extraFreeRegionCount; i++) {
            VulkanFreeRegion *r = &pool->extraFreeRegions[i];
            if (r->memory != sub.memory) continue;

            if (r->offset + r->size == newOffset) {
                newOffset = r->offset;
                newSize += r->size;
                pool->extraFreeRegions[i] = pool->extraFreeRegions[--pool->extraFreeRegionCount];
                merged = 1;
                break;
            }
            if (newOffset + newSize == r->offset) {
                newSize += r->size;
                pool->extraFreeRegions[i] = pool->extraFreeRegions[--pool->extraFreeRegionCount];
                merged = 1;
                break;
            }
        }
    }

    // Si la región coalescida toca el tope asignado del bloque, rebobinar allocatedOffset
    if (newOffset + newSize == block->allocatedOffset) {
        block->allocatedOffset = newOffset;
        return;
    }

    insert_free_region(pool, sub.memory, newOffset, newSize);
}

void vulkan_memory_pool_destroy(VulkanMemoryPool *pool) {
    if (!pool || pool->device == VK_NULL_HANDLE) return;

    for (uint32_t i = 0; i < pool->blockCount; i++) {
        VulkanMemoryBlock *b = &pool->blocks[i];
        if (b->mappedBase) {
            vkUnmapMemory(pool->device, b->memory);
            b->mappedBase = NULL;
        }
        if (b->memory != VK_NULL_HANDLE) {
            vkFreeMemory(pool->device, b->memory, NULL);
            b->memory = VK_NULL_HANDLE;
        }
    }
    pool->blockCount = 0;
    pool->freeRegionCount = 0;
    if (pool->extraFreeRegions) {
        free(pool->extraFreeRegions);
        pool->extraFreeRegions = NULL;
    }
    pool->extraFreeRegionCount = 0;
    pool->extraFreeRegionCapacity = 0;
}
