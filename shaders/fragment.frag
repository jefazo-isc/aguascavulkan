#version 450

layout(set=0, binding=0) uniform sampler2D satelliteTex;
layout(set=0, binding=1) uniform sampler2D facadeTex;

struct PointLight {
    vec4 posRadius;      // xyz: posición mundo (m), w: radio de alcance (m)
    vec4 colorIntensity; // rgb: color normalizado (0..1), w: intensidad luminosa
};

layout(set=0, binding=2) uniform LightingBlock {
    PointLight lights[32];
    int lightCount;
    float flashlightOn;
    float pad0;
    float pad1;
    vec4 flashPos; // xyz: pos, w: alcance
    vec4 flashDir; // xyz: dir adelante, w: cos(spot angle)
} lighting;

layout(push_constant) uniform PushConstants {
    mat4 mvp;
    mat4 model;
    vec4 sunDir;     // xyz: dirección del sol, w: intensidad ambiental
    vec4 skyColor;   // rgb: color del cielo, a: factor nocturno (0.0=día, 1.0=noche)
    vec4 timeParams; // x: simHour (0-24)
} pc;

layout(location=0) in vec2 fragTexCoord;
layout(location=1) in vec4 fragColor;
layout(location=2) in float fragEmission;
layout(location=3) in vec3 fragNormal;
layout(location=4) in vec3 fragWorldPos;

layout(location=0) out vec4 outColor;

// Procedural hash y noise para detalle micro de materiales en espacio de mundo
float hash21(vec2 p) {
    p = fract(p * vec2(234.34, 435.345));
    p += dot(p, p + 34.23);
    return fract(p.x * p.y);
}

