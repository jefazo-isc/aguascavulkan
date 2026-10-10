#include "vulkan_device.h"
#include <SDL2/SDL_vulkan.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int init_vulkan_instance_and_device(VulkanEngine *eng, SDL_Window *window) {
    unsigned int extCount = 0;
    SDL_Vulkan_GetInstanceExtensions(window, &extCount, NULL);
    const char **extNames = malloc(sizeof(const char *) * extCount);
    SDL_Vulkan_GetInstanceExtensions(window, &extCount, extNames);

    VkApplicationInfo appInfo = {0};
    appInfo.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    appInfo.pApplicationName = "StreetView Vulkan";
    appInfo.apiVersion = VK_API_VERSION_1_2;

    VkInstanceCreateInfo createInfo = {0};
    createInfo.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    createInfo.pApplicationInfo = &appInfo;
    createInfo.enabledExtensionCount = extCount;
    createInfo.ppEnabledExtensionNames = extNames;

    if (vkCreateInstance(&createInfo, NULL, &eng->instance) != VK_SUCCESS) {
        fprintf(stderr, "Fallo al crear la instancia de Vulkan\n");
        free(extNames);
        return 0;
    }
    free(extNames);

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

    for (uint32_t d = 0; d < deviceCount; d++) {
        uint32_t queueFamilyCount = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(devices[d], &queueFamilyCount, NULL);
        if (queueFamilyCount == 0) continue;

        VkQueueFamilyProperties *queueFamilies = malloc(sizeof(VkQueueFamilyProperties) * queueFamilyCount);
        vkGetPhysicalDeviceQueueFamilyProperties(devices[d], &queueFamilyCount, queueFamilies);

        for (uint32_t q = 0; q < queueFamilyCount; q++) {
            VkBool32 presentSupport = VK_FALSE;
            vkGetPhysicalDeviceSurfaceSupportKHR(devices[d], q, eng->surface, &presentSupport);
            if ((queueFamilies[q].queueFlags & VK_QUEUE_GRAPHICS_BIT) && presentSupport) {
                selectedQueueFamily = q;
                chosenDevice = devices[d];
                break;
            }
        }
        free(queueFamilies);
        if (chosenDevice != VK_NULL_HANDLE) break;
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

    VkPhysicalDeviceFeatures deviceFeatures = {0};
    deviceFeatures.samplerAnisotropy = VK_TRUE;

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
        vkDestroyInstance(eng->instance, NULL);
        eng->instance = VK_NULL_HANDLE;
    }
}
