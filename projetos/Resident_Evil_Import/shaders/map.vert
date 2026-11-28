#version 450
// Vertice do mapa e dos bonecos: posicao, normal, uv (32 bytes, igual a MapVertex).

layout(location = 0) in vec3 inPos;
layout(location = 1) in vec3 inNormal;
layout(location = 2) in vec2 inUV;

layout(binding = 0) uniform VSConstants {
    mat4 ViewProj;
    mat4 Model;
    vec4 EyePos;      // xyz = camera
};

layout(location = 0) out vec2 vUV;
layout(location = 1) out vec3 vNormal;
layout(location = 2) out float vFogDist;

void main() {
    vec4 world = Model * vec4(inPos, 1.0);
    gl_Position = ViewProj * world;
    vUV = inUV;
    vNormal = mat3(Model) * inNormal;
    vFogDist = length(world.xyz - EyePos.xyz);
}
