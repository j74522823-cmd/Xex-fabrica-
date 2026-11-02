# PROJECT_STATE — RE4 (GameCube debug decomp) → Xbox 360

Atualizado: 2026-11-01. Repositório: `j74522823-cmd/Xex-fabrica-`, branch `re4-port`, pasta `re4/`. Guia detalhado: `docs/HANDOFF.md`.

## Estado verificado (commit 48464a4)
- Compilação: 620/620 unidades com o compilador real (`powerpc-xsdk-elf-g++`), 0 erros.
- Link: fecha, 0 símbolos indefinidos, 0 definições múltiplas, 105 módulos REL ligados estaticamente.
- Saída: `re4.xex` (~24 MB) no release `re4-link` (`summary.txt`, `link.log`, `configure.log`).
- Tudo salvo e enviado à branch `re4-port`.
- Entrada: `platforms/xenon/main_xenon.cpp` → `aurora_initialize` (Vulkan, vsync, MEM1 24 MB, ARAM 16 MB) → `aurora_dvd_open("game:\re4.iso")` → `re4_game_main()` (main original renomeado). Fim de quadro: `VISetNextFrameBuffer` → `aurora_end_frame/update/begin_frame`.

## NUNCA TESTADO
O XEX nunca foi executado (nem no console nem no Xenia). Nada abaixo foi confirmado em execução.

## O que falta (exato)
1. **Primeiro teste no console**: colocar `re4.xex` + `re4.iso` (disco 1 debug, G4BE08) na mesma pasta; reportar até onde chega (logs `re4:` / `[aurora`).
2. **Disco**: nome/caminho `game:\re4.iso` fixo (macro `RE4_DISC_PATH`); disco 2 (`st3_*`) não tratado; troca de disco ignorada.
3. **Ritmo de quadros**: `VIWaitForRetrace` só dorme 2 ms e chama o callback; o presente real vem do Aurora. Se `SYS_SCREEN_STOP` pular `VISetNextFrameBuffer`, o quadro Aurora não fecha. `GXCopyDisp`/`GXDrawDone` não revisados.
4. **GX**: `GXClearBoundingBox` e `__GXSetIndirectMask` são no-ops.
5. **Módulos REL**: salas de módulo ausente caem em `re4_unresolved` (trava); "bss do DLL" (primeiros 0x80 bytes da estrutura do módulo, `read.cpp`) pode acoplar jogo↔módulo; `OSUnlink` não faz nada.
6. **Arquivos de debug**: `PC*` retornam -1; checar `file.cpp`.
7. **Memória**: pools do Aurora e heap do jogo (`MEM_ALLOC`) não dimensionados para 512 MB.
8. **Shaders**: sem shader pack do vulkan4xenon (compila no console).
9. **Áudio e vídeo**: tudo mudo (stubs AX/ADX/Sofdec); converter streams depois.
10. **TITLE_ID** provisório `0x52453420`.
11. **Fora do build**: `src/game/*.c`, `src/Tools`, `src/t_*`, `db_widget.cpp`, `exception.cpp`.
12. Código Gekko (paired singles/GQR) foi reescrito em C sem teste numérico.

## Ciclo de trabalho
Editar → `git push origin re4-port` → run "RE4 -> 360 (compilar e linkar)" (~15 min) → ler `summary.txt` via `gh api` REST (ver HANDOFF.md §3).
