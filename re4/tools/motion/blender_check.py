"""Headless Blender check of an exported glTF (run by motion_export.py export --blender-check):

    blender -b --python tools/motion/blender_check.py -- <file.gltf> <ref.json> [<render dir>]

Imports the file, asserts the armature has the bone count and the action the frame range the
reference describes, that the mesh objects are exactly the exporter's models (ref "mesh"
"labels") with its vertex / triangle counts, every mesh skinned to the armature, the shape keys of
the heads (ref "mesh" "shape_keys": name -> key names, from the .bin's shape table), samples the
world positions of the reference bones at its frames and compares them with the helper's parts
world positions (printed, max abs error), checks that the deformed mesh stays near the bones and
that a shape key at 1.0 moves its vertices by a face-sized amount (not an explosion), and renders
4 frames (workbench; textured when there is a mesh, solid for the stick figure) to PNGs in the
render directory. ref "strip": also every frame at 30 fps to <name>_strip.png (one row of 256 px
frames) and <name>.mp4. ref "nice": a directory for lit renders: EEVEE, three area lights (key,
fill, rim), the camera framed on the animated character's bounding box, at the first and middle
frame, and for every shape key a head close-up with that key at 1.0 (`<name>_nice_f000.png`,
`<name>_nice_<mesh>_<key>.png`).
"""
import json
import math
import os
import subprocess
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
gltf_path, ref_path = argv[0], argv[1]
render_dir = argv[2] if len(argv) > 2 else None
ref = json.load(open(ref_path))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = int(round(ref['fps']))   # the importer maps seconds to frames with it
bpy.ops.import_scene.gltf(filepath=gltf_path)

armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
assert len(armatures) == 1, f'expected one armature, found {len(armatures)}'
arm = armatures[0]
n_bones = len(arm.data.bones)
assert n_bones == ref['bones'], f'armature has {n_bones} bones, expected {ref["bones"]}'
scene = bpy.context.scene

# the importer's bone display shape (bone_heuristic BLENDER: an "Icosphere" object) is not model geometry
shapes = {pb.custom_shape for pb in arm.pose.bones if pb.custom_shape}
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o not in shapes]
by_label = {}
if ref.get('mesh'):
    exp = ref['mesh']
    assert len(meshes) == exp['meshes'], f'{len(meshes)} mesh objects, expected {exp["meshes"]}'
    names = sorted(o.name for o in meshes)
    assert names == sorted(exp['labels']), f'mesh objects {names}, exporter wrote {sorted(exp["labels"])}'
    by_label = {o.name: o for o in meshes}
    n_v = sum(len(o.data.vertices) for o in meshes)
    n_t = sum(len(o.data.polygons) for o in meshes)
    assert all(len(p.vertices) == 3 for o in meshes for p in o.data.polygons), 'non-triangle faces'
    assert n_v == exp['vertices'], f'{n_v} vertices imported, exporter wrote {exp["vertices"]}'
    assert n_t == exp['triangles'], f'{n_t} triangles imported, exporter wrote {exp["triangles"]}'
    for o in meshes:
        mods = [m for m in o.modifiers if m.type == 'ARMATURE']
        assert mods and mods[0].object == arm, f'{o.name}: not skinned to the armature'
        assert o.data.uv_layers and o.data.color_attributes, f'{o.name}: missing UVs or vertex colours'
        assert all(s.material and s.material.use_nodes for s in o.material_slots), f'{o.name}: material without nodes'
    n_img = len([i for i in bpy.data.images if i.filepath])
    assert n_img == exp['materials'], f'{n_img} images, exporter wrote {exp["materials"]} textures'
    print(f'blender: mesh: {len(meshes)} object(s) {", ".join(names)}: {n_v} vertices, {n_t} triangles, {n_img} textures, all skinned to {arm.name}')
    # shape keys: exactly the exporter's morph targets, on the heads only
    for o in meshes:
        want = exp['shape_keys'].get(o.name, [])
        have = [kb.name for kb in o.data.shape_keys.key_blocks[1:]] if o.data.shape_keys else []
        assert have == want, f'{o.name}: shape keys {have}, exporter wrote {want}'
    for label, keys in exp['shape_keys'].items():
        o = by_label[label]
        base = [v.co.copy() for v in o.data.vertices]
        for kb in o.data.shape_keys.key_blocks[1:]:
            moved = [(kb.data[i].co - base[i]).length for i in range(len(base))]
            n_moved = sum(1 for d in moved if d > 1e-9)
            assert n_moved, f'{label} {kb.name}: no vertex moves'
            # the disc's deltas are a few mm to two cm; a vertex moving more than 60 mm would be an explosion
            assert max(moved) < 60.0 * ref['scale'], f'{label} {kb.name}: a vertex moves {max(moved)}'
            print(f'blender: shape key {label} {kb.name}: {n_moved} of {len(base)} vertices move, max {max(moved):.4f} ({ref["units"]})')

