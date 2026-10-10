#ifndef VULKAN_DEVICE_H
#define VULKAN_DEVICE_H

#include "vulkan_types.h"

int init_vulkan_instance_and_device(VulkanEngine *eng, SDL_Window *window);
void cleanup_vulkan_instance_and_device(VulkanEngine *eng);

#endif // VULKAN_DEVICE_H
