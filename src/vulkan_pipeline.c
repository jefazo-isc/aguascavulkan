#include "vulkan_pipeline.h"
#include <stdio.h>
#include <stdlib.h>
static uint32_t* read_spv_file(const char* filename, size_t* outSize) {
    if (!filename || !outSize) return NULL;
    *outSize = 0;
    FILE* f = fopen(filename, "rb");
    if (!f) return NULL;

    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return NULL;
    }
    long tell = ftell(f);
    if (tell <= 0 || (tell % 4) != 0) {
        fprintf(stderr, "[Pipeline] Error: Archivo SPV inválido o tamaño no múltiplo de 4: %s (%ld bytes)\n",
                filename, tell);
        fclose(f);
        return NULL;
    }
    size_t size = (size_t)tell;
    rewind(f);

    uint32_t* code = (uint32_t*)malloc(size);
    if (!code) {
        fclose(f);
        return NULL;
    }
    size_t bytesRead = fread(code, 1, size, f);
    fclose(f);
    if (bytesRead != size) {
        fprintf(stderr, "[Pipeline] Error: Lectura incompleta de SPV %s (%zu / %zu bytes)\n",
                filename, bytesRead, size);
        free(code);
        return NULL;
    }
    *outSize = size;
    return code;
}
static VkShaderModule create_shader_module(VkDevice device, const char* filename){
    size_t codeSize=0; uint32_t* code=read_spv_file(filename,&codeSize);
    if(!code){ fprintf(stderr,"No SPV: %s\n",filename); return VK_NULL_HANDLE; }
    VkShaderModuleCreateInfo ci={0}; ci.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO; ci.codeSize=codeSize; ci.pCode=code;
    VkShaderModule mod=VK_NULL_HANDLE; VkResult res=vkCreateShaderModule(device,&ci,NULL,&mod); free(code);
    if(res!=VK_SUCCESS){ fprintf(stderr,"Error shader %s\n",filename); return VK_NULL_HANDLE; }
    return mod;
}
int create_render_pass(VulkanEngine *eng){
    VkAttachmentDescription atts[2]={0};
    atts[0].format=eng->swapchainImageFormat; atts[0].samples=VK_SAMPLE_COUNT_1_BIT; atts[0].loadOp=VK_ATTACHMENT_LOAD_OP_CLEAR; atts[0].storeOp=VK_ATTACHMENT_STORE_OP_STORE; atts[0].stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE; atts[0].stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE; atts[0].initialLayout=VK_IMAGE_LAYOUT_UNDEFINED; atts[0].finalLayout=VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    atts[1].format=eng->depthFormat; atts[1].samples=VK_SAMPLE_COUNT_1_BIT; atts[1].loadOp=VK_ATTACHMENT_LOAD_OP_CLEAR; atts[1].storeOp=VK_ATTACHMENT_STORE_OP_DONT_CARE; atts[1].stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE; atts[1].stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE; atts[1].initialLayout=VK_IMAGE_LAYOUT_UNDEFINED; atts[1].finalLayout=VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
    VkAttachmentReference colRef={0,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL}; VkAttachmentReference depthRef={1,VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL};
    VkSubpassDescription sub={0}; sub.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS; sub.colorAttachmentCount=1; sub.pColorAttachments=&colRef; sub.pDepthStencilAttachment=&depthRef;
    VkSubpassDependency dep={0}; dep.srcSubpass=VK_SUBPASS_EXTERNAL; dep.dstSubpass=0; dep.srcStageMask=VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT|VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT; dep.srcAccessMask=0; dep.dstStageMask=VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT|VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT; dep.dstAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT|VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;
    VkRenderPassCreateInfo rpi={0}; rpi.sType=VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO; rpi.attachmentCount=2; rpi.pAttachments=atts; rpi.subpassCount=1; rpi.pSubpasses=&sub; rpi.dependencyCount=1; rpi.pDependencies=&dep;
    return vkCreateRenderPass(eng->device,&rpi,NULL,&eng->renderPass)==VK_SUCCESS;
}
int create_framebuffers(VulkanEngine *eng){
    eng->framebuffers=malloc(sizeof(VkFramebuffer)*eng->imageCount); if(!eng->framebuffers) return 0;
    for(uint32_t i=0;i<eng->imageCount;i++){
        VkImageView atts[2]={eng->swapchainImageViews[i],eng->depthImageView};
        VkFramebufferCreateInfo fbi={0}; fbi.sType=VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO; fbi.renderPass=eng->renderPass; fbi.attachmentCount=2; fbi.pAttachments=atts; fbi.width=eng->swapchainExtent.width; fbi.height=eng->swapchainExtent.height; fbi.layers=1;
        if(vkCreateFramebuffer(eng->device,&fbi,NULL,&eng->framebuffers[i])!=VK_SUCCESS){ fprintf(stderr,"Fallo FB %u\n",i); return 0; }
    } return 1;
}
void destroy_framebuffers(VulkanEngine *eng){
    if(eng->framebuffers){ for(uint32_t i=0;i<eng->imageCount;i++) if(eng->framebuffers[i]!=VK_NULL_HANDLE) vkDestroyFramebuffer(eng->device,eng->framebuffers[i],NULL); free(eng->framebuffers); eng->framebuffers=NULL; }
}
int create_pipeline_and_descriptors(VulkanEngine *eng){
    VkShaderModule vertModule=create_shader_module(eng->device,"shaders/vertex.spv");
    VkShaderModule fragModule=create_shader_module(eng->device,"shaders/fragment.spv");
    if(vertModule==VK_NULL_HANDLE||fragModule==VK_NULL_HANDLE) return 0;
    VkPipelineShaderStageCreateInfo vertStage={0}; vertStage.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; vertStage.stage=VK_SHADER_STAGE_VERTEX_BIT; vertStage.module=vertModule; vertStage.pName="main";
    VkPipelineShaderStageCreateInfo fragStage={0}; fragStage.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; fragStage.stage=VK_SHADER_STAGE_FRAGMENT_BIT; fragStage.module=fragModule; fragStage.pName="main";
    VkPipelineShaderStageCreateInfo stages[]={vertStage,fragStage};
    VkVertexInputBindingDescription bindingDescs[2];
    bindingDescs[0] = vertex_get_binding_description(); // Binding 0: Per-vertex
    bindingDescs[1].binding = 1;                         // Binding 1: Per-instance (coches)
    bindingDescs[1].stride = 96;                         // sizeof(CarInstanceData)
    bindingDescs[1].inputRate = VK_VERTEX_INPUT_RATE_INSTANCE;

    VkVertexInputAttributeDescription attrDescs[11];
    vertex_get_attribute_descriptions(attrDescs);

    // Attribs 5..8: inInstanceModel (mat4)
    for (uint32_t i = 0; i < 4; i++) {
        attrDescs[5 + i].binding = 1;
        attrDescs[5 + i].location = 5 + i;
        attrDescs[5 + i].format = VK_FORMAT_R32G32B32A32_SFLOAT;
        attrDescs[5 + i].offset = i * 16;
    }
    // Attrib 9: inInstanceTint (vec4)
    attrDescs[9].binding = 1;
    attrDescs[9].location = 9;
    attrDescs[9].format = VK_FORMAT_R32G32B32A32_SFLOAT;
    attrDescs[9].offset = 64;

    // Attrib 10: inInstanceBrake (float)
    attrDescs[10].binding = 1;
    attrDescs[10].location = 10;
    attrDescs[10].format = VK_FORMAT_R32_SFLOAT;
    attrDescs[10].offset = 80;

    VkPipelineVertexInputStateCreateInfo vi={0}; vi.sType=VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO; vi.vertexBindingDescriptionCount=2; vi.pVertexBindingDescriptions=bindingDescs; vi.vertexAttributeDescriptionCount=11; vi.pVertexAttributeDescriptions=attrDescs;
    VkPipelineInputAssemblyStateCreateInfo ia={0}; ia.sType=VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO; ia.topology=VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkViewport vp={0,0,(float)eng->swapchainExtent.width,(float)eng->swapchainExtent.height,0.0f,1.0f};
    VkRect2D sc={ {0,0}, eng->swapchainExtent };
    VkPipelineViewportStateCreateInfo vps={0}; vps.sType=VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO; vps.viewportCount=1; vps.pViewports=&vp; vps.scissorCount=1; vps.pScissors=&sc;
    VkDynamicState dyn[2]={VK_DYNAMIC_STATE_VIEWPORT,VK_DYNAMIC_STATE_SCISSOR};
    VkPipelineDynamicStateCreateInfo ds={0}; ds.sType=VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO; ds.dynamicStateCount=2; ds.pDynamicStates=dyn;
    VkPipelineRasterizationStateCreateInfo rast={0}; rast.sType=VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO; rast.polygonMode=VK_POLYGON_MODE_FILL; rast.lineWidth=1.0f; rast.cullMode=VK_CULL_MODE_NONE; rast.frontFace=VK_FRONT_FACE_COUNTER_CLOCKWISE;
    VkPipelineMultisampleStateCreateInfo ms={0}; ms.sType=VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO; ms.rasterizationSamples=VK_SAMPLE_COUNT_1_BIT;
    VkPipelineDepthStencilStateCreateInfo dss={0}; dss.sType=VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO; dss.depthTestEnable=VK_TRUE; dss.depthWriteEnable=VK_TRUE; dss.depthCompareOp=VK_COMPARE_OP_LESS_OR_EQUAL;
    VkPipelineColorBlendAttachmentState cbAtt={0};
    cbAtt.colorWriteMask=VK_COLOR_COMPONENT_R_BIT|VK_COLOR_COMPONENT_G_BIT|VK_COLOR_COMPONENT_B_BIT|VK_COLOR_COMPONENT_A_BIT;
    cbAtt.blendEnable=VK_TRUE;
    cbAtt.srcColorBlendFactor=VK_BLEND_FACTOR_SRC_ALPHA;
    cbAtt.dstColorBlendFactor=VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    cbAtt.colorBlendOp=VK_BLEND_OP_ADD;
    cbAtt.srcAlphaBlendFactor=VK_BLEND_FACTOR_ONE;
    cbAtt.dstAlphaBlendFactor=VK_BLEND_FACTOR_ZERO;
    cbAtt.alphaBlendOp=VK_BLEND_OP_ADD;
    VkPipelineColorBlendStateCreateInfo cb={0}; cb.sType=VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO; cb.attachmentCount=1; cb.pAttachments=&cbAtt;
    VkDescriptorSetLayoutBinding bindings[4]={0};
    bindings[0].binding=0; bindings[0].descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; bindings[0].descriptorCount=1; bindings[0].stageFlags=VK_SHADER_STAGE_FRAGMENT_BIT;
    bindings[1].binding=1; bindings[1].descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; bindings[1].descriptorCount=1; bindings[1].stageFlags=VK_SHADER_STAGE_FRAGMENT_BIT;
    bindings[2].binding=2; bindings[2].descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER; bindings[2].descriptorCount=1; bindings[2].stageFlags=VK_SHADER_STAGE_FRAGMENT_BIT;
    bindings[3].binding=3; bindings[3].descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; bindings[3].descriptorCount=1; bindings[3].stageFlags=VK_SHADER_STAGE_FRAGMENT_BIT;
    VkDescriptorSetLayoutCreateInfo li={0}; li.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO; li.bindingCount=4; li.pBindings=bindings;
    if(vkCreateDescriptorSetLayout(eng->device,&li,NULL,&eng->descriptorSetLayout)!=VK_SUCCESS){ vkDestroyShaderModule(eng->device,fragModule,NULL); vkDestroyShaderModule(eng->device,vertModule,NULL); return 0; }
    VkPushConstantRange pcr={0}; pcr.stageFlags=VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT; pcr.offset=0; pcr.size=sizeof(PushConstants);
    VkPipelineLayoutCreateInfo pli={0}; pli.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO; pli.setLayoutCount=1; pli.pSetLayouts=&eng->descriptorSetLayout; pli.pushConstantRangeCount=1; pli.pPushConstantRanges=&pcr;
    if(vkCreatePipelineLayout(eng->device,&pli,NULL,&eng->pipelineLayout)!=VK_SUCCESS){ vkDestroyShaderModule(eng->device,fragModule,NULL); vkDestroyShaderModule(eng->device,vertModule,NULL); return 0; }
    VkGraphicsPipelineCreateInfo pi={0}; pi.sType=VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO; pi.stageCount=2; pi.pStages=stages; pi.pVertexInputState=&vi; pi.pInputAssemblyState=&ia; pi.pViewportState=&vps; pi.pDynamicState=&ds; pi.pRasterizationState=&rast; pi.pMultisampleState=&ms; pi.pDepthStencilState=&dss; pi.pColorBlendState=&cb; pi.layout=eng->pipelineLayout; pi.renderPass=eng->renderPass; pi.subpass=0;
    VkResult pr=vkCreateGraphicsPipelines(eng->device,VK_NULL_HANDLE,1,&pi,NULL,&eng->graphicsPipeline);
    vkDestroyShaderModule(eng->device,fragModule,NULL); vkDestroyShaderModule(eng->device,vertModule,NULL);
    return pr==VK_SUCCESS;
}
int create_sync_objects(VulkanEngine *eng){
    VkSemaphoreCreateInfo si={VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO,NULL,0};
    VkFenceCreateInfo fi={VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,NULL,VK_FENCE_CREATE_SIGNALED_BIT};

    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if (vkCreateSemaphore(eng->device, &si, NULL, &eng->imageAvailableSemaphores[i]) != VK_SUCCESS ||
            vkCreateFence(eng->device, &fi, NULL, &eng->inFlightFences[i]) != VK_SUCCESS) {
            return 0;
        }
    }

    eng->renderFinishedSemaphoreCount = eng->imageCount;
    if (eng->renderFinishedSemaphoreCount > 0) {
        eng->renderFinishedSemaphores = calloc(eng->renderFinishedSemaphoreCount, sizeof(VkSemaphore));
        if (!eng->renderFinishedSemaphores) {
            eng->renderFinishedSemaphoreCount = 0;
            return 0;
        }
        for (uint32_t i = 0; i < eng->renderFinishedSemaphoreCount; i++) {
            if (vkCreateSemaphore(eng->device, &si, NULL, &eng->renderFinishedSemaphores[i]) != VK_SUCCESS) {
                return 0;
            }
        }
    }

    VkCommandPoolCreateInfo cpi={0}; cpi.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO; cpi.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT; cpi.queueFamilyIndex=eng->graphicsQueueFamily;
    if(vkCreateCommandPool(eng->device,&cpi,NULL,&eng->commandPool)!=VK_SUCCESS) return 0;
    VkCommandBufferAllocateInfo cai={0}; cai.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO; cai.commandPool=eng->commandPool; cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount=MAX_FRAMES_IN_FLIGHT;
    if (vkAllocateCommandBuffers(eng->device,&cai,eng->commandBuffers)!=VK_SUCCESS) return 0;

    eng->currentFrame = 0;
    return 1;
}
void cleanup_pipeline_and_sync(VulkanEngine *eng){
    for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if(eng->inFlightFences[i]!=VK_NULL_HANDLE) { vkDestroyFence(eng->device,eng->inFlightFences[i],NULL); eng->inFlightFences[i] = VK_NULL_HANDLE; }
        if(eng->imageAvailableSemaphores[i]!=VK_NULL_HANDLE) { vkDestroySemaphore(eng->device,eng->imageAvailableSemaphores[i],NULL); eng->imageAvailableSemaphores[i] = VK_NULL_HANDLE; }
    }
    if (eng->renderFinishedSemaphores) {
        for (uint32_t i = 0; i < eng->renderFinishedSemaphoreCount; i++) {
            if (eng->renderFinishedSemaphores[i] != VK_NULL_HANDLE) {
                vkDestroySemaphore(eng->device, eng->renderFinishedSemaphores[i], NULL);
                eng->renderFinishedSemaphores[i] = VK_NULL_HANDLE;
            }
        }
        free(eng->renderFinishedSemaphores);
        eng->renderFinishedSemaphores = NULL;
    }
    eng->renderFinishedSemaphoreCount = 0;
    if(eng->commandPool!=VK_NULL_HANDLE) { vkDestroyCommandPool(eng->device,eng->commandPool,NULL); eng->commandPool = VK_NULL_HANDLE; }
    if(eng->graphicsPipeline!=VK_NULL_HANDLE) vkDestroyPipeline(eng->device,eng->graphicsPipeline,NULL);
    if(eng->pipelineLayout!=VK_NULL_HANDLE) vkDestroyPipelineLayout(eng->device,eng->pipelineLayout,NULL);
    if(eng->descriptorSetLayout!=VK_NULL_HANDLE) vkDestroyDescriptorSetLayout(eng->device,eng->descriptorSetLayout,NULL);
    destroy_framebuffers(eng);
    if(eng->renderPass!=VK_NULL_HANDLE) vkDestroyRenderPass(eng->device,eng->renderPass,NULL);
}
