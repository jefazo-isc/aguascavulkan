#include "vulkan_texture.h"
#include "vulkan_swapchain.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

static VkImage s_facadeImage = VK_NULL_HANDLE;
static VkDeviceMemory s_facadeMemory = VK_NULL_HANDLE;
static VkImageView s_facadeView = VK_NULL_HANDLE;


static VkResult create_gpu_image(VkDevice device, VkPhysicalDevice physicalDevice,
                                 VkImage* image, VkDeviceMemory* imageMemory,
                                 uint32_t w, uint32_t h, VkFormat format,
                                 VkImageTiling tiling, VkImageUsageFlags usage,
                                 VkMemoryPropertyFlags props) {
    VkImageCreateInfo ci={0}; ci.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    ci.imageType=VK_IMAGE_TYPE_2D; ci.extent.width=w; ci.extent.height=h; ci.extent.depth=1;
    ci.mipLevels=1; ci.arrayLayers=1; ci.format=format; ci.tiling=tiling;
    ci.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED; ci.usage=usage;
    ci.samples=VK_SAMPLE_COUNT_1_BIT; ci.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
    if (vkCreateImage(device,&ci,NULL,image)!=VK_SUCCESS) return VK_ERROR_INITIALIZATION_FAILED;
    VkMemoryRequirements mr; vkGetImageMemoryRequirements(device,*image,&mr);
    VkMemoryAllocateInfo ai={0}; ai.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    ai.allocationSize=mr.size;
    uint32_t ti=find_memory_type(physicalDevice,mr.memoryTypeBits,props);
    if (ti==UINT32_MAX){ vkDestroyImage(device,*image,NULL); return VK_ERROR_OUT_OF_DEVICE_MEMORY; }
    ai.memoryTypeIndex=ti;
    if (vkAllocateMemory(device,&ai,NULL,imageMemory)!=VK_SUCCESS){ vkDestroyImage(device,*image,NULL); return VK_ERROR_OUT_OF_DEVICE_MEMORY; }
    vkBindImageMemory(device,*image,*imageMemory,0);
    return VK_SUCCESS;
}
static void copy_buf_to_img(VkCommandBuffer cb, VkBuffer buf, VkImage img, uint32_t w, uint32_t h){
    VkBufferImageCopy r={0}; r.bufferOffset=0; r.bufferRowLength=0; r.bufferImageHeight=0;
    r.imageSubresource.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT; r.imageSubresource.mipLevel=0; r.imageSubresource.baseArrayLayer=0; r.imageSubresource.layerCount=1;
    r.imageOffset=(VkOffset3D){0,0,0}; r.imageExtent=(VkExtent3D){w,h,1};
    vkCmdCopyBufferToImage(cb,buf,img,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&r);
}
static int create_image_view_sampler(VulkanEngine *eng, VkImage img, VkImageView *view, VkFormat fmt){
    VkImageViewCreateInfo vi={0}; vi.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
    vi.image=img; vi.viewType=VK_IMAGE_VIEW_TYPE_2D; vi.format=fmt;
    vi.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT; vi.subresourceRange.baseMipLevel=0; vi.subresourceRange.levelCount=1; vi.subresourceRange.baseArrayLayer=0; vi.subresourceRange.layerCount=1;
    if (vkCreateImageView(eng->device,&vi,NULL,view)!=VK_SUCCESS) return 0;
    return 1;
}
static int upload_texture_data(VulkanEngine *eng, unsigned char* data, uint32_t w, uint32_t h, VkImage dstImage){
    VkBufferCreateInfo bi={0}; bi.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO; bi.size=w*h*4; bi.usage=VK_BUFFER_USAGE_TRANSFER_SRC_BIT; bi.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
    VkBuffer staging; if (vkCreateBuffer(eng->device,&bi,NULL,&staging)!=VK_SUCCESS) return 0;
    VkMemoryRequirements mr; vkGetBufferMemoryRequirements(eng->device,staging,&mr);
    uint32_t mt=find_memory_type(eng->physicalDevice,mr.memoryTypeBits,VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (mt==UINT32_MAX){ vkDestroyBuffer(eng->device,staging,NULL); return 0; }
    VkMemoryAllocateInfo ai={0}; ai.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO; ai.allocationSize=mr.size; ai.memoryTypeIndex=mt;
    VkDeviceMemory mem; if (vkAllocateMemory(eng->device,&ai,NULL,&mem)!=VK_SUCCESS){ vkDestroyBuffer(eng->device,staging,NULL); return 0; }
    vkBindBufferMemory(eng->device,staging,mem,0);
    void* ptr; vkMapMemory(eng->device,mem,0,bi.size,0,&ptr); memcpy(ptr,data,bi.size); vkUnmapMemory(eng->device,mem);
    VkCommandBufferAllocateInfo cai={0}; cai.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO; cai.commandPool=eng->commandPool; cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount=1;
    VkCommandBuffer cb; vkAllocateCommandBuffers(eng->device,&cai,&cb);
    VkCommandBufferBeginInfo bbi={VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO, NULL, VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT, NULL};
    vkBeginCommandBuffer(cb,&bbi);
    VkImageMemoryBarrier bar={0}; bar.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER; bar.oldLayout=VK_IMAGE_LAYOUT_UNDEFINED; bar.newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    bar.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED; bar.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED; bar.image=dstImage;
    bar.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT; bar.subresourceRange.baseMipLevel=0; bar.subresourceRange.levelCount=1; bar.subresourceRange.baseArrayLayer=0; bar.subresourceRange.layerCount=1;
    bar.srcAccessMask=0; bar.dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&bar);
    copy_buf_to_img(cb,staging,dstImage,w,h);
    bar.oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL; bar.newLayout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    bar.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT; bar.dstAccessMask=VK_ACCESS_SHADER_READ_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,0,0,NULL,0,NULL,1,&bar);
    vkEndCommandBuffer(cb);
    VkSubmitInfo si={0}; si.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO; si.commandBufferCount=1; si.pCommandBuffers=&cb;
    vkQueueSubmit(eng->graphicsQueue,1,&si,VK_NULL_HANDLE); vkQueueWaitIdle(eng->graphicsQueue);
    vkFreeCommandBuffers(eng->device,eng->commandPool,1,&cb);
    vkDestroyBuffer(eng->device,staging,NULL); vkFreeMemory(eng->device,mem,NULL);
    return 1;
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
int init_satellite_texture(VulkanEngine *eng, const char* texturePath){
    int width,height,channels; stbi_set_flip_vertically_on_load(0);
    unsigned char* data=stbi_load(texturePath,&width,&height,&channels,4);
    const char* altPaths[]={"assets/satellite.png","models/satellite.png","../assets/satellite.png","satellite.png",NULL};
    int pi=0;
    while(!data && altPaths[pi]){ data=stbi_load(altPaths[pi],&width,&height,&channels,4); if(data){ printf("[Textura] Cargada desde fallback %s\n",altPaths[pi]); texturePath=altPaths[pi]; break; } pi++; }
    if(!data){ fprintf(stderr,"No se pudo cargar textura: %s\n",texturePath); return 0; }
    eng->textureWidth=width; eng->textureHeight=height;
    printf("[Textura FASE1] Satelital %dx%d desde %s\n",width,height,texturePath);
    VkFormat fmt=VK_FORMAT_R8G8B8A8_UNORM;
    if(create_gpu_image(eng->device,eng->physicalDevice,&eng->textureImage,&eng->textureImageMemory,width,height,fmt,VK_IMAGE_TILING_OPTIMAL,VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_SAMPLED_BIT,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)!=VK_SUCCESS){ stbi_image_free(data); return 0; }
    VkBufferCreateInfo bi={0}; bi.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO; bi.size=width*height*4; bi.usage=VK_BUFFER_USAGE_TRANSFER_SRC_BIT; bi.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
    if(vkCreateBuffer(eng->device,&bi,NULL,&eng->textureStagingBuffer)!=VK_SUCCESS){ stbi_image_free(data); return 0; }
    VkMemoryRequirements mr; vkGetBufferMemoryRequirements(eng->device,eng->textureStagingBuffer,&mr);
    uint32_t mt=find_memory_type(eng->physicalDevice,mr.memoryTypeBits,VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if(mt==UINT32_MAX){ stbi_image_free(data); return 0; }
    VkMemoryAllocateInfo ai={0}; ai.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO; ai.allocationSize=mr.size; ai.memoryTypeIndex=mt;
    if(vkAllocateMemory(eng->device,&ai,NULL,&eng->textureStagingMemory)!=VK_SUCCESS){ stbi_image_free(data); return 0; }
    vkBindBufferMemory(eng->device,eng->textureStagingBuffer,eng->textureStagingMemory,0);
    void* ptr; vkMapMemory(eng->device,eng->textureStagingMemory,0,bi.size,0,&ptr); memcpy(ptr,data,bi.size); vkUnmapMemory(eng->device,eng->textureStagingMemory);
    stbi_image_free(data);
    VkCommandBufferAllocateInfo cai={0}; cai.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO; cai.commandPool=eng->commandPool; cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount=1;
    VkCommandBuffer cb; vkAllocateCommandBuffers(eng->device,&cai,&cb);
    VkCommandBufferBeginInfo bbi={VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,NULL,VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,NULL};
    vkBeginCommandBuffer(cb,&bbi);
    VkImageMemoryBarrier bar={0}; bar.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER; bar.oldLayout=VK_IMAGE_LAYOUT_UNDEFINED; bar.newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL; bar.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED; bar.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED; bar.image=eng->textureImage;
    bar.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT; bar.subresourceRange.baseMipLevel=0; bar.subresourceRange.levelCount=1; bar.subresourceRange.baseArrayLayer=0; bar.subresourceRange.layerCount=1; bar.srcAccessMask=0; bar.dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&bar);
    copy_buf_to_img(cb,eng->textureStagingBuffer,eng->textureImage,width,height);
    bar.oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL; bar.newLayout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL; bar.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT; bar.dstAccessMask=VK_ACCESS_SHADER_READ_BIT;
    vkCmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,0,0,NULL,0,NULL,1,&bar);
    vkEndCommandBuffer(cb);
    VkSubmitInfo si={0}; si.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO; si.commandBufferCount=1; si.pCommandBuffers=&cb;
    vkQueueSubmit(eng->graphicsQueue,1,&si,VK_NULL_HANDLE); vkQueueWaitIdle(eng->graphicsQueue);
    vkFreeCommandBuffers(eng->device,eng->commandPool,1,&cb);
    /* Liberar staging buffer de textura satelital — la transferencia ya completó */
    if(eng->textureStagingBuffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(eng->device, eng->textureStagingBuffer, NULL);
        eng->textureStagingBuffer = VK_NULL_HANDLE;
    }
    if(eng->textureStagingMemory != VK_NULL_HANDLE) {
        vkFreeMemory(eng->device, eng->textureStagingMemory, NULL);
        eng->textureStagingMemory = VK_NULL_HANDLE;
    }
    VkImageViewCreateInfo vi={0}; vi.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO; vi.image=eng->textureImage; vi.viewType=VK_IMAGE_VIEW_TYPE_2D; vi.format=fmt;
    vi.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT; vi.subresourceRange.baseMipLevel=0; vi.subresourceRange.levelCount=1; vi.subresourceRange.baseArrayLayer=0; vi.subresourceRange.layerCount=1;
    if(vkCreateImageView(eng->device,&vi,NULL,&eng->textureImageView)!=VK_SUCCESS) return 0;
    VkSamplerCreateInfo samplerInfo={0}; samplerInfo.sType=VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO;
    samplerInfo.magFilter=VK_FILTER_NEAREST; samplerInfo.minFilter=VK_FILTER_NEAREST;
    samplerInfo.addressModeU=VK_SAMPLER_ADDRESS_MODE_REPEAT; samplerInfo.addressModeV=VK_SAMPLER_ADDRESS_MODE_REPEAT; samplerInfo.addressModeW=VK_SAMPLER_ADDRESS_MODE_REPEAT;
    samplerInfo.anisotropyEnable=VK_TRUE; samplerInfo.maxAnisotropy=8.0f; samplerInfo.borderColor=VK_BORDER_COLOR_INT_OPAQUE_BLACK;
    samplerInfo.unnormalizedCoordinates=VK_FALSE; samplerInfo.compareEnable=VK_FALSE; samplerInfo.mipmapMode=VK_SAMPLER_MIPMAP_MODE_LINEAR;
    if(vkCreateSampler(eng->device,&samplerInfo,NULL,&eng->textureSampler)!=VK_SUCCESS) return 0;
    int fw = 0, fh = 0, fch = 0;
    int isAtlasLoaded = 0;
    unsigned char* fdata = stbi_load("models/texture_atlas_16x16.png", &fw, &fh, &fch, 4);
    if (!fdata) {
        fdata = stbi_load("assets/texture_atlas_16x16.png", &fw, &fh, &fch, 4);
    }
    if (fdata) {
        isAtlasLoaded = 1;
        printf("[Textura] Atlas pixel-art cargado: %dx%d (%d canales)\n", fw, fh, fch);
    } else {
        fdata = generate_facade_texture(&fw, &fh);
        printf("[Textura] Fachada procedural fallback %dx%d\n", fw, fh);
    }
    if(create_gpu_image(eng->device,eng->physicalDevice,&s_facadeImage,&s_facadeMemory,fw,fh,fmt,VK_IMAGE_TILING_OPTIMAL,VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_SAMPLED_BIT,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)!=VK_SUCCESS){
        if (isAtlasLoaded) stbi_image_free(fdata); else free(fdata);
        return 0;
    }
    if(!upload_texture_data(eng,fdata,fw,fh,s_facadeImage)){
        if (isAtlasLoaded) stbi_image_free(fdata); else free(fdata);
        return 0;
    }
    if (isAtlasLoaded) stbi_image_free(fdata); else free(fdata);
    if(!create_image_view_sampler(eng,s_facadeImage,&s_facadeView,fmt)) return 0;

    /* Crear buffer UBO de iluminación dinámica (32 luces puntuales + linterna) */
    VkBufferCreateInfo uboInfo = {0};
    uboInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    uboInfo.size = sizeof(LightingUBO);
    uboInfo.usage = VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT;
    uboInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    if (vkCreateBuffer(eng->device, &uboInfo, NULL, &eng->lightingBuffer) != VK_SUCCESS) return 0;

    VkMemoryRequirements uboReqs;
    vkGetBufferMemoryRequirements(eng->device, eng->lightingBuffer, &uboReqs);
    uint32_t uboMemType = find_memory_type(eng->physicalDevice, uboReqs.memoryTypeBits,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    VkMemoryAllocateInfo uboAlloc = {0};
    uboAlloc.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    uboAlloc.allocationSize = uboReqs.size;
    uboAlloc.memoryTypeIndex = uboMemType;
    if (vkAllocateMemory(eng->device, &uboAlloc, NULL, &eng->lightingBufferMemory) != VK_SUCCESS) return 0;
    vkBindBufferMemory(eng->device, eng->lightingBuffer, eng->lightingBufferMemory, 0);
    vkMapMemory(eng->device, eng->lightingBufferMemory, 0, sizeof(LightingUBO), 0, (void**)&eng->lightingUboMapped);
    memset(eng->lightingUboMapped, 0, sizeof(LightingUBO));

    VkDescriptorPoolSize poolSizes[2] = {
        {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 2},
        {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1}
    };
    VkDescriptorPoolCreateInfo poolInfo={0}; poolInfo.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO; poolInfo.poolSizeCount=2; poolInfo.pPoolSizes=poolSizes; poolInfo.maxSets=1;
    if(vkCreateDescriptorPool(eng->device,&poolInfo,NULL,&eng->descriptorPool)!=VK_SUCCESS) return 0;
    VkDescriptorSetAllocateInfo allocInfoDS={0}; allocInfoDS.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO; allocInfoDS.descriptorPool=eng->descriptorPool; allocInfoDS.descriptorSetCount=1; allocInfoDS.pSetLayouts=&eng->descriptorSetLayout;
    if(vkAllocateDescriptorSets(eng->device,&allocInfoDS,&eng->descriptorSet)!=VK_SUCCESS) return 0;
    VkDescriptorImageInfo imgInfo0={0}; imgInfo0.sampler=eng->textureSampler; imgInfo0.imageView=eng->textureImageView; imgInfo0.imageLayout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    VkDescriptorImageInfo imgInfo1={0}; imgInfo1.sampler=eng->textureSampler; imgInfo1.imageView=s_facadeView; imgInfo1.imageLayout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    VkDescriptorBufferInfo bufInfo = {0};
    bufInfo.buffer = eng->lightingBuffer;
    bufInfo.offset = 0;
    bufInfo.range = sizeof(LightingUBO);

    VkWriteDescriptorSet writes[3]={0};
    writes[0].sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; writes[0].dstSet=eng->descriptorSet; writes[0].dstBinding=0; writes[0].descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; writes[0].descriptorCount=1; writes[0].pImageInfo=&imgInfo0;
    writes[1].sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; writes[1].dstSet=eng->descriptorSet; writes[1].dstBinding=1; writes[1].descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; writes[1].descriptorCount=1; writes[1].pImageInfo=&imgInfo1;
    writes[2].sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; writes[2].dstSet=eng->descriptorSet; writes[2].dstBinding=2; writes[2].descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER; writes[2].descriptorCount=1; writes[2].pBufferInfo=&bufInfo;
    vkUpdateDescriptorSets(eng->device,3,writes,0,NULL);
    printf("[Textura FASE1] DescriptorSet con 2 texturas y UBO de luces listo\n");
    return 1;
}
void cleanup_texture_resources(VulkanEngine *eng){
    if(eng->lightingUboMapped){ vkUnmapMemory(eng->device, eng->lightingBufferMemory); eng->lightingUboMapped = NULL; }
    if(eng->lightingBuffer != VK_NULL_HANDLE){ vkDestroyBuffer(eng->device, eng->lightingBuffer, NULL); eng->lightingBuffer = VK_NULL_HANDLE; }
    if(eng->lightingBufferMemory != VK_NULL_HANDLE){ vkFreeMemory(eng->device, eng->lightingBufferMemory, NULL); eng->lightingBufferMemory = VK_NULL_HANDLE; }
    if(eng->descriptorPool!=VK_NULL_HANDLE){ vkDestroyDescriptorPool(eng->device,eng->descriptorPool,NULL); eng->descriptorPool=VK_NULL_HANDLE; }
    if(eng->textureSampler!=VK_NULL_HANDLE){ vkDestroySampler(eng->device,eng->textureSampler,NULL); eng->textureSampler=VK_NULL_HANDLE; }
    if(eng->textureImageView!=VK_NULL_HANDLE){ vkDestroyImageView(eng->device,eng->textureImageView,NULL); eng->textureImageView=VK_NULL_HANDLE; }
    if(s_facadeView!=VK_NULL_HANDLE){ vkDestroyImageView(eng->device,s_facadeView,NULL); s_facadeView=VK_NULL_HANDLE; }
    if(eng->textureImage!=VK_NULL_HANDLE){ vkDestroyImage(eng->device,eng->textureImage,NULL); eng->textureImage=VK_NULL_HANDLE; }
    if(s_facadeImage!=VK_NULL_HANDLE){ vkDestroyImage(eng->device,s_facadeImage,NULL); s_facadeImage=VK_NULL_HANDLE; }
    if(eng->textureImageMemory!=VK_NULL_HANDLE){ vkFreeMemory(eng->device,eng->textureImageMemory,NULL); eng->textureImageMemory=VK_NULL_HANDLE; }
    if(s_facadeMemory!=VK_NULL_HANDLE){ vkFreeMemory(eng->device,s_facadeMemory,NULL); s_facadeMemory=VK_NULL_HANDLE; }
    if(eng->textureStagingBuffer!=VK_NULL_HANDLE){ vkDestroyBuffer(eng->device,eng->textureStagingBuffer,NULL); eng->textureStagingBuffer=VK_NULL_HANDLE; }
    if(eng->textureStagingMemory!=VK_NULL_HANDLE){ vkFreeMemory(eng->device,eng->textureStagingMemory,NULL); eng->textureStagingMemory=VK_NULL_HANDLE; }
}
