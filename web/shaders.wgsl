// ============================================================================
// StreetVulkan WebGPU PBR Shader (WGSL)
// Translated from shaders/vertex.vert + shaders/fragment.frag
// ============================================================================

struct PointLight {
    posRadius: vec4<f32>,      // xyz: world pos (m), w: range radius (m)
    colorIntensity: vec4<f32>, // rgb: normalized color, w: intensity
};

struct Uniforms {
    mvp: mat4x4<f32>,
    model: mat4x4<f32>,
    sunDir: vec4<f32>,         // xyz: sun direction, w: ambient intensity
    skyColor: vec4<f32>,       // rgb: sky color, a: night factor (0=day, 1=night)
    camPos: vec4<f32>,         // xyz: camera world position, w: simHour (0..24)
    flashPos: vec4<f32>,       // xyz: flashlight position, w: range
    flashDir: vec4<f32>,       // xyz: flashlight forward dir, w: cos(cutoff)
    params: vec4<f32>,         // x: lightCount, y: flashlightOn, z: timeSec, w: unused
    lights: array<PointLight, 64>,
};

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var texSampler: sampler;
@group(0) @binding(2) var satelliteTex: texture_2d<f32>;
@group(0) @binding(3) var facadeTex: texture_2d<f32>;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) texCoord: vec2<f32>,
    @location(3) color: vec4<f32>,
    @location(4) emission: f32,
};

struct VertexOutput {
    @builtin(position) clipPos: vec4<f32>,
    @location(0) texCoord: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) emission: f32,
    @location(3) normal: vec3<f32>,
    @location(4) worldPos: vec3<f32>,
};

const PI: f32 = 3.14159265358979323846;

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    let worldPos4 = u.model * vec4<f32>(in.position, 1.0);
    out.clipPos = u.mvp * worldPos4;
    out.worldPos = worldPos4.xyz;
    let n = (u.model * vec4<f32>(in.normal, 0.0)).xyz;
    let nLenSq = dot(n, n);
    out.normal = select(vec3<f32>(0.0, 1.0, 0.0), normalize(n), nLenSq > 1e-10);
    out.texCoord = in.texCoord;
    out.color = in.color;
    out.emission = in.emission;
    return out;
}

@vertex
fn vs_building(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    let worldPos4 = u.model * vec4<f32>(in.position, 1.0);
    out.clipPos = u.mvp * worldPos4;
    out.worldPos = worldPos4.xyz;
    let n = (u.model * vec4<f32>(in.normal, 0.0)).xyz;
    let nLenSq = dot(n, n);
    out.normal = select(vec3<f32>(0.0, 1.0, 0.0), normalize(n), nLenSq > 1e-10);
    out.texCoord = in.texCoord;
    out.color = in.color;
    out.emission = in.emission;
    return out;
}

fn srgbToLinear(c: vec3<f32>) -> vec3<f32> {
    return pow(max(c, vec3<f32>(0.0)), vec3<f32>(2.2));
}

fn linearToSrgb(c: vec3<f32>) -> vec3<f32> {
    return pow(clamp(c, vec3<f32>(0.0), vec3<f32>(1.0)), vec3<f32>(1.0 / 2.2));
}

fn hash21(p_in: vec2<f32>) -> f32 {
    var p = fract(p_in * vec2<f32>(234.34, 435.345));
    p += dot(p, p + vec2<f32>(34.23));
    return fract(p.x * p.y);
}

