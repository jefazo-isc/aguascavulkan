#include "vulkan_swapchain.h"
#include "vulkan_pipeline.h"
#include <SDL2/SDL_vulkan.h>
#include <stdio.h>
#include <stdlib.h>

uint32_t find_memory_type(VkPhysicalDevice physicalDevice, uint32_t typeFilter, VkMemoryPropertyFlags properties) {
    VkPhysicalDeviceMemoryProperties memProperties;
    vkGetPhysicalDeviceMemoryProperties(physicalDevice, &memProperties);

    for (uint32_t i = 0; i < memProperties.memoryTypeCount; i++) {
        if ((typeFilter & (1 << i)) &&
            (memProperties.memoryTypes[i].propertyFlags & properties) == properties) {
            return i;
        }
    }
    return UINT32_MAX;
}

static VkFormat findSupportedDepthFormat(VkPhysicalDevice physicalDevice) {
    VkFormat candidates[] = {
        VK_FORMAT_D32_SFLOAT,
        VK_FORMAT_D32_SFLOAT_S8_UINT,
        VK_FORMAT_D24_UNORM_S8_UINT
    };
    for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); i++) {
        VkFormatProperties props;
        vkGetPhysicalDeviceFormatProperties(physicalDevice, candidates[i], &props);
        if ((props.optimalTilingFeatures & VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT) ==
            VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT) {
            return candidates[i];
        }
    }
    return VK_FORMAT_UNDEFINED;
}

