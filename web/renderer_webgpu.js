// ============================================================================
// StreetVulkan WebGPU Renderer (executes directly over Vulkan on Linux/Win/Android)
// ============================================================================

export class WebGPURenderer {
    constructor() {
        this.backendName = 'WebGPU (Vulkan)';
        this.gpuName = 'WebGPU Adapter';
        this.canvas = null;
        this.context = null;
        this.format = null;
        this.adapter = null;
        this.device = null;
        this.pipeline = null;
        this.buildingPipeline = null;
        this.bindGroupLayout = null;
        this.bindGroup = null;
        this.uniformBuffer = null;
        this.sampler = null;
        this.satelliteTexture = null;
        this.facadeTexture = null;
        this.depthTexture = null;
        this.depthWidth = 0;
        this.depthHeight = 0;
        this.sectors = new Map();
        this.vehicleMesh = null;
    }

    async init(canvas, options = {}) {
        if (!navigator.gpu) {
            throw new Error('navigator.gpu is unavailable in this browser');
        }
        this.canvas = canvas;
        this.adapter = await navigator.gpu.requestAdapter({
            powerPreference: 'high-performance',
        });
        if (!this.adapter) {
            throw new Error('Failed to acquire a WebGPU adapter');
        }

        const info = this.adapter.info || (this.adapter.requestAdapterInfo ? await this.adapter.requestAdapterInfo() : null);
        if (info) {
            const parts = [info.description || info.device, info.architecture, info.vendor].filter(Boolean);
            if (parts.length > 0) {
                this.gpuName = parts.slice(0, 2).join(' · ');
            }
        }

        this.device = await this.adapter.requestDevice();
        this.context = canvas.getContext('webgpu');
        if (!this.context) {
            throw new Error('Failed to create WebGPU canvas context');
        }
        this.format = navigator.gpu.getPreferredCanvasFormat();
        this.context.configure({
            device: this.device,
            format: this.format,
            alphaMode: 'opaque',
        });

        const shaderUrl = options.shaderUrl || new URL('./shaders.wgsl', import.meta.url).href;
        const resp = await fetch(shaderUrl);
        if (!resp.ok) {
            throw new Error(`Failed to fetch WGSL shader (${resp.status}): ${shaderUrl}`);
        }
        const wgslCode = await resp.text();
        const shaderModule = this.device.createShaderModule({
            label: 'StreetVulkan PBR WGSL',
            code: wgslCode,
        });

        if (shaderModule.getCompilationInfo) {
            const compInfo = await shaderModule.getCompilationInfo();
            for (const msg of compInfo.messages) {
                if (msg.type === 'error') {
                    throw new Error(`WGSL compile error (line ${msg.lineNum}): ${msg.message}`);
                }
            }
        }

        this.bindGroupLayout = this.device.createBindGroupLayout({
            entries: [
                {
                    binding: 0,
                    visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
                    buffer: { type: 'uniform' },
                },
                {
                    binding: 1,
                    visibility: GPUShaderStage.FRAGMENT,
                    sampler: { type: 'filtering' },
                },
                {
                    binding: 2,
                    visibility: GPUShaderStage.FRAGMENT,
                    texture: { sampleType: 'float' },
                },
                {
                    binding: 3,
                    visibility: GPUShaderStage.FRAGMENT,
                    texture: { sampleType: 'float' },
                },
            ],
        });

        this.pipeline = this.device.createRenderPipeline({
            label: 'StreetVulkan WebGPU PBR Pipeline',
            layout: this.device.createPipelineLayout({
                bindGroupLayouts: [this.bindGroupLayout],
            }),
            vertex: {
                module: shaderModule,
                entryPoint: 'vs_main',
                buffers: [
                    { arrayStride: 12, attributes: [{ shaderLocation: 0, offset: 0, format: 'float32x3' }] },
                    { arrayStride: 12, attributes: [{ shaderLocation: 1, offset: 0, format: 'float32x3' }] },
                    { arrayStride: 8,  attributes: [{ shaderLocation: 2, offset: 0, format: 'float32x2' }] },
                    { arrayStride: 16, attributes: [{ shaderLocation: 3, offset: 0, format: 'float32x4' }] },
                    { arrayStride: 4,  attributes: [{ shaderLocation: 4, offset: 0, format: 'float32' }] },
                ],
            },
            fragment: {
                module: shaderModule,
                entryPoint: 'fs_main',
                targets: [
                    {
                        format: this.format,
                        blend: {
                            color: {
                                srcFactor: 'src-alpha',
                                dstFactor: 'one-minus-src-alpha',
                                operation: 'add',
                            },
                            alpha: {
                                srcFactor: 'one',
                                dstFactor: 'zero',
                                operation: 'add',
                            },
                        },
                    },
                ],
            },
            primitive: {
                topology: 'triangle-list',
                cullMode: 'none',
                frontFace: 'ccw',
            },
            depthStencil: {
                format: 'depth24plus',
                depthWriteEnabled: true,
                depthCompare: 'less-equal',
            },
        });

        this.buildingPipeline = this.device.createRenderPipeline({
            label: 'StreetVulkan WebGPU Building Pipeline',
            layout: this.device.createPipelineLayout({
                bindGroupLayouts: [this.bindGroupLayout],
            }),
            vertex: {
                module: shaderModule,
                entryPoint: 'vs_building',
                buffers: [
                    { arrayStride: 12, attributes: [{ shaderLocation: 0, offset: 0, format: 'float32x3' }] },
                    { arrayStride: 12, attributes: [{ shaderLocation: 1, offset: 0, format: 'float32x3' }] },
                    { arrayStride: 8,  attributes: [{ shaderLocation: 2, offset: 0, format: 'float32x2' }] },
                    { arrayStride: 16, attributes: [{ shaderLocation: 3, offset: 0, format: 'float32x4' }] },
                    { arrayStride: 4,  attributes: [{ shaderLocation: 4, offset: 0, format: 'float32' }] },
                ],
            },
            fragment: {
                module: shaderModule,
                entryPoint: 'fs_building',
                targets: [
                    {
                        format: this.format,
                        blend: {
                            color: {
                                srcFactor: 'src-alpha',
                                dstFactor: 'one-minus-src-alpha',
                                operation: 'add',
                            },
                            alpha: {
                                srcFactor: 'one',
                                dstFactor: 'zero',
                                operation: 'add',
                            },
                        },
                    },
                ],
            },
            primitive: {
                topology: 'triangle-list',
                cullMode: 'none',
                frontFace: 'ccw',
            },
            depthStencil: {
                format: 'depth24plus',
                depthWriteEnabled: true,
                depthCompare: 'less-equal',
            },
        });

        this.uniformBuffer = this.device.createBuffer({
            label: 'StreetVulkan Uniforms',
            size: 2272, // 14 vec4/mat4 slots (224B) + 64 PointLights (2048B)
            usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
        });

        this.sampler = this.device.createSampler({
            magFilter: 'linear',
            minFilter: 'linear',
            mipmapFilter: 'linear',
            addressModeU: 'clamp-to-edge',
            addressModeV: 'clamp-to-edge',
        });

        this.resize(canvas.width || 1280, canvas.height || 720);
        return {
            backend: this.backendName,
            gpuName: this.gpuName,
        };
    }

