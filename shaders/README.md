# Shaders

## Overview

The `shaders` component provides the GLSL `#version 450` graphics pipeline stages for rendering static urban geometry, instanced vehicles, procedural surfaces, georeferenced photo planes, and 2D HUD overlays. [vertex.vert](./vertex.vert) handles static world-space pass-through and per-instance vehicle transforms, selective chassis tinting, and brake-light emission boosts. [fragment.frag](./fragment.frag) dispatches early-out HUD and photo-plane paths, resolves material PBR parameters (`albedo`, `roughness`, `metallic`) via `fragColor.a` (`matID`), evaluates Cook-Torrance GGX/Schlick PBR lighting (sun, up to 64 point lights, spot flashlight, and sky-based ambient approximation), applies long-range atmospheric sky fog (`getAtmosphericSky`), adds distance-compensated post-fog emission, and applies Narkowicz filmic ACES tone mapping (`ACESFilm`) for `VK_FORMAT_B8G8R8A8_SRGB` swapchain output.

## Interface

### GLSL Stages and Build Rules

- `[shaders/vertex.vert:#version 450]` ([vertex.vert](./vertex.vert)): GLSL 450 vertex shader stage.
- `[shaders/fragment.frag:#version 450]` ([fragment.frag](./fragment.frag)): GLSL 450 fragment shader stage.
- `[Makefile:glslangValidator -V]` ([Makefile](../Makefile)): Pattern rules `$(SHADERDIR)/%.spv: $(SHADERDIR)/%.vert` and `$(SHADERDIR)/%.spv: $(SHADERDIR)/%.frag` compile shaders with `glslangValidator -V $< -o $@` (`[Makefile:SHADERDIR]`, `[Makefile:SHADERS_VERT]`, `[Makefile:SHADERS_FRAG]`, `[Makefile:SPV_VERT]`, `[Makefile:SPV_FRAG]`, `[Makefile:all]`), and `[Makefile:clean]` removes `$(SHADERDIR)/*.spv`.

### Vertex Inputs, Push Constants, and Stage Varyings

- **Binding 0 (per-vertex)** in [vertex.vert](./vertex.vert):
  - `[shaders/vertex.vert:inPosition]`: `layout(location=0) in vec3 inPosition`
  - `[shaders/vertex.vert:inNormal]`: `layout(location=1) in vec3 inNormal`
  - `[shaders/vertex.vert:inTexCoord]`: `layout(location=2) in vec2 inTexCoord`
  - `[shaders/vertex.vert:inColor]`: `layout(location=3) in vec4 inColor`
  - `[shaders/vertex.vert:inEmission]`: `layout(location=4) in float inEmission`
- **Binding 1 (per-instance, 96-byte stride comment: 64 B `mat4` + 16 B `vec4` + 4 B `float` + 12 B padding)** in [vertex.vert](./vertex.vert):
  - `[shaders/vertex.vert:inInstanceModel]`: `layout(location=5) in mat4 inInstanceModel` (occupies locations `5`, `6`, `7`, and `8`)
  - `[shaders/vertex.vert:inInstanceTint]`: `layout(location=9) in vec4 inInstanceTint` (`a < 0.5` selects static geometry; `a >= 0.5` selects instanced vehicles)
  - `[shaders/vertex.vert:inInstanceBrake]`: `layout(location=10) in float inInstanceBrake` (`> 0.5` triggers brake-light emission boost)
- **Push Constants**:
  - `[shaders/vertex.vert:PushConstants]` (`[shaders/vertex.vert:pc]`): `layout(push_constant) uniform PushConstants { mat4 mvp; mat4 model; } pc;` — `pc.mvp` computes `gl_Position`; `pc.model` is declared in the block but unused in `[shaders/vertex.vert:main]`.
- **Stage I/O Varyings (`vertex.vert` out -> `fragment.frag` in)**:
  - `[shaders/vertex.vert:fragTexCoord]` / `[shaders/fragment.frag:fragTexCoord]`: `layout(location=0) vec2 fragTexCoord`
  - `[shaders/vertex.vert:fragColor]` / `[shaders/fragment.frag:fragColor]`: `layout(location=1) vec4 fragColor` (RGB color; `a` carries `matID`)
  - `[shaders/vertex.vert:fragEmission]` / `[shaders/fragment.frag:fragEmission]`: `layout(location=2) float fragEmission`
  - `[shaders/vertex.vert:fragNormal]` / `[shaders/fragment.frag:fragNormal]`: `layout(location=3) vec3 fragNormal` (normalized world-space normal)
  - `[shaders/vertex.vert:fragWorldPos]` / `[shaders/fragment.frag:fragWorldPos]`: `layout(location=4) vec3 fragWorldPos`

