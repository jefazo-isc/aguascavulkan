#ifndef VULKAN_SWAPCHAIN_H
#define VULKAN_SWAPCHAIN_H

#include "vulkan_types.h"

uint32_t find_memory_type(VkPhysicalDevice physicalDevice, uint32_t typeFilter, VkMemoryPropertyFlags properties);
int create_swapchain_and_depth(VulkanEngine *eng);
void cleanup_swapchain_and_depth(VulkanEngine *eng);
int recreate_swapchain(VulkanEngine *eng);

#endif // VULKAN_SWAPCHAIN_H