    _createRgbaTexture(texData, label) {
        const tex = this.device.createTexture({
            label,
            size: { width: texData.width, height: texData.height, depthOrArrayLayers: 1 },
            format: 'rgba8unorm',
            usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT,
        });
        this.device.queue.writeTexture(
            { texture: tex },
            texData.data,
            { bytesPerRow: texData.width * 4, rowsPerImage: texData.height },
            { width: texData.width, height: texData.height, depthOrArrayLayers: 1 }
        );
        return tex;
    }

    uploadTextures(satelliteTexData, facadeTexData) {
        if (this.satelliteTexture) this.satelliteTexture.destroy();
        if (this.facadeTexture) this.facadeTexture.destroy();

        this.satelliteTexture = this._createRgbaTexture(satelliteTexData, 'SatelliteTexture');
        this.facadeTexture = this._createRgbaTexture(facadeTexData, 'FacadeAtlasTexture');

        this.bindGroup = this.device.createBindGroup({
            layout: this.bindGroupLayout,
            entries: [
                { binding: 0, resource: { buffer: this.uniformBuffer } },
                { binding: 1, resource: this.sampler },
                { binding: 2, resource: this.satelliteTexture.createView() },
                { binding: 3, resource: this.facadeTexture.createView() },
            ],
        });
    }