### Descriptor Set 0 Bindings and Fragment Output

- `[shaders/fragment.frag:satelliteTex]`: `layout(set=0, binding=0) uniform sampler2D satelliteTex` — orthophoto terrain and rooftop albedo texture.
- `[shaders/fragment.frag:facadeTex]`: `layout(set=0, binding=1) uniform sampler2D facadeTex` — urban facade, tree-bark, prop atlas, and alpha-cutout mask.
- `[shaders/fragment.frag:LightingBlock]` (`[shaders/fragment.frag:lighting]`): `layout(set=0, binding=2) uniform LightingBlock` containing `[shaders/fragment.frag:PointLight]` (`lights[64]` with `vec4 posRadius` and `vec4 colorIntensity`), `int lightCount`, `float flashlightOn`, `float pad0`, `float pad1`, `vec4 flashPos` (`xyz` position, `w` range), `vec4 flashDir` (`xyz` forward direction, `w` `cos(spot angle)`), `vec4 sunDir` (`xyz` sun direction, `w` ambient intensity), `vec4 skyColor` (`rgb` sky tint, `a` `nightFactor` `0.0..1.0`), and `vec4 timeParams` (`x` `simHour` `0..24`, `yzw` `camPos`).
- `[shaders/fragment.frag:photoTex]`: `layout(set=0, binding=3) uniform sampler2D photoTex` — georeferenced photo plane texture.
- `[shaders/fragment.frag:outColor]`: `layout(location=0) out vec4 outColor` — final RGBA fragment output.

### Instancing, Material (`matID`), Lighting, and Helper Symbols