static int create_depth_resources(VulkanEngine *eng) {
    eng->depthFormat = findSupportedDepthFormat(eng->physicalDevice);
    if (eng->depthFormat == VK_FORMAT_UNDEFINED) {
        fprintf(stderr, "No se encontró un formato de profundidad soportado\n");
        return 0;
    }

    VkImageCreateInfo imageInfo = {0};
    imageInfo.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    imageInfo.imageType = VK_IMAGE_TYPE_2D;
    imageInfo.extent.width = eng->swapchainExtent.width;
    imageInfo.extent.height = eng->swapchainExtent.height;
    imageInfo.extent.depth = 1;
    imageInfo.mipLevels = 1;
    imageInfo.arrayLayers = 1;
    imageInfo.format = eng->depthFormat;
    imageInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
    imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    imageInfo.usage = VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT;
    imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
    imageInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    if (vkCreateImage(eng->device, &imageInfo, NULL, &eng->depthImage) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al crear imagen de profundidad\n");
        return 0;
    }

    VkMemoryRequirements memReqs;
    vkGetImageMemoryRequirements(eng->device, eng->depthImage, &memReqs);

    uint32_t memType = find_memory_type(eng->physicalDevice, memReqs.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (memType == UINT32_MAX) {
        fprintf(stderr, "Tipo de memoria incompatible para profundidad\n");
        return 0;
    }

    VkMemoryAllocateInfo allocInfo = {0};
    allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocInfo.allocationSize = memReqs.size;
    allocInfo.memoryTypeIndex = memType;

    if (vkAllocateMemory(eng->device, &allocInfo, NULL, &eng->depthImageMemory) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al asignar memoria de profundidad\n");
        return 0;
    }
    vkBindImageMemory(eng->device, eng->depthImage, eng->depthImageMemory, 0);

    VkImageViewCreateInfo viewInfo = {0};
    viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
    viewInfo.image = eng->depthImage;
    viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
    viewInfo.format = eng->depthFormat;
    viewInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
    viewInfo.subresourceRange.baseMipLevel = 0;
    viewInfo.subresourceRange.levelCount = 1;
    viewInfo.subresourceRange.baseArrayLayer = 0;
    viewInfo.subresourceRange.layerCount = 1;

    if (vkCreateImageView(eng->device, &viewInfo, NULL, &eng->depthImageView) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al crear ImageView de profundidad\n");
        return 0;
    }

    return 1;
}

int create_swapchain_and_depth(VulkanEngine *eng) {
    uint32_t formatCount = 0;
    vkGetPhysicalDeviceSurfaceFormatsKHR(eng->physicalDevice, eng->surface, &formatCount, NULL);
    VkSurfaceFormatKHR surfaceFormat = { VK_FORMAT_B8G8R8A8_SRGB, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR };
    if (formatCount > 0) {
        VkSurfaceFormatKHR *formats = malloc(sizeof(VkSurfaceFormatKHR) * formatCount);
        vkGetPhysicalDeviceSurfaceFormatsKHR(eng->physicalDevice, eng->surface, &formatCount, formats);
        surfaceFormat = formats[0];
        for (uint32_t i = 0; i < formatCount; i++) {
            if (formats[i].format == VK_FORMAT_B8G8R8A8_SRGB &&
                formats[i].colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) {
                surfaceFormat = formats[i];
                break;
            }
        }
        free(formats);
    }
    eng->swapchainImageFormat = surfaceFormat.format;

    VkSurfaceCapabilitiesKHR surfCaps;
    vkGetPhysicalDeviceSurfaceCapabilitiesKHR(eng->physicalDevice, eng->surface, &surfCaps);
    eng->swapchainExtent = surfCaps.currentExtent;
    eng->imageCount = surfCaps.minImageCount + 1;
    if (surfCaps.maxImageCount > 0 && eng->imageCount > surfCaps.maxImageCount) {
        eng->imageCount = surfCaps.maxImageCount;
    }

    VkPresentModeKHR presentMode = VK_PRESENT_MODE_FIFO_KHR;

    VkSwapchainCreateInfoKHR swapchainCreateInfo = {0};
    swapchainCreateInfo.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
    swapchainCreateInfo.surface = eng->surface;
    swapchainCreateInfo.minImageCount = eng->imageCount;
    swapchainCreateInfo.imageFormat = eng->swapchainImageFormat;
    swapchainCreateInfo.imageColorSpace = surfaceFormat.colorSpace;
    swapchainCreateInfo.imageExtent = eng->swapchainExtent;
    swapchainCreateInfo.imageArrayLayers = 1;
    swapchainCreateInfo.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
    swapchainCreateInfo.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
    swapchainCreateInfo.preTransform = surfCaps.currentTransform;
    swapchainCreateInfo.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    swapchainCreateInfo.presentMode = presentMode;
    swapchainCreateInfo.clipped = VK_TRUE;

    if (vkCreateSwapchainKHR(eng->device, &swapchainCreateInfo, NULL, &eng->swapchain) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al crear Swapchain\n");
        return 0;
    }

    vkGetSwapchainImagesKHR(eng->device, eng->swapchain, &eng->imageCount, NULL);
    eng->swapchainImages = malloc(sizeof(VkImage) * eng->imageCount);
    vkGetSwapchainImagesKHR(eng->device, eng->swapchain, &eng->imageCount, eng->swapchainImages);

    eng->swapchainImageViews = malloc(sizeof(VkImageView) * eng->imageCount);
    for (uint32_t i = 0; i < eng->imageCount; i++) {
        VkImageViewCreateInfo viewInfo = {0};
        viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        viewInfo.image = eng->swapchainImages[i];
        viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
        viewInfo.format = eng->swapchainImageFormat;
        viewInfo.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        viewInfo.subresourceRange.baseMipLevel = 0;
        viewInfo.subresourceRange.levelCount = 1;
        viewInfo.subresourceRange.baseArrayLayer = 0;
        viewInfo.subresourceRange.layerCount = 1;
        if (vkCreateImageView(eng->device, &viewInfo, NULL, &eng->swapchainImageViews[i]) != VK_SUCCESS) {
            fprintf(stderr, "Error al crear ImageView de Swapchain %u\n", i);
            return 0;
        }
    }

    return create_depth_resources(eng);
}

int recreate_swapchain(VulkanEngine *eng) {
    int width = 0, height = 0;
    if (eng->window) {
        SDL_Vulkan_GetDrawableSize(eng->window, &width, &height);
        if (width == 0 || height == 0) {
            return 0; // Retornar de inmediato sin bloquear la cola de eventos de SDL
        }
    }

    vkDeviceWaitIdle(eng->device);

    // 1. Destruir framebuffers actuales
    destroy_framebuffers(eng);

    // 2. Destruir recursos de profundidad actuales
    if (eng->depthImageView != VK_NULL_HANDLE) {
        vkDestroyImageView(eng->device, eng->depthImageView, NULL);
        eng->depthImageView = VK_NULL_HANDLE;
    }
    if (eng->depthImage != VK_NULL_HANDLE) {
        vkDestroyImage(eng->device, eng->depthImage, NULL);
        eng->depthImage = VK_NULL_HANDLE;
    }
    if (eng->depthImageMemory != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, eng->depthImageMemory, NULL);
        eng->depthImageMemory = VK_NULL_HANDLE;
    }

    // 3. Guardar swapchain antiguo
    VkSwapchainKHR oldSwapchain = eng->swapchain;

    // 4. Destruir ImageViews del swapchain antiguo
    if (eng->swapchainImageViews) {
        for (uint32_t i = 0; i < eng->imageCount; i++) {
            if (eng->swapchainImageViews[i] != VK_NULL_HANDLE) {
                vkDestroyImageView(eng->device, eng->swapchainImageViews[i], NULL);
            }
        }
        free(eng->swapchainImageViews);
        eng->swapchainImageViews = NULL;
    }
    if (eng->swapchainImages) {
        free(eng->swapchainImages);
        eng->swapchainImages = NULL;
    }

    // 5. Consultar nuevas capacidades de la superficie
    VkSurfaceCapabilitiesKHR surfCaps;
    vkGetPhysicalDeviceSurfaceCapabilitiesKHR(eng->physicalDevice, eng->surface, &surfCaps);

    if (surfCaps.currentExtent.width != UINT32_MAX) {
        eng->swapchainExtent = surfCaps.currentExtent;
    } else {
        eng->swapchainExtent.width = (uint32_t)width;
        eng->swapchainExtent.height = (uint32_t)height;
        if (eng->swapchainExtent.width < surfCaps.minImageExtent.width)
            eng->swapchainExtent.width = surfCaps.minImageExtent.width;
        if (eng->swapchainExtent.width > surfCaps.maxImageExtent.width)
            eng->swapchainExtent.width = surfCaps.maxImageExtent.width;
        if (eng->swapchainExtent.height < surfCaps.minImageExtent.height)
            eng->swapchainExtent.height = surfCaps.minImageExtent.height;
        if (eng->swapchainExtent.height > surfCaps.maxImageExtent.height)
            eng->swapchainExtent.height = surfCaps.maxImageExtent.height;
    }

    eng->imageCount = surfCaps.minImageCount + 1;
    if (surfCaps.maxImageCount > 0 && eng->imageCount > surfCaps.maxImageCount) {
        eng->imageCount = surfCaps.maxImageCount;
    }

    // Consultar formato de superficie soportado (misma lógica que create_swapchain_and_depth)
    uint32_t formatCount = 0;
    vkGetPhysicalDeviceSurfaceFormatsKHR(eng->physicalDevice, eng->surface, &formatCount, NULL);
    VkSurfaceFormatKHR surfaceFormat = { VK_FORMAT_B8G8R8A8_SRGB, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR };
    if (formatCount > 0) {
        VkSurfaceFormatKHR *formats = malloc(sizeof(VkSurfaceFormatKHR) * formatCount);
        vkGetPhysicalDeviceSurfaceFormatsKHR(eng->physicalDevice, eng->surface, &formatCount, formats);
        surfaceFormat = formats[0];
        for (uint32_t i = 0; i < formatCount; i++) {
            if (formats[i].format == VK_FORMAT_B8G8R8A8_SRGB &&
                formats[i].colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) {
                surfaceFormat = formats[i];
                break;
            }
        }
        free(formats);
    }

    VkSwapchainCreateInfoKHR swapchainCreateInfo = {0};
    swapchainCreateInfo.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
    swapchainCreateInfo.surface = eng->surface;
    swapchainCreateInfo.minImageCount = eng->imageCount;
    swapchainCreateInfo.imageFormat = eng->swapchainImageFormat;
    swapchainCreateInfo.imageColorSpace = surfaceFormat.colorSpace;
    swapchainCreateInfo.imageExtent = eng->swapchainExtent;
    swapchainCreateInfo.imageArrayLayers = 1;
    swapchainCreateInfo.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
    swapchainCreateInfo.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
    swapchainCreateInfo.preTransform = surfCaps.currentTransform;
    swapchainCreateInfo.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    swapchainCreateInfo.presentMode = VK_PRESENT_MODE_FIFO_KHR;
    swapchainCreateInfo.clipped = VK_TRUE;
    swapchainCreateInfo.oldSwapchain = oldSwapchain;

    VkSwapchainKHR newSwapchain;
    if (vkCreateSwapchainKHR(eng->device, &swapchainCreateInfo, NULL, &newSwapchain) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al recrear Swapchain\n");
        return 0;
    }
    eng->swapchain = newSwapchain;

    // 6. Destruir swapchain antiguo
    if (oldSwapchain != VK_NULL_HANDLE) {
        vkDestroySwapchainKHR(eng->device, oldSwapchain, NULL);
    }

    // 7. Adquirir nuevas imágenes y crear ImageViews
    vkGetSwapchainImagesKHR(eng->device, eng->swapchain, &eng->imageCount, NULL);
    eng->swapchainImages = malloc(sizeof(VkImage) * eng->imageCount);
    vkGetSwapchainImagesKHR(eng->device, eng->swapchain, &eng->imageCount, eng->swapchainImages);

    eng->swapchainImageViews = malloc(sizeof(VkImageView) * eng->imageCount);
    for (uint32_t i = 0; i < eng->imageCount; i++) {
        VkImageViewCreateInfo viewInfo = {0};
        viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        viewInfo.image = eng->swapchainImages[i];
        viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
        viewInfo.format = eng->swapchainImageFormat;
        viewInfo.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        viewInfo.subresourceRange.baseMipLevel = 0;
        viewInfo.subresourceRange.levelCount = 1;
        viewInfo.subresourceRange.baseArrayLayer = 0;
        viewInfo.subresourceRange.layerCount = 1;
        if (vkCreateImageView(eng->device, &viewInfo, NULL, &eng->swapchainImageViews[i]) != VK_SUCCESS) {
            fprintf(stderr, "Error al crear ImageView de Swapchain %u en recreación\n", i);
            return 0;
        }
    }

    // 8. Recrear buffer de profundidad
    if (!create_depth_resources(eng)) {
        return 0;
    }

    // 9. Recrear framebuffers
    if (!create_framebuffers(eng)) {
        return 0;
    }

    eng->framebufferResized = 0;
    return 1;
}

