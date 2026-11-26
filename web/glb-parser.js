// ============================================================================
// glb-parser.js — Parser binario GLB 2.0
// Lee ArrayBuffers que vienen de red. Falla si el archivo está truncado,
// tiene accessors malformados o el servidor manda datos corruptos.
// Esta es la única fuente de fallos externos — mantenerla aislada es
// exactamente el punto de este módulo.
// ============================================================================

// ----------------------------------------------------------------------------
// Extrae un TypedArray desde un accessor glTF.
// Fast-path: view de cero-copia si el stride y alignment lo permiten.
// Slow-path: copia elemento a elemento con conversión de tipo.
// ----------------------------------------------------------------------------
function extractAccessorTypedArray(gltf, accessorIdx, arrayBuffer, binBaseOffset, numComponents, expectedType) {
    const acc = gltf.accessors[accessorIdx];
    const bv  = gltf.bufferViews[acc.bufferView];
    const byteOffset  = binBaseOffset + (bv.byteOffset || 0) + (acc.byteOffset || 0);
    const elemCount   = acc.count * numComponents;
    const compType    = acc.componentType || 5126;
    const isNormalized = Boolean(acc.normalized);

    // Fast path
    if (expectedType === Float32Array && compType === 5126) {
        const compSize = 4;
        const expectedStride = numComponents * compSize;
        const actualStride   = bv.byteStride || 0;
        if ((actualStride === 0 || actualStride === expectedStride) && (byteOffset % compSize === 0)) {
            return new Float32Array(arrayBuffer, byteOffset, elemCount);
        }
    } else if (expectedType === Uint32Array && compType === 5125) {
        const compSize = 4;
        const actualStride = bv.byteStride || 0;
        if ((actualStride === 0 || actualStride === numComponents * compSize) && (byteOffset % compSize === 0)) {
            return new Uint32Array(arrayBuffer, byteOffset, elemCount);
        }
    } else if (expectedType === Uint16Array && compType === 5123) {
        const compSize = 2;
        const actualStride = bv.byteStride || 0;
        if ((actualStride === 0 || actualStride === numComponents * compSize) && (byteOffset % compSize === 0)) {
            return new Uint16Array(arrayBuffer, byteOffset, elemCount);
        }
    } else if (expectedType === Uint8Array && compType === 5121) {
        const actualStride = bv.byteStride || 0;
        if (actualStride === 0 || actualStride === numComponents) {
            return new Uint8Array(arrayBuffer, byteOffset, elemCount);
        }
    }

    // Slow path: copia con conversión
    const out = new expectedType(elemCount);
    const view = new DataView(arrayBuffer);
    let compSize = 4;
    if (compType === 5120 || compType === 5121) compSize = 1;
    else if (compType === 5122 || compType === 5123) compSize = 2;
    const stride = bv.byteStride || (numComponents * compSize);

    for (let i = 0; i < acc.count; i++) {
        const rowOff = byteOffset + i * stride;
        for (let c = 0; c < numComponents; c++) {
            const off = rowOff + c * compSize;
            let val = 0;
            if (compType === 5126)      val = view.getFloat32(off, true);
            else if (compType === 5125) val = view.getUint32(off, true);
            else if (compType === 5123) { val = view.getUint16(off, true); if (expectedType === Float32Array && isNormalized) val /= 65535.0; }
            else if (compType === 5122) { val = view.getInt16(off, true);  if (expectedType === Float32Array && isNormalized) val = Math.max(-1.0, val / 32767.0); }
            else if (compType === 5121) { val = view.getUint8(off);        if (expectedType === Float32Array && isNormalized) val /= 255.0; }
            else if (compType === 5120) { val = view.getInt8(off);         if (expectedType === Float32Array && isNormalized) val = Math.max(-1.0, val / 127.0); }
            out[i * numComponents + c] = val;
        }
    }
    return out;
}

