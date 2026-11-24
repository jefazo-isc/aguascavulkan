#version 450

layout(set=0, binding=0) uniform sampler2D satelliteTex;
layout(set=0, binding=1) uniform sampler2D facadeTex;
layout(set=0, binding=3) uniform sampler2D photoTex;   // Foto georeferenciada (binding 3)

struct PointLight {
    vec4 posRadius;      // xyz: posición mundo (m), w: radio de alcance (m)
    vec4 colorIntensity; // rgb: color normalizado (0..1), w: intensidad luminosa
};

layout(set=0, binding=2) uniform LightingBlock {
    PointLight lights[64];
    int lightCount;
    float flashlightOn;
    float pad0;
    float pad1;
    vec4 flashPos;   // xyz: pos, w: alcance
    vec4 flashDir;   // xyz: dir adelante, w: cos(spot angle)
    vec4 sunDir;     // xyz: dirección del sol, w: intensidad ambiental
    vec4 skyColor;   // rgb: color del cielo, a: factor nocturno (0.0=día, 1.0=noche)
    vec4 timeParams; // x: simHour (0-24), yzw: camPos (x, y, z)
} lighting;

layout(location=0) in vec2 fragTexCoord;
layout(location=1) in vec4 fragColor;
layout(location=2) in float fragEmission;
layout(location=3) in vec3 fragNormal;
layout(location=4) in vec3 fragWorldPos;

layout(location=0) out vec4 outColor;

const float PI = 3.14159265358979323846;

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

// =========================================================================
// MODELO PBR (PHYSICALLY BASED RENDERING) - COOK-TORRANCE GGX / SCHLICK
// Basado en la especificación Khronos glTF 2.0 y Sascha Willems (Licencia MIT)
// =========================================================================

// 1. Función de Distribución Normal (D) - Trowbridge-Reitz GGX
float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    
    float num = a2;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = PI * denom * denom;
    
    return num / max(denom, 0.000001);
}

// 2. Función de Geometría / Oclusión (G) - Schlick-GGX Smith
float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = (roughness + 1.0);
    float k = (r * r) / 8.0;
    float num = NdotV;
    float denom = NdotV * (1.0 - k) + k;
    return num / max(denom, 0.000001);
}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    float ggx2 = GeometrySchlickGGX(NdotV, roughness);
    float ggx1 = GeometrySchlickGGX(NdotL, roughness);
    return ggx1 * ggx2;
}

