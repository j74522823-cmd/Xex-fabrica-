# Bad Ice-Cream — build para Xbox 360 (xsdk)

Estado: **escrito, mas não compilado com a toolchain PowerPC nem rodado no console.** Só a sintaxe de `platform_xbox360.cpp` foi checada no PC contra os headers reais do xsdk (commit 3960a1d). Espere corrigir pequenos erros no primeiro build.

## Build (na sua máquina, com o xsdk já montado)
```
cmake -S xbox360 -B build/bic -G Ninja -DCMAKE_TOOLCHAIN_FILE=<xsdk>/cmake/xsdk.cmake
cmake --build build/bic
```
Saída: `build/bic/badicecream.xex`. O CMake compila `src/engine.cpp`, `src/render.cpp`, `src/game.cpp` e `xbox360/platform_xbox360.cpp`, e gera `badicecream_shaders.h` com `xsdk_add_shaders` (nomes esperados: `sprite_vert`, `sprite_frag`, `SPRITE_VERT_PUSH`, `SPRITE_VERT_PUSH_REGISTERS`, `SPRITE_FRAG_SAMPLER_0_0`; se o gerador der outros nomes, ajuste em `platform_xbox360.cpp`).

## Dados
Gere a pasta `runtime/` no PC: `python3 -I tools/export_runtime.py . runtime` (PIL, numpy, ffmpeg).
No console, copie o conteúdo de `runtime/` para `data/` ao lado do `.xex`: `data/atlas.txt`, `data/atlas0..5.argb`, `data/levels/`, `data/snd/`, `data/snd.txt`.
O jogo lê `game:/data/...`.

## Controles
- Os **dois primeiros controles conectados** (índices 0 a 3) são o jogador 1 e o 2.
- No título: START no controle 1 = 1 jogador; START no controle 2 = **coop**.
- Direcional ou analógico esquerdo: andar. A/B/X/Y/LB/RB: soprar gelo. BACK: sair.

## Pontos de atenção
- 6 páginas de atlas 2048x2048 A8R8G8B8 = 96 MB de memória de GPU.
- Escala do palco 550 -> 720 de altura (1.31x) com filtro ponto: pixels de tamanhos desiguais.
- Lógica a 25 Hz, tela a 60 Hz: sem interpolação, pode trepidar.
- Teto de 4096 sprites por quadro (log avisa se estourar).
- Áudio: mixer mono nas duas frentes, 24 vozes, música na voz 0.

## Pela fábrica de XEX (GitHub Actions)
Um push em `projetos/` gera a release **ultimo-xex** com `badicecream.xex`, `badicecream-data.zip` e `log.txt`.
Extraia `badicecream-data.zip` para uma pasta `data/` ao lado do .xex no console (game:/data/).