// ----------------------------------------------------------------------------
// parseGLB — Parsea un ArrayBuffer GLB 2.0 en arrays de atributos separados.
// Retorna: { pos, norm, uv, col, em, indices, indexFormat, vertexCount,
//            indexCount, submeshes, buildingIndices }
// ----------------------------------------------------------------------------
export function parseGLB(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    if (arrayBuffer.byteLength < 20) throw new Error('GLB demasiado pequeño');

    const magic   = view.getUint32(0, true);
    const version = view.getUint32(4, true);
    if (magic !== 0x46546C67 || version !== 2) {
        throw new Error(`Encabezado GLB inválido: magic=0x${magic.toString(16)} version=${version}`);
    }

    let offset = 12;
    let gltf = null;
    let binBaseOffset = 0;
    let binByteLength = 0;

    while (offset + 8 <= arrayBuffer.byteLength) {
        const chunkLen  = view.getUint32(offset, true);
        const chunkType = view.getUint32(offset + 4, true);
        const dataStart = offset + 8;
        if (chunkType === 0x4E4F534A) {
            const jsonBytes = new Uint8Array(arrayBuffer, dataStart, chunkLen);
            gltf = JSON.parse(new TextDecoder('utf-8').decode(jsonBytes));
        } else if (chunkType === 0x004E4942) {
            binBaseOffset = dataStart;
            binByteLength = chunkLen;
        }
        offset = dataStart + chunkLen;
    }

    if (!gltf || !gltf.meshes || gltf.meshes.length === 0 || binByteLength === 0) {
        throw new Error('GLB sin chunk JSON de malla o sin chunk BIN');
    }

    // Recolectar primitivas válidas
    const primDescriptors = [];
    let totalVertexCount = 0;
    let totalIndexCount  = 0;

    for (let m = 0; m < gltf.meshes.length; m++) {
        const mesh = gltf.meshes[m];
        if (!mesh.primitives || mesh.primitives.length === 0) continue;
        for (let p = 0; p < mesh.primitives.length; p++) {
            const prim  = mesh.primitives[p];
            const attrs = prim.attributes;
            if (!attrs || attrs.POSITION === undefined) continue;

            const posAcc = gltf.accessors[attrs.POSITION];
            if (!posAcc || !posAcc.count) continue;
            const vertCount = posAcc.count;

            let idxCount = vertCount;
            if (prim.indices !== undefined) {
                const idxAcc = gltf.accessors[prim.indices];
                if (idxAcc) idxCount = idxAcc.count;
            }

            const meshName = mesh.name || '';
            const matName  = (prim.material !== undefined && gltf.materials && gltf.materials[prim.material])
                ? (gltf.materials[prim.material].name || '')
                : '';
            const isBuilding = /build|edific|facad|roof|wall|casa|rolcar|comercial|commerc|residen|tienda|store|shop|house/i.test(meshName) ||
                               /build|edific|facad|roof|wall|casa|rolcar|comercial|commerc|residen|tienda|store|shop|house/i.test(matName);

            primDescriptors.push({ meshIdx: m, primIdx: p, meshName, matName, isBuilding, attrs,
                indicesAccIdx: prim.indices, materialIdx: prim.material, vertCount, idxCount });
            totalVertexCount += vertCount;
            totalIndexCount  += idxCount;
        }
    }

    if (totalVertexCount === 0) throw new Error('GLB no contiene geometría de vértices válida');

    const pos  = new Float32Array(totalVertexCount * 3);
    const norm = new Float32Array(totalVertexCount * 3);
    const uv   = new Float32Array(totalVertexCount * 2);
    const col  = new Float32Array(totalVertexCount * 4);
    const em   = new Float32Array(totalVertexCount);

    const useUint32 = (totalVertexCount > 65535) || primDescriptors.some(d => {
        if (d.indicesAccIdx === undefined) return false;
        const acc = gltf.accessors[d.indicesAccIdx];
        return acc && acc.componentType === 5125;
    });
    const indices    = useUint32 ? new Uint32Array(totalIndexCount) : new Uint16Array(totalIndexCount);
    const indexFormat = useUint32 ? 'uint32' : 'uint16';

    const submeshes = [];
    let vertWriteOffset = 0;
    let idxWriteOffset  = 0;

    for (const desc of primDescriptors) {
        const { attrs, vertCount, idxCount, isBuilding, meshIdx, primIdx, meshName } = desc;
        const vStart = vertWriteOffset;
        const iStart = idxWriteOffset;

        // POSITION
        pos.set(extractAccessorTypedArray(gltf, attrs.POSITION, arrayBuffer, binBaseOffset, 3, Float32Array), vStart * 3);

        // NORMAL
        if (attrs.NORMAL !== undefined) {
            norm.set(extractAccessorTypedArray(gltf, attrs.NORMAL, arrayBuffer, binBaseOffset, 3, Float32Array), vStart * 3);
        } else {
            for (let i = 0; i < vertCount; i++) norm[(vStart + i) * 3 + 1] = 1.0;
        }

        // TEXCOORD_0
        const uvIdx = attrs.TEXCOORD_0 !== undefined ? attrs.TEXCOORD_0 : attrs.TEXCOORD;
        if (uvIdx !== undefined) {
            uv.set(extractAccessorTypedArray(gltf, uvIdx, arrayBuffer, binBaseOffset, 2, Float32Array), vStart * 2);
        }

        // COLOR_0
        const colIdx = attrs.COLOR_0 !== undefined ? attrs.COLOR_0 : attrs.COLOR;
        if (colIdx !== undefined) {
            const acc    = gltf.accessors[colIdx];
            const numComp = (acc && acc.type === 'VEC3') ? 3 : 4;
            const primCol = extractAccessorTypedArray(gltf, colIdx, arrayBuffer, binBaseOffset, numComp, Float32Array);
            if (numComp === 4) {
                col.set(primCol, vStart * 4);
            } else {
                for (let i = 0; i < vertCount; i++) {
                    col[(vStart + i) * 4 + 0] = primCol[i * 3 + 0];
                    col[(vStart + i) * 4 + 1] = primCol[i * 3 + 1];
                    col[(vStart + i) * 4 + 2] = primCol[i * 3 + 2];
                    col[(vStart + i) * 4 + 3] = 1.0;
                }
            }
        } else {
            for (let i = 0; i < vertCount; i++) {
                const off = (vStart + i) * 4;
                col[off + 0] = 1.0; col[off + 1] = 1.0; col[off + 2] = 1.0;
                col[off + 3] = (uvIdx !== undefined) ? 0.0 : 1.0;
            }
        }

        // EMISSION
        let matEmission = 0.0;
        if (desc.materialIdx !== undefined && gltf.materials && gltf.materials[desc.materialIdx]) {
            const mat = gltf.materials[desc.materialIdx];
            if (mat.emissiveFactor) {
                const ef = mat.emissiveFactor;
                if (ef[0] > 0.01 || ef[1] > 0.01 || ef[2] > 0.01) {
                    matEmission = (ef[0] + ef[1] + ef[2]) / 3.0 * 3.0;
                }
            }
        }
        const emIdx = attrs._EMISSION !== undefined ? attrs._EMISSION
                    : (attrs.EMISSION !== undefined ? attrs.EMISSION : attrs._EMISSION_FACTOR);
        if (emIdx !== undefined) {
            em.set(extractAccessorTypedArray(gltf, emIdx, arrayBuffer, binBaseOffset, 1, Float32Array), vStart);
        } else if (matEmission > 0.0) {
            em.fill(matEmission, vStart, vStart + vertCount);
        }

        // INDICES
        if (desc.indicesAccIdx !== undefined) {
            const acc = gltf.accessors[desc.indicesAccIdx];
            let primIndices;
            if (acc.componentType === 5125)      primIndices = extractAccessorTypedArray(gltf, desc.indicesAccIdx, arrayBuffer, binBaseOffset, 1, Uint32Array);
            else if (acc.componentType === 5123) primIndices = extractAccessorTypedArray(gltf, desc.indicesAccIdx, arrayBuffer, binBaseOffset, 1, Uint16Array);
            else                                 primIndices = extractAccessorTypedArray(gltf, desc.indicesAccIdx, arrayBuffer, binBaseOffset, 1, Uint8Array);

            if (vStart === 0) {
                indices.set(primIndices, iStart);
            } else {
                for (let k = 0; k < primIndices.length; k++) {
                    indices[iStart + k] = vStart + primIndices[k];
                }
            }
        } else {
            for (let k = 0; k < vertCount; k++) indices[iStart + k] = vStart + k;
        }

        submeshes.push({
            name: meshName || `mesh_${meshIdx}_prim_${primIdx}`,
            meshIndex: meshIdx, primIndex: primIdx,
            vertexStart: vStart, vertexCount: vertCount,
            indexStart: iStart, indexCount: idxCount,
            isBuilding,
        });

        vertWriteOffset += vertCount;
        idxWriteOffset  += idxCount;
    }

    // Separar índices de edificios de los de terreno por matID (color.a)
    // 0.35 = Techos, 1.00 = Fachadas, 1.14 = Rolcar Estuco, 1.18 = Cortinas metálicas
    const buildingTriIndices    = [];
    const nonBuildingTriIndices = [];
    for (let i = 0; i < indices.length; i += 3) {
        const i0 = indices[i], i1 = indices[i + 1], i2 = indices[i + 2];
        const avgMat = (col[i0 * 4 + 3] + col[i1 * 4 + 3] + col[i2 * 4 + 3]) / 3.0;
        const isBldg = (avgMat > 0.30 && avgMat < 0.40) ||
                       (avgMat > 0.98 && avgMat < 1.05) ||
                       (avgMat > 1.10 && avgMat < 1.25);
        (isBldg ? buildingTriIndices : nonBuildingTriIndices).push(i0, i1, i2);
    }

    const buildingIndices = buildingTriIndices.length > 0
        ? (useUint32 ? new Uint32Array(buildingTriIndices) : new Uint16Array(buildingTriIndices))
        : null;

    if (submeshes.length === 1 && !submeshes[0].isBuilding && buildingTriIndices.length > 0) {
        const nonBuildingIndices = useUint32
            ? new Uint32Array(nonBuildingTriIndices)
            : new Uint16Array(nonBuildingTriIndices);
        submeshes[0].name       = 'sector_terrain';
        submeshes[0].indexCount = nonBuildingTriIndices.length;
        submeshes[0].customIndices = nonBuildingIndices;
        submeshes[0].isBuilding    = false;
        submeshes.push({
            name: 'sector_buildings', meshIndex: 0, primIndex: 1,
            vertexStart: 0, vertexCount: totalVertexCount,
            indexStart: 0,  indexCount: buildingTriIndices.length,
            isBuilding: true, customIndices: buildingIndices,
        });
    }

    return { pos, norm, uv, col, em, indices, indexFormat,
             vertexCount: totalVertexCount, indexCount: totalIndexCount,
             submeshes, buildingIndices };
}
