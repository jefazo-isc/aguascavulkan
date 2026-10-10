#ifndef VULKAN_TEXTURE_H
#define VULKAN_TEXTURE_H

#include "vulkan_types.h"

int init_satellite_texture(VulkanEngine *eng, const char* texturePath);
void cleanup_texture_resources(VulkanEngine *eng);

#endif // VULKAN_TEXTURE_H
