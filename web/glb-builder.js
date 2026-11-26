// ============================================================================
// glb-builder.js — Constructores de meshes procedurales fallback
// Código completamente determinista. No depende de datos externos.
// Si hay un bug aquí es tuyo — no del servidor ni del archivo GLB.
// ============================================================================

// ----------------------------------------------------------------------------
// Escena fallback standalone (solo si ningún GLB es alcanzable por HTTP).
// Renderiza una plaza Rolcar Paseo de la Cruz con fachada y cortina.
// ----------------------------------------------------------------------------
export function buildStandaloneFallbackSector() {
    const positions = [], normals = [], uvs = [], colors = [], emissions = [];

    const pushQuad = (p0, p1, p2, p3, n, col, em = 0.0) => {
        const pts  = [p0, p1, p2, p0, p2, p3];
        const qUvs = [[0, 1], [1, 1], [1, 0], [0, 1], [1, 0], [0, 0]];
        for (let i = 0; i < 6; i++) {
            positions.push(pts[i][0], pts[i][1], pts[i][2]);
            normals.push(n[0], n[1], n[2]);
            uvs.push(qUvs[i][0], qUvs[i][1]);
            colors.push(col[0], col[1], col[2], col[3]);
            emissions.push(em);
        }
    };

    // Plaza de asfalto
    pushQuad([900, 0, 740], [1020, 0, 740], [1020, 0, 840], [900, 0, 840],
             [0, 1, 0], [0.22, 0.22, 0.24, 0.95]);
    // Fachada Rolcar Paseo de la Cruz
    pushQuad([964, 0, 770], [982, 0, 784], [982, 7.5, 784], [964, 7.5, 770],
             [-0.6, 0, 0.8], [0.94, 0.94, 0.92, 1.14]);
    // Cortina metálica
    pushQuad([966, 0.2, 771.5], [974, 0.2, 777.8], [974, 4.2, 777.8], [966, 4.2, 771.5],
             [-0.6, 0, 0.8], [0.48, 0.51, 0.53, 1.18]);
    // Logo con emisión verde Rolcar
    pushQuad([964, 4.5, 770.1], [982, 4.5, 784.1], [982, 5.6, 784.1], [964, 5.6, 770.1],
             [-0.6, 0, 0.8], [0.04, 0.45, 0.18, 1.14], 0.4);

    const vertexCount = positions.length / 3;
    const indices = new Uint32Array(vertexCount);
    for (let i = 0; i < vertexCount; i++) indices[i] = i;

    return {
        mesh: {
            pos: new Float32Array(positions),
            norm: new Float32Array(normals),
            uv:   new Float32Array(uvs),
            col:  new Float32Array(colors),
            em:   new Float32Array(emissions),
            indices, indexFormat: 'uint32',
            vertexCount, indexCount: vertexCount,
        },
        chunks: [{
            cx: 7, cz: 6, start: 0, count: vertexCount,
            min_x: 900, min_y: -1, min_z: 740,
            max_x: 1020, max_y: 20, max_z: 840,
        }],
    };
}

// ----------------------------------------------------------------------------
// Mesh fallback de vehículo (sedán de cajas procedurales).
// Se usa si car_sedan.glb no está disponible.
// ----------------------------------------------------------------------------
export function buildFallbackVehicleMesh() {
    const positions = [], normals = [], uvs = [], colors = [], emissions = [];

    const pushBox = (minX, minY, minZ, maxX, maxY, maxZ, col, em = 0.0) => {
        const pushFace = (p0, p1, p2, p3, n) => {
            const pts = [p0, p1, p2, p0, p2, p3];
            for (let i = 0; i < 6; i++) {
                positions.push(pts[i][0], pts[i][1], pts[i][2]);
                normals.push(n[0], n[1], n[2]);
                uvs.push(0.5, 0.5);
                colors.push(col[0], col[1], col[2], col[3]);
                emissions.push(em);
            }
        };
        pushFace([minX,maxY,minZ],[maxX,maxY,minZ],[maxX,maxY,maxZ],[minX,maxY,maxZ],[0,1,0]);
        pushFace([minX,minY,maxZ],[maxX,minY,maxZ],[maxX,minY,minZ],[minX,minY,minZ],[0,-1,0]);
        pushFace([minX,minY,maxZ],[maxX,minY,maxZ],[maxX,maxY,maxZ],[minX,maxY,maxZ],[0,0,1]);
        pushFace([maxX,minY,minZ],[minX,minY,minZ],[minX,maxY,minZ],[maxX,maxY,minZ],[0,0,-1]);
        pushFace([maxX,minY,maxZ],[maxX,minY,minZ],[maxX,maxY,minZ],[maxX,maxY,maxZ],[1,0,0]);
        pushFace([minX,minY,minZ],[minX,minY,maxZ],[minX,maxY,maxZ],[minX,maxY,minZ],[-1,0,0]);
    };

    // Carrocería
    pushBox(-0.9, 0.2, -2.1,  0.9, 0.9,  2.1, [0.15, 0.45, 0.85, 2.0]);
    // Cabina
    pushBox(-0.75, 0.9, -0.9, 0.75, 1.55, 1.3, [0.08, 0.12, 0.18, 2.0]);
    // Faros delanteros
    pushBox( 0.45, 0.45, 2.08,  0.75, 0.75, 2.12, [1.0, 0.98, 0.85, 2.0], 8.0);
    pushBox(-0.75, 0.45, 2.08, -0.45, 0.75, 2.12, [1.0, 0.98, 0.85, 2.0], 8.0);
    // Calaveras traseras
    pushBox( 0.45, 0.50, -2.12,  0.75, 0.75, -2.08, [1.0, 0.08, 0.05, 2.0], 6.0);
    pushBox(-0.75, 0.50, -2.12, -0.45, 0.75, -2.08, [1.0, 0.08, 0.05, 2.0], 6.0);

    const vertexCount = positions.length / 3;
    const indices = new Uint16Array(vertexCount);
    for (let i = 0; i < vertexCount; i++) indices[i] = i;

    return {
        pos:  new Float32Array(positions),
        norm: new Float32Array(normals),
        uv:   new Float32Array(uvs),
        col:  new Float32Array(colors),
        em:   new Float32Array(emissions),
        indices, indexFormat: 'uint16',
        vertexCount, indexCount: vertexCount,
    };
}