actions = list(bpy.data.actions)
assert actions, 'no action imported'
first = min(a.frame_range[0] for a in actions)
last = max(a.frame_range[1] for a in actions)
exp_last = ref['frames'] - 1
assert abs(first) < 1e-3 and abs(last - exp_last) < 1e-3, f'action frame range {first}..{last}, expected 0..{exp_last}'
scene.frame_start = 0
scene.frame_end = ref['frames'] - 1
print(f'blender: armature {arm.name}: {n_bones} bones, action range {first:g}..{last:g}, {len(actions)} action(s)')

# world positions of the reference bones (bone heads = parts origins) at the reference frames
max_err = 0.0
for frame, bones in ref['samples'].items():
    scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    for name, expect in bones.items():
        pb = arm.pose.bones[name]
        head = arm.matrix_world @ pb.head
        err = max(abs(head[i] - expect[i]) for i in range(3))
        max_err = max(max_err, err)
        print(f'blender: frame {frame} {name}: blender ({head.x:.5f}, {head.y:.5f}, {head.z:.5f})'
              f' helper ({expect[0]:.5f}, {expect[1]:.5f}, {expect[2]:.5f}) err {err:.2e}')
print(f'blender: max abs error of sampled bone positions vs helper: {max_err:.3e} (units: {ref["units"]})')
assert max_err < ref['tolerance'], f'bone positions differ from the helper by {max_err}'


def evaluated_points(frame, objects):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objects:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ v.co for v in ev.data.vertices]
    return pts


def bbox(pts):
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


if ref.get('mesh'):
    # the deformed mesh must stay near the bones at every sampled frame: an exploded vertex or a
    # stretched limb (wrong weights / bind matrices) reaches far outside the skeleton's box
    worst = 0.0
    for frame in ref['samples']:
        scene.frame_set(int(frame))
        bpy.context.view_layer.update()
        lo, hi = bbox([arm.matrix_world @ pb.head for pb in arm.pose.bones])
        margin = 0.25 * max(hi - lo)
        for p in evaluated_points(int(frame), meshes):
            out = max(max(lo[i] - margin - p[i], p[i] - hi[i] - margin, 0.0) for i in range(3))
            worst = max(worst, out)
    print(f'blender: deformed mesh outside the bones\' box + 25%: {worst:.4f} (0 = inside at every sampled frame)')
    assert worst == 0.0, f'mesh vertices reach {worst} outside the skeleton box: exploded / stretched skinning'


def look_at(cam, target):
    direction = target - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def frame_box(cam, lo, hi, aspect, fill=0.85, direction=Vector((0.35, -1.0, 0.25))):
    """Place the camera on `direction` from the box centre so the box's bounding sphere fills `fill`
    of the view's smaller dimension."""
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-3)
    fov = cam.data.angle
    if aspect > 1:
        fov = 2 * math.atan(math.tan(fov / 2) / aspect)
    dist = radius / math.sin(fov / 2) / fill
    cam.location = center + direction.normalized() * dist
    look_at(cam, center)


