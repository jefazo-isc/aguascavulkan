#ifndef VULKAN_MEMORY_POOL_H
#define VULKAN_MEMORY_POOL_H

#include <vulkan/vulkan.h>
#include <stdint.h>

#define VK_POOL_MAX_BLOCKS 128
#define VK_POOL_MAX_FREE_REGIONS 256

typedef struct {
    VkDeviceMemory memory;
    VkDeviceSize size;
    VkDeviceSize allocatedOffset;
    void *mappedBase; // != NULL si es memoria HOST_VISIBLE
} VulkanMemoryBlock;

typedef struct {
    VkDeviceMemory memory;
    VkDeviceSize offset;
    VkDeviceSize size;
} VulkanFreeRegion;

typedef struct {
    VkDevice device;
    VkPhysicalDevice physicalDevice;
    uint32_t memoryTypeIndex;
    VkMemoryPropertyFlags propertyFlags;
    VkDeviceSize defaultBlockSize;
    VulkanMemoryBlock blocks[VK_POOL_MAX_BLOCKS];
    uint32_t blockCount;
    VulkanFreeRegion freeRegions[VK_POOL_MAX_FREE_REGIONS];
    uint32_t freeRegionCount;
    VulkanFreeRegion *extraFreeRegions;
    uint32_t extraFreeRegionCount;
    uint32_t extraFreeRegionCapacity;
} VulkanMemoryPool;

typedef struct {
    VkDeviceMemory memory;
    VkDeviceSize offset;
    void *mappedPtr; // Puntero directo al host accesible por CPU si el bloque está mapeado
} VulkanSuballocation;

/**
 * Inicializa un pool de memoria grande para un tipo específico de memoria Vulkan.
 */
int vulkan_memory_pool_init(VulkanMemoryPool *pool, VkDevice device, VkPhysicalDevice physicalDevice,
                            uint32_t memoryTypeIndex, VkMemoryPropertyFlags propertyFlags,
                            VkDeviceSize defaultBlockSize);

/**
 * Subasigna 'size' bytes con el alineamiento requerido por el recurso de hardware.
 * Crea un nuevo bloque de VRAM/RAM solo cuando los bloques existentes se llenan.
 */
VulkanSuballocation vulkan_memory_pool_suballocate(VulkanMemoryPool *pool, VkDeviceSize size, VkDeviceSize alignment);

/**
 * Vincula un VkBuffer subasignando la memoria adecuada del pool.
 */
int vulkan_memory_pool_bind_buffer(VulkanMemoryPool *pool, VkBuffer buffer, VulkanSuballocation *outSub);

/**
 * Vincula un VkImage subasignando la memoria adecuada del pool.
 */
int vulkan_memory_pool_bind_image(VulkanMemoryPool *pool, VkImage image, VulkanSuballocation *outSub);

/**
 * Libera una subasignación previa devolviéndola al bloque o a la lista de regiones libres (con coalescencia).
 */
void vulkan_memory_pool_free_suballocation(VulkanMemoryPool *pool, VulkanSuballocation sub, VkDeviceSize size);

/**
 * Libera de forma centralizada todos los bloques grandes de memoria de Vulkan asignados en el pool.
 */
void vulkan_memory_pool_destroy(VulkanMemoryPool *pool);

#endif // VULKAN_MEMORY_POOL_H
