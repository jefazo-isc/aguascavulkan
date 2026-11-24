#include "vulkan_texture.h"
#include "vulkan_swapchain.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <math.h>
#include <dirent.h>
#include <unistd.h>
#pragma GCC push_options
#pragma GCC optimize("O0")
#define STBI_ONLY_PNG
#define STBI_ONLY_JPEG
#define STBI_NO_SIMD
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
#pragma GCC pop_options

static uint32_t calculate_mip_levels(uint32_t w, uint32_t h) {
    uint32_t maxDim = (w > h) ? w : h;
    uint32_t levels = 1;
    while (maxDim > 1) {
        maxDim >>= 1;
        levels++;
    }
    return levels;
}

/* Verifica si el hardware soporta blit origen y destino para el formato en tiling optimo. */
static int format_supports_mipmap_blit(VkPhysicalDevice physicalDevice, VkFormat fmt) {
    VkFormatProperties formatProperties;
    vkGetPhysicalDeviceFormatProperties(physicalDevice, fmt, &formatProperties);
    VkFormatFeatureFlags required = VK_FORMAT_FEATURE_BLIT_SRC_BIT | VK_FORMAT_FEATURE_BLIT_DST_BIT;
    return (formatProperties.optimalTilingFeatures & required) == required;
}

static VkResult create_gpu_image(VulkanEngine *eng,
                                 VkImage* image,
                                 uint32_t w, uint32_t h, uint32_t mipLevels, VkFormat format,
                                 VkImageTiling tiling, VkImageUsageFlags usage) {
    VkImageCreateInfo ci = {0};
    ci.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    ci.imageType = VK_IMAGE_TYPE_2D;
    ci.extent.width = w;
    ci.extent.height = h;
    ci.extent.depth = 1;
    ci.mipLevels = mipLevels;
    ci.arrayLayers = 1;
    ci.format = format;
    ci.tiling = tiling;
    ci.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    ci.usage = usage;
    ci.samples = VK_SAMPLE_COUNT_1_BIT;
    ci.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    if (vkCreateImage(eng->device, &ci, NULL, image) != VK_SUCCESS) return VK_ERROR_INITIALIZATION_FAILED;

    // Vincular al pool exclusivo de imágenes en VRAM (evita violar bufferImageGranularity)
    if (!vulkan_memory_pool_bind_image(&eng->vramImagePool, *image, NULL)) {
        vkDestroyImage(eng->device, *image, NULL);
        *image = VK_NULL_HANDLE;
        return VK_ERROR_OUT_OF_DEVICE_MEMORY;
    }
    return VK_SUCCESS;
}

static void copy_buf_to_img(VkCommandBuffer cb, VkBuffer buf, VkImage img, uint32_t w, uint32_t h){
    VkBufferImageCopy r = {0};
    r.bufferOffset = 0;
    r.bufferRowLength = 0;
    r.bufferImageHeight = 0;
    r.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    r.imageSubresource.mipLevel = 0;
    r.imageSubresource.baseArrayLayer = 0;
    r.imageSubresource.layerCount = 1;
    r.imageOffset = (VkOffset3D){0, 0, 0};
    r.imageExtent = (VkExtent3D){w, h, 1};
    vkCmdCopyBufferToImage(cb, buf, img, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &r);
}

static int create_image_view(VulkanEngine *eng, VkImage img, VkImageView *view, VkFormat fmt, uint32_t mipLevels){
    VkImageViewCreateInfo vi = {0};
    vi.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
    vi.image = img;
    vi.viewType = VK_IMAGE_VIEW_TYPE_2D;
    vi.format = fmt;
    vi.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    vi.subresourceRange.baseMipLevel = 0;
    vi.subresourceRange.levelCount = mipLevels;
    vi.subresourceRange.baseArrayLayer = 0;
    vi.subresourceRange.layerCount = 1;
    if (vkCreateImageView(eng->device, &vi, NULL, view) != VK_SUCCESS) return 0;
    return 1;
}

static void release_texture_staging(VulkanEngine *eng, VkBuffer staging, int usingPool,
                                    VulkanSuballocation stagingSub, VkDeviceSize allocSize,
                                    VkDeviceMemory stagingMem) {
    if (staging != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, staging, NULL);
    }
    if (usingPool) {
        vulkan_memory_pool_free_suballocation(&eng->hostVisiblePool, stagingSub, allocSize);
    } else if (stagingMem != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, stagingMem, NULL);
    }
}

/* Mapea temporalmente un rango de memoria Vulkan y copia los datos de origen. */
static int copy_to_device_memory(VkDevice device, VkDeviceMemory mem, VkDeviceSize offset,
                                 const void *src, VkDeviceSize size) {
    void *mappedPtr = NULL;
    if (vkMapMemory(device, mem, offset, size, 0, &mappedPtr) != VK_SUCCESS) {
        return 0;
    }
    memcpy(mappedPtr, src, size);
    vkUnmapMemory(device, mem);
    return 1;
}

