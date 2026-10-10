#ifndef MATH_CAMERA_H
#define MATH_CAMERA_H

#include <math.h>

#define DEG2RAD(d) ((d) * 0.017453292519943295f)

// ==================================== 3D MATRIX & VECTOR MATH ====================================

typedef struct {
    float x, y, z;
} Vec3;

typedef struct {
    float m[16]; // column-major
} Mat4;

static inline Mat4 mat4_identity(void) {
    Mat4 res = {0};
    res.m[0] = 1.0f;
    res.m[5] = 1.0f;
    res.m[10] = 1.0f;
    res.m[15] = 1.0f;
    return res;
}

static inline Mat4 mat4_multiply(Mat4 a, Mat4 b) {
    Mat4 res = {0};
    for (int col = 0; col < 4; col++) {
        for (int row = 0; row < 4; row++) {
            float sum = 0.0f;
            for (int k = 0; k < 4; k++) {
                sum += a.m[k * 4 + row] * b.m[col * 4 + k];
            }
            res.m[col * 4 + row] = sum;
        }
    }
    return res;
}

static inline Mat4 mat4_perspective_vk(float fovy_rad, float aspect, float znear, float zfar) {
    Mat4 res = {0};
    float f = 1.0f / tanf(fovy_rad * 0.5f);
    res.m[0] = f / aspect;
    res.m[5] = -f; // Y invertido para el espacio de clip de Vulkan
    res.m[10] = zfar / (znear - zfar);
    res.m[11] = -1.0f;
    res.m[14] = (zfar * znear) / (znear - zfar);
    return res;
}

static inline Mat4 mat4_lookat(float eyeX, float eyeY, float eyeZ,
                        float centerX, float centerY, float centerZ,
                        float upX, float upY, float upZ) {
    float fx = centerX - eyeX;
    float fy = centerY - eyeY;
    float fz = centerZ - eyeZ;
    float flen = sqrtf(fx * fx + fy * fy + fz * fz);
    if (flen > 0.0f) { fx /= flen; fy /= flen; fz /= flen; }

    float sx = fy * upZ - fz * upY;
    float sy = fz * upX - fx * upZ;
    float sz = fx * upY - fy * upX;
    float slen = sqrtf(sx * sx + sy * sy + sz * sz);
    if (slen > 0.0f) { sx /= slen; sy /= slen; sz /= slen; }

    float ux = sy * fz - sz * fy;
    float uy = sz * fx - sx * fz;
    float uz = sx * fy - sy * fx;

    Mat4 res = mat4_identity();
    res.m[0] = sx;
    res.m[1] = ux;
    res.m[2] = -fx;
    res.m[3] = 0.0f;

    res.m[4] = sy;
    res.m[5] = uy;
    res.m[6] = -fy;
    res.m[7] = 0.0f;

    res.m[8] = sz;
    res.m[9] = uz;
    res.m[10] = -fz;
    res.m[11] = 0.0f;

    res.m[12] = -(sx * eyeX + sy * eyeY + sz * eyeZ);
    res.m[13] = -(ux * eyeX + uy * eyeY + uz * eyeZ);
    res.m[14] = fx * eyeX + fy * eyeY + fz * eyeZ;
    res.m[15] = 1.0f;

    return res;
}

// ==================================== SISTEMA DE CÁMARA LIBRE ====================================

typedef struct {
    Vec3 pos;
    float yaw;              // Ángulo horizontal en grados (-90 = mirando hacia -Z)
    float pitch;            // Ángulo vertical en grados (-89 a +89)
    float moveSpeed;        // Velocidad normal en unidades por segundo
    float sprintMultiplier; // Multiplicador con Shift
    float mouseSensitivity; // Sensibilidad del ratón
    int mouseCaptured;      // 1 si el cursor está capturado
} Camera;

extern Camera g_camera;

static inline void camera_get_vectors(const Camera* cam, Vec3* outForward, Vec3* outRight, Vec3* outUp) {
    float yawRad = DEG2RAD(cam->yaw);
    float pitchRad = DEG2RAD(cam->pitch);

    Vec3 f;
    f.x = cosf(pitchRad) * cosf(yawRad);
    f.y = sinf(pitchRad);
    f.z = cosf(pitchRad) * sinf(yawRad);
    float flen = sqrtf(f.x * f.x + f.y * f.y + f.z * f.z);
    if (flen > 0.0f) { f.x /= flen; f.y /= flen; f.z /= flen; }

    Vec3 r;
    r.x = -sinf(yawRad);
    r.y = 0.0f;
    r.z = cosf(yawRad);
    float rlen = sqrtf(r.x * r.x + r.z * r.z);
    if (rlen > 0.0f) { r.x /= rlen; r.z /= rlen; }

    Vec3 u;
    u.x = r.y * f.z - r.z * f.y;
    u.y = r.z * f.x - r.x * f.z;
    u.z = r.x * f.y - r.y * f.x;
    float ulen = sqrtf(u.x * u.x + u.y * u.y + u.z * u.z);
    if (ulen > 0.0f) { u.x /= ulen; u.y /= ulen; u.z /= ulen; }

    if (outForward) *outForward = f;
    if (outRight) *outRight = r;
    if (outUp) *outUp = u;
}

#endif // MATH_CAMERA_H
