#version 450
// Textura + luz direcional + neblina de fim de tarde.

layout(location = 0) in vec2 vUV;
layout(location = 1) in vec3 vNormal;
layout(location = 2) in float vFogDist;

layout(binding = 1) uniform sampler2D Diffuse;

layout(binding = 2) uniform PSConstants {
    vec4 Tint;        // rgb = cor (bonecos), a = 1
    vec4 SunDir;      // xyz = direcao PARA o sol
    vec4 FogColor;    // rgb = cor, a = densidade
};

layout(location = 0) out vec4 outColor;

void main() {
    vec4 tex = texture(Diffuse, vUV);
    if (tex.a < 0.5) discard;                       // folhagem, cercas
    vec3 n = normalize(vNormal);
    float sun = max(dot(n, SunDir.xyz), 0.0);
    vec3 light = vec3(0.42, 0.40, 0.38) + vec3(0.85, 0.72, 0.55) * sun;
    vec3 color = tex.rgb * Tint.rgb * light;
    float fog = 1.0 - exp(-vFogDist * FogColor.a);
    outColor = vec4(mix(color, FogColor.rgb, clamp(fog, 0.0, 1.0)), 1.0);
}