fn noise2D(p: vec2<f32>) -> f32 {
    let i = floor(p);
    var f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    let a = hash21(i);
    let b = hash21(i + vec2<f32>(1.0, 0.0));
    let c = hash21(i + vec2<f32>(0.0, 1.0));
    let d = hash21(i + vec2<f32>(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

fn DistributionGGX(N: vec3<f32>, H: vec3<f32>, roughness: f32) -> f32 {
    let a = roughness * roughness;
    let a2 = a * a;
    let NdotH = max(dot(N, H), 0.0);
    let NdotH2 = NdotH * NdotH;
    let num = a2;
    var denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = PI * denom * denom;
    return num / max(denom, 0.000001);
}

fn GeometrySchlickGGX(NdotV: f32, roughness: f32) -> f32 {
    let r = roughness + 1.0;
    let k = (r * r) / 8.0;
    let num = NdotV;
    let denom = NdotV * (1.0 - k) + k;
    return num / max(denom, 0.000001);
}

fn GeometrySmith(N: vec3<f32>, V: vec3<f32>, L: vec3<f32>, roughness: f32) -> f32 {
    let NdotV = max(dot(N, V), 0.0);
    let NdotL = max(dot(N, L), 0.0);
    let ggx2 = GeometrySchlickGGX(NdotV, roughness);
    let ggx1 = GeometrySchlickGGX(NdotL, roughness);
    return ggx1 * ggx2;
}

fn FresnelSchlick(cosTheta: f32, F0: vec3<f32>) -> vec3<f32> {
    return F0 + (vec3<f32>(1.0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

fn FresnelSchlickRoughness(cosTheta: f32, F0: vec3<f32>, roughness: f32) -> vec3<f32> {
    return F0 + (max(vec3<f32>(1.0 - roughness), F0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

fn getAtmosphericSky(rayDir: vec3<f32>, sunDir: vec3<f32>) -> vec3<f32> {
    let sunCos = dot(rayDir, sunDir);
    let skyDayTop = vec3<f32>(0.18, 0.44, 0.85);
    let skyDayHorizon = vec3<f32>(0.65, 0.78, 0.95);
    let sunsetColor = vec3<f32>(0.95, 0.40, 0.12);
    let skyNightTop = vec3<f32>(0.01, 0.02, 0.05);
    let skyNightHoriz = vec3<f32>(0.03, 0.06, 0.12);

    let horizonFactor = max(0.0, 1.0 - abs(rayDir.y));
    let sunsetFactor = clamp(1.0 - abs(sunDir.y * 3.0), 0.0, 1.0);

    let daySky = mix(skyDayHorizon, skyDayTop, max(0.0, rayDir.y));
    let nightSky = mix(skyNightHoriz, skyNightTop, max(0.0, rayDir.y));

    let dayFactor = clamp(sunDir.y * 2.0 + 0.2, 0.0, 1.0);
    var finalSky = mix(nightSky, daySky, dayFactor);
    finalSky = mix(finalSky, sunsetColor, sunsetFactor * horizonFactor * dayFactor);

    if (sunCos > 0.996) {
        finalSky += vec3<f32>(1.0, 0.95, 0.8) * 3.5;
    }
    return finalSky;
}

fn ACESFilm(x: vec3<f32>) -> vec3<f32> {
    let a: f32 = 2.51;
    let b: f32 = 0.03;
    let c: f32 = 2.43;
    let d: f32 = 0.59;
    let e: f32 = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), vec3<f32>(0.0), vec3<f32>(1.0));
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    // Evaluate texture samples and derivatives in uniform control flow
    let tileCoord = in.worldPos.xz / 1.5;
    let tileFwidth = max(fwidth(tileCoord), vec2<f32>(1e-4));
    let satRaw = textureSample(satelliteTex, texSampler, in.texCoord);
    let facRaw = textureSample(facadeTex, texSampler, in.texCoord);
    let sat = vec4<f32>(srgbToLinear(satRaw.rgb), satRaw.a);
    let fac = vec4<f32>(srgbToLinear(facRaw.rgb), facRaw.a);

    // HUD debug overlay shortcut
    if (in.emission >= 9.5) {
        return in.color;
    }

    let matID = in.color.a;
    let camPos = u.camPos.xyz;
    var N = normalize(in.normal);
    let toCam = camPos - in.worldPos;
    let camDistSq = dot(toCam, toCam);
    let V = select(vec3<f32>(0.0, 1.0, 0.0), toCam * inverseSqrt(camDistSq), camDistSq > 1e-10);

    // Georeferenced photo plane (matID == 1.3)
    if (matID > 1.25 && matID < 1.35) {
        return vec4<f32>(linearToSrgb(fac.rgb), 1.0);
    }

    // Flip normals on double-sided vegetation/foliage (0.65 < matID < 0.85)
    if (matID > 0.65 && matID < 0.85) {
        if (dot(N, V) < 0.0) {
            N = -N;
        }
    }

    var albedo: vec3<f32> = in.color.rgb;
    var roughness: f32 = 0.85;
    var metallic: f32 = 0.0;

    // 1. Vehicles (matID >= 1.5)
    if (matID >= 1.5) {
        albedo = in.color.rgb;
        if (in.emission < 0.4) {
            if (in.color.r < 0.25 && in.color.g < 0.25 && in.color.b < 0.25) {
                roughness = 0.90;
                metallic = 0.02;
            } else if (in.color.b > 0.50 && in.color.r < 0.45) {
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
    }
    // 2. Terrain / Satellite with topographic height-based coloring (matID == 0.0)
    else if (matID < 0.1) {
        let h = in.worldPos.y;
        let t = clamp((h + 25.0) / 50.0, 0.0, 1.0);
        let valleyGreen = vec3<f32>(0.22, 0.32, 0.14);
        let midEarth    = vec3<f32>(0.38, 0.30, 0.18);
        let hillRock    = vec3<f32>(0.52, 0.48, 0.40);
        var terrainBase: vec3<f32>;
        if (t < 0.5) {
            terrainBase = mix(valleyGreen, midEarth, t * 2.0);
        } else {
            terrainBase = mix(midEarth, hillRock, (t - 0.5) * 2.0);
        }
        let terrainNoise = noise2D(in.worldPos.xz * 0.12) * 0.06 - 0.03;
        let detailNoise = noise2D(in.worldPos.xz * 0.8) * 0.04 - 0.02;
        let contourLine = 1.0 - smoothstep(0.0, 0.3, abs(fract(h / 5.0) - 0.5) * 2.0) * 0.12;
        albedo = clamp(terrainBase + vec3<f32>(terrainNoise + detailNoise), vec3<f32>(0.02), vec3<f32>(0.98)) * contourLine;
        albedo = mix(albedo, sat.rgb * 0.9 + vec3<f32>(terrainNoise), 0.15);
        roughness = 0.92;
        metallic = 0.0;
    }
    // 3. Roof (matID == 0.35)
    else if (matID < 0.5) {
        albedo = mix(sat.rgb * 0.88, in.color.rgb, 0.15);
        roughness = 0.80;
        metallic = 0.05;
    }
    // 4. Cast shadow (matID == 0.6)
    else if (matID > 0.55 && matID < 0.65) {
        albedo = sat.rgb * 0.4 + in.color.rgb * 0.2;
        roughness = 0.95;
        metallic = 0.0;
    }
    // 5. Tree trunk (matID == 0.7)
    else if (matID > 0.65 && matID < 0.75) {
        albedo = fac.rgb * (in.color.rgb * 1.45);
        roughness = 0.94;
        metallic = 0.0;
    }
    // 6. Tree foliage (matID == 0.8)
    else if (matID >= 0.75 && matID < 0.85) {
        albedo = in.color.rgb;
        roughness = 0.90;
        metallic = 0.0;
    }
    // 7. Street level: Asphalt, concrete sidewalks, retaining walls, curbs (matID == 0.95)
    else if (matID > 0.92 && matID < 0.98) {
        let col = in.color.rgb;
        if (col.r > 0.60 && col.g > 0.60 && col.b > 0.55 && abs(N.y) > 0.7) {
            let grid = abs(fract(tileCoord - vec2<f32>(0.5)) - vec2<f32>(0.5)) / tileFwidth;
            let lineFactor = 1.0 - min(min(grid.x, grid.y), 1.0);
            let grain = noise2D(in.worldPos.xz * 12.0) * 0.06 - 0.03;
            let concreteBase = vec3<f32>(0.35, 0.34, 0.32);
            albedo = mix(concreteBase, col * 0.55, 0.25) * (0.95 + grain) - vec3<f32>(lineFactor * 0.12);
            roughness = 0.88;
            metallic = 0.0;
        } else if (col.r < 0.38 && col.g < 0.38 && col.b < 0.40 && abs(N.y) > 0.7) {
            let grain = noise2D(in.worldPos.xz * 16.0) * 0.04;
            let aggregate = noise2D(in.worldPos.xz * 4.0) * 0.03;
            let darkTarmac = vec3<f32>(0.09, 0.09, 0.10);
            albedo = mix(darkTarmac, col, 0.20) + vec3<f32>(grain + aggregate - 0.025);
            roughness = 0.94;
            metallic = 0.01;
        } else if (col.r > 0.45 && col.g > 0.45 && abs(N.y) <= 0.7) {
            let flute = sin((in.worldPos.x + in.worldPos.z) * 10.47) * 0.5 + 0.5;
            let fluteShadow = smoothstep(0.15, 0.85, flute) * 0.32 + 0.68;
            let grain = noise2D(vec2<f32>(in.worldPos.x + in.worldPos.z, in.worldPos.y) * 4.0) * 0.06 - 0.03;
            let wallBaseCol = vec3<f32>(0.48, 0.46, 0.43);
            albedo = (mix(wallBaseCol, col, 0.4) + vec3<f32>(grain)) * fluteShadow;
            roughness = 0.88;
            metallic = 0.01;
        } else {
            if (col.r < 0.55 && col.g < 0.55 && col.b < 0.55 && abs(N.y) <= 0.7) {
                albedo = col * 0.80;
                roughness = 0.85;
                metallic = 0.0;
            } else {
                let grain = noise2D(in.worldPos.xz * 8.0) * 0.04;
                albedo = col + vec3<f32>(grain - 0.02);
                roughness = 0.55;
                metallic = 0.10;
            }
        }
    }
    // 8. Textured atlas facades & urban props (matID == 1.0)
    else if (matID >= 0.98 && matID <= 1.02 && in.emission < 0.1) {
        if (fac.a < 0.25 && in.color.r > 0.92 && in.color.g > 0.92 && in.color.b > 0.92) {
            discard;
        }
        albedo = mix(fac.rgb, in.color.rgb, 0.16);
        roughness = 0.70;
        metallic = 0.05;
    }
    // 9. Procedural architecture (zero PNGs): Rolcar stucco/signage/poles (1.14) & steel shutters (1.18)
    else if (matID >= 1.12 && matID <= 1.22) {
        if (matID < 1.16) {
            let stucco = noise2D(in.worldPos.xz * 6.0 + vec2<f32>(in.worldPos.y * 6.0)) * 0.025 - 0.012;
            albedo = clamp(in.color.rgb + vec3<f32>(stucco), vec3<f32>(0.02), vec3<f32>(0.98));
            roughness = 0.62;
            metallic = 0.04;
        } else {
            // Corrugated rolling steel shutter in pure WGSL math (uv.y: 0=top, 1=bottom)
            let uv = clamp(in.texCoord, vec2<f32>(0.0), vec2<f32>(1.0));
            let isRail = (uv.x < 0.035 || uv.x > 0.965);
            let isHood = (uv.y < 0.13);
            let isBottomBar = (uv.y > 0.93);
            if (isRail || isHood || isBottomBar) {
                albedo = select(vec3<f32>(0.32, 0.35, 0.36), vec3<f32>(0.24, 0.27, 0.28), isHood);
                roughness = 0.42;
                metallic = 0.65;
            } else {
                let slatPhase = fract(uv.y * 26.0);
                let rib = sin(slatPhase * 6.2831853) * 0.08;
                let seam = smoothstep(0.08, 0.16, slatPhase) * (1.0 - smoothstep(0.86, 0.96, slatPhase));
                let metalGrain = noise2D(vec2<f32>(uv.x * 32.0, uv.y * 120.0)) * 0.03 - 0.015;
                var steelCol = vec3<f32>(0.48, 0.51, 0.53) * (0.78 + 0.22 * seam) + vec3<f32>(rib + metalGrain);
                if (abs(uv.x - 0.5) < 0.018 && uv.y > 0.80 && uv.y < 0.91) {
                    steelCol = vec3<f32>(0.18, 0.20, 0.21);
                }
                albedo = clamp(steelCol, vec3<f32>(0.12), vec3<f32>(0.82));
                roughness = 0.34;
                metallic = 0.74;
            }
        }
    } else {
        albedo = in.color.rgb;
        roughness = 0.75;
        metallic = 0.0;
    }

    var F0 = vec3<f32>(0.04);
    F0 = mix(F0, albedo, metallic);

    var Lo = vec3<f32>(0.0);

    // 1. Directional Sun PBR Cook-Torrance
    let L_sun = normalize(u.sunDir.xyz);
    let H_sun = normalize(V + L_sun);
    let NdotL_sun = max(dot(N, L_sun), 0.0);

    if (NdotL_sun > 0.0) {
        let NDF = DistributionGGX(N, H_sun, roughness);
        let G = GeometrySmith(N, V, L_sun, roughness);
        let F = FresnelSchlick(max(dot(H_sun, V), 0.0), F0);

        let numerator = NDF * G * F;
        let denominator = 4.0 * max(dot(N, V), 0.0) * NdotL_sun + 0.0001;
        let specular = clamp(numerator / denominator, vec3<f32>(0.0), vec3<f32>(0.85));

        let kD = (vec3<f32>(1.0) - F) * (1.0 - metallic);
        let sunRadiance = vec3<f32>(1.2, 1.15, 1.05) * max(u.sunDir.y * 1.5 + 0.2, 0.0);
        Lo += (kD * albedo / PI + specular) * sunRadiance * NdotL_sun;
    }

    // 2. Dynamic Point Lights (Traffic signals & streetlights)
    let lightCount = min(i32(u.params.x), 64);
    for (var i: i32 = 0; i < lightCount; i = i + 1) {
        let radius = u.lights[i].posRadius.w;
        let intensity = u.lights[i].colorIntensity.w;
        if (radius <= 0.0 || intensity <= 0.0) {
            continue;
        }

        let toLight = u.lights[i].posRadius.xyz - in.worldPos;
        let distSq = dot(toLight, toLight);
        if (distSq >= radius * radius || distSq <= 1e-6) {
            continue;
        }

        let d = sqrt(distSq);
        let L_point = toLight / d;
        var NdotL_p = max(dot(N, L_point), 0.0);
        if (abs(N.y) > 0.35) {
            NdotL_p = max(NdotL_p, 0.35);
        }
        if (NdotL_p <= 0.0) {
            continue;
        }

        let lCol = u.lights[i].colorIntensity.rgb;
        let H_point = normalize(V + L_point);

        var atten = clamp(1.0 - (d / radius), 0.0, 1.0);
        atten = atten * atten;

        let NDF = DistributionGGX(N, H_point, roughness);
        let G = GeometrySmith(N, V, L_point, roughness);
        let F = FresnelSchlick(max(dot(H_point, V), 0.0), F0);

        let numerator = NDF * G * F;
        let denominator = 4.0 * max(dot(N, V), 0.0) * NdotL_p + 0.0001;
        let specular = clamp(numerator / denominator, vec3<f32>(0.0), vec3<f32>(0.85));

        let kD = (vec3<f32>(1.0) - F) * (1.0 - metallic);
        let radiance = lCol * (intensity * atten);
        Lo += (kD * albedo / PI + specular) * radiance * NdotL_p;
    }

    // 3. Player inspection spot flashlight
    if (u.params.y > 0.5) {
        let toFrag = in.worldPos - u.flashPos.xyz;
        let distSq = dot(toFrag, toFrag);
        let flashRange = u.flashPos.w;
        if (distSq < flashRange * flashRange && distSq > 0.04) {
            let d = sqrt(distSq);
            let L_flash = normalize(-toFrag);
            let dir = toFrag / d;
            let cosAngle = dot(dir, normalize(u.flashDir.xyz));
            let spotCutoff = u.flashDir.w;
            if (cosAngle > spotCutoff) {
                let spotFactor = smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle);
                var atten = clamp(1.0 - (d / flashRange), 0.0, 1.0);
                atten = atten * atten;
                var NdotL_f = max(dot(N, L_flash), 0.0);
                if (abs(N.y) > 0.35) {
                    NdotL_f = max(NdotL_f, 0.35);
                }
                if (NdotL_f > 0.0) {
                    let H_flash = normalize(V + L_flash);
                    let NDF = DistributionGGX(N, H_flash, roughness);
                    let G = GeometrySmith(N, V, L_flash, roughness);
                    let F = FresnelSchlick(max(dot(H_flash, V), 0.0), F0);
                    let specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_f + 0.0001), vec3<f32>(0.0), vec3<f32>(0.85));
                    let kD = (vec3<f32>(1.0) - F) * (1.0 - metallic);
                    let radiance = vec3<f32>(1.0, 0.98, 0.92) * (5.0 * atten * spotFactor);
                    Lo += (kD * albedo / PI + specular) * radiance * NdotL_f;
                }
            }
        }
    }

    // 4. Ambient PBR sky IBL
    let ambientSky = u.skyColor.rgb * u.sunDir.w;
    let F_ambient = FresnelSchlickRoughness(max(dot(N, V), 0.0), F0, roughness);
    let kD_amb = (vec3<f32>(1.0) - F_ambient) * (1.0 - metallic);
    let ambient = (kD_amb * albedo * ambientSky * 0.85) + (F_ambient * ambientSky * (1.0 - roughness) * 0.20);

    var color = ambient + Lo;

    // 5. Atmospheric distance fog
    let dist = length(camPos - in.worldPos);
    let fog = clamp((dist - 2000.0) / 16000.0, 0.0, 0.50);
    let rayDir = select(vec3<f32>(0.0, 1.0, 0.0), normalize(in.worldPos - camPos), dist > 1e-4);
    var sky = getAtmosphericSky(rayDir, L_sun);
    sky = mix(sky, u.skyColor.rgb, 0.4);
    color = mix(color, sky, fog * 0.45);

    // 6. Direct PBR emission (signs, traffic lenses, lamps)
    let nightFactor = u.skyColor.a;
    var emissionColor = vec3<f32>(0.0);
    if (in.emission >= 4.0) {
        let pulse = 0.92 + 0.08 * sin(u.params.z * 3.0);
        emissionColor = in.color.rgb * ((4.0 + in.emission * 1.5) * pulse);
    } else if (in.emission > 0.5) {
        let keepColor = ((matID > 0.92 && matID < 0.98) || (matID >= 1.12 && matID <= 1.22));
        let glowCol = select(vec3<f32>(1.0, 0.94, 0.72), in.color.rgb, keepColor);
        let distPreserve = clamp(dist / 200.0, 1.0, 3.5);
        emissionColor = glowCol * (in.emission * (1.8 + nightFactor * 3.0) * distPreserve);
    } else if (in.emission > 0.0) {
        emissionColor = in.color.rgb * (in.emission * (1.0 + nightFactor * 2.2));
    }
    color += emissionColor;

    // 7. ACES Filmic Tonemap + sRGB Gamma
    color = ACESFilm(color);
    color = linearToSrgb(color);
    return vec4<f32>(color, 1.0);
}

// ============================================================================
// Specialized Building Fragment Shader (WebGPU Building Pipeline)
// Optimized for architectural materials: roofs (0.35), textured facades (1.0),
// Rolcar stucco (1.14), rolling steel shutters (1.18), and night window glow.
// ============================================================================
@fragment
fn fs_building(in: VertexOutput) -> @location(0) vec4<f32> {
    // 1. Uniform control flow texture sampling
    let satRaw = textureSample(satelliteTex, texSampler, in.texCoord);
    let facRaw = textureSample(facadeTex, texSampler, in.texCoord);
    let sat = vec4<f32>(srgbToLinear(satRaw.rgb), satRaw.a);
    let fac = vec4<f32>(srgbToLinear(facRaw.rgb), facRaw.a);

    // Direct emission pass-through for HUD/debug overlays
    if (in.emission >= 9.5) {
        return in.color;
    }

    let matID = in.color.a;
    let camPos = u.camPos.xyz;
    var N = normalize(in.normal);
    let toCam = camPos - in.worldPos;
    let camDistSq = dot(toCam, toCam);
    let V = select(vec3<f32>(0.0, 1.0, 0.0), toCam * inverseSqrt(camDistSq), camDistSq > 1e-10);

    var albedo: vec3<f32> = in.color.rgb;
    var roughness: f32 = 0.72;
    var metallic: f32 = 0.04;

    // 1. Building Roofs (matID < 0.50, nominally 0.35)
    if (matID < 0.50) {
        albedo = mix(sat.rgb * 0.88, in.color.rgb, 0.15);
        roughness = 0.80;
        metallic = 0.05;
    }
    // 2. Textured Atlas Facades: Brick, Cantera, Window Grilles, Shopfronts (0.98 <= matID <= 1.02)
    else if (matID >= 0.98 && matID <= 1.02 && in.emission < 0.1) {
        if (fac.a < 0.25 && in.color.r > 0.92 && in.color.g > 0.92 && in.color.b > 0.92) {
            discard;
        }
        albedo = mix(fac.rgb, in.color.rgb, 0.16);
        roughness = 0.68;
        metallic = 0.05;
    }
    // 3. Procedural Rolcar Architecture: Stucco/Signage (1.14) & Rolling Steel Shutters (1.18)
    else if (matID >= 1.12 && matID <= 1.22) {
        if (matID < 1.16) {
            let stucco = noise2D(in.worldPos.xz * 6.0 + vec2<f32>(in.worldPos.y * 6.0)) * 0.025 - 0.012;
            albedo = clamp(in.color.rgb + vec3<f32>(stucco), vec3<f32>(0.02), vec3<f32>(0.98));
            roughness = 0.62;
            metallic = 0.04;
        } else {
            let uv = clamp(in.texCoord, vec2<f32>(0.0), vec2<f32>(1.0));
            let isRail = (uv.x < 0.035 || uv.x > 0.965);
            let isHood = (uv.y < 0.13);
            let isBottomBar = (uv.y > 0.93);
            if (isRail || isHood || isBottomBar) {
                albedo = select(vec3<f32>(0.32, 0.35, 0.36), vec3<f32>(0.24, 0.27, 0.28), isHood);
                roughness = 0.42;
                metallic = 0.65;
            } else {
                let slatPhase = fract(uv.y * 26.0);
                let rib = sin(slatPhase * 6.2831853) * 0.08;
                let seam = smoothstep(0.08, 0.16, slatPhase) * (1.0 - smoothstep(0.86, 0.96, slatPhase));
                let metalGrain = noise2D(vec2<f32>(uv.x * 32.0, uv.y * 120.0)) * 0.03 - 0.015;
                var steelCol = vec3<f32>(0.48, 0.51, 0.53) * (0.78 + 0.22 * seam) + vec3<f32>(rib + metalGrain);
                if (abs(uv.x - 0.5) < 0.018 && uv.y > 0.80 && uv.y < 0.91) {
                    steelCol = vec3<f32>(0.18, 0.20, 0.21);
                }
                albedo = clamp(steelCol, vec3<f32>(0.12), vec3<f32>(0.82));
                roughness = 0.34;
                metallic = 0.74;
            }
        }
    } else {
        albedo = in.color.rgb;
        roughness = 0.75;
        metallic = 0.0;
    }

    var F0 = vec3<f32>(0.04);
    F0 = mix(F0, albedo, metallic);

    var Lo = vec3<f32>(0.0);

    // Directional Sun PBR Cook-Torrance
    let L_sun = normalize(u.sunDir.xyz);
    let H_sun = normalize(V + L_sun);
    let NdotL_sun = max(dot(N, L_sun), 0.0);

    if (NdotL_sun > 0.0) {
        let NDF = DistributionGGX(N, H_sun, roughness);
        let G = GeometrySmith(N, V, L_sun, roughness);
        let F = FresnelSchlick(max(dot(H_sun, V), 0.0), F0);

        let numerator = NDF * G * F;
        let denominator = 4.0 * max(dot(N, V), 0.0) * NdotL_sun + 0.0001;
        let specular = clamp(numerator / denominator, vec3<f32>(0.0), vec3<f32>(0.85));

        let kD = (vec3<f32>(1.0) - F) * (1.0 - metallic);
        let sunRadiance = vec3<f32>(1.2, 1.15, 1.05) * max(u.sunDir.y * 1.5 + 0.2, 0.0);
        Lo += (kD * albedo / PI + specular) * sunRadiance * NdotL_sun;
    }

    // Dynamic Point Lights (Streets, storefronts, and architectural illumination)
    let lightCount = min(i32(u.params.x), 64);
    for (var i: i32 = 0; i < lightCount; i = i + 1) {
        let radius = u.lights[i].posRadius.w;
        let intensity = u.lights[i].colorIntensity.w;
        if (radius <= 0.0 || intensity <= 0.0) {
            continue;
        }

        let toLight = u.lights[i].posRadius.xyz - in.worldPos;
        let distSq = dot(toLight, toLight);
        if (distSq >= radius * radius || distSq <= 1e-6) {
            continue;
        }

        let d = sqrt(distSq);
        let L_point = toLight / d;
        var NdotL_p = max(dot(N, L_point), 0.0);
        if (abs(N.y) > 0.35) {
            NdotL_p = max(NdotL_p, 0.35);
        }
        if (NdotL_p <= 0.0) {
            continue;
        }

        let lCol = u.lights[i].colorIntensity.rgb;
        let H_point = normalize(V + L_point);

        var atten = clamp(1.0 - (d / radius), 0.0, 1.0);
        atten = atten * atten;

        let NDF = DistributionGGX(N, H_point, roughness);
        let G = GeometrySmith(N, V, L_point, roughness);
        let F = FresnelSchlick(max(dot(H_point, V), 0.0), F0);

        let numerator = NDF * G * F;
        let denominator = 4.0 * max(dot(N, V), 0.0) * NdotL_p + 0.0001;
        let specular = clamp(numerator / denominator, vec3<f32>(0.0), vec3<f32>(0.85));

        let kD = (vec3<f32>(1.0) - F) * (1.0 - metallic);
        let radiance = lCol * (intensity * atten);
        Lo += (kD * albedo / PI + specular) * radiance * NdotL_p;
    }

    // Inspection flashlight spotlight
    if (u.params.y > 0.5) {
        let toFrag = in.worldPos - u.flashPos.xyz;
        let distSq = dot(toFrag, toFrag);
        let flashRange = u.flashPos.w;
        if (distSq < flashRange * flashRange && distSq > 0.04) {
            let d = sqrt(distSq);
            let L_flash = normalize(-toFrag);
            let dir = toFrag / d;
            let cosAngle = dot(dir, normalize(u.flashDir.xyz));
            let spotCutoff = u.flashDir.w;
            if (cosAngle > spotCutoff) {
                let spotFactor = smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle);
                var atten = clamp(1.0 - (d / flashRange), 0.0, 1.0);
                atten = atten * atten;
                var NdotL_f = max(dot(N, L_flash), 0.0);
                if (abs(N.y) > 0.35) {
                    NdotL_f = max(NdotL_f, 0.35);
                }
                if (NdotL_f > 0.0) {
                    let H_flash = normalize(V + L_flash);
                    let NDF = DistributionGGX(N, H_flash, roughness);
                    let G = GeometrySmith(N, V, L_flash, roughness);
                    let F = FresnelSchlick(max(dot(H_flash, V), 0.0), F0);
                    let specular = clamp((NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * NdotL_f + 0.0001), vec3<f32>(0.0), vec3<f32>(0.85));
                    let kD = (vec3<f32>(1.0) - F) * (1.0 - metallic);
                    let radiance = vec3<f32>(1.0, 0.98, 0.92) * (5.0 * atten * spotFactor);
                    Lo += (kD * albedo / PI + specular) * radiance * NdotL_f;
                }
            }
        }
    }

    // Ambient sky IBL
    let ambientSky = u.skyColor.rgb * u.sunDir.w;
    let F_ambient = FresnelSchlickRoughness(max(dot(N, V), 0.0), F0, roughness);
    let kD_amb = (vec3<f32>(1.0) - F_ambient) * (1.0 - metallic);
    let ambient = (kD_amb * albedo * ambientSky * 0.85) + (F_ambient * ambientSky * (1.0 - roughness) * 0.20);

    var color = ambient + Lo;

    // Atmospheric distance fog
    let dist = length(camPos - in.worldPos);
    let fog = clamp((dist - 2000.0) / 16000.0, 0.0, 0.50);
    let rayDir = select(vec3<f32>(0.0, 1.0, 0.0), normalize(in.worldPos - camPos), dist > 1e-4);
    var sky = getAtmosphericSky(rayDir, L_sun);
    sky = mix(sky, u.skyColor.rgb, 0.4);
    color = mix(color, sky, fog * 0.45);

    // Direct PBR emission for illuminated building windows and storefront signage
    let nightFactor = u.skyColor.a;
    var emissionColor = vec3<f32>(0.0);
    if (in.emission >= 4.0) {
        emissionColor = in.color.rgb * (4.0 + in.emission * 1.5);
    } else if (in.emission > 0.5) {
        let keepColor = (matID >= 1.12 && matID <= 1.22);
        let glowCol = select(vec3<f32>(1.0, 0.94, 0.72), in.color.rgb, keepColor);
        let distPreserve = clamp(dist / 200.0, 1.0, 3.5);
        emissionColor = glowCol * (in.emission * (1.8 + nightFactor * 3.0) * distPreserve);
    } else if (in.emission > 0.0) {
        emissionColor = in.color.rgb * (in.emission * (1.0 + nightFactor * 2.2));
    }
    color += emissionColor;

    // ACES Filmic Tonemap + sRGB Gamma
    color = ACESFilm(color);
    color = linearToSrgb(color);
    return vec4<f32>(color, 1.0);
}
