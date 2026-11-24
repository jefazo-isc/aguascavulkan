/* web/main_wasm.c - Emscripten / Standalone C Port of StreetVulkan Core
 *
 * Exposes the exact same ABI as web/street_vulkan_core.wat so CI/CD pipelines
 * with Emscripten (emcc) can compile the C headers directly to WebAssembly,
 * matching the hand-assembled WAT kernel 1:1.
 */

#include <math.h>
#include <stdint.h>

#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#define SV_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define SV_EXPORT __attribute__((visibility("default")))
#endif

/* Rename inline header functions whose names match our flat WASM ABI exports */
#define mat4_multiply c_mat4_multiply
#define mat4_lookat c_mat4_lookat
#define camera_get_vectors c_camera_get_vectors
#include "math_camera.h"
#undef mat4_multiply
#undef mat4_lookat
#undef camera_get_vectors

#define frustum_extract c_frustum_extract
#include "frustum_cull.h"
#undef frustum_extract

SV_EXPORT int32_t get_version(void) {
    return 1;
}

SV_EXPORT void camera_get_vectors(float yaw_deg, float pitch_deg,
                                  float *out_fwd, float *out_right, float *out_up) {
    Camera cam = {0};
    cam.yaw = yaw_deg;
    cam.pitch = pitch_deg;
    Vec3 f, r, u;
    c_camera_get_vectors(&cam, &f, &r, &u);
    if (out_fwd) {
        out_fwd[0] = f.x;
        out_fwd[1] = f.y;
        out_fwd[2] = f.z;
    }
    if (out_right) {
        out_right[0] = r.x;
        out_right[1] = r.y;
        out_right[2] = r.z;
    }
    if (out_up) {
        out_up[0] = u.x;
        out_up[1] = u.y;
        out_up[2] = u.z;
    }
}

SV_EXPORT void camera_step(float *pos, float yaw_deg, float pitch_deg,
                           float move_fwd, float move_right, float move_up,
                           float speed, float dt) {
    if (!pos) return;
    Camera cam = {0};
    cam.yaw = yaw_deg;
    cam.pitch = pitch_deg;
    Vec3 f, r, u;
    c_camera_get_vectors(&cam, &f, &r, &u);
    float step = speed * dt;
    pos[0] += (move_fwd * f.x + move_right * r.x + move_up * u.x) * step;
    pos[1] += (move_fwd * f.y + move_right * r.y + move_up * u.y) * step;
    pos[2] += (move_fwd * f.z + move_right * r.z + move_up * u.z) * step;
}

SV_EXPORT void mat4_perspective_webgpu(float *out, float fovy_rad, float aspect,
                                       float znear, float zfar) {
    if (!out) return;
    float f = 1.0f / tanf(fovy_rad * 0.5f);
    float inv_nf = 1.0f / (znear - zfar);
    for (int i = 0; i < 16; ++i) out[i] = 0.0f;
    out[0] = f / aspect;
    out[5] = f; /* WebGPU NDC +Y up, Z in [0, 1] */
    out[10] = zfar * inv_nf;
    out[11] = -1.0f;
    out[14] = (zfar * znear) * inv_nf;
}

SV_EXPORT void mat4_perspective_webgl(float *out, float fovy_rad, float aspect,
                                      float znear, float zfar) {
    if (!out) return;
    float f = 1.0f / tanf(fovy_rad * 0.5f);
    float inv_nf = 1.0f / (znear - zfar);
    for (int i = 0; i < 16; ++i) out[i] = 0.0f;
    out[0] = f / aspect;
    out[5] = f; /* WebGL NDC +Y up, Z in [-1, 1] */
    out[10] = (zfar + znear) * inv_nf;
    out[11] = -1.0f;
    out[14] = (2.0f * zfar * znear) * inv_nf;
}

