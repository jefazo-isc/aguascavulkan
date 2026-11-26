// ============================================================================
// StreetVulkan WebGL2 Fallback Renderer (GLSL ES 3.00)
// Matches WebGPU PBR shader & uniform layout for universal browser compatibility
// ============================================================================

const VS_GLSL300 = `#version 300 es
precision highp float;

layout(location=0) in vec3 inPosition;
layout(location=1) in vec3 inNormal;
layout(location=2) in vec2 inTexCoord;
layout(location=3) in vec4 inColor;
layout(location=4) in float inEmission;

struct PointLight {
    vec4 posRadius;
    vec4 colorIntensity;
};

layout(std140) uniform LightingUniforms {
    mat4 u_mvp;
    mat4 u_model;
    vec4 u_sunDir;
    vec4 u_skyColor;
    vec4 u_camPos;
    vec4 u_flashPos;
    vec4 u_flashDir;
    vec4 u_params;
    PointLight u_lights[64];
};

out vec2 fragTexCoord;
out vec4 fragColor;
out float fragEmission;
out vec3 fragNormal;
out vec3 fragWorldPos;

void main() {
    vec4 worldPos = u_model * vec4(inPosition, 1.0);
    gl_Position = u_mvp * worldPos;
    fragWorldPos = worldPos.xyz;
    vec3 n = (u_model * vec4(inNormal, 0.0)).xyz;
    float nLenSq = dot(n, n);
    fragNormal = (nLenSq > 1e-10) ? normalize(n) : vec3(0.0, 1.0, 0.0);
    fragTexCoord = inTexCoord;
    fragColor = inColor;
    fragEmission = inEmission;
}
`;

// Instanced vehicles: 96-byte CarInstanceData stream (mat4 model, vec4 tint, float brake, pad[3])
// mirroring shaders/vertex.vert. Shares the FS_GLSL300 fragment stage (matID 2.0 = vehicle).
const VS_VEHICLE_GLSL300 = `#version 300 es
precision highp float;

layout(location=0) in vec3 inPosition;
layout(location=1) in vec3 inNormal;
layout(location=2) in vec2 inTexCoord;
layout(location=3) in vec4 inColor;
layout(location=4) in float inEmission;
layout(location=5) in vec4 inModel0;
layout(location=6) in vec4 inModel1;
layout(location=7) in vec4 inModel2;
layout(location=8) in vec4 inModel3;
layout(location=9) in vec4 inTint;
layout(location=10) in float inBrake;

struct PointLight {
    vec4 posRadius;
    vec4 colorIntensity;
};

layout(std140) uniform LightingUniforms {
    mat4 u_mvp;
    mat4 u_model;
    vec4 u_sunDir;
    vec4 u_skyColor;
    vec4 u_camPos;
    vec4 u_flashPos;
    vec4 u_flashDir;
    vec4 u_params;
    PointLight u_lights[64];
};

out vec2 fragTexCoord;
out vec4 fragColor;
out float fragEmission;
out vec3 fragNormal;
out vec3 fragWorldPos;

void main() {
    mat4 worldMat = mat4(inModel0, inModel1, inModel2, inModel3);
    vec4 worldPos = worldMat * vec4(inPosition, 1.0);
    gl_Position = u_mvp * worldPos;
    fragWorldPos = worldPos.xyz;
    fragNormal = normalize(mat3(worldMat) * inNormal);
    fragTexCoord = inTexCoord;

    // Tint only the body paint: keep lights, black rubber/trim and glass intact
    vec3 carCol = inColor.rgb;
    bool isLight = inEmission > 0.4;
    bool isTrim = inColor.r < 0.28 && inColor.g < 0.28 && inColor.b < 0.28;
    bool isGlass = inColor.b > 0.55 && inColor.r < 0.45 && inColor.g > 0.45;
    if (!isLight && !isTrim && !isGlass) {
        carCol = inColor.rgb * inTint.rgb * 1.30;
    }
    fragColor = vec4(carCol, 2.0);

    fragEmission = inEmission;
    if (inBrake > 0.5 && inEmission > 0.4 && inColor.r > 0.6 && inColor.g < 0.25) {
        fragEmission = 3.0;
    }
}
`;