    _createGpuBuffer(typedOrBytes, usage, label) {
        const byteLength = typedOrBytes.byteLength;
        const alignedSize = (byteLength + 3) & ~3;
        const buf = this.device.createBuffer({
            label,
            size: Math.max(4, alignedSize),
            usage: usage | GPUBufferUsage.COPY_DST,
        });
        if (byteLength === alignedSize) {
            this.device.queue.writeBuffer(buf, 0, typedOrBytes.buffer, typedOrBytes.byteOffset, byteLength);
        } else {
            const padded = new Uint8Array(alignedSize);
            padded.set(new Uint8Array(typedOrBytes.buffer, typedOrBytes.byteOffset, byteLength));
            this.device.queue.writeBuffer(buf, 0, padded);
        }
        return buf;
    }

    uploadSector(sectorKey, meshData, chunks) {
        if (this.sectors.has(sectorKey)) {
            this.unloadSector(sectorKey);
        }

        // Support de-interleaving if vertices are packed in engine struct format (52B = 13 floats)
        if (meshData.interleaved && (!meshData.pos || !meshData.norm)) {
            const raw = meshData.interleaved;
            const src = (raw instanceof Float32Array)
                ? raw
                : (raw.buffer
                    ? new Float32Array(raw.buffer, raw.byteOffset || 0, Math.floor((raw.byteLength || 0) / 4))
                    : new Float32Array(raw));
            const totalVerts = meshData.vertexCount || Math.floor(src.length / 13);
            const pos = new Float32Array(totalVerts * 3);
            const norm = new Float32Array(totalVerts * 3);
            const uv = new Float32Array(totalVerts * 2);
            const col = new Float32Array(totalVerts * 4);
            const em = new Float32Array(totalVerts);
            for (let i = 0; i < totalVerts; i++) {
                const s = i * 13;
                pos[i * 3 + 0] = src[s + 0];
                pos[i * 3 + 1] = src[s + 1];
                pos[i * 3 + 2] = src[s + 2];
                norm[i * 3 + 0] = src[s + 3];
                norm[i * 3 + 1] = src[s + 4];
                norm[i * 3 + 2] = src[s + 5];
                uv[i * 2 + 0] = src[s + 6];
                uv[i * 2 + 1] = src[s + 7];
                col[i * 4 + 0] = src[s + 8];
                col[i * 4 + 1] = src[s + 9];
                col[i * 4 + 2] = src[s + 10];
                col[i * 4 + 3] = src[s + 11];
                em[i] = src[s + 12];
            }
            meshData.pos = pos;
            meshData.norm = norm;
            meshData.uv = uv;
            meshData.col = col;
            meshData.em = em;
            meshData.vertexCount = totalVerts;
        }

        if (!meshData.indices && meshData.vertexCount) {
            const vCount = meshData.vertexCount;
            const useUint32 = vCount > 65535;
            const idx = useUint32 ? new Uint32Array(vCount) : new Uint16Array(vCount);
            for (let i = 0; i < vCount; i++) idx[i] = i;
            meshData.indices = idx;
            meshData.indexCount = vCount;
            meshData.indexFormat = useUint32 ? 'uint32' : 'uint16';
        }

        const posBuf = this._createGpuBuffer(meshData.pos, GPUBufferUsage.VERTEX, `${sectorKey}:pos`);
        const normBuf = this._createGpuBuffer(meshData.norm, GPUBufferUsage.VERTEX, `${sectorKey}:norm`);
        const uvBuf = this._createGpuBuffer(meshData.uv, GPUBufferUsage.VERTEX, `${sectorKey}:uv`);
        const colBuf = this._createGpuBuffer(meshData.col, GPUBufferUsage.VERTEX, `${sectorKey}:col`);
        const emBuf = this._createGpuBuffer(meshData.em, GPUBufferUsage.VERTEX, `${sectorKey}:em`);
        const idxBuf = this._createGpuBuffer(meshData.indices, GPUBufferUsage.INDEX, `${sectorKey}:idx`);

        let buildingIdxBuf = null;
        let buildingIndexCount = 0;
        let buildingIndexFormat = meshData.indexFormat || 'uint32';
        if (meshData.buildingIndices && meshData.buildingIndices.length > 0) {
            buildingIdxBuf = this._createGpuBuffer(meshData.buildingIndices, GPUBufferUsage.INDEX, `${sectorKey}:bldg_idx`);
            buildingIndexCount = meshData.buildingIndices.length;
            buildingIndexFormat = (meshData.buildingIndices instanceof Uint16Array) ? 'uint16' : 'uint32';
        }

        const submeshes = (meshData.submeshes || []).map((s, idx) => {
            let customIdxBuf = null;
            let customIndexFormat = meshData.indexFormat || 'uint32';
            if (s.customIndices && s.customIndices.length > 0) {
                customIdxBuf = this._createGpuBuffer(s.customIndices, GPUBufferUsage.INDEX, `${sectorKey}:sub_${idx}_idx`);
                customIndexFormat = (s.customIndices instanceof Uint16Array) ? 'uint16' : 'uint32';
            }
            return { ...s, customIdxBuf, customIndexFormat };
        });
        const buildingSubmeshes = submeshes.filter(s => s.isBuilding);

        this.sectors.set(sectorKey, {
            posBuf,
            normBuf,
            uvBuf,
            colBuf,
            emBuf,
            idxBuf,
            buildingIdxBuf,
            buildingIndexCount,
            buildingIndexFormat,
            indexFormat: meshData.indexFormat || 'uint32',
            indexCount: meshData.indexCount,
            vertexCount: meshData.vertexCount,
            chunks: chunks || [],
            submeshes,
            buildingSubmeshes,
        });
    }

