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
No console, copie o conteúdo de `runtime/` para `data/` ao lado do .xex: `data/atlas.txt`, `data/atlas0..5.argb`, `data/levels/`, `data/snd/`, `data/snd.txt`.
O jogo lê `game:/data/...`.

## Controles
- Os dois primeiros controles conectados são usados como P1 e P2.
- No título, START do P1 abre a seleção de personagens.
- Na seleção, esquerda/direita alterna entre Vanilla e Strawberry para o jogador correspondente.
- START do P2 entra no coop; START do P1 confirma e começa a fase.
- Durante a fase: direcional ou analógico esquerdo para andar; A/B/X/Y/LB/RB para soprar gelo; BACK para sair.

## Passwords
O sistema de passwords está **planejado, mas ainda não implementado**. A proposta inicial é gerar uma senha curta ao concluir uma fase e permitir continuar digitando-a no menu. A senha deve guardar apenas o necessário para retomar o progresso (fase desbloqueada e modo solo/coop), sem depender de perfil Xbox, HD ou armazenamento interno. Veja `docs/PASSWORDS.md`.

## Pontos de atenção
- 6 páginas de atlas 2048x2048 A8R8G8B8 = 96 MB de memória de GPU.
- Escala do palco 550 -> 720 de altura (1.31x) com filtro ponto: pixels de tamanhos desiguais.
- Lógica a 25 Hz, tela a 60 Hz: sem interpolação, pode trepidar.
- Teto de 4096 sprites por quadro (log avisa se estourar).
- Áudio: mixer mono nas duas frentes, 24 vozes, música na voz 0.

## Pela fábrica de XEX (GitHub Actions)
Um push em `projetos/` gera a release **ultimo-xex** com `badicecream.xex`, `badicecream-data.zip` e `log.txt`.
Extraia `badicecream-data.zip` para uma pasta `data/` ao lado do .xex no console (`game:/data/`).
