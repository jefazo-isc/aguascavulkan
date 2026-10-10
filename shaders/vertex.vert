#version 450

// Binding 0: atributos per-vertex
layout(location=0) in vec3 inPosition;
layout(location=1) in vec3 inNormal;
layout(location=2) in vec2 inTexCoord;
layout(location=3) in vec4 inColor;
layout(location=4) in float inEmission;

// Binding 1: datos per-instance  (mat4 model 64B + tint 16B + brake 4B + pad 12B = 96B)
layout(location=5) in mat4 inInstanceModel;   // ocupa locations 5,6,7,8
layout(location=9) in vec4 inInstanceTint;
layout(location=10) in float inInstanceBrake;

layout(push_constant) uniform PushConstants {
    mat4 mvp;
    mat4 model;
    vec4 sunDir;
    vec4 skyColor;
    vec4 timeParams;
} pc;

layout(location=0) out vec2 fragTexCoord;
layout(location=1) out vec4 fragColor;
layout(location=2) out float fragEmission;
layout(location=3) out vec3 fragNormal;
layout(location=4) out vec3 fragWorldPos;

void main(){
    // Si inInstanceModel[3][3] == 1.0 es identidad → geometría estática → usamos pc.model
    // Para coches la matrix es el transform real → distinta de identidad en traslación
    // Técnica: tint.a == 0.0 marca geometría estática (tint sin uso real se pone a 0)
    mat4 worldMat;
    vec4 finalColor;
    float finalEmission = inEmission;

    if (inInstanceTint.a < 0.5) {
        // Geometría estática: usar pc.model (identidad), tint ignorado
        worldMat = mat4(1.0); // identidad - posiciones ya en world space
        finalColor = inColor;
    } else {
        // Coche instanciado: aplicar transform del coche + modular color con tint
        worldMat = inInstanceModel;
        finalColor = inColor * vec4(inInstanceTint.rgb, 1.0);
        // Luz de frenos: si brake>0.5 y pixel es taillight (rojo, emission>0.5) aumentar emisión
        if (inInstanceBrake > 0.5 && inEmission > 0.5 && inColor.r > 0.7 && inColor.g < 0.2) {
            finalEmission = 2.5;
        }
    }

    vec4 worldPos = worldMat * vec4(inPosition, 1.0);
    gl_Position = pc.mvp * worldPos;
    fragWorldPos = worldPos.xyz;
    fragNormal = normalize(mat3(worldMat) * inNormal);
    fragTexCoord = inTexCoord;
    fragColor = finalColor;
    fragEmission = finalEmission;
}