    unloadSector(sectorKey) {
        const sec = this.sectors.get(sectorKey);
        if (!sec) return;
        sec.posBuf.destroy();
        sec.normBuf.destroy();
        sec.uvBuf.destroy();
        sec.colBuf.destroy();
        sec.emBuf.destroy();
        sec.idxBuf.destroy();
        if (sec.buildingIdxBuf) sec.buildingIdxBuf.destroy();
        if (sec.submeshes) {
            for (const sub of sec.submeshes) {
                if (sub.customIdxBuf) sub.customIdxBuf.destroy();
            }
        }
        this.sectors.delete(sectorKey);
    }

    resize(width, height) {
        const w = Math.max(1, width | 0);
        const h = Math.max(1, height | 0);
        if (this.depthTexture && this.depthWidth === w && this.depthHeight === h) {
            return;
        }
        if (this.depthTexture) {
            this.depthTexture.destroy();
        }
        this.depthWidth = w;
        this.depthHeight = h;
        this.depthTexture = this.device.createTexture({
            label: 'Depth24Plus',
            size: { width: w, height: h, depthOrArrayLayers: 1 },
            format: 'depth24plus',
            usage: GPUTextureUsage.RENDER_ATTACHMENT,
        });
    }

    render(frame) {
        if (!this.bindGroup || !this.pipeline) {
            return { drawCalls: 0, visibleChunks: 0, totalChunks: 0, visibleVerts: 0, totalVerts: 0 };
        }

        const w = Math.max(1, this.canvas.width | 0);
        const h = Math.max(1, this.canvas.height | 0);
        if (w !== this.depthWidth || h !== this.depthHeight) {
            this.resize(w, h);
        }

        this.device.queue.writeBuffer(this.uniformBuffer, 0, frame.uniformBufferData);

        const commandEncoder = this.device.createCommandEncoder();
        const textureView = this.context.getCurrentTexture().createView();
        const pass = commandEncoder.beginRenderPass({
            colorAttachments: [
                {
                    view: textureView,
                    clearValue: {
                        r: frame.clearColor[0],
                        g: frame.clearColor[1],
                        b: frame.clearColor[2],
                        a: 1.0,
                    },
                    loadOp: 'clear',
                    storeOp: 'store',
                },
            ],
            depthStencilAttachment: {
                view: this.depthTexture.createView(),
                depthClearValue: 1.0,
                depthLoadOp: 'clear',
                depthStoreOp: 'discard',
            },
        });

        pass.setPipeline(this.pipeline);
        pass.setBindGroup(0, this.bindGroup);

        let drawCalls = 0;
        let visibleChunks = 0;
        let totalChunks = 0;
        let visibleVerts = 0;
        let totalVerts = 0;

        for (const [sectorKey, sec] of this.sectors.entries()) {
            pass.setVertexBuffer(0, sec.posBuf);
            pass.setVertexBuffer(1, sec.normBuf);
            pass.setVertexBuffer(2, sec.uvBuf);
            pass.setVertexBuffer(3, sec.colBuf);
            pass.setVertexBuffer(4, sec.emBuf);

            totalVerts += sec.vertexCount;
            const flags = frame.cullFlagsBySector ? frame.cullFlagsBySector.get(sectorKey) : null;

            // Mode 1: Building-only rendering explicitly requested
            if (frame.renderMode === 'buildings') {
                if (sec.buildingIdxBuf && sec.buildingIndexCount > 0) {
                    if (this.buildingPipeline) pass.setPipeline(this.buildingPipeline);
                    pass.setIndexBuffer(sec.buildingIdxBuf, sec.buildingIndexFormat);
                    pass.drawIndexed(sec.buildingIndexCount, 1, 0, 0, 0);
                    drawCalls++;
                    visibleChunks++;
                    visibleVerts += sec.buildingIndexCount;
                    totalChunks += 1;
                } else if (sec.buildingSubmeshes && sec.buildingSubmeshes.length > 0) {
                    if (this.buildingPipeline) pass.setPipeline(this.buildingPipeline);
                    for (const sub of sec.buildingSubmeshes) {
                        const idxBuf = sub.customIdxBuf || sec.idxBuf;
                        const fmt = sub.customIdxBuf ? sub.customIndexFormat : sec.indexFormat;
                        pass.setIndexBuffer(idxBuf, fmt);
                        const start = sub.customIdxBuf ? 0 : sub.indexStart;
                        pass.drawIndexed(sub.indexCount, 1, start, 0, 0);
                        drawCalls++;
                        visibleChunks++;
                        visibleVerts += sub.indexCount;
                        totalChunks += 1;
                    }
                }
                continue;
            }

            // Mode 2: Standard sector rendering with spatial chunks & frustum culling
            if (sec.chunks && sec.chunks.length > 0) {
                pass.setPipeline(this.pipeline);
                pass.setIndexBuffer(sec.idxBuf, sec.indexFormat);
                totalChunks += sec.chunks.length;
                for (let i = 0; i < sec.chunks.length; i++) {
                    if (!frame.cullingEnabled || !flags || flags[i] !== 0) {
                        const chk = sec.chunks[i];
                        pass.drawIndexed(chk.count, 1, chk.start, 0, 0);
                        drawCalls++;
                        visibleChunks++;
                        visibleVerts += chk.count;
                    }
                }
                continue;
            }

            // Mode 3: Submesh-based rendering (when model has separate submeshes and no spatial chunks)
            if (sec.submeshes && sec.submeshes.length > 1) {
                totalChunks += sec.submeshes.length;
                let currentPipeline = null;
                for (const sub of sec.submeshes) {
                    const targetPipeline = (sub.isBuilding && this.buildingPipeline) ? this.buildingPipeline : this.pipeline;
                    if (currentPipeline !== targetPipeline) {
                        pass.setPipeline(targetPipeline);
                        currentPipeline = targetPipeline;
                    }
                    const idxBuf = sub.customIdxBuf || sec.idxBuf;
                    const fmt = sub.customIdxBuf ? sub.customIndexFormat : sec.indexFormat;
                    pass.setIndexBuffer(idxBuf, fmt);
                    const start = sub.customIdxBuf ? 0 : sub.indexStart;
                    pass.drawIndexed(sub.indexCount, 1, start, 0, 0);
                    drawCalls++;
                    visibleChunks++;
                    visibleVerts += sub.indexCount;
                }
                continue;
            }

            // Mode 4: Fallback single unified mesh without chunks
            pass.setPipeline(this.pipeline);
            pass.setIndexBuffer(sec.idxBuf, sec.indexFormat);
            totalChunks += 1;
            pass.drawIndexed(sec.indexCount, 1, 0, 0, 0);
            drawCalls++;
            visibleChunks++;
            visibleVerts += sec.indexCount;
        }

        pass.end();
        this.device.queue.submit([commandEncoder.finish()]);

        return { drawCalls, visibleChunks, totalChunks, visibleVerts, totalVerts };
    }