void cleanup_swapchain_and_depth(VulkanEngine *eng) {
    if (eng->depthImageView != VK_NULL_HANDLE) {
        vkDestroyImageView(eng->device, eng->depthImageView, NULL);
        eng->depthImageView = VK_NULL_HANDLE;
    }
    if (eng->depthImage != VK_NULL_HANDLE) {
        vkDestroyImage(eng->device, eng->depthImage, NULL);
        eng->depthImage = VK_NULL_HANDLE;
    }
    if (eng->depthImageMemory != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, eng->depthImageMemory, NULL);
        eng->depthImageMemory = VK_NULL_HANDLE;
    }

    if (eng->swapchainImageViews) {
        for (uint32_t i = 0; i < eng->imageCount; i++) {
            if (eng->swapchainImageViews[i] != VK_NULL_HANDLE) {
                vkDestroyImageView(eng->device, eng->swapchainImageViews[i], NULL);
            }
        }
        free(eng->swapchainImageViews);
        eng->swapchainImageViews = NULL;
    }

    if (eng->swapchainImages) {
        free(eng->swapchainImages);
        eng->swapchainImages = NULL;
    }

    if (eng->swapchain != VK_NULL_HANDLE) {
        vkDestroySwapchainKHR(eng->device, eng->swapchain, NULL);
        eng->swapchain = VK_NULL_HANDLE;
    }
}