// 3. Ecuación de Fresnel (F) - Aproximación de Schlick
vec3 FresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 FresnelSchlickRoughness(float cosTheta, vec3 F0, float roughness) {
    return F0 + (max(vec3(1.0 - roughness), F0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

// --- Shader de Cielo y Dispersión Atmosférica Procedural ---
vec3 getAtmosphericSky(vec3 rayDir, vec3 sunDir) {
    float sunCos = dot(rayDir, sunDir);
    
    // Paletas de iluminación atmosférica
    vec3 skyDayTop     = vec3(0.18, 0.44, 0.85);   // Azul profundo de día
    vec3 skyDayHorizon = vec3(0.65, 0.78, 0.95);   // Horizonte claro
    vec3 sunsetColor   = vec3(0.95, 0.40, 0.12);   // Naranja cálido de atardecer
    vec3 skyNightTop   = vec3(0.01, 0.02, 0.05);   // Noche oscura
    vec3 skyNightHoriz = vec3(0.03, 0.06, 0.12);   // Horizonte nocturno
    
    float horizonFactor = max(0.0, 1.0 - abs(rayDir.y));
    float sunsetFactor  = clamp(1.0 - abs(sunDir.y * 3.0), 0.0, 1.0);
    
    vec3 daySky   = mix(skyDayHorizon, skyDayTop, max(0.0, rayDir.y));
    vec3 nightSky = mix(skyNightHoriz, skyNightTop, max(0.0, rayDir.y));
    
    float dayFactor = clamp(sunDir.y * 2.0 + 0.2, 0.0, 1.0);
    vec3 finalSky   = mix(nightSky, daySky, dayFactor);
    
    // Matiz cálido en el horizonte al amanecer/atardecer
    finalSky = mix(finalSky, sunsetColor, sunsetFactor * horizonFactor * dayFactor);
    
    // Disco solar realista
    if (sunCos > 0.996) {
        finalSky += vec3(1.0, 0.95, 0.8) * 3.5;
    }
    
    return finalSky;
}

// Tone Mapping Fotorrealista (Filmic ACES)
vec3 ACESFilm(vec3 x) {
    float a = 2.51f;
    float b = 0.03f;
    float c = 2.43f;
    float d = 0.59f;
    float e = 0.14f;
    return clamp((x*(a*x+b))/(x*(c*x+d)+e), 0.0, 1.0);
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
    vec3 camPos = lighting.timeParams.yzw;
    vec3 N = normalize(fragNormal);
    vec3 V = normalize(camPos - fragWorldPos);

    // ── PLANO DE FOTOGRAFÍA GEOREFERENCIADA ─────────────────────────────────
    // matID == 1.3 identifica al photo plane generado por photo_plane_importer.py.
    // Se renderiza la foto directamente sin PBR para máxima fidelidad fotográfica.
    if (matID > 1.25 && matID < 1.35) {
        vec3 photoColor = texture(photoTex, fragTexCoord).rgb;
        outColor = vec4(photoColor, 1.0);
        return;
    }
    // Invertir normales solo para follaje/vegetación translúcida de doble cara (matID entre 0.65 y 0.85)
    if (matID > 0.65 && matID < 0.85) {
        if (dot(N, V) < 0.0) N = -N;
    }

    // ---------------------------------------------------------------------
    // Clasificación de Propiedades de Material PBR (Albedo, Roughness, Metallic)
    // ---------------------------------------------------------------------
    vec3 albedo;
    float roughness = 0.85;
    float metallic  = 0.00;

    // 🚨 1. VEHÍCULOS INSTANCIADOS (Coches, camionetas, taxis, autobuses): matID >= 1.5
    // ¡NUNCA aplicar texturas de fachadas ni ortofoto satelital sobre los coches!
    if (matID >= 1.5) {
        albedo = fragColor.rgb;
        if (fragEmission < 0.4) {
            if (fragColor.r < 0.25 && fragColor.g < 0.25 && fragColor.b < 0.25) {
                // Neumáticos de goma negra mate y molduras
                roughness = 0.90;
                metallic  = 0.02;
            } else if (fragColor.b > 0.50 && fragColor.r < 0.45) {
                // Cristales / Parabrisas lisos
                roughness = 0.08;
                metallic  = 0.20;
            } else {
                // Carrocería de pintura automotriz brillante y reflectante (Glossy PBR)
                roughness = 0.18;
                metallic  = 0.65;
            }
        } else {
            // Faros delanteros y luces traseras de freno
            roughness = 0.35;
            metallic  = 0.0;
        }
    }
    // 2. MATERIALES URBANOS DE LA CIUDAD (matID < 1.5)
    else if(matID < 0.1){
        // Terreno satélite puro (0.0): textura ortofotográfica
        albedo = sat.rgb;
        roughness = 0.90;
        metallic = 0.0;
    } else if(matID < 0.5){
        // Azotea (0.35)
        albedo = mix(sat.rgb * 0.88, fragColor.rgb, 0.15);
        roughness = 0.80;
        metallic = 0.05;
    } else if(matID > 0.55 && matID < 0.65){
        // Sombra proyectada (0.6)
        albedo = sat.rgb * 0.4 + fragColor.rgb * 0.2;
        roughness = 0.95;
        metallic = 0.0;
    } else if(matID > 0.65 && matID < 0.75){
        // Tronco de árbol (0.7): mapeo de corteza de madera natural desde el Atlas
        albedo = fac.rgb * (fragColor.rgb * 1.45);
        roughness = 0.94;
        metallic = 0.0;
    } else if(matID >= 0.75 && matID < 0.85){
        // Follaje de árbol (0.8): sombreado botánico
        albedo = fragColor.rgb;
        roughness = 0.90;
        metallic = 0.0;
    } else if(matID > 0.92 && matID < 0.98){
        // NIVEL DE CALLE: Asfalto, banquetas de concreto, guarniciones (matID 0.95)
        vec3 col = fragColor.rgb;
        
        // Banqueta de concreto (color claro ~0.7)
        if(col.r > 0.60 && col.g > 0.60 && col.b > 0.55 && abs(N.y) > 0.7) {
            vec2 tileCoord = fragWorldPos.xz / 1.5;
            vec2 grid = abs(fract(tileCoord - 0.5) - 0.5) / fwidth(tileCoord);
            float lineFactor = 1.0 - min(min(grid.x, grid.y), 1.0);
            float grain = noise2D(fragWorldPos.xz * 12.0) * 0.06 - 0.03;
            // Tono concreto real mate y no sobreexpuesto
            vec3 concreteBase = vec3(0.35, 0.34, 0.32);
            albedo = (mix(concreteBase, col * 0.55, 0.25) * (0.95 + grain) - vec3(lineFactor * 0.12));
            roughness = 0.88;
            metallic = 0.0;
        }
        // Asfalto vehicular (color oscuro < 0.38)
        else if(col.r < 0.38 && col.g < 0.38 && col.b < 0.40 && abs(N.y) > 0.7) {
            float grain = noise2D(fragWorldPos.xz * 16.0) * 0.04;
            float aggregate = noise2D(fragWorldPos.xz * 4.0) * 0.03;
            // Asfalto oscuro y realista (carbón/tarmac)
            vec3 darkTarmac = vec3(0.09, 0.09, 0.10);
            albedo = mix(darkTarmac, col, 0.20) + vec3(grain + aggregate - 0.025);
            roughness = 0.94; // Micro-rugosidad de asfalto
            metallic = 0.01;
        }
        // Muros de contención y túneles (concreto vertical ~0.45 a 0.75)
        else if (col.r > 0.45 && col.g > 0.45 && abs(N.y) <= 0.7) {
            // Textura acanalada / columnas estriadas verticales del paso a desnivel (período ~0.6m)
            float flute = sin((fragWorldPos.x + fragWorldPos.z) * 10.47) * 0.5 + 0.5; // ranuras cada ~60cm
            float fluteShadow = smoothstep(0.15, 0.85, flute) * 0.32 + 0.68;
            float grain = noise2D(vec2(fragWorldPos.x + fragWorldPos.z, fragWorldPos.y) * 4.0) * 0.06 - 0.03;
            // Tono beige cálido/cantera de los muros de contención de Aguascalientes
            vec3 wallBaseCol = vec3(0.48, 0.46, 0.43);
            albedo = (mix(wallBaseCol, col, 0.4) + vec3(grain)) * fluteShadow;
            roughness = 0.88;
            metallic = 0.01;
        }
        // Guarniciones pintadas, bordillos, postes y semáforos metálicos
        else {
            if (col.r < 0.55 && col.g < 0.55 && col.b < 0.55 && abs(N.y) <= 0.7) {
                // Bordillo de concreto
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
    } else if(matID >= 0.98 && matID <= 1.02 && fragEmission < 0.1) {
        // Elementos y Props Urbanos con Atlas (Fachadas, cortinas de metal, ladrillo, rejas, mallas, stop signs, hidrantes)
        // Soporte para transparencia recortada (Alpha Test) en mallas ciclónicas y barandales
        if (fac.a < 0.25 && fragColor.r > 0.92 && fragColor.g > 0.92 && fragColor.b > 0.92) {
            discard;
        }
        albedo = mix(fac.rgb, fragColor.rgb, 0.16);
        roughness = 0.70;
        metallic = 0.05;
    } else if(matID >= 1.12 && matID <= 1.22) {
        // Arquitectura Procedural en Código (cero PNGs): estuco/molduras (1.14) y cortina de acero (1.18)
        if (matID < 1.16) {
            float stucco = noise2D(fragWorldPos.xz * 6.0 + fragWorldPos.y * 6.0) * 0.025 - 0.012;
            albedo = clamp(fragColor.rgb + vec3(stucco), vec3(0.02), vec3(0.98));
            roughness = 0.62;
            metallic = 0.04;
        } else {
            // Cortina metálica arrollable acanalada en código puro (uv.y: 0=arriba, 1=abajo)
            vec2 uv = clamp(fragTexCoord, vec2(0.0), vec2(1.0));
            bool isRail = (uv.x < 0.035 || uv.x > 0.965);
            bool isHood = (uv.y < 0.13);
            bool isBottomBar = (uv.y > 0.93);
            if (isRail || isHood || isBottomBar) {
                albedo = isHood ? vec3(0.24, 0.27, 0.28) : vec3(0.32, 0.35, 0.36);
                roughness = 0.42;
                metallic = 0.65;
            } else {
                // Duelas horizontales acanaladas de acero galvanizado
                float slatPhase = fract(uv.y * 26.0);
                float rib = sin(slatPhase * 6.2831853) * 0.08;
                float seam = smoothstep(0.08, 0.16, slatPhase) * (1.0 - smoothstep(0.86, 0.96, slatPhase));
                float metalGrain = noise2D(vec2(uv.x * 32.0, uv.y * 120.0)) * 0.03 - 0.015;
                vec3 steelCol = vec3(0.48, 0.51, 0.53) * (0.78 + 0.22 * seam) + vec3(rib + metalGrain);
                // Sutil franja verde corporativa inferior o cerradura metálica central
                if (abs(uv.x - 0.5) < 0.018 && uv.y > 0.80 && uv.y < 0.91) {
                    steelCol = vec3(0.18, 0.20, 0.21);
                }
                albedo = clamp(steelCol, vec3(0.12), vec3(0.82));
                roughness = 0.34;
                metallic = 0.74;
            }
        }
    } else {
        // Otros elementos estáticos de la ciudad
        albedo = fragColor.rgb;
        roughness = 0.75;
        metallic = 0.0;
    }

    // Reflectancia dieléctrica base F0 (0.04 para la mayoría de materiales dieléctricos)
    vec3 F0 = vec3(0.04);
    F0 = mix(F0, albedo, metallic);

    // ---------------------------------------------------------------------
    // Ecuación de Reflectancia PBR (Cook-Torrance BRDF)
    // ---------------------------------------------------------------------
    vec3 Lo = vec3(0.0);

    // 1. Contribución de la Luz Solar Direccional
    vec3 L_sun = normalize(lighting.sunDir.xyz);
    vec3 H_sun = normalize(V + L_sun);
    float NdotL_sun = max(dot(N, L_sun), 0.0);

    if (NdotL_sun > 0.0) {
        float NDF = DistributionGGX(N, H_sun, roughness);
        float G   = GeometrySmith(N, V, L_sun, roughness);
        vec3 F    = FresnelSchlick(max(dot(H_sun, V), 0.0), F0);

        vec3 numerator    = NDF * G * F;
        float denominator = 4.0 * max(dot(N, V), 0.0) * NdotL_sun + 0.0001;
        vec3 specular     = clamp(numerator / denominator, vec3(0.0), vec3(0.85));

        vec3 kS = F;
        vec3 kD = vec3(1.0) - kS;
        kD *= (1.0 - metallic);

        vec3 sunRadiance = vec3(1.2, 1.15, 1.05) * max(lighting.sunDir.y * 1.5 + 0.2, 0.0);
        Lo += (kD * albedo / PI + specular) * sunRadiance * NdotL_sun;
    }

    // 2. Contribución de Luces Puntuales (Semáforos, Farolas, Alumbrado Público)
    for (int i = 0; i < lighting.lightCount; ++i) {
        float radius = lighting.lights[i].posRadius.w;
        float intensity = lighting.lights[i].colorIntensity.w;
        if (radius <= 0.0 || intensity <= 0.0) continue;

        vec3 toLight = lighting.lights[i].posRadius.xyz - fragWorldPos;
        float distSq = dot(toLight, toLight);
        // Poda temprana: descartar luces fuera del radio sin calcular raíz cuadrada ni BRDF
        if (distSq >= radius * radius) continue;

        float dist = sqrt(distSq);
        vec3 L_point = toLight / dist;
        float NdotL_p = max(dot(N, L_point), 0.0);

        if (abs(N.y) > 0.35) {
            NdotL_p = max(NdotL_p, 0.35); // Iluminación rasante en suelo
        }

        // Poda de superficie posterior (backface / oculta al ángulo de incidencia)
        if (NdotL_p <= 0.0) continue;

        vec3 lCol = lighting.lights[i].colorIntensity.rgb;
        vec3 H_point = normalize(V + L_point);

        float atten = clamp(1.0 - (dist / radius), 0.0, 1.0);
        atten = atten * atten; // Decaimiento cuadrático

        float NDF = DistributionGGX(N, H_point, roughness);
        float G   = GeometrySmith(N, V, L_point, roughness);
        vec3 F    = FresnelSchlick(max(dot(H_point, V), 0.0), F0);

        vec3 numerator    = NDF * G * F;
        float denominator = 4.0 * max(dot(N, V), 0.0) * NdotL_p + 0.0001;
        vec3 specular     = clamp(numerator / denominator, vec3(0.0), vec3(0.85));

        vec3 kS = F;
        vec3 kD = (vec3(1.0) - kS) * (1.0 - metallic);

        vec3 radiance = lCol * (intensity * atten);
        Lo += (kD * albedo / PI + specular) * radiance * NdotL_p;
    }

    // 3. Linterna Spot de Inspección del Jugador
    if (lighting.flashlightOn > 0.5) {
        vec3 toFrag = fragWorldPos - lighting.flashPos.xyz;
        float distSq = dot(toFrag, toFrag);
        float flashRange = lighting.flashPos.w;
        if (distSq < flashRange * flashRange && distSq > 0.04) {
            float dist = sqrt(distSq);
            vec3 L_flash = normalize(-toFrag);
            vec3 dir = toFrag / dist;
            float cosAngle = dot(dir, normalize(lighting.flashDir.xyz));
            float spotCutoff = lighting.flashDir.w;
            if (cosAngle > spotCutoff) {
                float spotFactor = smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle);
                float atten = clamp(1.0 - (dist / flashRange), 0.0, 1.0);
                atten = atten * atten;
                float NdotL_f = max(dot(N, L_flash), 0.0);
                if (abs(N.y) > 0.35) NdotL_f = max(NdotL_f, 0.35);

                if (NdotL_f > 0.0) {
                    vec3 H_flash = normalize(V + L_flash);
                    float NDF = DistributionGGX(N, H_flash, roughness);
                    float G   = GeometrySmith(N, V, L_flash, roughness);
                    vec3 F    = FresnelSchlick(max(dot(H_flash, V), 0.0), F0);

                    vec3 specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_f + 0.0001), vec3(0.0), vec3(0.85));
                    vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
                    vec3 radiance = vec3(1.0, 0.98, 0.92) * (5.0 * atten * spotFactor);
                    Lo += (kD * albedo / PI + specular) * radiance * NdotL_f;
                }
            }
        }
    }

    // 4. Luz Ambiental PBR (Aproximación IBL según el color del cielo y sol)
    vec3 ambientSky = lighting.skyColor.rgb * lighting.sunDir.w;
    vec3 F_ambient = FresnelSchlickRoughness(max(dot(N, V), 0.0), F0, roughness);
    vec3 kD_amb = (1.0 - F_ambient) * (1.0 - metallic);
    vec3 ambient = (kD_amb * albedo * ambientSky * 0.85) + (F_ambient * ambientSky * (1.0 - roughness) * 0.20);

    vec3 color = ambient + Lo;

    // 5. Niebla Atmosférica Fotorrealista (ajustada a escala metropolitana de 15 km)
    float dist = length(camPos - fragWorldPos);
    float fog = clamp((dist - 2000.0) / 16000.0, 0.0, 0.50);

    vec3 rayDir = normalize(fragWorldPos - camPos);
    vec3 sky = getAtmosphericSky(rayDir, L_sun);
    sky = mix(sky, lighting.skyColor.rgb, 0.4);
    color = mix(color, sky, fog * 0.45);

    // 6. Emisión PBR directa (Faros de coches, lentes de semáforos, ventanas, farolas)
    // Se suma DESPUÉS de la niebla atmosférica con compensación por distancia
    // para que las luces no se apaguen ni se desvanezcan en el horizonte
    float nightFactor = lighting.skyColor.a;
    vec3 emissionColor = vec3(0.0);
    if (fragEmission >= 4.0) {
        // Semáforo brillante: alta penetración visual a larga distancia
        emissionColor = fragColor.rgb * (4.0 + fragEmission * 1.5);
    } else if (fragEmission > 0.5) {
        // Faros y calaveras de coches, ventanas iluminadas
        vec3 glowCol = ((matID > 0.92 && matID < 0.98) || (matID >= 1.12 && matID <= 1.22)) ? fragColor.rgb : vec3(1.0, 0.94, 0.72);
        // Factor de preservación a la distancia para compensar la caída de cobertura subpíxel
        float distPreserve = clamp(dist / 200.0, 1.0, 3.5);
        emissionColor = glowCol * (fragEmission * (1.8 + nightFactor * 3.0) * distPreserve);
    } else if (fragEmission > 0.0) {
        // Brillo sutil de edificios y ventanas
        emissionColor = fragColor.rgb * (fragEmission * (1.0 + nightFactor * 2.2));
    }
    color += emissionColor;

    // 7. Tone Mapping ACES Fotorrealista (conversión linear->sRGB aplicada por el swapchain VK_FORMAT_B8G8R8A8_SRGB)
    color = ACESFilm(color);

    outColor = vec4(color, 1.0);
}
