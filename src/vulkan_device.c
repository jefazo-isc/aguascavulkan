#include "vulkan_device.h"
#include <SDL2/SDL_vulkan.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef DEBUG
static const char *VALIDATION_LAYERS[] = {
    "VK_LAYER_KHRONOS_validation"
};
static const uint32_t VALIDATION_LAYER_COUNT = sizeof(VALIDATION_LAYERS) / sizeof(VALIDATION_LAYERS[0]);

static VKAPI_ATTR VkBool32 VKAPI_CALL debug_callback(
    VkDebugUtilsMessageSeverityFlagBitsEXT severity,
    VkDebugUtilsMessageTypeFlagsEXT type,
    const VkDebugUtilsMessengerCallbackDataEXT *pCallbackData,
    void *pUserData)
{
    (void)type;
    (void)pUserData;
    const char *prefix = "[Vulkan Validation]";
    if (severity & VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT) {
        fprintf(stderr, "%s [ERROR]: %s\n", prefix, pCallbackData->pMessage);
    } else if (severity & VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT) {
        fprintf(stderr, "%s [WARN]: %s\n", prefix, pCallbackData->pMessage);
    } else {
        printf("%s [INFO]: %s\n", prefix, pCallbackData->pMessage);
    }
    return VK_FALSE;
}

static int check_validation_layer_support(void) {
    uint32_t layerCount = 0;
    vkEnumerateInstanceLayerProperties(&layerCount, NULL);
    if (layerCount == 0) return 0;

    VkLayerProperties *availableLayers = malloc(sizeof(VkLayerProperties) * layerCount);
    vkEnumerateInstanceLayerProperties(&layerCount, availableLayers);

    for (uint32_t i = 0; i < VALIDATION_LAYER_COUNT; i++) {
        int layerFound = 0;
        for (uint32_t j = 0; j < layerCount; j++) {
            if (strcmp(VALIDATION_LAYERS[i], availableLayers[j].layerName) == 0) {
                layerFound = 1;
                break;
            }
        }
        if (!layerFound) {
            free(availableLayers);
            return 0;
        }
    }
    free(availableLayers);
    return 1;
}
#endif

static int check_device_extension_support(VkPhysicalDevice device) {
    uint32_t extCount = 0;
    vkEnumerateDeviceExtensionProperties(device, NULL, &extCount, NULL);
    if (extCount == 0) return 0;

    VkExtensionProperties *availableExts = malloc(sizeof(VkExtensionProperties) * extCount);
    if (!availableExts) return 0;
    vkEnumerateDeviceExtensionProperties(device, NULL, &extCount, availableExts);

    int swapchainSupported = 0;
    for (uint32_t i = 0; i < extCount; i++) {
        if (strcmp(availableExts[i].extensionName, VK_KHR_SWAPCHAIN_EXTENSION_NAME) == 0) {
            swapchainSupported = 1;
            break;
        }
    }
    free(availableExts);
    return swapchainSupported;
}

