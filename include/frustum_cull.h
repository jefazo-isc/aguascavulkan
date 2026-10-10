/* frustum_cull.h - Frustum culling para chunks del sistema StreetVulkan
 *
 * Extrae los 6 planos del frustum desde la matriz MVP (column-major)
 * y prueba AABB contra el frustum.
 */
#ifndef FRUSTUM_CULL_H
#define FRUSTUM_CULL_H

#include <math.h>

typedef struct {
    float a, b, c, d; // Plano: ax + by + cz + d = 0
} FrustumPlane;

typedef struct {
    FrustumPlane planes[6]; // left, right, bottom, top, near, far
} Frustum;

typedef struct {
    float min_x, min_y, min_z;
    float max_x, max_y, max_z;
} AABB;

/* Extraer los 6 planos del frustum desde la MVP (column-major).
 * Método Gribb/Hartmann: planos = filas de (P*V*M) combinadas. */
static inline Frustum frustum_extract(const float mvp[16]) {
    Frustum f;
    /* Column-major: row i of the matrix = mvp[i], mvp[4+i], mvp[8+i], mvp[12+i] */
    /* Left:   row3 + row0 */
    f.planes[0].a = mvp[3]  + mvp[0];
    f.planes[0].b = mvp[7]  + mvp[4];
    f.planes[0].c = mvp[11] + mvp[8];
    f.planes[0].d = mvp[15] + mvp[12];
    /* Right:  row3 - row0 */
    f.planes[1].a = mvp[3]  - mvp[0];
    f.planes[1].b = mvp[7]  - mvp[4];
    f.planes[1].c = mvp[11] - mvp[8];
    f.planes[1].d = mvp[15] - mvp[12];
    /* Bottom: row3 + row1 */
    f.planes[2].a = mvp[3]  + mvp[1];
    f.planes[2].b = mvp[7]  + mvp[5];
    f.planes[2].c = mvp[11] + mvp[9];
    f.planes[2].d = mvp[15] + mvp[13];
    /* Top:    row3 - row1 */
    f.planes[3].a = mvp[3]  - mvp[1];
    f.planes[3].b = mvp[7]  - mvp[5];
    f.planes[3].c = mvp[11] - mvp[9];
    f.planes[3].d = mvp[15] - mvp[13];
    /* Near:   row3 + row2 */
    f.planes[4].a = mvp[3]  + mvp[2];
    f.planes[4].b = mvp[7]  + mvp[6];
    f.planes[4].c = mvp[11] + mvp[10];
    f.planes[4].d = mvp[15] + mvp[14];
    /* Far:    row3 - row2 */
    f.planes[5].a = mvp[3]  - mvp[2];
    f.planes[5].b = mvp[7]  - mvp[6];
    f.planes[5].c = mvp[11] - mvp[10];
    f.planes[5].d = mvp[15] - mvp[14];

    /* Normalizar planos */
    for (int i = 0; i < 6; i++) {
        float len = sqrtf(f.planes[i].a * f.planes[i].a +
                          f.planes[i].b * f.planes[i].b +
                          f.planes[i].c * f.planes[i].c);
        if (len > 1e-8f) {
            f.planes[i].a /= len;
            f.planes[i].b /= len;
            f.planes[i].c /= len;
            f.planes[i].d /= len;
        }
    }
    return f;
}

/* Probar si un AABB es visible (total o parcialmente) desde el frustum.
 * Devuelve 1 si visible, 0 si completamente fuera. */
static inline int frustum_test_aabb(const Frustum *f, const AABB *box) {
    for (int i = 0; i < 6; i++) {
        const FrustumPlane *p = &f->planes[i];
        /* Esquina P-vertex: la más lejana en la dirección del normal del plano */
        float px = (p->a >= 0.0f) ? box->max_x : box->min_x;
        float py = (p->b >= 0.0f) ? box->max_y : box->min_y;
        float pz = (p->c >= 0.0f) ? box->max_z : box->min_z;
        /* Si el P-vertex está en el lado negativo, la caja está completamente fuera */
        if (p->a * px + p->b * py + p->c * pz + p->d < 0.0f) {
            return 0;
        }
    }
    return 1;
}

#endif /* FRUSTUM_CULL_H */