const FS_GLSL300 = `#version 300 es
precision highp float;
precision highp int;

struct PointLight {
    vec4 posRadius;
    vec4 colorIntensity;
};

layout(std140) uniform LightingUniforms {
    mat4 u_mvp;
    mat4 u_model;
    vec4 u_sunDir;
    vec4 u_skyColor;
    vec4 u_camPos;
    vec4 u_flashPos;
    vec4 u_flashDir;
    vec4 u_params;
    PointLight u_lights[64];
};

uniform sampler2D satelliteTex;
uniform sampler2D facadeTex;

in vec2 fragTexCoord;
in vec4 fragColor;
in float fragEmission;
in vec3 fragNormal;
in vec3 fragWorldPos;

out vec4 outColor;

const float PI = 3.14159265358979323846;

vec3 srgbToLinear(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(2.2));
}

vec3 linearToSrgb(vec3 c) {
    return pow(clamp(c, vec3(0.0), vec3(1.0)), vec3(1.0 / 2.2));
}

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

float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = PI * denom * denom;
    return a2 / max(denom, 0.000001);
}

float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    return NdotV / max(NdotV * (1.0 - k) + k, 0.000001);
}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    return GeometrySchlickGGX(NdotV, roughness) * GeometrySchlickGGX(NdotL, roughness);
}

vec3 FresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 FresnelSchlickRoughness(float cosTheta, vec3 F0, float roughness) {
    return F0 + (max(vec3(1.0 - roughness), F0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 getAtmosphericSky(vec3 rayDir, vec3 sunDir) {
    float sunCos = dot(rayDir, sunDir);
    vec3 skyDayTop = vec3(0.18, 0.44, 0.85);
    vec3 skyDayHorizon = vec3(0.65, 0.78, 0.95);
    vec3 sunsetColor = vec3(0.95, 0.40, 0.12);
    vec3 skyNightTop = vec3(0.01, 0.02, 0.05);
    vec3 skyNightHoriz = vec3(0.03, 0.06, 0.12);

    float horizonFactor = max(0.0, 1.0 - abs(rayDir.y));
    float sunsetFactor = clamp(1.0 - abs(sunDir.y * 3.0), 0.0, 1.0);

    vec3 daySky = mix(skyDayHorizon, skyDayTop, max(0.0, rayDir.y));
    vec3 nightSky = mix(skyNightHoriz, skyNightTop, max(0.0, rayDir.y));

    float dayFactor = clamp(sunDir.y * 2.0 + 0.2, 0.0, 1.0);
    vec3 finalSky = mix(nightSky, daySky, dayFactor);
    finalSky = mix(finalSky, sunsetColor, sunsetFactor * horizonFactor * dayFactor);

    if (sunCos > 0.996) {
        finalSky += vec3(1.0, 0.95, 0.8) * 3.5;
    }
    return finalSky;
}

vec3 ACESFilm(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    if (fragEmission >= 9.5) {
        outColor = fragColor;
        return;
    }

    float matID = fragColor.a;
    vec4 satRaw = texture(satelliteTex, fragTexCoord);
    vec4 facRaw = texture(facadeTex, fragTexCoord);
    vec4 sat = vec4(srgbToLinear(satRaw.rgb), satRaw.a);
    vec4 fac = vec4(srgbToLinear(facRaw.rgb), facRaw.a);

    vec3 camPos = u_camPos.xyz;
    vec3 N = normalize(fragNormal);
    vec3 toCam = camPos - fragWorldPos;
    float camDistSq = dot(toCam, toCam);
    vec3 V = (camDistSq > 1e-10) ? (toCam * inversesqrt(camDistSq)) : vec3(0.0, 1.0, 0.0);

    if (matID > 1.25 && matID < 1.35) {
        outColor = vec4(linearToSrgb(fac.rgb), 1.0);
        return;
    }

    if (matID > 0.65 && matID < 0.85) {
        if (dot(N, V) < 0.0) N = -N;
    }

    vec3 albedo = fragColor.rgb;
    float roughness = 0.85;
    float metallic = 0.0;

    if (matID >= 1.5) {
        albedo = fragColor.rgb;
        if (fragEmission < 0.4) {
            if (fragColor.r < 0.25 && fragColor.g < 0.25 && fragColor.b < 0.25) {
                roughness = 0.90;
                metallic = 0.02;
            } else if (fragColor.b > 0.50 && fragColor.r < 0.45) {
                roughness = 0.08;
                metallic = 0.20;
            } else {
                roughness = 0.18;
                metallic = 0.65;
            }
        } else {
            roughness = 0.35;
            metallic = 0.0;
        }
    } else if (matID < 0.1) {
        // Height-based terrain coloring with topographic shading
        float h = fragWorldPos.y;
        // Aguascalientes relative terrain: valleys ~-25m, hills ~+25m from base_elevation
        float t = clamp((h + 25.0) / 50.0, 0.0, 1.0);
        // Natural terrain gradient: low=green valley → mid=brown earth → high=light rock
        vec3 valleyGreen = vec3(0.22, 0.32, 0.14);
        vec3 midEarth    = vec3(0.38, 0.30, 0.18);
        vec3 hillRock    = vec3(0.52, 0.48, 0.40);
        vec3 terrainBase;
        if (t < 0.5) {
            terrainBase = mix(valleyGreen, midEarth, t * 2.0);
        } else {
            terrainBase = mix(midEarth, hillRock, (t - 0.5) * 2.0);
        }
        // Add procedural noise for natural variation
        float terrainNoise = noise2D(fragWorldPos.xz * 0.12) * 0.06 - 0.03;
        float detailNoise = noise2D(fragWorldPos.xz * 0.8) * 0.04 - 0.02;
        // Subtle contour lines every 5 meters
        float contourLine = 1.0 - smoothstep(0.0, 0.3, abs(fract(h / 5.0) - 0.5) * 2.0) * 0.12;
        albedo = clamp(terrainBase + vec3(terrainNoise + detailNoise), vec3(0.02), vec3(0.98)) * contourLine;
        // Blend with satellite texture for areas where it has real data
        albedo = mix(albedo, sat.rgb * 0.9 + vec3(terrainNoise), 0.15);
        roughness = 0.92;
        metallic = 0.0;
    } else if (matID < 0.5) {
        albedo = mix(sat.rgb * 0.88, fragColor.rgb, 0.15);
        roughness = 0.80;
        metallic = 0.05;
    } else if (matID > 0.55 && matID < 0.65) {
        albedo = sat.rgb * 0.4 + fragColor.rgb * 0.2;
        roughness = 0.95;
        metallic = 0.0;
    } else if (matID > 0.65 && matID < 0.75) {
        albedo = fac.rgb * (fragColor.rgb * 1.45);
        roughness = 0.94;
        metallic = 0.0;
    } else if (matID >= 0.75 && matID < 0.85) {
        albedo = fragColor.rgb;
        roughness = 0.90;
        metallic = 0.0;
    } else if (matID > 0.92 && matID < 0.98) {
        vec3 col = fragColor.rgb;
        if (col.r > 0.60 && col.g > 0.60 && col.b > 0.55 && abs(N.y) > 0.7) {
            vec2 tileCoord = fragWorldPos.xz / 1.5;
            vec2 grid = abs(fract(tileCoord - 0.5) - 0.5) / max(fwidth(tileCoord), vec2(1e-4));
            float lineFactor = 1.0 - min(min(grid.x, grid.y), 1.0);
            float grain = noise2D(fragWorldPos.xz * 12.0) * 0.06 - 0.03;
            vec3 concreteBase = vec3(0.35, 0.34, 0.32);
            albedo = mix(concreteBase, col * 0.55, 0.25) * (0.95 + grain) - vec3(lineFactor * 0.12);
            roughness = 0.88;
            metallic = 0.0;
        } else if (col.r < 0.38 && col.g < 0.38 && col.b < 0.40 && abs(N.y) > 0.7) {
            float grain = noise2D(fragWorldPos.xz * 16.0) * 0.04;
            float aggregate = noise2D(fragWorldPos.xz * 4.0) * 0.03;
            vec3 darkTarmac = vec3(0.09, 0.09, 0.10);
            albedo = mix(darkTarmac, col, 0.20) + vec3(grain + aggregate - 0.025);
            roughness = 0.94;
            metallic = 0.01;
        } else if (col.r > 0.45 && col.g > 0.45 && abs(N.y) <= 0.7) {
            float flute = sin((fragWorldPos.x + fragWorldPos.z) * 10.47) * 0.5 + 0.5;
            float fluteShadow = smoothstep(0.15, 0.85, flute) * 0.32 + 0.68;
            float grain = noise2D(vec2(fragWorldPos.x + fragWorldPos.z, fragWorldPos.y) * 4.0) * 0.06 - 0.03;
            vec3 wallBaseCol = vec3(0.48, 0.46, 0.43);
            albedo = (mix(wallBaseCol, col, 0.4) + vec3(grain)) * fluteShadow;
            roughness = 0.88;
            metallic = 0.01;
        } else {
            if (col.r < 0.55 && col.g < 0.55 && col.b < 0.55 && abs(N.y) <= 0.7) {
                albedo = col * 0.80;
                roughness = 0.85;
                metallic = 0.0;
            } else {
                float grain = noise2D(fragWorldPos.xz * 8.0) * 0.04;
                albedo = col + vec3(grain - 0.02);
                roughness = 0.55;
                metallic = 0.10;
            }
        }
    } else if (matID >= 0.98 && matID <= 1.02 && fragEmission < 0.1) {
        if (fac.a < 0.25 && fragColor.r > 0.92 && fragColor.g > 0.92 && fragColor.b > 0.92) {
            discard;
        }
        albedo = mix(fac.rgb, fragColor.rgb, 0.16);
        roughness = 0.70;
        metallic = 0.05;
    } else if (matID >= 1.12 && matID <= 1.22) {
        if (matID < 1.16) {
            float stucco = noise2D(fragWorldPos.xz * 6.0 + fragWorldPos.y * 6.0) * 0.025 - 0.012;
            albedo = clamp(fragColor.rgb + vec3(stucco), vec3(0.02), vec3(0.98));
            roughness = 0.62;
            metallic = 0.04;
        } else {
            vec2 uv = clamp(fragTexCoord, vec2(0.0), vec2(1.0));
            bool isRail = (uv.x < 0.035 || uv.x > 0.965);
            bool isHood = (uv.y < 0.13);
            bool isBottomBar = (uv.y > 0.93);
            if (isRail || isHood || isBottomBar) {
                albedo = isHood ? vec3(0.24, 0.27, 0.28) : vec3(0.32, 0.35, 0.36);
                roughness = 0.42;
                metallic = 0.65;
            } else {
                float slatPhase = fract(uv.y * 26.0);
                float rib = sin(slatPhase * 6.2831853) * 0.08;
                float seam = smoothstep(0.08, 0.16, slatPhase) * (1.0 - smoothstep(0.86, 0.96, slatPhase));
                float metalGrain = noise2D(vec2(uv.x * 32.0, uv.y * 120.0)) * 0.03 - 0.015;
                vec3 steelCol = vec3(0.48, 0.51, 0.53) * (0.78 + 0.22 * seam) + vec3(rib + metalGrain);
                if (abs(uv.x - 0.5) < 0.018 && uv.y > 0.80 && uv.y < 0.91) {
                    steelCol = vec3(0.18, 0.20, 0.21);
                }
                albedo = clamp(steelCol, vec3(0.12), vec3(0.82));
                roughness = 0.34;
                metallic = 0.74;
            }
        }
    } else {
        albedo = fragColor.rgb;
        roughness = 0.75;
        metallic = 0.0;
    }

    vec3 F0 = mix(vec3(0.04), albedo, metallic);
    vec3 Lo = vec3(0.0);

    vec3 L_sun = normalize(u_sunDir.xyz);
    vec3 H_sun = normalize(V + L_sun);
    float NdotL_sun = max(dot(N, L_sun), 0.0);
    if (NdotL_sun > 0.0) {
        float NDF = DistributionGGX(N, H_sun, roughness);
        float G = GeometrySmith(N, V, L_sun, roughness);
        vec3 F = FresnelSchlick(max(dot(H_sun, V), 0.0), F0);
        vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_sun + 0.0001), vec3(0.0), vec3(0.85));
        vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
        vec3 sunRadiance = vec3(1.2, 1.15, 1.05) * max(u_sunDir.y * 1.5 + 0.2, 0.0);
        Lo += (kD * albedo / PI + specular) * sunRadiance * NdotL_sun;
    }

    int lightCount = min(int(u_params.x), 64);
    for (int i = 0; i < 64; ++i) {
        if (i >= lightCount) break;
        float radius = u_lights[i].posRadius.w;
        float intensity = u_lights[i].colorIntensity.w;
        if (radius <= 0.0 || intensity <= 0.0) continue;

        vec3 toLight = u_lights[i].posRadius.xyz - fragWorldPos;
        float distSq = dot(toLight, toLight);
        if (distSq >= radius * radius || distSq <= 1e-6) continue;

        float d = sqrt(distSq);
        vec3 L_point = toLight / d;
        float NdotL_p = max(dot(N, L_point), 0.0);
        if (abs(N.y) > 0.35) NdotL_p = max(NdotL_p, 0.35);
        if (NdotL_p <= 0.0) continue;

        vec3 lCol = u_lights[i].colorIntensity.rgb;
        vec3 H_point = normalize(V + L_point);
        float atten = clamp(1.0 - (d / radius), 0.0, 1.0);
        atten = atten * atten;

        float NDF = DistributionGGX(N, H_point, roughness);
        float G = GeometrySmith(N, V, L_point, roughness);
        vec3 F = FresnelSchlick(max(dot(H_point, V), 0.0), F0);
        vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_p + 0.0001), vec3(0.0), vec3(0.85));
        vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
        vec3 radiance = lCol * (intensity * atten);
        Lo += (kD * albedo / PI + specular) * radiance * NdotL_p;
    }

    if (u_params.y > 0.5) {
        vec3 toFrag = fragWorldPos - u_flashPos.xyz;
        float distSq = dot(toFrag, toFrag);
        float flashRange = u_flashPos.w;
        if (distSq < flashRange * flashRange && distSq > 0.04) {
            float d = sqrt(distSq);
            vec3 L_flash = normalize(-toFrag);
            vec3 dir = toFrag / d;
            float cosAngle = dot(dir, normalize(u_flashDir.xyz));
            float spotCutoff = u_flashDir.w;
            if (cosAngle > spotCutoff) {
                float spotFactor = smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle);
                float atten = clamp(1.0 - (d / flashRange), 0.0, 1.0);
                atten = atten * atten;
                float NdotL_f = max(dot(N, L_flash), 0.0);
                if (abs(N.y) > 0.35) NdotL_f = max(NdotL_f, 0.35);
                if (NdotL_f > 0.0) {
                    vec3 H_flash = normalize(V + L_flash);
                    float NDF = DistributionGGX(N, H_flash, roughness);
                    float G = GeometrySmith(N, V, L_flash, roughness);
                    vec3 F = FresnelSchlick(max(dot(H_flash, V), 0.0), F0);
                    vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_f + 0.0001), vec3(0.0), vec3(0.85));
                    vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
                    vec3 radiance = vec3(1.0, 0.98, 0.92) * (5.0 * atten * spotFactor);
                    Lo += (kD * albedo / PI + specular) * radiance * NdotL_f;
                }
            }
        }
    }

    vec3 ambientSky = u_skyColor.rgb * u_sunDir.w;
    vec3 F_ambient = FresnelSchlickRoughness(max(dot(N, V), 0.0), F0, roughness);
    vec3 kD_amb = (vec3(1.0) - F_ambient) * (1.0 - metallic);
    vec3 ambient = (kD_amb * albedo * ambientSky * 0.85) + (F_ambient * ambientSky * (1.0 - roughness) * 0.20);

    vec3 color = ambient + Lo;

    float dist = length(camPos - fragWorldPos);
    float fog = clamp((dist - 2000.0) / 16000.0, 0.0, 0.50);
    vec3 rayDir = (dist > 1e-4) ? normalize(fragWorldPos - camPos) : vec3(0.0, 1.0, 0.0);
    vec3 sky = getAtmosphericSky(rayDir, L_sun);
    sky = mix(sky, u_skyColor.rgb, 0.4);
    color = mix(color, sky, fog * 0.45);

    float nightFactor = u_skyColor.a;
    vec3 emissionColor = vec3(0.0);
    if (fragEmission >= 4.0) {
        float pulse = 0.92 + 0.08 * sin(u_params.z * 3.0);
        emissionColor = fragColor.rgb * ((4.0 + fragEmission * 1.5) * pulse);
    } else if (fragEmission > 0.5) {
        bool keepColor = ((matID > 0.92 && matID < 0.98) || (matID >= 1.12 && matID <= 1.22));
        vec3 glowCol = keepColor ? fragColor.rgb : vec3(1.0, 0.94, 0.72);
        float distPreserve = clamp(dist / 200.0, 1.0, 3.5);
        emissionColor = glowCol * (fragEmission * (1.8 + nightFactor * 3.0) * distPreserve);
    } else if (fragEmission > 0.0) {
        emissionColor = fragColor.rgb * (fragEmission * (1.0 + nightFactor * 2.2));
    }
    color += emissionColor;

    color = ACESFilm(color);
    color = linearToSrgb(color);
    outColor = vec4(color, 1.0);
}
`;