- `[shaders/vertex.vert:main]`: Static geometry (`inInstanceTint.a < 0.5`) forces `worldMat = mat4(1.0)` and `finalColor = inColor`. Instanced vehicles (`inInstanceTint.a >= 0.5`) set `worldMat = inInstanceModel` and `finalColor.a = 2.0`, preserve `inColor.rgb` when `inEmission > 0.4` (lights), `inColor.r < 0.28 && inColor.g < 0.28 && inColor.b < 0.28` (tires/trim), or `inColor.b > 0.55 && inColor.r < 0.45 && inColor.g > 0.45` (glass), tint body paint via `inColor.rgb * inInstanceTint.rgb * 1.30`, and set `finalEmission = 3.0` when `inInstanceBrake > 0.5 && inEmission > 0.4 && inColor.r > 0.6 && inColor.g < 0.25`.
- `[shaders/fragment.frag:PI]`: `const float PI = 3.14159265358979323846`.
- `[shaders/fragment.frag:hash21]`, `[shaders/fragment.frag:noise2D]`: Procedural 2D hash (`vec2(234.34, 435.345)`, `34.23`) and cubic-Hermite value noise for micro-detail on sidewalks, asphalt, walls, stucco, and steel shutters.
- `[shaders/fragment.frag:DistributionGGX]`, `[shaders/fragment.frag:GeometrySchlickGGX]`, `[shaders/fragment.frag:GeometrySmith]`, `[shaders/fragment.frag:FresnelSchlick]`, `[shaders/fragment.frag:FresnelSchlickRoughness]`: Cook-Torrance GGX/Schlick BRDF terms (`k = ((roughness + 1)^2) / 8`).
- `[shaders/fragment.frag:getAtmosphericSky]`: Procedural day/sunset/night sky gradient (`skyDayTop = (0.18, 0.44, 0.85)`, `skyDayHorizon = (0.65, 0.78, 0.95)`, `sunsetColor = (0.95, 0.40, 0.12)`, `skyNightTop = (0.01, 0.02, 0.05)`, `skyNightHoriz = (0.03, 0.06, 0.12)`, `dayFactor = clamp(sunDir.y * 2.0 + 0.2, 0.0, 1.0)`) and solar disk (`+ vec3(1.0, 0.95, 0.8) * 3.5` when `sunCos > 0.996`).
- `[shaders/fragment.frag:ACESFilm]`: Narkowicz filmic ACES curve (`a = 2.51`, `b = 0.03`, `c = 2.43`, `d = 0.59`, `e = 0.14`) clamped to `[0.0, 1.0]`.
- `[shaders/fragment.frag:main]`:
  - **Early-out paths**: `fragEmission >= 9.5` outputs `vec4(fragColor.rgb, fragColor.a)` directly for 2D HUD overlays; `1.25 < matID < 1.35` (`1.3`) outputs `vec4(texture(photoTex, fragTexCoord).rgb, 1.0)` directly for georeferenced photo planes.
  - **`matID` (`fragColor.a`) material dispatch**:
    - `matID >= 1.5` (`2.0` instanced vehicles): for `fragEmission < 0.4`, tires (`fragColor.r < 0.25 && fragColor.g < 0.25 && fragColor.b < 0.25`) `roughness=0.90, metallic=0.02`, glass (`b > 0.50 && r < 0.45`) `roughness=0.08, metallic=0.20`, body paint `roughness=0.18, metallic=0.65`; for `fragEmission >= 0.4`, lights `roughness=0.35, metallic=0.0`.
    - `matID < 0.1` (`0.0` satellite terrain): `sat.rgb`, `roughness=0.90, metallic=0.0`.
    - `matID < 0.5` (`0.35` rooftops): `mix(sat.rgb * 0.88, fragColor.rgb, 0.15)`, `roughness=0.80, metallic=0.05`.
    - `0.55 < matID < 0.65` (`0.6` cast shadows): `sat.rgb * 0.4 + fragColor.rgb * 0.2`, `roughness=0.95, metallic=0.0`.
    - `0.65 < matID < 0.75` (`0.7` tree trunks): `fac.rgb * (fragColor.rgb * 1.45)`, `roughness=0.94, metallic=0.0`.
    - `0.75 <= matID < 0.85` (`0.8` tree foliage): `fragColor.rgb`, `roughness=0.90, metallic=0.0` (with double-sided normal flip `if (dot(N, V) < 0.0) N = -N` across `0.65 < matID < 0.85`).
    - `0.92 < matID < 0.98` (`0.95` street level): sidewalks (`col.r > 0.60 && col.g > 0.60 && col.b > 0.55 && abs(N.y) > 0.7`, `1.5` m `fwidth` grid, `concreteBase = vec3(0.35, 0.34, 0.32)`, `r=0.88/m=0.0`), asphalt (`col.r < 0.38 && col.g < 0.38 && col.b < 0.40 && abs(N.y) > 0.7`, `darkTarmac = vec3(0.09, 0.09, 0.10)`, `r=0.94/m=0.01`), fluted walls (`col.r > 0.45 && col.g > 0.45 && abs(N.y) <= 0.7`, `sin((x+z)*10.47)` fluting, `wallBaseCol = vec3(0.48, 0.46, 0.43)`, `r=0.88/m=0.01`), concrete curbs (`col.r < 0.55 && col.g < 0.55 && col.b < 0.55 && abs(N.y) <= 0.7`, `col * 0.80`, `r=0.85/m=0.0`), and painted curbs/poles (`r=0.55/m=0.10`).
    - `0.98 <= matID <= 1.02 && fragEmission < 0.1` (`1.0` atlas facades/props): `mix(fac.rgb, fragColor.rgb, 0.16)`, `roughness=0.70, metallic=0.05`, alpha-test `discard` when `fac.a < 0.25 && fragColor.r > 0.92 && fragColor.g > 0.92 && fragColor.b > 0.92`.
    - `1.12 <= matID <= 1.22` (procedural architecture): stucco/moldings (`< 1.16`, `r=0.62/m=0.04`) and 26-slat rolling steel shutter (`>= 1.16`, rails/hood/bottom bar `r=0.42/m=0.65`, slats `fract(uv.y * 26.0)` `r=0.34/m=0.74`).
    - Fallback (`else`): `fragColor.rgb`, `roughness=0.75, metallic=0.0`.
  - **Lighting, fog, and post-fog emission constants**: `F0 = mix(vec3(0.04), albedo, metallic)`; sun radiance `vec3(1.2, 1.15, 1.05) * max(sunDir.y * 1.5 + 0.2, 0.0)`; point-light quadratic attenuation `(1.0 - dist / radius)^2`; flashlight radiance `vec3(1.0, 0.98, 0.92) * (5.0 * atten * smoothstep(spotCutoff, spotCutoff + 0.08, cosAngle))`; Cook-Torrance specular clamped to `[0.0, 0.85]`; ground grazing floor `NdotL >= 0.35` when `abs(N.y) > 0.35`; ambient weights `0.85` diffuse / `0.20` specular; fog `clamp((dist - 2000.0) / 16000.0, 0.0, 0.50)` blended at `fog * 0.45` toward `mix(sky, lighting.skyColor.rgb, 0.4)`; post-fog emission for `fragEmission >= 4.0` (`fragColor.rgb * (4.0 + fragEmission * 1.5)`), `> 0.5` (`glowCol * (fragEmission * (1.8 + nightFactor * 3.0) * clamp(dist / 200.0, 1.0, 3.5))` with warm tint `vec3(1.0, 0.94, 0.72)` outside `matID` `(0.92, 0.98)` and `[1.12, 1.22]`), and `> 0.0` (`fragColor.rgb * (fragEmission * (1.0 + nightFactor * 2.2))`).

