#ifndef VULKAN_PIPELINE_H
#define VULKAN_PIPELINE_H

#include "vulkan_types.h"

int create_render_pass(VulkanEngine *eng);
int create_framebuffers(VulkanEngine *eng);
void destroy_framebuffers(VulkanEngine *eng);
int create_pipeline_and_descriptors(VulkanEngine *eng);
int create_sync_objects(VulkanEngine *eng);
void cleanup_pipeline_and_sync(VulkanEngine *eng);

#endif // VULKAN_PIPELINE_H