SV_EXPORT void mat4_lookat(float *out,
                           float ex, float ey, float ez,
                           float cx, float cy, float cz,
                           float ux, float uy, float uz) {
    if (!out) return;
    Mat4 m = c_mat4_lookat(ex, ey, ez, cx, cy, cz, ux, uy, uz);
    for (int i = 0; i < 16; ++i) out[i] = m.m[i];
}

SV_EXPORT void mat4_multiply(float *out, const float *a_ptr, const float *b_ptr) {
    if (!out || !a_ptr || !b_ptr) return;
    Mat4 a, b;
    for (int i = 0; i < 16; ++i) {
        a.m[i] = a_ptr[i];
        b.m[i] = b_ptr[i];
    }
    Mat4 res = c_mat4_multiply(a, b);
    for (int i = 0; i < 16; ++i) out[i] = res.m[i];
}

SV_EXPORT void frustum_extract(float *planes_out, const float *mvp) {
    if (!planes_out || !mvp) return;
    Frustum f = c_frustum_extract(mvp);
    for (int i = 0; i < 6; ++i) {
        planes_out[i * 4 + 0] = f.planes[i].a;
        planes_out[i * 4 + 1] = f.planes[i].b;
        planes_out[i * 4 + 2] = f.planes[i].c;
        planes_out[i * 4 + 3] = f.planes[i].d;
    }
}

SV_EXPORT int32_t cull_chunks(const float *planes_ptr, const float *aabbs_ptr,
                              uint8_t *out_flags, int32_t count) {
    if (!planes_ptr || !aabbs_ptr || !out_flags || count <= 0) return 0;
    Frustum f;
    for (int i = 0; i < 6; ++i) {
        f.planes[i].a = planes_ptr[i * 4 + 0];
        f.planes[i].b = planes_ptr[i * 4 + 1];
        f.planes[i].c = planes_ptr[i * 4 + 2];
        f.planes[i].d = planes_ptr[i * 4 + 3];
    }
    int32_t visible = 0;
    for (int32_t i = 0; i < count; ++i) {
        const float *b = &aabbs_ptr[i * 6];
        AABB box = { b[0], b[1], b[2], b[3], b[4], b[5] };
        uint8_t vis = (uint8_t)(frustum_test_aabb(&f, &box) ? 1 : 0);
        out_flags[i] = vis;
        visible += (int32_t)vis;
    }
    return visible;
}

SV_EXPORT int32_t traffic_tick(float *sim_time_ptr, float dt) {
    if (!sim_time_ptr) return 0;
    float t = *sim_time_ptr + dt;
    t -= 24.0f * floorf(t / 24.0f);
    if (t >= 24.0f || t < 0.0f) t = 0.0f;
    *sim_time_ptr = t;

    if (t < 9.0f) return 0;   /* NS Green */
    if (t < 12.0f) return 1;  /* NS Amber */
    if (t < 21.0f) return 2;  /* EW Green */
    return 3;                 /* EW Amber */
}

SV_EXPORT int32_t update_vehicle_stream(float *cars_ptr, int32_t car_count, float dt, float speed) {
    if (!cars_ptr || car_count <= 0) return 0;
    for (int32_t i = 0; i < car_count; ++i) {
        float *car = &cars_ptr[i * 6];
        float prog = car[4] + dt * speed;
        if (prog >= 1.0f) {
            prog -= 1.0f;
        }
        car[4] = prog;
        float cid = car[5];
        if (cid < 0.5f) {
            /* Corridor 0: Av. Paseo de la Cruz (East-West axis X: 200 -> 1000, Z ~ 795.5) */
            car[0] = 200.0f + prog * 800.0f;
            car[2] = 795.5f;
            car[3] = 90.0f;
        } else {
            /* Corridor 1: Av. José María Chávez (North-South axis X ~ 952.0, Z: 200 -> 1000) */
            car[0] = 952.0f;
            car[2] = 200.0f + prog * 800.0f;
            car[3] = 0.0f;
        }
    }
    return car_count;
}