## Invariants

- `[shaders/vertex.vert:main]`: Static geometry (`inInstanceTint.a < 0.5`) ignores `pc.model` and forces `worldMat = mat4(1.0)`, requiring static `inPosition` and `inNormal` inputs to be pre-transformed in world space; `fragNormal = normalize(mat3(worldMat) * inNormal)` assumes non-degenerate normals and rigid or uniformly scaled `inInstanceModel` transforms (no inverse-transpose normal matrix).
- `[shaders/vertex.vert:inInstanceTint]`: Instance/static sentinel encoding requires `inInstanceTint.a < 0.5` for static meshes and `>= 0.5` for instanced vehicles (which overwrites `fragColor.a`/`matID` to `2.0` to enter `matID >= 1.5` without colliding with static `matID` values `0.0..1.35`), and assumes vertex buffer binding `1` provides 96-byte per-instance records at locations `5..10` (`[shaders/vertex.vert:inInstanceModel]`, `[shaders/vertex.vert:inInstanceBrake]`).
- `[shaders/vertex.vert:main]`: Car selective tinting preserves `inColor.r < 0.28 && inColor.g < 0.28 && inColor.b < 0.28` (tires) and `b > 0.55 && r < 0.45 && g > 0.45` (glass), whereas `[shaders/fragment.frag:main]` classifies tires at `fragColor.r < 0.25 && fragColor.g < 0.25 && fragColor.b < 0.25` and glass at `b > 0.50 && r < 0.45`, requiring tinted body paint (`* inInstanceTint.rgb * 1.30`) not to fall into those ranges.
- `[shaders/fragment.frag:LightingBlock]`: Fixed UBO array `PointLight lights[64]` indexed up to `lighting.lightCount` requires the host to clamp `0 <= lighting.lightCount <= 64`.
- `[shaders/fragment.frag:DistributionGGX]`, `[shaders/fragment.frag:GeometrySchlickGGX]`: Denominators are guarded against division by zero with `max(denom, 0.000001)`.
- `[shaders/fragment.frag:main]`: Cook-Torrance specular denominators add `+ 0.0001` and clamp specular output to `[0.0, 0.85]`; point lights skip `radius <= 0.0 || intensity <= 0.0` and `distSq >= radius * radius` (without a separate `distSq == 0.0` guard for exact fragment-light coincidence), while the flashlight skips `distSq >= flashRange * flashRange || distSq <= 0.04`.
- `[shaders/fragment.frag:main]`: Vector normalizations (`fragNormal`, `camPos - fragWorldPos`, `lighting.sunDir.xyz`, `lighting.flashDir.xyz`, `fragWorldPos - camPos`, and `V + L`) require non-zero input lengths, and sidewalk grid `fwidth(tileCoord)` requires valid screen-space derivatives.
- `[shaders/fragment.frag:main]`: Alpha-test `discard` executes only when `matID` is in `[0.98, 1.02]` with `fragEmission < 0.1` and `fac.a < 0.25 && fragColor.r > 0.92 && fragColor.g > 0.92 && fragColor.b > 0.92`; emissive props (`fragEmission >= 0.1`) fall through to the static fallback branch.
- `[shaders/fragment.frag:main]`: PBR radiance and `ACESFilm` produce `[0.0, 1.0]` linear output in `outColor`, relying on swapchain format `VK_FORMAT_B8G8R8A8_SRGB` for linear-to-sRGB encoding (whereas HUD `fragEmission >= 9.5` and photo plane `matID` `1.3` bypass PBR, fog, and ACES).
- `[Makefile:SPV_VERT]`: Both `$(SPV_VERT)` and `$(SPV_FRAG)` map stems directly to `$(SHADERDIR)/%.spv` via `[Makefile:glslangValidator -V]`, requiring distinct filenames (without extensions) between `.vert` and `.frag` sources under `shaders/`.

## Side Effects

- `[shaders/vertex.vert:main]`: Writes clip-space `gl_Position` and per-vertex stage varyings `fragTexCoord`, `fragColor`, `fragEmission`, `fragNormal`, and `fragWorldPos`.
- `[shaders/fragment.frag:outColor]`: Writes shaded/tone-mapped RGBA values to color attachment `0` (`outColor`), or terminates fragment output via `discard` during `[shaders/fragment.frag:main]` alpha-testing.
- `[Makefile:glslangValidator -V]`: Writes compiled SPIR-V binaries (`$(SHADERDIR)/%.spv`) to disk during build; `[Makefile:clean]` deletes `$(SHADERDIR)/*.spv`.

## Verification

- Run: `make all`
- Run: `make test`