const VS_BUILDING_GLSL300 = `#version 300 es
precision highp float;

layout(location=0) in vec3 inPosition;
layout(location=1) in vec3 inNormal;
layout(location=2) in vec2 inTexCoord;
layout(location=3) in vec4 inColor;
layout(location=4) in float inEmission;

struct PointLight {
    vec4 posRadius;
    vec4 colorIntensity;
};

layout(std140) uniform LightingUniforms {
    mat4 u_mvp;
    mat4 u_model;
    vec4 u_sunDir;
    vec4 u_skyColor;
    vec4 u_camPos;
    vec4 u_flashPos;
    vec4 u_flashDir;
    vec4 u_params;
    PointLight u_lights[64];
};

out vec2 fragTexCoord;
out vec4 fragColor;
out float fragEmission;
out vec3 fragNormal;
out vec3 fragWorldPos;

void main() {
    vec4 worldPos = u_model * vec4(inPosition, 1.0);
    gl_Position = u_mvp * worldPos;
    fragWorldPos = worldPos.xyz;
    vec3 n = (u_model * vec4(inNormal, 0.0)).xyz;
    float nLenSq = dot(n, n);
    fragNormal = (nLenSq > 1e-10) ? normalize(n) : vec3(0.0, 1.0, 0.0);
    fragTexCoord = inTexCoord;
    fragColor = inColor;
    fragEmission = inEmission;
}
`;

