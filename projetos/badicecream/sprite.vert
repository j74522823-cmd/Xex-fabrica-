#version 450
// A sprite's corner: its place in pixels from the viewport's top left, its atlas coordinate and its tint.
layout(location = 0) in vec2 a_position;
layout(location = 1) in vec4 a_color;
layout(location = 2) in vec2 a_uv;
layout(location = 0) out vec2 v_uv;
layout(location = 1) out vec4 v_color;
// Pixels to clip space: scaled by xy, then moved by zw.
layout(push_constant) uniform Push { vec4 to_clip; } pc;

void main()
{
	gl_Position = vec4(a_position * pc.to_clip.xy + pc.to_clip.zw, 0.0, 1.0);
	v_uv = a_uv;
	v_color = a_color;
}
