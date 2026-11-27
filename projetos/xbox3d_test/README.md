# XSDK Two Player House

A first 3D sandbox for Xbox 360, built directly on the XSDK GPU path (no GX).

## Scene
- A small open-front room generated procedurally from cube meshes.
- Two simple mannequin characters, each with independent world coordinates.
- Fixed shared camera.
- Two controller slots: player 1 uses controller index 0, player 2 uses controller index 1.
- BACK on player 1 exits.

## Controls
- Controller 1 left stick: move the blue-green character.
- Controller 2 left stick: move the orange character.
- Controller 1 BACK: exit.

## Build and test
The XSDK GitHub Actions workflow compiles this folder into `xbox3d_test.xex`.
A successful Actions build proves compilation only. The XEX still needs to be launched on a real Xbox 360 to verify rendering and controller behavior.

This is a procedural prototype, not an imported RE4 house or production character model. It intentionally avoids external assets so the first test is self-contained.