int init_vulkan_instance_and_device(VulkanEngine *eng, SDL_Window *window) {
    unsigned int sdlExtCount = 0;
    SDL_Vulkan_GetInstanceExtensions(window, &sdlExtCount, NULL);

#ifdef DEBUG
    if (!check_validation_layer_support()) {
        fprintf(stderr, "\n[ERROR CRÍTICO]: Bandera DEBUG activada pero 'VK_LAYER_KHRONOS_validation' no está instalada en el sistema.\n"
                        "Para solucionarlo, instala el paquete de validación (ej. 'sudo apt install vulkan-validationlayers' o paquete equivalente).\n\n");
        return 0;
    }
    uint32_t extCount = sdlExtCount + 1;
#else
    uint32_t extCount = sdlExtCount;
#endif

    const char **extNames = malloc(sizeof(const char *) * extCount);
    SDL_Vulkan_GetInstanceExtensions(window, &sdlExtCount, extNames);
#ifdef DEBUG
    extNames[sdlExtCount] = VK_EXT_DEBUG_UTILS_EXTENSION_NAME;
#endif

    VkApplicationInfo appInfo = {0};
    appInfo.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    appInfo.pApplicationName = "StreetView Vulkan";
    appInfo.apiVersion = VK_API_VERSION_1_2;

    VkInstanceCreateInfo createInfo = {0};
    createInfo.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    createInfo.pApplicationInfo = &appInfo;
    createInfo.enabledExtensionCount = extCount;
    createInfo.ppEnabledExtensionNames = extNames;
#ifdef DEBUG
    createInfo.enabledLayerCount = VALIDATION_LAYER_COUNT;
    createInfo.ppEnabledLayerNames = VALIDATION_LAYERS;
#else
    createInfo.enabledLayerCount = 0;
#endif

    if (vkCreateInstance(&createInfo, NULL, &eng->instance) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al crear la instancia de Vulkan\n");
        free(extNames);
        return 0;
    }
    free(extNames);

#ifdef DEBUG
    {
        VkDebugUtilsMessengerCreateInfoEXT dci = {0};
        dci.sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT;
        dci.messageSeverity = VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT |
                              VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
        dci.messageType = VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT |
                          VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT |
                          VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
        dci.pfnUserCallback = debug_callback;

        PFN_vkCreateDebugUtilsMessengerEXT func =
            (PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(eng->instance, "vkCreateDebugUtilsMessengerEXT");
        if (func) {
            func(eng->instance, &dci, NULL, &eng->debugMessenger);
            printf("[Vulkan] Capa de validación 'VK_LAYER_KHRONOS_validation' activa con depuración estricta.\n");
        }
    }
#endif

    if (!SDL_Vulkan_CreateSurface(window, eng->instance, &eng->surface)) {
        fprintf(stderr, "Fallo al crear la superficie SDL Vulkan\n");
        return 0;
    }

    uint32_t deviceCount = 0;
    vkEnumeratePhysicalDevices(eng->instance, &deviceCount, NULL);
    if (deviceCount == 0) {
        fprintf(stderr, "No se encontraron GPUs con soporte para Vulkan\n");
        return 0;
    }

    VkPhysicalDevice *devices = malloc(sizeof(VkPhysicalDevice) * deviceCount);
    vkEnumeratePhysicalDevices(eng->instance, &deviceCount, devices);

    uint32_t selectedQueueFamily = UINT32_MAX;
    VkPhysicalDevice chosenDevice = VK_NULL_HANDLE;
    int chosenIsDiscrete = 0;

    for (uint32_t d = 0; d < deviceCount; d++) {
        if (!check_device_extension_support(devices[d])) continue;

        uint32_t queueFamilyCount = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(devices[d], &queueFamilyCount, NULL);
        if (queueFamilyCount == 0) continue;

        VkQueueFamilyProperties *queueFamilies = malloc(sizeof(VkQueueFamilyProperties) * queueFamilyCount);
        if (!queueFamilies) continue;
        vkGetPhysicalDeviceQueueFamilyProperties(devices[d], &queueFamilyCount, queueFamilies);

        uint32_t candidateQueueFamily = UINT32_MAX;
        for (uint32_t q = 0; q < queueFamilyCount; q++) {
            VkBool32 presentSupport = VK_FALSE;
            vkGetPhysicalDeviceSurfaceSupportKHR(devices[d], q, eng->surface, &presentSupport);
            if ((queueFamilies[q].queueFlags & VK_QUEUE_GRAPHICS_BIT) && presentSupport) {
                candidateQueueFamily = q;
                break;
            }
        }
        free(queueFamilies);

        if (candidateQueueFamily == UINT32_MAX) continue;

        VkPhysicalDeviceProperties candidateProps;
        vkGetPhysicalDeviceProperties(devices[d], &candidateProps);
        int isDiscrete = (candidateProps.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU);

        if (chosenDevice == VK_NULL_HANDLE || (isDiscrete && !chosenIsDiscrete)) {
            chosenDevice = devices[d];
            selectedQueueFamily = candidateQueueFamily;
            chosenIsDiscrete = isDiscrete;
            if (chosenIsDiscrete) break;
        }
    }
    free(devices);

    if (chosenDevice == VK_NULL_HANDLE) {
        fprintf(stderr, "No se encontró una GPU compatible con gráficos y presentación\n");
        return 0;
    }

    eng->physicalDevice = chosenDevice;
    eng->graphicsQueueFamily = selectedQueueFamily;

    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(chosenDevice, &props);
    snprintf(eng->gpuName, sizeof(eng->gpuName), "%s", props.deviceName);

    float queuePriority = 1.0f;
    VkDeviceQueueCreateInfo queueCreateInfo = {0};
    queueCreateInfo.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    queueCreateInfo.queueFamilyIndex = eng->graphicsQueueFamily;
    queueCreateInfo.queueCount = 1;
    queueCreateInfo.pQueuePriorities = &queuePriority;

    VkPhysicalDeviceFeatures supportedFeatures;
    vkGetPhysicalDeviceFeatures(eng->physicalDevice, &supportedFeatures);

    VkPhysicalDeviceFeatures deviceFeatures = {0};
    if (supportedFeatures.samplerAnisotropy == VK_TRUE) {
        deviceFeatures.samplerAnisotropy = VK_TRUE;
    }

    const char *deviceExtensions[] = { VK_KHR_SWAPCHAIN_EXTENSION_NAME };
    VkDeviceCreateInfo deviceCreateInfo = {0};
    deviceCreateInfo.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    deviceCreateInfo.queueCreateInfoCount = 1;
    deviceCreateInfo.pQueueCreateInfos = &queueCreateInfo;
    deviceCreateInfo.enabledExtensionCount = 1;
    deviceCreateInfo.ppEnabledExtensionNames = deviceExtensions;
    deviceCreateInfo.pEnabledFeatures = &deviceFeatures;

    if (vkCreateDevice(eng->physicalDevice, &deviceCreateInfo, NULL, &eng->device) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al crear el dispositivo lógico\n");
        return 0;
    }
    vkGetDeviceQueue(eng->device, eng->graphicsQueueFamily, 0, &eng->graphicsQueue);

    return 1;
}

void cleanup_vulkan_instance_and_device(VulkanEngine *eng) {
    if (eng->device != VK_NULL_HANDLE) {
        vkDestroyDevice(eng->device, NULL);
        eng->device = VK_NULL_HANDLE;
    }
    if (eng->surface != VK_NULL_HANDLE) {
        vkDestroySurfaceKHR(eng->instance, eng->surface, NULL);
        eng->surface = VK_NULL_HANDLE;
    }
    if (eng->instance != VK_NULL_HANDLE) {
#ifdef DEBUG
        if (eng->debugMessenger != VK_NULL_HANDLE) {
            PFN_vkDestroyDebugUtilsMessengerEXT func =
                (PFN_vkDestroyDebugUtilsMessengerEXT)vkGetInstanceProcAddr(eng->instance, "vkDestroyDebugUtilsMessengerEXT");
            if (func) {
                func(eng->instance, eng->debugMessenger, NULL);
            }
            eng->debugMessenger = VK_NULL_HANDLE;
        }
#endif
        vkDestroyInstance(eng->instance, NULL);
        eng->instance = VK_NULL_HANDLE;
    }
}