    renderBuildings(pass, sectorKey) {
        if (!this.buildingPipeline || !this.bindGroup) return 0;
        pass.setPipeline(this.buildingPipeline);
        pass.setBindGroup(0, this.bindGroup);
        let calls = 0;

        const renderSec = (sec) => {
            pass.setVertexBuffer(0, sec.posBuf);
            pass.setVertexBuffer(1, sec.normBuf);
            pass.setVertexBuffer(2, sec.uvBuf);
            pass.setVertexBuffer(3, sec.colBuf);
            pass.setVertexBuffer(4, sec.emBuf);

            if (sec.buildingIdxBuf && sec.buildingIndexCount > 0) {
                pass.setIndexBuffer(sec.buildingIdxBuf, sec.buildingIndexFormat);
                pass.drawIndexed(sec.buildingIndexCount, 1, 0, 0, 0);
                calls++;
            } else if (sec.buildingSubmeshes && sec.buildingSubmeshes.length > 0) {
                for (const sub of sec.buildingSubmeshes) {
                    const idxBuf = sub.customIdxBuf || sec.idxBuf;
                    const fmt = sub.customIdxBuf ? sub.customIndexFormat : sec.indexFormat;
                    pass.setIndexBuffer(idxBuf, fmt);
                    const start = sub.customIdxBuf ? 0 : sub.indexStart;
                    pass.drawIndexed(sub.indexCount, 1, start, 0, 0);
                    calls++;
                }
            }
        };

        if (sectorKey) {
            const sec = this.sectors.get(sectorKey);
            if (sec) renderSec(sec);
        } else {
            for (const sec of this.sectors.values()) {
                renderSec(sec);
            }
        }
        return calls;
    }