/* Crea un staging buffer (desde hostVisiblePool o asignacion directa) y copia la textura. */
static int create_staging_buffer_and_upload(VulkanEngine *eng, const unsigned char *data, VkDeviceSize imageSize,
                                            VkBuffer *outStaging, int *outUsingPool, VulkanSuballocation *outSub,
                                            VkDeviceSize *outAllocSize, VkDeviceMemory *outMem) {
    VkBufferCreateInfo bi = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = imageSize,
        .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE
    };
    VkBuffer staging = VK_NULL_HANDLE;
    if (vkCreateBuffer(eng->device, &bi, NULL, &staging) != VK_SUCCESS) return 0;

    VkMemoryRequirements memReqs;
    vkGetBufferMemoryRequirements(eng->device, staging, &memReqs);
    *outStaging = staging;
    *outAllocSize = memReqs.size;
    *outUsingPool = 0;
    *outMem = VK_NULL_HANDLE;

    if (eng->hostVisiblePool.device != VK_NULL_HANDLE &&
        vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, staging, outSub)) {
        *outUsingPool = 1;
        if (outSub->mappedPtr != NULL) {
            memcpy(outSub->mappedPtr, data, imageSize);
            return 1;
        }
        if (!copy_to_device_memory(eng->device, outSub->memory, outSub->offset, data, imageSize)) {
            release_texture_staging(eng, staging, *outUsingPool, *outSub, memReqs.size, *outMem);
            return 0;
        }
        return 1;
    }

    uint32_t memType = find_memory_type(eng->physicalDevice, memReqs.memoryTypeBits,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (memType == UINT32_MAX) {
        vkDestroyBuffer(eng->device, staging, NULL);
        return 0;
    }

    VkMemoryAllocateInfo allocInfo = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = memReqs.size,
        .memoryTypeIndex = memType
    };
    if (vkAllocateMemory(eng->device, &allocInfo, NULL, outMem) != VK_SUCCESS) {
        vkDestroyBuffer(eng->device, staging, NULL);
        return 0;
    }
    if (vkBindBufferMemory(eng->device, staging, *outMem, 0) != VK_SUCCESS ||
        !copy_to_device_memory(eng->device, *outMem, 0, data, imageSize)) {
        release_texture_staging(eng, staging, *outUsingPool, *outSub, memReqs.size, *outMem);
        return 0;
    }
    return 1;
}

/* Inserta una barrera de layout sobre un rango contiguo de niveles mip. */
static void transition_image_mip_range(VkCommandBuffer cb, VkImage image,
                                       uint32_t baseMip, uint32_t levelCount,
                                       VkImageLayout oldLayout, VkImageLayout newLayout,
                                       VkAccessFlags srcAccess, VkAccessFlags dstAccess,
                                       VkPipelineStageFlags srcStage, VkPipelineStageFlags dstStage) {
    VkImageMemoryBarrier bar = {0};
    bar.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    bar.oldLayout = oldLayout;
    bar.newLayout = newLayout;
    bar.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    bar.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    bar.image = image;
    bar.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    bar.subresourceRange.baseMipLevel = baseMip;
    bar.subresourceRange.levelCount = levelCount;
    bar.subresourceRange.baseArrayLayer = 0;
    bar.subresourceRange.layerCount = 1;
    bar.srcAccessMask = srcAccess;
    bar.dstAccessMask = dstAccess;
    vkCmdPipelineBarrier(cb, srcStage, dstStage, 0, 0, NULL, 0, NULL, 1, &bar);
}