const FS_BUILDING_GLSL300 = `#version 300 es
precision highp float;
precision highp int;

struct PointLight {
    vec4 posRadius;
    vec4 colorIntensity;
};

layout(std140) uniform LightingUniforms {
    mat4 u_mvp;
    mat4 u_model;
    vec4 u_sunDir;
    vec4 u_skyColor;
    vec4 u_camPos;
    vec4 u_flashPos;
    vec4 u_flashDir;
    vec4 u_params;
    PointLight u_lights[64];
};

uniform sampler2D satelliteTex;
uniform sampler2D facadeTex;

in vec2 fragTexCoord;
in vec4 fragColor;
in float fragEmission;
in vec3 fragNormal;
in vec3 fragWorldPos;

out vec4 outColor;

const float PI = 3.14159265358979323846;

vec3 srgbToLinear(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(2.2));
}

vec3 linearToSrgb(vec3 c) {
    return pow(clamp(c, vec3(0.0), vec3(1.0)), vec3(1.0 / 2.2));
}

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

float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = PI * denom * denom;
    return a2 / max(denom, 0.000001);
}

float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    return NdotV / max(NdotV * (1.0 - k) + k, 0.000001);
}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    return GeometrySchlickGGX(NdotV, roughness) * GeometrySchlickGGX(NdotL, roughness);
}

vec3 FresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 FresnelSchlickRoughness(float cosTheta, vec3 F0, float roughness) {
    return F0 + (max(vec3(1.0 - roughness), F0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 getAtmosphericSky(vec3 rayDir, vec3 sunDir) {
    float sunCos = dot(rayDir, sunDir);
    vec3 skyDayTop = vec3(0.18, 0.44, 0.85);
    vec3 skyDayHorizon = vec3(0.65, 0.78, 0.95);
    vec3 sunsetColor = vec3(0.95, 0.40, 0.12);
    vec3 skyNightTop = vec3(0.01, 0.02, 0.05);
    vec3 skyNightHoriz = vec3(0.03, 0.06, 0.12);

    float horizonFactor = max(0.0, 1.0 - abs(rayDir.y));
    float sunsetFactor = clamp(1.0 - abs(sunDir.y * 3.0), 0.0, 1.0);
    vec3 daySky = mix(skyDayTop, skyDayHorizon, horizonFactor * 0.7);
    daySky = mix(daySky, sunsetColor, sunsetFactor * 0.5 * horizonFactor);

    vec3 nightSky = mix(skyNightTop, skyNightHoriz, horizonFactor * 0.8);
    float sunAltitude = clamp(sunDir.y * 2.0 + 0.2, 0.0, 1.0);
    vec3 sky = mix(nightSky, daySky, sunAltitude);

    if (sunCos > 0.9995 && sunDir.y > -0.05) {
        sky += vec3(8.0, 7.5, 6.0);
    } else if (sunCos > 0.992 && sunDir.y > -0.05) {
        float flare = (sunCos - 0.992) / (0.9995 - 0.992);
        sky += vec3(1.2, 0.95, 0.6) * (flare * flare);
    }
    return sky;
}

vec3 ACESFilm(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec4 satRaw = texture(satelliteTex, fragTexCoord);
    vec4 facRaw = texture(facadeTex, fragTexCoord);
    vec4 sat = vec4(srgbToLinear(satRaw.rgb), satRaw.a);
    vec4 fac = vec4(srgbToLinear(facRaw.rgb), facRaw.a);

    if (fragEmission >= 9.5) {
        outColor = fragColor;
        return;
    }

    float matID = fragColor.a;
    vec3 camPos = u_camPos.xyz;
    vec3 N = normalize(fragNormal);
    vec3 toCam = camPos - fragWorldPos;
    float camDistSq = dot(toCam, toCam);
    vec3 V = (camDistSq > 1e-10) ? toCam * inversesqrt(camDistSq) : vec3(0.0, 1.0, 0.0);

    vec3 albedo = fragColor.rgb;
    float roughness = 0.72;
    float metallic = 0.04;

    // 1. Building Roofs (matID < 0.50, nominally 0.35)
    if (matID < 0.50) {
        albedo = mix(sat.rgb * 0.88, fragColor.rgb, 0.15);
        roughness = 0.80;
        metallic = 0.05;
    }
    // 2. Textured Atlas Facades (0.98 <= matID <= 1.02)
    else if (matID >= 0.98 && matID <= 1.02 && fragEmission < 0.1) {
        if (fac.a < 0.25 && fragColor.r > 0.92 && fragColor.g > 0.92 && fragColor.b > 0.92) {
            discard;
        }
        albedo = mix(fac.rgb, fragColor.rgb, 0.16);
        roughness = 0.68;
        metallic = 0.05;
    }
    // 3. Procedural Rolcar Architecture: Stucco (1.14) & Rolling Shutters (1.18)
    else if (matID >= 1.12 && matID <= 1.22) {
        if (matID < 1.16) {
            float stucco = noise2D(fragWorldPos.xz * 6.0 + vec2(fragWorldPos.y * 6.0)) * 0.025 - 0.012;
            albedo = clamp(fragColor.rgb + vec3(stucco), vec3(0.02), vec3(0.98));
            roughness = 0.62;
            metallic = 0.04;
        } else {
            vec2 uv = clamp(fragTexCoord, vec2(0.0), vec2(1.0));
            bool isRail = (uv.x < 0.035 || uv.x > 0.965);
            bool isHood = (uv.y < 0.13);
            bool isBottomBar = (uv.y > 0.93);
            if (isRail || isHood || isBottomBar) {
                albedo = isHood ? vec3(0.24, 0.27, 0.28) : vec3(0.32, 0.35, 0.36);
                roughness = 0.42;
                metallic = 0.65;
            } else {
                float slatPhase = fract(uv.y * 26.0);
                float rib = sin(slatPhase * 6.2831853) * 0.08;
                float seam = smoothstep(0.08, 0.16, slatPhase) * (1.0 - smoothstep(0.86, 0.96, slatPhase));
                float metalGrain = noise2D(vec2(uv.x * 32.0, uv.y * 120.0)) * 0.03 - 0.015;
                vec3 steelCol = vec3(0.48, 0.51, 0.53) * (0.78 + 0.22 * seam) + vec3(rib + metalGrain);
                if (abs(uv.x - 0.5) < 0.018 && uv.y > 0.80 && uv.y < 0.91) {
                    steelCol = vec3(0.18, 0.20, 0.21);
                }
                albedo = clamp(steelCol, vec3(0.12), vec3(0.82));
                roughness = 0.34;
                metallic = 0.74;
            }
        }
    } else {
        albedo = fragColor.rgb;
        roughness = 0.75;
        metallic = 0.0;
    }

    vec3 F0 = mix(vec3(0.04), albedo, metallic);
    vec3 Lo = vec3(0.0);

    vec3 L_sun = normalize(u_sunDir.xyz);
    vec3 H_sun = normalize(V + L_sun);
    float NdotL_sun = max(dot(N, L_sun), 0.0);
    if (NdotL_sun > 0.0) {
        float NDF = DistributionGGX(N, H_sun, roughness);
        float G = GeometrySmith(N, V, L_sun, roughness);
        vec3 F = FresnelSchlick(max(dot(H_sun, V), 0.0), F0);
        vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_sun + 0.0001), vec3(0.0), vec3(0.85));
        vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
        vec3 sunRadiance = vec3(1.2, 1.15, 1.05) * max(u_sunDir.y * 1.5 + 0.2, 0.0);
        Lo += (kD * albedo / PI + specular) * sunRadiance * NdotL_sun;
    }

    int lightCount = min(int(u_params.x), 64);
    for (int i = 0; i < 64; ++i) {
        if (i >= lightCount) break;
        float radius = u_lights[i].posRadius.w;
        float intensity = u_lights[i].colorIntensity.w;
        if (radius <= 0.0 || intensity <= 0.0) continue;

        vec3 toLight = u_lights[i].posRadius.xyz - fragWorldPos;
        float distSq = dot(toLight, toLight);
        if (distSq >= radius * radius || distSq <= 1e-6) continue;

        float d = sqrt(distSq);
        vec3 L_point = toLight / d;
        float NdotL_p = max(dot(N, L_point), 0.0);
        if (abs(N.y) > 0.35) NdotL_p = max(NdotL_p, 0.35);
        if (NdotL_p <= 0.0) continue;

        vec3 lCol = u_lights[i].colorIntensity.rgb;
        vec3 H_point = normalize(V + L_point);
        float atten = clamp(1.0 - (d / radius), 0.0, 1.0);
        atten = atten * atten;

        float NDF = DistributionGGX(N, H_point, roughness);
        float G = GeometrySmith(N, V, L_point, roughness);
        vec3 F = FresnelSchlick(max(dot(H_point, V), 0.0), F0);
        vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_p + 0.0001), vec3(0.0), vec3(0.85));
        vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
        vec3 radiance = lCol * (intensity * atten);
        Lo += (kD * albedo / PI + specular) * radiance * NdotL_p;
    }

    if (u_params.y > 0.5) {
        vec3 toFrag = fragWorldPos - u_flashPos.xyz;
        float distSq = dot(toFrag, toFrag);
        float flashRange = u_flashPos.w;
        if (distSq < flashRange * flashRange && distSq > 0.04) {
            float d = sqrt(distSq);
            vec3 L_flash = normalize(-toFrag);
            vec3 dir = toFrag / d;
            float cosAngle = dot(dir, normalize(u_flashDir.xyz));
            float spotCutoff = u_flashDir.w;
            if (cosAngle > spotCutoff) {
                float spotFactor = smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle);
                float atten = clamp(1.0 - (d / flashRange), 0.0, 1.0);
                atten = atten * atten;
                float NdotL_f = max(dot(N, L_flash), 0.0);
                if (abs(N.y) > 0.35) NdotL_f = max(NdotL_f, 0.35);
                if (NdotL_f > 0.0) {
                    vec3 H_flash = normalize(V + L_flash);
                    float NDF = DistributionGGX(N, H_flash, roughness);
                    float G = GeometrySmith(N, V, L_flash, roughness);
                    vec3 F = FresnelSchlick(max(dot(H_flash, V), 0.0), F0);
                    vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_f + 0.0001), vec3(0.0), vec3(0.85));
                    vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
                    vec3 radiance = vec3(1.0, 0.98, 0.92) * (5.0 * atten * spotFactor);
                    Lo += (kD * albedo / PI + specular) * radiance * NdotL_f;
                }
            }
        }
    }

    vec3 ambientSky = u_skyColor.rgb * u_sunDir.w;
    vec3 F_ambient = FresnelSchlickRoughness(max(dot(N, V), 0.0), F0, roughness);
    vec3 kD_amb = (vec3(1.0) - F_ambient) * (1.0 - metallic);
    vec3 ambient = (kD_amb * albedo * ambientSky * 0.85) + (F_ambient * ambientSky * (1.0 - roughness) * 0.20);

    vec3 color = ambient + Lo;

    float dist = length(camPos - fragWorldPos);
    float fog = clamp((dist - 2000.0) / 16000.0, 0.0, 0.50);
    vec3 rayDir = (dist > 1e-4) ? normalize(fragWorldPos - camPos) : vec3(0.0, 1.0, 0.0);
    vec3 sky = getAtmosphericSky(rayDir, L_sun);
    sky = mix(sky, u_skyColor.rgb, 0.4);
    color = mix(color, sky, fog * 0.45);

    float nightFactor = u_skyColor.a;
    vec3 emissionColor = vec3(0.0);
    if (fragEmission >= 4.0) {
        float pulse = 0.92 + 0.08 * sin(u_params.z * 3.0);
        emissionColor = fragColor.rgb * ((4.0 + fragEmission * 1.5) * pulse);
    } else if (fragEmission > 0.5) {
        bool keepColor = (matID >= 1.12 && matID <= 1.22);
        vec3 glowCol = keepColor ? fragColor.rgb : vec3(1.0, 0.94, 0.72);
        float distPreserve = clamp(dist / 200.0, 1.0, 3.5);
        emissionColor = glowCol * (fragEmission * (1.8 + nightFactor * 3.0) * distPreserve);
    } else if (fragEmission > 0.0) {
        emissionColor = fragColor.rgb * (fragEmission * (1.0 + nightFactor * 2.2));
    }
    color += emissionColor;

    color = ACESFilm(color);
    color = linearToSrgb(color);
    outColor = vec4(color, 1.0);
}
`;