if render_dir:
    os.makedirs(render_dir, exist_ok=True)
    # a camera in front of the model, framing the bounding box of the motion (bone heads at the
    # sampled frames; the mesh extends about a head beyond the bones)
    pts = []
    for frame in ref['samples']:
        scene.frame_set(int(frame))
        bpy.context.view_layer.update()
        pts += [arm.matrix_world @ pb.head for pb in arm.pose.bones]
    lo, hi = bbox(pts)
    center = (lo + hi) / 2
    size = max(hi - lo) * 1.15 or 1.0
    cam_data = bpy.data.cameras.new('cam')
    cam = bpy.data.objects.new('cam', cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + Vector((0.0, -size * 1.8, size * 0.1))
    look_at(cam, center)
    scene.camera = cam
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'TEXTURE' if ref.get('mesh') else 'SINGLE'
    scene.display.shading.show_object_outline = not ref.get('mesh')
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.image_settings.file_format = 'PNG'
    for o in bpy.data.objects:
        if o.type == 'ARMATURE':
            o.show_in_front = True
            o.data.display_type = 'OCTAHEDRAL'
            o.hide_render = bool(ref.get('mesh'))
    n = ref['frames']
    for f in sorted(set([0, n // 3, (2 * n) // 3, n - 1])):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(render_dir, f'{ref["name"]}_f{f:03d}.png')
        bpy.ops.render.render(write_still=True)
        print(f'blender: rendered {scene.render.filepath}')
    if ref.get('strip'):
        # every frame at 256 px: an mp4 at the motion's fps and one long row (the film strip)
        frame_dir = os.path.join(render_dir, f'{ref["name"]}_frames')
        os.makedirs(frame_dir, exist_ok=True)
        scene.render.resolution_x = scene.render.resolution_y = 256
        scene.frame_start = 0
        scene.frame_end = n - 1
        scene.render.filepath = os.path.join(frame_dir, 'f')
        bpy.ops.render.render(animation=True)
        frames = [os.path.join(frame_dir, f'f{f:04d}.png') for f in range(n)]
        mp4 = os.path.join(render_dir, f'{ref["name"]}.mp4')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(int(round(ref['fps']))), '-i',
                        os.path.join(frame_dir, 'f%04d.png'), '-pix_fmt', 'yuv420p', mp4], check=True)
        strip = os.path.join(render_dir, f'{ref["name"]}_strip.png')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', os.path.join(frame_dir, 'f%04d.png'),
                        '-filter_complex', f'tile={n}x1', '-frames:v', '1', strip], check=True)
        print(f'blender: strip {strip} ({n} frames), video {mp4}')

if ref.get('nice') and ref.get('mesh'):
    nice_dir = ref['nice']
    os.makedirs(nice_dir, exist_ok=True)
    n = ref['frames']
    # the animated bounding box: the evaluated (skinned) mesh at the sampled frames
    pts = []
    for frame in sorted(set([0, n // 3, (2 * n) // 3, n - 1])):
        pts += evaluated_points(frame, meshes)
    lo, hi = bbox(pts)
    center = (lo + hi) / 2
    height = hi.z - lo.z
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = [e for e in engines if 'EEVEE' in e][0]
    scene.render.resolution_x = 900
    scene.render.resolution_y = 1200
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    world = bpy.data.worlds.new('world')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.18, 0.19, 0.21, 1.0)
    bg.inputs['Strength'].default_value = 0.6
    for o in bpy.data.objects:
        if o.type == 'ARMATURE':
            o.hide_render = True
    cam_data = bpy.data.cameras.new('nice_cam')
    cam_data.lens = 50.0
    cam = bpy.data.objects.new('nice_cam', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    # three area lights around the character: key front-left above, fill front-right, rim behind
    for name, offset, energy, size in [('key', Vector((-1.6, -1.8, 1.6)), 900.0, 1.5),
                                       ('fill', Vector((2.0, -1.4, 0.8)), 350.0, 2.5),
                                       ('rim', Vector((0.6, 2.2, 1.8)), 700.0, 1.0)]:
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy * height * height
        ld.size = size * height
        lo_ = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo_)
        lo_.location = center + offset * height
        look_at(lo_, center)
    aspect = scene.render.resolution_x / scene.render.resolution_y
    for f in sorted(set([0, n // 2])):
        frame_box(cam, lo, hi, aspect)
        scene.frame_set(f)
        scene.render.filepath = os.path.join(nice_dir, f'{ref["name"]}_nice_f{f:03d}.png')
        bpy.ops.render.render(write_still=True)
        print(f'blender: rendered {scene.render.filepath}')
    # one head close-up per shape key at 1.0 (and the neutral head for comparison), frame 0
    for label, keys in ref['mesh']['shape_keys'].items():
        o = by_label[label]
        scene.frame_set(0)
        hlo, hhi = bbox(evaluated_points(0, [o]))
        frame_box(cam, hlo, hhi, aspect, fill=0.7, direction=Vector((0.25, -1.0, 0.05)))
        for kb in o.data.shape_keys.key_blocks[1:]:
            kb.value = 0.0
        scene.render.filepath = os.path.join(nice_dir, f'{ref["name"]}_nice_{label}_neutral.png')
        bpy.ops.render.render(write_still=True)
        print(f'blender: rendered {scene.render.filepath}')
        for kb in o.data.shape_keys.key_blocks[1:]:
            kb.value = 1.0
            scene.render.filepath = os.path.join(nice_dir, f'{ref["name"]}_nice_{label}_{kb.name}.png')
            bpy.ops.render.render(write_still=True)
            print(f'blender: rendered {scene.render.filepath} ({label} {kb.name} = 1.0)')
            kb.value = 0.0
print('blender: OK')
