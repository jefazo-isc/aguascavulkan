#ifndef VULKAN_ENGINE_H
#define VULKAN_ENGINE_H

#include "vulkan_types.h"

int vulkan_init(VulkanEngine *eng, SDL_Window *window);
void vulkan_draw(VulkanEngine *eng, float deltaTime);
void vulkan_destroy(VulkanEngine *eng);
float vulkan_get_ground_elevation(VulkanEngine *eng, float x, float z);

#endif // VULKAN_ENGINE_H