export class WebGL2Renderer {
    constructor() {
        this.backendName = 'WebGL2';
        this.gpuName = 'WebGL2 GPU';
        this.canvas = null;
        this.gl = null;
        this.program = null;
        this.buildingProgram = null;
        this.vehicleProgram = null;
        this.vehicleMeshes = [];
        this.vehicleInstanceBuf = null;
        this.vehicleInstanceBytes = 0;
        this.ubo = null;
        this.satelliteTex = null;
        this.facadeTex = null;
        this.sectors = new Map();
    }

    _compileShader(gl, type, source) {
        const shader = gl.createShader(type);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            const log = gl.getShaderInfoLog(shader);
            gl.deleteShader(shader);
            throw new Error(`WebGL2 shader compile error: ${log}`);
        }
        return shader;
    }

    _createProgram(gl, vsSource, fsSource) {
        const vs = this._compileShader(gl, gl.VERTEX_SHADER, vsSource);
        const fs = this._compileShader(gl, gl.FRAGMENT_SHADER, fsSource);
        const prog = gl.createProgram();
        gl.attachShader(prog, vs);
        gl.attachShader(prog, fs);
        gl.linkProgram(prog);
        gl.deleteShader(vs);
        gl.deleteShader(fs);

        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
            const log = gl.getProgramInfoLog(prog);
            gl.deleteProgram(prog);
            throw new Error(`WebGL2 program link error: ${log}`);
        }

        const uboIndex = gl.getUniformBlockIndex(prog, 'LightingUniforms');
        if (uboIndex !== gl.INVALID_INDEX && uboIndex !== -1) {
            gl.uniformBlockBinding(prog, uboIndex, 0);
        }

        gl.useProgram(prog);
        const locSat = gl.getUniformLocation(prog, 'satelliteTex');
        if (locSat) gl.uniform1i(locSat, 0);
        const locFac = gl.getUniformLocation(prog, 'facadeTex');
        if (locFac) gl.uniform1i(locFac, 1);

        return prog;
    }

    async init(canvas) {
        this.canvas = canvas;
        const gl = canvas.getContext('webgl2', {
            antialias: true,
            alpha: false,
            depth: true,
            powerPreference: 'high-performance',
        });
        if (!gl) {
            throw new Error('WebGL2 is unavailable in this browser');
        }
        this.gl = gl;

        const dbgExt = gl.getExtension('WEBGL_debug_renderer_info');
        if (dbgExt) {
            const rendererStr = gl.getParameter(dbgExt.UNMASKED_RENDERER_WEBGL);
            if (rendererStr) this.gpuName = rendererStr;
        } else {
            const rendererStr = gl.getParameter(gl.RENDERER);
            if (rendererStr) this.gpuName = rendererStr;
        }

        this.program = this._createProgram(gl, VS_GLSL300, FS_GLSL300);
        this.buildingProgram = this._createProgram(gl, VS_BUILDING_GLSL300, FS_BUILDING_GLSL300);
        this.vehicleProgram = this._createProgram(gl, VS_VEHICLE_GLSL300, FS_GLSL300);
        this.vehicleInstanceBuf = gl.createBuffer();

        this.ubo = gl.createBuffer();
        gl.bindBuffer(gl.UNIFORM_BUFFER, this.ubo);
        gl.bufferData(gl.UNIFORM_BUFFER, 2272, gl.DYNAMIC_DRAW);
        gl.bindBufferBase(gl.UNIFORM_BUFFER, 0, this.ubo);

        gl.enable(gl.DEPTH_TEST);
        gl.depthFunc(gl.LEQUAL);
        gl.depthMask(true);
        gl.disable(gl.CULL_FACE);
        gl.enable(gl.BLEND);
        gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ZERO);

        this.resize(canvas.width || 1280, canvas.height || 720);
        return {
            backend: this.backendName,
            gpuName: this.gpuName,
        };
    }

    _createGlTexture(texData) {
        const gl = this.gl;
        const tex = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(
            gl.TEXTURE_2D,
            0,
            gl.RGBA8,
            texData.width,
            texData.height,
            0,
            gl.RGBA,
            gl.UNSIGNED_BYTE,
            texData.data
        );
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        return tex;
    }

    uploadTextures(satelliteTexData, facadeTexData) {
        const gl = this.gl;
        if (this.satelliteTex) gl.deleteTexture(this.satelliteTex);
        if (this.facadeTex) gl.deleteTexture(this.facadeTex);
        this.satelliteTex = this._createGlTexture(satelliteTexData);
        this.facadeTex = this._createGlTexture(facadeTexData);
    }

    _createArrayBuffer(typed) {
        const gl = this.gl;
        const buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, typed, gl.STATIC_DRAW);
        buf.size = typed.byteLength;
        buf.byteLength = typed.byteLength;
        return buf;
    }

    _deleteVehicleMesh(mesh) {
        const gl = this.gl;
        if (!mesh || !gl) return;
        gl.deleteVertexArray(mesh.vao);
        gl.deleteBuffer(mesh.posBuf);
        gl.deleteBuffer(mesh.normBuf);
        gl.deleteBuffer(mesh.uvBuf);
        gl.deleteBuffer(mesh.colBuf);
        gl.deleteBuffer(mesh.emBuf);
        gl.deleteBuffer(mesh.idxBuf);
    }

    // One mesh per vehicle type (web/traffic_sim.js CAR_TYPES); typeIndex 0 = sedan.
    uploadVehicleModel(meshData, typeIndex = 0) {
        const gl = this.gl;
        if (!gl || !meshData) return;
        this._deleteVehicleMesh(this.vehicleMeshes[typeIndex]);
        this.vehicleMeshes[typeIndex] = null;

        const vao = gl.createVertexArray();
        gl.bindVertexArray(vao);

        const posBuf = this._createArrayBuffer(meshData.pos);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

        const normBuf = this._createArrayBuffer(meshData.norm);
        gl.enableVertexAttribArray(1);
        gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);

        const uvBuf = this._createArrayBuffer(meshData.uv);
        gl.enableVertexAttribArray(2);
        gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 0, 0);

        const colBuf = this._createArrayBuffer(meshData.col);
        gl.enableVertexAttribArray(3);
        gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 0, 0);

        const emBuf = this._createArrayBuffer(meshData.em);
        gl.enableVertexAttribArray(4);
        gl.vertexAttribPointer(4, 1, gl.FLOAT, false, 0, 0);

        // Per-instance attributes 5..10 read from the shared instance buffer (pointers set per draw)
        gl.bindBuffer(gl.ARRAY_BUFFER, this.vehicleInstanceBuf);
        for (let loc = 5; loc <= 10; loc++) {
            gl.enableVertexAttribArray(loc);
            gl.vertexAttribDivisor(loc, 1);
        }

        const idxBuf = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, meshData.indices, gl.STATIC_DRAW);
        idxBuf.size = meshData.indices.byteLength;
        idxBuf.byteLength = meshData.indices.byteLength;

        gl.bindVertexArray(null);

        const isUint16 = (meshData.indexFormat === 'uint16');
        this.vehicleMeshes[typeIndex] = {
            vao,
            posBuf,
            normBuf,
            uvBuf,
            colBuf,
            emBuf,
            idxBuf,
            glIndexType: isUint16 ? gl.UNSIGNED_SHORT : gl.UNSIGNED_INT,
            indexCount: meshData.indexCount,
            vertexCount: meshData.vertexCount,
        };
    }

    get vehicleMesh() {
        return this.vehicleMeshes[0] || null;
    }

    _renderVehicles(vehicles) {
        const gl = this.gl;
        const { instances, typeCounts, typeOffsets } = vehicles;
        gl.useProgram(this.vehicleProgram);
        gl.bindBuffer(gl.UNIFORM_BUFFER, this.ubo);
        gl.bindBufferBase(gl.UNIFORM_BUFFER, 0, this.ubo);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this.satelliteTex);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, this.facadeTex);

        gl.bindBuffer(gl.ARRAY_BUFFER, this.vehicleInstanceBuf);
        if (this.vehicleInstanceBytes < instances.byteLength) {
            gl.bufferData(gl.ARRAY_BUFFER, instances.byteLength, gl.DYNAMIC_DRAW);
            this.vehicleInstanceBytes = instances.byteLength;
        }
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, instances);

        let drawCalls = 0;
        let verts = 0;
        const stride = 96;
        for (let t = 0; t < typeCounts.length; t++) {
            const count = typeCounts[t];
            const mesh = this.vehicleMeshes[t] || this.vehicleMeshes[0];
            if (!count || !mesh) continue;
            gl.bindVertexArray(mesh.vao);
            // WebGL2 has no baseInstance: offset the instance attribute pointers instead
            const base = typeOffsets[t] * stride;
            gl.bindBuffer(gl.ARRAY_BUFFER, this.vehicleInstanceBuf);
            for (let c = 0; c < 4; c++) {
                gl.vertexAttribPointer(5 + c, 4, gl.FLOAT, false, stride, base + c * 16);
            }
            gl.vertexAttribPointer(9, 4, gl.FLOAT, false, stride, base + 64);
            gl.vertexAttribPointer(10, 1, gl.FLOAT, false, stride, base + 80);
            gl.drawElementsInstanced(gl.TRIANGLES, mesh.indexCount, mesh.glIndexType, 0, count);
            drawCalls++;
            verts += mesh.indexCount * count;
        }
        gl.bindVertexArray(null);
        return { drawCalls, verts };
    }

    uploadSector(sectorKey, meshData, chunks) {
        const gl = this.gl;
        if (this.sectors.has(sectorKey)) {
            this.unloadSector(sectorKey);
        }

        // Support de-interleaving 52-byte engine struct buffers (13 floats per vertex)
        if (meshData.interleaved) {
            const raw = meshData.interleaved;
            const vCount = meshData.vertexCount || Math.floor(raw.length / 13);
            const pos = new Float32Array(vCount * 3);
            const norm = new Float32Array(vCount * 3);
            const uv = new Float32Array(vCount * 2);
            const col = new Float32Array(vCount * 4);
            const em = new Float32Array(vCount);

            for (let i = 0; i < vCount; i++) {
                const off = i * 13;
                pos[i * 3 + 0] = raw[off + 0];
                pos[i * 3 + 1] = raw[off + 1];
                pos[i * 3 + 2] = raw[off + 2];

                norm[i * 3 + 0] = raw[off + 3];
                norm[i * 3 + 1] = raw[off + 4];
                norm[i * 3 + 2] = raw[off + 5];

                uv[i * 2 + 0] = raw[off + 6];
                uv[i * 2 + 1] = raw[off + 7];

                col[i * 4 + 0] = raw[off + 8];
                col[i * 4 + 1] = raw[off + 9];
                col[i * 4 + 2] = raw[off + 10];
                col[i * 4 + 3] = raw[off + 11];

                em[i] = raw[off + 12];
            }

            meshData = {
                pos,
                norm,
                uv,
                col,
                em,
                vertexCount: vCount,
                indexCount: meshData.indexCount || vCount,
                indexFormat: meshData.indexFormat || (vCount > 65535 ? 'uint32' : 'uint16'),
                indices: meshData.indices || (vCount > 65535 ? new Uint32Array(vCount) : new Uint16Array(vCount)),
                buildingIndices: meshData.buildingIndices,
                submeshes: meshData.submeshes,
            };
            if (!meshData.indices || meshData.indices.length === 0) {
                meshData.indices = (vCount > 65535 ? new Uint32Array(vCount) : new Uint16Array(vCount));
                for (let i = 0; i < vCount; i++) meshData.indices[i] = i;
            }
        }

        const vao = gl.createVertexArray();
        gl.bindVertexArray(vao);

        const posBuf = this._createArrayBuffer(meshData.pos);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

        const normBuf = this._createArrayBuffer(meshData.norm);
        gl.enableVertexAttribArray(1);
        gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);

        const uvBuf = this._createArrayBuffer(meshData.uv);
        gl.enableVertexAttribArray(2);
        gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 0, 0);

        const colBuf = this._createArrayBuffer(meshData.col);
        gl.enableVertexAttribArray(3);
        gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 0, 0);

        const emBuf = this._createArrayBuffer(meshData.em);
        gl.enableVertexAttribArray(4);
        gl.vertexAttribPointer(4, 1, gl.FLOAT, false, 0, 0);

        const idxBuf = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, meshData.indices, gl.STATIC_DRAW);
        idxBuf.size = meshData.indices.byteLength;
        idxBuf.byteLength = meshData.indices.byteLength;

        gl.bindVertexArray(null);

        // Extract building-only index buffer if present
        let buildingIdxBuf = null;
        let buildingIndexCount = 0;
        let buildingGlIndexType = gl.UNSIGNED_INT;
        let buildingIndexBytes = 4;
        if (meshData.buildingIndices && meshData.buildingIndices.length > 0) {
            buildingIdxBuf = gl.createBuffer();
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buildingIdxBuf);
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, meshData.buildingIndices, gl.STATIC_DRAW);
            buildingIdxBuf.size = meshData.buildingIndices.byteLength;
            buildingIdxBuf.byteLength = meshData.buildingIndices.byteLength;
            buildingIndexCount = meshData.buildingIndices.length;
            const isU16 = (meshData.buildingIndices instanceof Uint16Array);
            buildingGlIndexType = isU16 ? gl.UNSIGNED_SHORT : gl.UNSIGNED_INT;
            buildingIndexBytes = isU16 ? 2 : 4;
        }

        // Handle submeshes with custom index buffers
        const submeshes = meshData.submeshes || [];
        for (const s of submeshes) {
            if (s.customIndices && s.customIndices.length > 0) {
                s.customIdxBuf = gl.createBuffer();
                gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, s.customIdxBuf);
                gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, s.customIndices, gl.STATIC_DRAW);
                s.customIdxBuf.size = s.customIndices.byteLength;
                s.customIdxBuf.byteLength = s.customIndices.byteLength;
                const isU16 = (s.customIndices instanceof Uint16Array);
                s.customGlIndexType = isU16 ? gl.UNSIGNED_SHORT : gl.UNSIGNED_INT;
                s.customIndexBytes = isU16 ? 2 : 4;
            }
        }
        const buildingSubmeshes = submeshes.filter(s => s.isBuilding);

        const isUint16 = (meshData.indexFormat === 'uint16');
        this.sectors.set(sectorKey, {
            vao,
            posBuf,
            normBuf,
            uvBuf,
            colBuf,
            emBuf,
            idxBuf,
            buildingIdxBuf,
            buildingIndexCount,
            buildingGlIndexType,
            buildingIndexBytes,
            submeshes,
            buildingSubmeshes,
            glIndexType: isUint16 ? gl.UNSIGNED_SHORT : gl.UNSIGNED_INT,
            indexBytes: isUint16 ? 2 : 4,
            indexCount: meshData.indexCount,
            vertexCount: meshData.vertexCount,
            chunks: chunks || [],
        });
    }

    unloadSector(sectorKey) {
        const gl = this.gl;
        const sec = this.sectors.get(sectorKey);
        if (!sec) return;
        gl.deleteVertexArray(sec.vao);
        gl.deleteBuffer(sec.posBuf);
        gl.deleteBuffer(sec.normBuf);
        gl.deleteBuffer(sec.uvBuf);
        gl.deleteBuffer(sec.colBuf);
        gl.deleteBuffer(sec.emBuf);
        gl.deleteBuffer(sec.idxBuf);
        if (sec.buildingIdxBuf) gl.deleteBuffer(sec.buildingIdxBuf);
        if (sec.submeshes) {
            for (const s of sec.submeshes) {
                if (s.customIdxBuf) gl.deleteBuffer(s.customIdxBuf);
            }
        }
        this.sectors.delete(sectorKey);
    }

    renderBuildings(sectorKey) {
        const gl = this.gl;
        if (!gl || (!this.buildingProgram && !this.program)) return 0;
        const sec = this.sectors.get(sectorKey);
        if (!sec) return 0;

        const prog = this.buildingProgram || this.program;
        gl.useProgram(prog);
        gl.bindBuffer(gl.UNIFORM_BUFFER, this.ubo);
        gl.bindBufferBase(gl.UNIFORM_BUFFER, 0, this.ubo);

        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this.satelliteTex);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, this.facadeTex);

        gl.bindVertexArray(sec.vao);
        let calls = 0;

        if (sec.buildingIdxBuf && sec.buildingIndexCount > 0) {
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.buildingIdxBuf);
            gl.drawElements(gl.TRIANGLES, sec.buildingIndexCount, sec.buildingGlIndexType, 0);
            calls++;
        } else if (sec.buildingSubmeshes && sec.buildingSubmeshes.length > 0) {
            for (const sub of sec.buildingSubmeshes) {
                if (sub.customIdxBuf) {
                    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sub.customIdxBuf);
                    gl.drawElements(gl.TRIANGLES, sub.indexCount, sub.customGlIndexType, 0);
                } else {
                    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.idxBuf);
                    gl.drawElements(gl.TRIANGLES, sub.indexCount, sec.glIndexType, sub.indexStart * sec.indexBytes);
                }
                calls++;
            }
        }
        gl.bindVertexArray(null);
        return calls;
    }

    resize(width, height) {
        if (!this.gl) return;
        this.gl.viewport(0, 0, Math.max(1, width | 0), Math.max(1, height | 0));
    }

    render(frame) {
        const gl = this.gl;
        if (!gl || !this.program) {
            return { drawCalls: 0, visibleChunks: 0, totalChunks: 0, visibleVerts: 0, totalVerts: 0 };
        }

        gl.viewport(0, 0, Math.max(1, this.canvas.width | 0), Math.max(1, this.canvas.height | 0));
        gl.clearColor(frame.clearColor[0], frame.clearColor[1], frame.clearColor[2], 1.0);
        gl.clearDepth(1.0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        gl.bindBuffer(gl.UNIFORM_BUFFER, this.ubo);
        gl.bufferSubData(gl.UNIFORM_BUFFER, 0, frame.uniformBufferData);

        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this.satelliteTex);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, this.facadeTex);

        let drawCalls = 0;
        let visibleChunks = 0;
        let totalChunks = 0;
        let visibleVerts = 0;
        let totalVerts = 0;

        // Mode 1: Building-only rendering explicitly requested
        if (frame.renderMode === 'buildings') {
            const prog = this.buildingProgram || this.program;
            gl.useProgram(prog);

            for (const [, sec] of this.sectors.entries()) {
                totalVerts += sec.vertexCount;
                gl.bindVertexArray(sec.vao);

                if (sec.buildingIdxBuf && sec.buildingIndexCount > 0) {
                    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.buildingIdxBuf);
                    gl.drawElements(gl.TRIANGLES, sec.buildingIndexCount, sec.buildingGlIndexType, 0);
                    drawCalls++;
                    visibleChunks++;
                    visibleVerts += sec.buildingIndexCount;
                } else if (sec.buildingSubmeshes && sec.buildingSubmeshes.length > 0) {
                    for (const sub of sec.buildingSubmeshes) {
                        if (sub.customIdxBuf) {
                            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sub.customIdxBuf);
                            gl.drawElements(gl.TRIANGLES, sub.indexCount, sub.customGlIndexType, 0);
                        } else {
                            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.idxBuf);
                            gl.drawElements(gl.TRIANGLES, sub.indexCount, sec.glIndexType, sub.indexStart * sec.indexBytes);
                        }
                        drawCalls++;
                        visibleChunks++;
                        visibleVerts += sub.indexCount;
                    }
                }
            }
            gl.bindVertexArray(null);
            return { drawCalls, visibleChunks, totalChunks: this.sectors.size, visibleVerts, totalVerts };
        }

        // Mode 2: Full Scene Rendering
        for (const [sectorKey, sec] of this.sectors.entries()) {
            gl.bindVertexArray(sec.vao);
            totalVerts += sec.vertexCount;

            // Priority 1: Standard spatial chunk rendering with frustum culling
            if (sec.chunks && sec.chunks.length > 0) {
                gl.useProgram(this.program);
                gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.idxBuf);
                totalChunks += sec.chunks.length;
                const flags = frame.cullFlagsBySector ? frame.cullFlagsBySector.get(sectorKey) : null;
                for (let i = 0; i < sec.chunks.length; i++) {
                    if (!frame.cullingEnabled || !flags || flags[i] !== 0) {
                        const chk = sec.chunks[i];
                        gl.drawElements(
                            gl.TRIANGLES,
                            chk.count,
                            sec.glIndexType,
                            chk.start * sec.indexBytes
                        );
                        drawCalls++;
                        visibleChunks++;
                        visibleVerts += chk.count;
                    }
                }
                continue;
            }

            // Priority 2: Submesh-based rendering (when model has separate submeshes and no spatial chunks)
            if (sec.submeshes && sec.submeshes.length > 1) {
                totalChunks += sec.submeshes.length;
                for (const sub of sec.submeshes) {
                    const targetProg = (sub.isBuilding && this.buildingProgram) ? this.buildingProgram : this.program;
                    gl.useProgram(targetProg);

                    if (sub.customIdxBuf) {
                        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sub.customIdxBuf);
                        gl.drawElements(gl.TRIANGLES, sub.indexCount, sub.customGlIndexType, 0);
                    } else {
                        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.idxBuf);
                        gl.drawElements(gl.TRIANGLES, sub.indexCount, sec.glIndexType, sub.indexStart * sec.indexBytes);
                    }
                    drawCalls++;
                    visibleChunks++;
                    visibleVerts += sub.indexCount;
                }
                continue;
            }

            // Priority 3: Monolithic single-draw fallback
            totalChunks += 1;
            gl.useProgram(this.program);
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, sec.idxBuf);
            gl.drawElements(gl.TRIANGLES, sec.indexCount, sec.glIndexType, 0);
            drawCalls++;
            visibleChunks++;
            visibleVerts += sec.indexCount;
        }

        // Instanced road-graph vehicles (web/traffic_sim.js)
        const vehicles = frame.vehicles;
        if (vehicles && this.vehicleProgram && this.vehicleMeshes.length > 0 && vehicles.instances) {
            const vStats = this._renderVehicles(vehicles);
            drawCalls += vStats.drawCalls;
            visibleVerts += vStats.verts;
        }

        gl.bindVertexArray(null);
        return { drawCalls, visibleChunks, totalChunks, visibleVerts, totalVerts };
    }

    destroy() {
        for (const key of Array.from(this.sectors.keys())) {
            this.unloadSector(key);
        }
        for (const mesh of this.vehicleMeshes) this._deleteVehicleMesh(mesh);
        this.vehicleMeshes = [];
        if (this.gl && this.vehicleInstanceBuf) this.gl.deleteBuffer(this.vehicleInstanceBuf);
        if (this.gl) {
            if (this.satelliteTex) this.gl.deleteTexture(this.satelliteTex);
            if (this.facadeTex) this.gl.deleteTexture(this.facadeTex);
            if (this.ubo) this.gl.deleteBuffer(this.ubo);
            if (this.buildingProgram) this.gl.deleteProgram(this.buildingProgram);
            if (this.vehicleProgram) this.gl.deleteProgram(this.vehicleProgram);
            if (this.program) this.gl.deleteProgram(this.program);
        }
    }
}