float noise2D(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

// --- Shader de Cielo y Dispersión Atmosférica Procedural (Open-Source GLSL) ---
vec3 getAtmosphericSky(vec3 rayDir, vec3 sunDir) {
    float sunCos = dot(rayDir, sunDir);
    
    // Paletas de iluminación atmosférica
    vec3 skyDayTop     = vec3(0.20, 0.48, 0.88);   // Azul profundo de día
    vec3 skyDayHorizon = vec3(0.65, 0.78, 0.95);   // Horizonte claro
    vec3 sunsetColor   = vec3(0.95, 0.42, 0.15);   // Naranja cálido de atardecer
    vec3 skyNightTop   = vec3(0.01, 0.02, 0.06);   // Noche oscura
    vec3 skyNightHoriz = vec3(0.04, 0.07, 0.14);   // Horizonte nocturno
    
    float horizonFactor = max(0.0, 1.0 - abs(rayDir.y));
    float sunsetFactor  = clamp(1.0 - abs(sunDir.y * 3.0), 0.0, 1.0);
    
    vec3 daySky   = mix(skyDayHorizon, skyDayTop, max(0.0, rayDir.y));
    vec3 nightSky = mix(skyNightHoriz, skyNightTop, max(0.0, rayDir.y));
    
    float dayFactor = clamp(sunDir.y * 2.0 + 0.2, 0.0, 1.0);
    vec3 finalSky   = mix(nightSky, daySky, dayFactor);
    
    // Matiz naranja en el horizonte al amanecer/atardecer
    finalSky = mix(finalSky, sunsetColor, sunsetFactor * horizonFactor * dayFactor);
    
    // Resplandor del Sol
    if (sunCos > 0.995) {
        finalSky += vec3(1.0, 0.9, 0.7) * 1.8;
    }
    
    return finalSky;
}

void main(){
    // HUD debug overlay: emission >= 9.5 = quad 2D de pantalla (sin luces ni niebla)
    if(fragEmission >= 9.5){
        outColor = vec4(fragColor.rgb, fragColor.a);
        return;
    }

    float matID = fragColor.a;
    vec4 sat = texture(satelliteTex, fragTexCoord);
    vec4 fac = texture(facadeTex, fragTexCoord);
    vec3 N = normalize(fragNormal);
    vec3 L = normalize(pc.sunDir.xyz);
    
    float diff = max(dot(N, L), 0.0);
    float ambient = pc.sunDir.w;
    diff = ambient + (1.0 - ambient) * diff;

    vec4 base;
    if(matID < 0.1){
        // Terreno satélite puro (0.0): textura ortofotográfica de alta definición
        base = sat;
    } else if(matID < 0.5){
        // Azotea (0.35)
        base = mix(sat * 0.88, vec4(fragColor.rgb, 1.0), 0.15);
    } else if(matID > 0.55 && matID < 0.65){
        // Sombra proyectada (0.6)
        base = vec4(sat.rgb * 0.4 + fragColor.rgb * 0.2, 1.0);
    } else if(matID > 0.65 && matID < 0.85){
        // Tronco (0.7) y Follaje (0.8)
        base = vec4(fragColor.rgb, 1.0);
    } else if(matID > 0.92 && matID < 0.98){
        // NIVEL DE CALLE: Asfalto, banquetas de concreto, guarniciones (matID 0.95)
        vec3 col = fragColor.rgb;
        
        // Banqueta de concreto (color base claro ~0.7)
        if(col.r > 0.65 && col.g > 0.65 && col.b > 0.65 && abs(N.y) > 0.7) {
            vec2 tileCoord = fragWorldPos.xz / 1.5;
            vec2 grid = abs(fract(tileCoord - 0.5) - 0.5) / fwidth(tileCoord);
            float lineFactor = 1.0 - min(min(grid.x, grid.y), 1.0);
            float grain = noise2D(fragWorldPos.xz * 12.0) * 0.08 - 0.04;
            vec3 concrete = col * (0.96 + grain) - vec3(lineFactor * 0.18);
            base = vec4(concrete, 1.0);
        }
        // Asfalto vehicular (color base oscuro ~0.22)
        else if(col.r < 0.35 && col.g < 0.35 && col.b < 0.35 && abs(N.y) > 0.7) {
            float grain = noise2D(fragWorldPos.xz * 16.0) * 0.06;
            float aggregate = noise2D(fragWorldPos.xz * 4.0) * 0.04;
            vec3 asphalt = col + vec3(grain + aggregate - 0.05);
            base = vec4(asphalt, 1.0);
        }
        // Guarniciones pintadas, postes y semáforos
        else {
            float grain = noise2D(fragWorldPos.xz * 8.0) * 0.05;
            base = vec4(col + vec3(grain - 0.025), 1.0);
        }
    } else {
        // Fachadas (1.0) y Ventanas (0.9)
        base = mix(fac, vec4(fragColor.rgb, 1.0), 0.22);
    }
    
    // --- Cálculo de Luces Puntuales Dinámicas (Semáforos, Farolas, Beacons) ---
    vec3 pointLightContrib = vec3(0.0);
    for (int i = 0; i < lighting.lightCount; ++i) {
        vec3 lPos = lighting.lights[i].posRadius.xyz;
        float radius = lighting.lights[i].posRadius.w;
        vec3 lCol = lighting.lights[i].colorIntensity.rgb;
        float intensity = lighting.lights[i].colorIntensity.w;

        vec3 toLight = lPos - fragWorldPos;
        float dist = length(toLight);
        if (dist < radius) {
            vec3 dir = toLight / dist;
            float atten = clamp(1.0 - (dist / radius), 0.0, 1.0);
            atten = atten * atten; // Suave decaimiento cuadrático

            float nDotL = max(dot(N, dir), 0.0);
            if (abs(N.y) > 0.35) {
                nDotL = max(nDotL, 0.45); // Asfalto y banquetas capturan bien la luz
            }
            pointLightContrib += lCol * (intensity * atten * nDotL);
        }
    }

    // --- Linterna de Inspección del Jugador (Cono Spotlight) ---
    if (lighting.flashlightOn > 0.5) {
        vec3 toFrag = fragWorldPos - lighting.flashPos.xyz;
        float dist = length(toFrag);
        float flashRange = lighting.flashPos.w;
        if (dist < flashRange && dist > 0.2) {
            vec3 dir = toFrag / dist;
            float cosAngle = dot(dir, normalize(lighting.flashDir.xyz));
            float spotCutoff = lighting.flashDir.w; // 0.866 (~30 deg)
            if (cosAngle > spotCutoff) {
                float spotFactor = smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle);
                float atten = clamp(1.0 - (dist / flashRange), 0.0, 1.0);
                atten = atten * atten;
                float nDotL = max(dot(N, -dir), 0.0);
                if (abs(N.y) > 0.35) nDotL = max(nDotL, 0.45);
                pointLightContrib += vec3(1.0, 0.98, 0.90) * (4.0 * atten * spotFactor * nDotL);
            }
        }
    }

    // Aplicar iluminación difusa solar
    if (matID >= 0.1) {
        base.rgb *= diff;
    } else {
        base.rgb *= (ambient + 0.35 * diff);
    }

    // Integrar contribución de todas las luces del entorno (iluminación vial y urbana)
    base.rgb += pointLightContrib * (base.rgb * 1.5 + vec3(0.20));

    // Iluminación Emisiva Directa (Semáforos activos, beacons, ventanas nocturnas)
    float nightFactor = pc.skyColor.a;
    if (fragEmission >= 4.0) {
        // Lente de Semáforo ACTIVO: Deslumbrante, autoiluminado y visible nítidamente
        base.rgb = fragColor.rgb * (2.4 + fragEmission * 0.5);
    } else if (fragEmission > 0.5) {
        // Ventanas nocturnas y beacons
        vec3 glowCol = (matID > 0.92 && matID < 0.98) ? fragColor.rgb : vec3(1.0, 0.92, 0.6);
        base.rgb += (fragEmission * (1.0 + nightFactor * 1.8)) * glowCol;
    } else if (fragEmission > 0.0) {
        base.rgb += vec3(fragEmission * 0.4);
    }

    // Niebla con dispersión atmosférica del cielo
    float dist = gl_FragCoord.z / gl_FragCoord.w;
    float fog = clamp((dist - 300.0) / 2500.0, 0.0, 0.6);
    
    // Las estrellas y luces muy brillantes no se difuminan con niebla
    if (fragEmission >= 0.65 && dist > 1200.0) {
        fog = 0.0;
    }

    vec3 sky = getAtmosphericSky(-N, L);
    sky = mix(sky, pc.skyColor.rgb, 0.5);
    vec3 finalCol = mix(base.rgb, sky, fog * 0.5);

    outColor = vec4(finalCol, 1.0);
}