/* Sube nivel 0 desde staging y genera mipmaps por blit si el formato lo soporta. */
static void record_mipmap_chain(VkCommandBuffer cb, VkBuffer staging, VkImage dstImage,
                                uint32_t w, uint32_t h, uint32_t mipLevels,
                                VkFilter blitFilter, int canBlit) {
    // 1. Transición de toda la imagen a TRANSFER_DST_OPTIMAL
    transition_image_mip_range(cb, dstImage, 0, mipLevels,
                               VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                               0, VK_ACCESS_TRANSFER_WRITE_BIT,
                               VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);

    // 2. Copia de buffer staging a mip level 0
    copy_buf_to_img(cb, staging, dstImage, w, h);

    // Si no hay soporte hardware de blit (SRC/DST) o solo existe mip 0, evitar vkCmdBlitImage
    if (!canBlit || mipLevels <= 1) {
        transition_image_mip_range(cb, dstImage, 0, mipLevels,
                                   VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                                   VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT,
                                   VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
        return;
    }

    // 3. Generación incremental de la cadena de mipmaps vía vkCmdBlitImage
    int32_t mipWidth = (int32_t)w;
    int32_t mipHeight = (int32_t)h;

    for (uint32_t i = 1; i < mipLevels; i++) {
        // Transición de mipLevel i - 1 a TRANSFER_SRC_OPTIMAL
        transition_image_mip_range(cb, dstImage, i - 1, 1,
                                   VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                                   VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT,
                                   VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);

        // Blit de i - 1 a i
        VkImageBlit blit = {0};
        blit.srcOffsets[0] = (VkOffset3D){ 0, 0, 0 };
        blit.srcOffsets[1] = (VkOffset3D){ mipWidth, mipHeight, 1 };
        blit.srcSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        blit.srcSubresource.mipLevel = i - 1;
        blit.srcSubresource.baseArrayLayer = 0;
        blit.srcSubresource.layerCount = 1;

        blit.dstOffsets[0] = (VkOffset3D){ 0, 0, 0 };
        blit.dstOffsets[1] = (VkOffset3D){
            mipWidth > 1 ? mipWidth / 2 : 1,
            mipHeight > 1 ? mipHeight / 2 : 1,
            1
        };
        blit.dstSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        blit.dstSubresource.mipLevel = i;
        blit.dstSubresource.baseArrayLayer = 0;
        blit.dstSubresource.layerCount = 1;

        vkCmdBlitImage(cb,
            dstImage, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
            dstImage, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            1, &blit,
            blitFilter);

        // Transición de mipLevel i - 1 a SHADER_READ_ONLY_OPTIMAL
        transition_image_mip_range(cb, dstImage, i - 1, 1,
                                   VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                                   VK_ACCESS_TRANSFER_READ_BIT, VK_ACCESS_SHADER_READ_BIT,
                                   VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);

        if (mipWidth > 1) mipWidth /= 2;
        if (mipHeight > 1) mipHeight /= 2;
    }

    // Transición del último nivel mip a SHADER_READ_ONLY_OPTIMAL
    transition_image_mip_range(cb, dstImage, mipLevels - 1, 1,
                               VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                               VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT,
                               VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
}

static int upload_texture_data_with_mipmaps(VulkanEngine *eng, unsigned char* data, uint32_t w, uint32_t h,
                                            uint32_t mipLevels, VkImage dstImage, VkFormat fmt) {
    if (!data || w == 0 || h == 0 || mipLevels == 0) return 0;

    VkDeviceSize imageSize = (VkDeviceSize)w * h * 4;
    VkBuffer staging = VK_NULL_HANDLE;
    VulkanSuballocation stagingSub = {0};
    VkDeviceMemory stagingMem = VK_NULL_HANDLE;
    VkDeviceSize allocSize = 0;
    int usingPool = 0;

    if (!create_staging_buffer_and_upload(eng, data, imageSize, &staging, &usingPool,
                                          &stagingSub, &allocSize, &stagingMem)) {
        return 0;
    }

    // Verificar soporte de blit (SRC/DST) y filtrado lineal en optimalTilingFeatures
    VkFormatProperties formatProperties;
    vkGetPhysicalDeviceFormatProperties(eng->physicalDevice, fmt, &formatProperties);
    VkFormatFeatureFlags blitReq = VK_FORMAT_FEATURE_BLIT_SRC_BIT | VK_FORMAT_FEATURE_BLIT_DST_BIT;
    int canBlit = (formatProperties.optimalTilingFeatures & blitReq) == blitReq;
    VkFilter blitFilter = (formatProperties.optimalTilingFeatures & VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT)
                          ? VK_FILTER_LINEAR : VK_FILTER_NEAREST;

    VkCommandBufferAllocateInfo cai = {0};
    cai.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    cai.commandPool = eng->commandPool;
    cai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    cai.commandBufferCount = 1;
    VkCommandBuffer cb = VK_NULL_HANDLE;
    if (vkAllocateCommandBuffers(eng->device, &cai, &cb) != VK_SUCCESS) {
        release_texture_staging(eng, staging, usingPool, stagingSub, allocSize, stagingMem);
        return 0;
    }

    VkCommandBufferBeginInfo bbi = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
    };
    vkBeginCommandBuffer(cb, &bbi);
    record_mipmap_chain(cb, staging, dstImage, w, h, mipLevels, blitFilter, canBlit);
    vkEndCommandBuffer(cb);

    VkSubmitInfo si = {0};
    si.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    si.commandBufferCount = 1;
    si.pCommandBuffers = &cb;
    VkResult submitRes = vkQueueSubmit(eng->graphicsQueue, 1, &si, VK_NULL_HANDLE);
    vkQueueWaitIdle(eng->graphicsQueue);
    vkFreeCommandBuffers(eng->device, eng->commandPool, 1, &cb);

    // Liberación INMEDIATA de memoria efímera de staging
    release_texture_staging(eng, staging, usingPool, stagingSub, allocSize, stagingMem);
    return submitRes == VK_SUCCESS;
}

static unsigned char* generate_facade_texture(int *outW, int *outH){
    int W=256,H=256; unsigned char* data=malloc(W*H*4);
    for(int y=0;y<H;y++){ for(int x=0;x<W;x++){
        int brickW=32, brickH=16;
        int by=y/brickH, bx=x/brickW;
        int mortar = (y%brickH<2) || (x%brickW<2 && (by%2==0 || x%brickW>=16));
        unsigned char r,g,b;
        if(mortar){ r=180; g=180; b=175; }
        else {
            int var = (bx*17 + by*31) % 20;
            if((bx+by)%2==0){ r=190+var; g=165+var/2; b=140+var/2; }
            else { r=185+var; g=150+var/2; b=120+var/2; }
        }
        int idx=(y*W+x)*4; data[idx]=r; data[idx+1]=g; data[idx+2]=b; data[idx+3]=255;
    }} *outW=W; *outH=H; return data;
}

/* Copia un cuadrante RGBA (qw x qh) en la posicion (dstX, dstY) del mosaico combinado. */
static void copy_quadrant_rgba(unsigned char *dst, int totalW, int dstX, int dstY,
                               const unsigned char *src, int qw, int qh) {
    for (int y = 0; y < qh; y++) {
        memcpy(dst + ((size_t)(dstY + y) * (size_t)totalW + (size_t)dstX) * 4,
               src + (size_t)y * (size_t)qw * 4,
               (size_t)qw * 4);
    }
}

/* Busca el directorio (assets/ o ../assets/) que contenga los 4 cuadrantes satelitales. */
static int find_quadrant_paths(const char *paths[2][2]) {
    static const char *primary[2][2] = {
        {"assets/satellite_0_0.png", "assets/satellite_1_0.png"},
        {"assets/satellite_0_1.png", "assets/satellite_1_1.png"}
    };
    static const char *fallback[2][2] = {
        {"../assets/satellite_0_0.png", "../assets/satellite_1_0.png"},
        {"../assets/satellite_0_1.png", "../assets/satellite_1_1.png"}
    };
    const char *(*candidates[2])[2] = { primary, fallback };

    for (int k = 0; k < 2; k++) {
        int foundAll = 1;
        for (int r = 0; r < 2 && foundAll; r++) {
            for (int c = 0; c < 2; c++) {
                if (access(candidates[k][r][c], F_OK) != 0) {
                    foundAll = 0;
                    break;
                }
            }
        }
        if (foundAll) {
            for (int r = 0; r < 2; r++) {
                for (int c = 0; c < 2; c++) {
                    paths[r][c] = candidates[k][r][c];
                }
            }
            return 1;
        }
    }
    return 0;
}

/* Carga un cuadrante secundario en (qw2, qh2) y solo lo copia si coincide con q0w x q0h. */
static void load_matching_quadrant(unsigned char *combined, int totalW, const char *path,
                                   int dstX, int dstY, int q0w, int q0h) {
    int qw2 = 0, qh2 = 0, ch = 0;
    unsigned char *tile = stbi_load(path, &qw2, &qh2, &ch, 4);
    if (!tile) return;

    if (qw2 == q0w && qh2 == q0h) {
        copy_quadrant_rgba(combined, totalW, dstX, dstY, tile, q0w, q0h);
    } else {
        fprintf(stderr, "[Textura] AVISO: Cuadrante %s (%dx%d) difiere de q00 (%dx%d), omitido\n",
                path, qw2, qh2, q0w, q0h);
    }
    stbi_image_free(tile);
}

static unsigned char* load_quadrant_satellite(int *outW, int *outH) {
    const char *paths[2][2] = {{NULL, NULL}, {NULL, NULL}};
    if (!find_quadrant_paths(paths)) {
        return NULL;
    }

    printf("[Textura] Ensamblando ortofoto satelital desde 4 cuadrantes modulares (<45MB)...\n");

    int qw = 0, qh = 0, ch = 0;
    unsigned char *q00 = stbi_load(paths[0][0], &qw, &qh, &ch, 4);
    if (!q00) return NULL;
    if (qw <= 0 || qh <= 0 || qw > INT_MAX / 2 || qh > INT_MAX / 2) {
        stbi_image_free(q00);
        return NULL;
    }

    // Fijar dimensiones de referencia desde q00 para prevenir desbordamientos en el mosaico
    const int q0w = qw;
    const int q0h = qh;
    const int totalW = q0w * 2;
    const int totalH = q0h * 2;
    const size_t totalBytes = (size_t)totalW * (size_t)totalH * 4;
    unsigned char *combined = (unsigned char*)calloc(totalBytes, 1);
    if (!combined) {
        stbi_image_free(q00);
        return NULL;
    }

    // Cuadrante 0,0: Noroeste (col 0, row 0)
    copy_quadrant_rgba(combined, totalW, 0, 0, q00, q0w, q0h);
    stbi_image_free(q00);

    // Cuadrantes q10 (Noreste), q01 (Suroeste), q11 (Sureste)
    const struct { int r; int c; int dstX; int dstY; } tiles[3] = {
        {0, 1, q0w, 0},
        {1, 0, 0,   q0h},
        {1, 1, q0w, q0h}
    };
    for (int i = 0; i < 3; i++) {
        load_matching_quadrant(combined, totalW, paths[tiles[i].r][tiles[i].c],
                               tiles[i].dstX, tiles[i].dstY, q0w, q0h);
    }

    *outW = totalW;
    *outH = totalH;
    return combined;
}

/* Genera una textura RGBA 4x4 en memoria (tono neutro terreno/concreto) cuando faltan assets. */
static unsigned char* create_fallback_satellite_4x4(int *outW, int *outH) {
    const int W = 4;
    const int H = 4;
    unsigned char *data = (unsigned char*)malloc((size_t)W * (size_t)H * 4);
    if (!data) return NULL;
    for (int i = 0; i < W * H; i++) {
        data[i * 4 + 0] = 120;
        data[i * 4 + 1] = 125;
        data[i * 4 + 2] = 115;
        data[i * 4 + 3] = 255;
    }
    *outW = W;
    *outH = H;
    return data;
}

/* Carga la textura satelital desde cuadrantes, ruta indicada, fallbacks o buffer 4x4 en memoria. */
static unsigned char* load_satellite_pixels(const char *texturePath, int *outW, int *outH,
                                            int *outIsAllocated, const char **outSourceLabel) {
    int channels = 4;
    *outIsAllocated = 0;

    // 1. Intentar cargar desde los 4 cuadrantes modulares (< 45 MB c/u)
    unsigned char *data = load_quadrant_satellite(outW, outH);
    if (data) {
        *outIsAllocated = 1;
        *outSourceLabel = "assets/satellite_X_Y.png (4 cuadrantes)";
        return data;
    }

    // 2. Fallback al archivo monolítico si existe
    if (texturePath && access(texturePath, F_OK) == 0) {
        data = stbi_load(texturePath, outW, outH, &channels, 4);
        if (data) {
            *outSourceLabel = texturePath;
            return data;
        }
    }

    const char* altPaths[] = {"assets/satellite.png", "models/satellite.png", "../assets/satellite.png", "satellite.png", NULL};
    for (int pi = 0; altPaths[pi]; pi++) {
        data = stbi_load(altPaths[pi], outW, outH, &channels, 4);
        if (data) {
            printf("[Textura] Cargada desde fallback %s\n", altPaths[pi]);
            *outSourceLabel = altPaths[pi];
            return data;
        }
    }

    // 3. Fallback garantizado en memoria para no dejar descriptores ni LightingUBO sin inicializar
    fprintf(stderr,
            "[Textura] AVISO: No se pudo cargar textura satelital ni sus cuadrantes (%s), usando textura fallback 4x4\n",
            texturePath ? texturePath : "");
    data = create_fallback_satellite_4x4(outW, outH);
    if (!data) return NULL;
    *outIsAllocated = 1;
    *outSourceLabel = "fallback 4x4 en memoria";
    return data;
}

/* Carga el atlas de fachadas desde disco o genera el patron procedural de respaldo. */
static unsigned char* load_facade_pixels(int *outW, int *outH, int *outIsAtlasLoaded) {
    int fch = 0;
    unsigned char *fdata = stbi_load("models/texture_atlas_16x16.png", outW, outH, &fch, 4);
    if (!fdata) {
        fdata = stbi_load("assets/texture_atlas_16x16.png", outW, outH, &fch, 4);
    }
    if (fdata) {
        *outIsAtlasLoaded = 1;
        printf("[Textura] Atlas pixel-art cargado: %dx%d (%d canales)\n", *outW, *outH, fch);
        return fdata;
    }
    *outIsAtlasLoaded = 0;
    fdata = generate_facade_texture(outW, outH);
    printf("[Textura] Fachada procedural fallback %dx%d\n", *outW, *outH);
    return fdata;
}

/* Crea una VkImage en VRAM, sube sus pixeles con mipmaps, libera CPU RAM y crea su VkImageView. */
static int upload_image_and_view(VulkanEngine *eng, unsigned char *pixels, int isStbi,
                                 uint32_t w, uint32_t h, uint32_t mipLevels,
                                 VkFormat fmt, VkImageUsageFlags usage,
                                 VkImage *outImage, VkImageView *outView) {
    int uploaded = 0;
    if (create_gpu_image(eng, outImage, w, h, mipLevels, fmt, VK_IMAGE_TILING_OPTIMAL, usage) == VK_SUCCESS) {
        uploaded = upload_texture_data_with_mipmaps(eng, pixels, w, h, mipLevels, *outImage, fmt);
    }
    if (isStbi) {
        stbi_image_free(pixels);
    } else {
        free(pixels);
    }
    if (!uploaded) return 0;
    return create_image_view(eng, *outImage, outView, fmt, mipLevels);
}

/* Sube y crea la vista para la foto georeferenciada (binding 3 — photoTex), o fallback 1x1 blanco. */
static int init_photo_texture(VulkanEngine *eng, VkFormat fmt, VkImageUsageFlags imgUsage, int canBlit) {
    const char* genDir = "models/generated";
    unsigned char* pdata = NULL;
    int pw = 1, ph = 1;
    int isPhotoFromStbi = 0;
    DIR* gd = opendir(genDir);
    if (gd) {
        struct dirent* de;
        while ((de = readdir(gd)) != NULL) {
            size_t nl = strlen(de->d_name);
            if (nl < 5 || strncmp(de->d_name, "photo_", 6) != 0) continue;
            const char* ext = de->d_name + nl - 4;
            if (strcmp(ext, ".jpg") != 0 && strcmp(ext, ".png") != 0) continue;
            char fullPath[512];
            snprintf(fullPath, sizeof(fullPath), "%s/%s", genDir, de->d_name);
            int pc;
            pdata = stbi_load(fullPath, &pw, &ph, &pc, 4);
            if (pdata) {
                isPhotoFromStbi = 1;
                printf("[Textura] Foto georeferenciada cargada: %s (%dx%d)\n", fullPath, pw, ph);
                break;
            }
        }
        closedir(gd);
    }
    if (!pdata) {
        // Fallback: textura blanca 1×1 (el plano no se ve pero el binding es válido)
        pw = 1; ph = 1;
        pdata = (unsigned char*)calloc(4, 1);
        if (!pdata) return 0;
        pdata[0] = pdata[1] = pdata[2] = pdata[3] = 255;
        printf("[Textura] Sin foto georeferenciada — usando textura blanca de fallback para binding 3\n");
    }

    uint32_t phMipLevels = canBlit ? calculate_mip_levels((uint32_t)pw, (uint32_t)ph) : 1;
    // La vista de foto puede fallar sin abortar el motor; binding 3 hace fallback a facadeImageView
    (void)upload_image_and_view(eng, pdata, isPhotoFromStbi, (uint32_t)pw, (uint32_t)ph,
                                phMipLevels, fmt, imgUsage, &eng->photoImage, &eng->photoImageView);
    return 1;
}

/* Crea el sampler principal validando soporte y limite fisico de anisotropia. */
static int create_texture_sampler(VulkanEngine *eng, uint32_t maxMipLevels) {
    VkPhysicalDeviceFeatures features = {0};
    vkGetPhysicalDeviceFeatures(eng->physicalDevice, &features);
    VkPhysicalDeviceProperties props = {0};
    vkGetPhysicalDeviceProperties(eng->physicalDevice, &props);

    VkSamplerCreateInfo samplerInfo = {0};
    samplerInfo.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO;
    samplerInfo.magFilter = VK_FILTER_LINEAR;
    samplerInfo.minFilter = VK_FILTER_LINEAR;
    samplerInfo.addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;   // CLAMP para fotos (no repetir)
    samplerInfo.addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    samplerInfo.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    if (features.samplerAnisotropy == VK_TRUE) {
        samplerInfo.anisotropyEnable = VK_TRUE;
        samplerInfo.maxAnisotropy = fminf(8.0f, props.limits.maxSamplerAnisotropy);
    } else {
        samplerInfo.anisotropyEnable = VK_FALSE;
        samplerInfo.maxAnisotropy = 1.0f;
    }
    samplerInfo.borderColor = VK_BORDER_COLOR_INT_OPAQUE_BLACK;
    samplerInfo.unnormalizedCoordinates = VK_FALSE;
    samplerInfo.compareEnable = VK_FALSE;
    samplerInfo.mipmapMode = VK_SAMPLER_MIPMAP_MODE_LINEAR;
    samplerInfo.minLod = 0.0f;
    samplerInfo.maxLod = (float)maxMipLevels;
    samplerInfo.mipLodBias = 0.0f;
    return vkCreateSampler(eng->device, &samplerInfo, NULL, &eng->textureSampler) == VK_SUCCESS;
}

/* Crea los buffers LightingUBO, el descriptorPool y actualiza los descriptorSets por frame. */
static int create_lighting_buffers_and_descriptors(VulkanEngine *eng) {
    /* Crear buffers UBO de iluminación dinámica (uno por frame in flight) en hostVisiblePool */
    VkBufferCreateInfo uboInfo = {0};
    uboInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    uboInfo.size = sizeof(LightingUBO);
    uboInfo.usage = VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT;
    uboInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; ++i) {
        if (vkCreateBuffer(eng->device, &uboInfo, NULL, &eng->lightingBuffers[i]) != VK_SUCCESS) return 0;
        VulkanSuballocation uboSub;
        if (!vulkan_memory_pool_bind_buffer(&eng->hostVisiblePool, eng->lightingBuffers[i], &uboSub)) return 0;
        eng->lightingUboMapped[i] = (LightingUBO*)uboSub.mappedPtr;
        if (eng->lightingUboMapped[i]) {
            memset(eng->lightingUboMapped[i], 0, sizeof(LightingUBO));
        }
    }

    // Pool expandido: 3 samplers de imagen + 1 UBO por frame in flight
    VkDescriptorPoolSize poolSizes[2] = {
        {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 3 * MAX_FRAMES_IN_FLIGHT},
        {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1 * MAX_FRAMES_IN_FLIGHT}
    };
    VkDescriptorPoolCreateInfo poolInfo = {0};
    poolInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
    poolInfo.poolSizeCount = 2;
    poolInfo.pPoolSizes = poolSizes;
    poolInfo.maxSets = MAX_FRAMES_IN_FLIGHT;
    if (vkCreateDescriptorPool(eng->device, &poolInfo, NULL, &eng->descriptorPool) != VK_SUCCESS) return 0;

    VkDescriptorImageInfo imgInfo0 = {
        .sampler = eng->textureSampler,
        .imageView = eng->textureImageView,
        .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
    };
    VkDescriptorImageInfo imgInfo1 = {
        .sampler = eng->textureSampler,
        .imageView = eng->facadeImageView,
        .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
    };
    VkDescriptorImageInfo imgInfo3 = {
        .sampler = eng->textureSampler,
        .imageView = eng->photoImageView != VK_NULL_HANDLE
                        ? eng->photoImageView
                        : eng->facadeImageView,   // fallback si no hay foto
        .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
    };

    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; ++i) {
        VkDescriptorSetAllocateInfo allocInfoDS = {0};
        allocInfoDS.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        allocInfoDS.descriptorPool = eng->descriptorPool;
        allocInfoDS.descriptorSetCount = 1;
        allocInfoDS.pSetLayouts = &eng->descriptorSetLayout;
        if (vkAllocateDescriptorSets(eng->device, &allocInfoDS, &eng->descriptorSets[i]) != VK_SUCCESS) return 0;

        VkDescriptorBufferInfo bufInfo = {
            .buffer = eng->lightingBuffers[i],
            .offset = 0,
            .range = sizeof(LightingUBO)
        };

        VkWriteDescriptorSet writes[4] = {0};
        writes[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[0].dstSet = eng->descriptorSets[i];
        writes[0].dstBinding = 0;
        writes[0].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        writes[0].descriptorCount = 1;
        writes[0].pImageInfo = &imgInfo0;

        writes[1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[1].dstSet = eng->descriptorSets[i];
        writes[1].dstBinding = 1;
        writes[1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        writes[1].descriptorCount = 1;
        writes[1].pImageInfo = &imgInfo1;

        writes[2].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[2].dstSet = eng->descriptorSets[i];
        writes[2].dstBinding = 2;
        writes[2].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        writes[2].descriptorCount = 1;
        writes[2].pBufferInfo = &bufInfo;

        writes[3].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[3].dstSet = eng->descriptorSets[i];
        writes[3].dstBinding = 3;
        writes[3].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        writes[3].descriptorCount = 1;
        writes[3].pImageInfo = &imgInfo3;

        vkUpdateDescriptorSets(eng->device, 4, writes, 0, NULL);
    }
    return 1;
}

/* Inicializa texturas satelital/fachadas/foto, sampler y descriptores por frame. */
int init_satellite_texture(VulkanEngine *eng, const char* texturePath){
    int width = 0, height = 0;
    stbi_set_flip_vertically_on_load(0);
    int isDataAllocated = 0;
    const char *sourceLabel = NULL;
    unsigned char *data = load_satellite_pixels(texturePath, &width, &height, &isDataAllocated, &sourceLabel);
    if (!data) {
        return 0;
    }

    eng->textureWidth = (uint32_t)width;
    eng->textureHeight = (uint32_t)height;

    VkFormat fmt = VK_FORMAT_R8G8B8A8_SRGB;
    int canBlit = format_supports_mipmap_blit(eng->physicalDevice, fmt);
    if (!canBlit) {
        fprintf(stderr, "[Textura] AVISO: Hardware sin soporte BLIT_SRC/DST para formato %d, usando mipLevels = 1\n",
                (int)fmt);
    }

    uint32_t satMipLevels = canBlit ? calculate_mip_levels((uint32_t)width, (uint32_t)height) : 1;
    printf("[Textura] Satelital %dx%d (%u niveles de mipmap) desde %s (VRAM Pool)\n",
           width, height, satMipLevels, sourceLabel);

    VkImageUsageFlags imgUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT |
                                 VK_IMAGE_USAGE_SAMPLED_BIT |
                                 (canBlit ? VK_IMAGE_USAGE_TRANSFER_SRC_BIT : 0);

    if (!upload_image_and_view(eng, data, !isDataAllocated, (uint32_t)width, (uint32_t)height,
                               satMipLevels, fmt, imgUsage, &eng->textureImage, &eng->textureImageView)) {
        return 0;
    }

    int fw = 0, fh = 0, isAtlasLoaded = 0;
    unsigned char *fdata = load_facade_pixels(&fw, &fh, &isAtlasLoaded);
    if (!fdata) return 0;

    uint32_t facMipLevels = canBlit ? calculate_mip_levels((uint32_t)fw, (uint32_t)fh) : 1;
    printf("[Textura] Atlas/Fachadas %dx%d (%u niveles de mipmap)\n", fw, fh, facMipLevels);

    if (!upload_image_and_view(eng, fdata, isAtlasLoaded, (uint32_t)fw, (uint32_t)fh,
                               facMipLevels, fmt, imgUsage, &eng->facadeImage, &eng->facadeImageView)) {
        return 0;
    }

    // ── Cargar foto georeferenciada (binding 3 — photoTex) ──────────────────
    if (!init_photo_texture(eng, fmt, imgUsage, canBlit)) return 0;

    uint32_t maxMipLevels = (satMipLevels > facMipLevels) ? satMipLevels : facMipLevels;
    if (!create_texture_sampler(eng, maxMipLevels)) return 0;
    if (!create_lighting_buffers_and_descriptors(eng)) return 0;

    printf("[Textura] DescriptorSets (%d frames in flight): sat+facade+UBO+foto listos\n",
           MAX_FRAMES_IN_FLIGHT);
    return 1;
}

void cleanup_texture_resources(VulkanEngine *eng) {
    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; ++i) {
        eng->lightingUboMapped[i] = NULL;
        if (eng->lightingBuffers[i] != VK_NULL_HANDLE) {
            vkDestroyBuffer(eng->device, eng->lightingBuffers[i], NULL);
            eng->lightingBuffers[i] = VK_NULL_HANDLE;
        }
    }
    if (eng->descriptorPool != VK_NULL_HANDLE) {
        vkDestroyDescriptorPool(eng->device, eng->descriptorPool, NULL);
        eng->descriptorPool = VK_NULL_HANDLE;
    }
    if (eng->textureSampler != VK_NULL_HANDLE) {
        vkDestroySampler(eng->device, eng->textureSampler, NULL);
        eng->textureSampler = VK_NULL_HANDLE;
    }
    if (eng->textureImageView != VK_NULL_HANDLE) {
        vkDestroyImageView(eng->device, eng->textureImageView, NULL);
        eng->textureImageView = VK_NULL_HANDLE;
    }
    if (eng->facadeImageView != VK_NULL_HANDLE) {
        vkDestroyImageView(eng->device, eng->facadeImageView, NULL);
        eng->facadeImageView = VK_NULL_HANDLE;
    }
    if (eng->photoImageView != VK_NULL_HANDLE) {
        vkDestroyImageView(eng->device, eng->photoImageView, NULL);
        eng->photoImageView = VK_NULL_HANDLE;
    }
    if (eng->textureImage != VK_NULL_HANDLE) {
        vkDestroyImage(eng->device, eng->textureImage, NULL);
        eng->textureImage = VK_NULL_HANDLE;
    }
    if (eng->facadeImage != VK_NULL_HANDLE) {
        vkDestroyImage(eng->device, eng->facadeImage, NULL);
        eng->facadeImage = VK_NULL_HANDLE;
    }
    if (eng->photoImage != VK_NULL_HANDLE) {
        vkDestroyImage(eng->device, eng->photoImage, NULL);
        eng->photoImage = VK_NULL_HANDLE;
    }
}