    uploadVehicleModel(meshData) {
        if (!this.device || !meshData) return;
        if (this.vehicleMesh) {
            if (this.vehicleMesh.posBuf) this.vehicleMesh.posBuf.destroy();
            if (this.vehicleMesh.normBuf) this.vehicleMesh.normBuf.destroy();
            if (this.vehicleMesh.uvBuf) this.vehicleMesh.uvBuf.destroy();
            if (this.vehicleMesh.colBuf) this.vehicleMesh.colBuf.destroy();
            if (this.vehicleMesh.emBuf) this.vehicleMesh.emBuf.destroy();
            if (this.vehicleMesh.idxBuf) this.vehicleMesh.idxBuf.destroy();
            this.vehicleMesh = null;
        }

        const posBuf = this._createGpuBuffer(meshData.pos, GPUBufferUsage.VERTEX, 'vehicle:pos');
        const normBuf = this._createGpuBuffer(meshData.norm, GPUBufferUsage.VERTEX, 'vehicle:norm');
        const uvBuf = this._createGpuBuffer(meshData.uv, GPUBufferUsage.VERTEX, 'vehicle:uv');
        const colBuf = this._createGpuBuffer(meshData.col, GPUBufferUsage.VERTEX, 'vehicle:col');
        const emBuf = this._createGpuBuffer(meshData.em, GPUBufferUsage.VERTEX, 'vehicle:em');
        const idxBuf = this._createGpuBuffer(meshData.indices, GPUBufferUsage.INDEX, 'vehicle:idx');

        this.vehicleMesh = {
            posBuf,
            normBuf,
            uvBuf,
            colBuf,
            emBuf,
            idxBuf,
            indexFormat: meshData.indexFormat || 'uint16',
            indexCount: meshData.indexCount,
            vertexCount: meshData.vertexCount,
        };
    }

    destroy() {
        for (const key of Array.from(this.sectors.keys())) {
            this.unloadSector(key);
        }
        if (this.vehicleMesh) {
            if (this.vehicleMesh.posBuf) this.vehicleMesh.posBuf.destroy();
            if (this.vehicleMesh.normBuf) this.vehicleMesh.normBuf.destroy();
            if (this.vehicleMesh.uvBuf) this.vehicleMesh.uvBuf.destroy();
            if (this.vehicleMesh.colBuf) this.vehicleMesh.colBuf.destroy();
            if (this.vehicleMesh.emBuf) this.vehicleMesh.emBuf.destroy();
            if (this.vehicleMesh.idxBuf) this.vehicleMesh.idxBuf.destroy();
            this.vehicleMesh = null;
        }
        if (this.depthTexture) this.depthTexture.destroy();
        if (this.satelliteTexture) this.satelliteTexture.destroy();
        if (this.facadeTexture) this.facadeTexture.destroy();
        if (this.uniformBuffer) this.uniformBuffer.destroy();
        this.pipeline = null;
        this.buildingPipeline = null;
    }
}
