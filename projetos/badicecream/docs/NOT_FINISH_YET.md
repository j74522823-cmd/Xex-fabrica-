# Bad Ice-Cream 360 — estado "not finish yet" (2ª versão)

**Atualização (3ª rodada): `engine`, `render`, `game` e `platform_host` compilam sem erros (g++ 17, ASan/UBSan) e o host renderiza quadros corretos das fases 0 e 23 em coop (PPM conferido a olho). Ainda falta o backend Xbox 360.**

**Nada aqui foi testado em console. Só o núcleo (`engine.cpp`) foi compilado (g++ 17, ASan/UBSan): passou o teste de fumaça nas 40 fases, 2 jogadores, entrada aleatória, sem violações. `render.cpp`, `game.cpp` e `platform_host.cpp` foram escritos mas NÃO compilados nem rodados.**

## Feito
- `src/engine.cpp` + `engine.hpp`: simulação completa pelas regras do NOT_FINISH anterior (jogador, gelo, raio, 11 inimigos, 10 frutas em ondas, fogueiras, setas, câmera, **coop com 2 jogadores**, derrota só quando os dois morrem). Sons já com os nomes originais do bytecode.
- `tools/gen_tiles.py` → `src/tile_table.hpp`: tiles andáveis + pegada de objetos grandes. Em 36/40 fases todo item é alcançável; as 4 restantes só têm gelo em parede ou cerejas (teleportam).
- `tools/export_runtime.py`: gera `runtime/` (atlas.txt, 6 páginas ARGB, fases, 26 sons s16 48 kHz). Rode: `python3 -I tools/export_runtime.py . runtime` (precisa PIL, numpy, ffmpeg). Mapa dos sons: arquivo = id do clipe − 1.
- `src/platform.hpp` (interface), `atlas.hpp`, `render.cpp` (monta quads com z-order), `game.cpp` (título, fases, vitória/derrota, HUD, música), `platform_host.cpp` (teste no PC, grava PPM).
- XSDK estudado (clone local): GPU em C17 (`xsdk_gpu_*`, texturas A8R8G8B8, shaders GLSL via `xsdk_add_shaders`), entrada `XamInputGetState(0..3)`, áudio `xsdk_audio_*` (frames 256x6ch 48 kHz float), texto `xsdk_text_draw`, arquivos em `game:/data/...`, `clock_gettime`.

## Falta (nessa ordem)
1. (FEITO) Compilar/rodar o host: `g++ -std=c++17 src/engine.cpp src/render.cpp src/game.cpp src/platform_host.cpp -o bic_host && ./bic_host --data runtime --level 0 --frames 300 --dump f.ppm` e corrigir erros.
2. Backend Xbox 360 (não escrito): `gpu_sprites.c/.h` + `sprite.vert/.frag` (modelo: `src/text.c` do XSDK; locations 0 pos, 1 cor, 2 uv; blend SRC_ALPHA; sampler POINT/CLAMP), `platform_xbox360.cpp` (present_open 720p, escala 720/550 centralizada, 2 controles = 1º e 2º conectados entre os índices 0–3, mixer de áudio em thread), `main.cpp`, `CMakeLists.txt` com `xsdk.cmake`. Páginas do atlas = 6×16 MB de GPU (DXT5 reduziria).
3. Pacing: lógica 25 Hz, tela 60 Hz → trepidação; interpolar depois.

## Suposições (marcadas no código)
Tiles livres (heurística + teste de alcance), velocidade/regra de Kiwi e Pear, estados do Chaser, 1/4 de chance de teleporte do Tower, gelo derrete em fogueira que reacende, InvisibleTile e FlamePad inertes, fórmula do bônus de tempo, FPS=25, atraso de 50 quadros na vitória.
