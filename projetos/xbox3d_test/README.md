# XSDK Two-Player House — OBJ Import Test

A small Xbox 360 / XSDK 3D prototype using the direct XSDK GPU path (no GX).

## What's in this revision

- Two connected open-front rooms with a central doorway and a door leaf left ajar.
- Two independently controlled player characters.
- The mannequin is authored as an original Wavefront OBJ mesh.
- A build-time Python converter reads OBJ geometry, triangulates polygon faces and generates a compact C header. The Xbox does not parse text OBJ at runtime.
- Existing XSDK shaders, GPU buffers, splash, display and controller setup are retained.

## Controls

- Controller 1 left stick: move the blue-green character.
- Controller 2 left stick: move the orange character.
- Controller 1 BACK: exit.

Both players can pass between rooms through the doorway. The partition blocks crossing outside the opening.

## OBJ importer scope

The first importer supports `v` positions and `f` faces, including positive and negative position indices and common face tokens such as `v/vt/vn`. Polygon faces are fan-triangulated. UVs, normals, MTL materials, textures and skeletal animation are not imported yet; the shader applies the per-player tint.

The included `assets/player_lowpoly.obj` is an original low-poly mannequin made for this test.

## Build and test

The XSDK GitHub Actions workflow compiles this folder into `xbox3d_test.xex`.
A successful Actions build proves compilation only. The XEX still needs to be launched on a real Xbox 360 to verify rendering, room transitions and both controller slots.
