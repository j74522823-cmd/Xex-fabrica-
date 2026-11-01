# RE4 (GameCube debug build) → Xbox 360: guia para continuar

Documento para outra IA (ou pessoa) retomar o projeto. Última atualização: 2026-11-01.

## 1. O que é

- Origem: decompilação do **Resident Evil 4 GameCube (debug build)**, ~570 mil linhas de C/C++, sem assets, compilada originalmente com ProDG (GCC 2.95) e CodeWarrior. Config da versão: `config/G4BE08`.
- Destino: **Xbox 360 com RGH/hack** (homebrew XEX), compilado com **xsdk** (`xenosworks/xsdk`, GCC 15, alvo `powerpc-xsdk-elf`, sem Microsoft XDK).
- Dono do projeto: fala português (Brasil), **sem PC** (trabalha pelo celular/navegador), então tudo roda em GitHub Actions.
- Decisões dele: não reescrever o GX; música e vídeo podem começar **mudos** (converter depois, ex. mp4/Bink); **troca de disco não importa**; memória do console (512 MB compartilhados CPU/GPU) é preocupação.

## 2. Onde está o código

- Repositório: `https://github.com/j74522823-cmd/Xex-fabrica-` ("Jojo Engine"), branch **`re4-port`** (a `main` tem só o build antigo `xex.yml`, não mexer).
- O projeto fica na pasta **`re4/`** da branch. Cópia de trabalho local da sessão anterior: `/home/claude/re4-360` (git próprio; **sem** `orig/` nem assets).
- Workflows (`.github/workflows/`):
  - `xex.yml` ("Fabrica de XEX"): do usuário; gera o compilador e guarda no release **`toolchain-xsdk`** (`toolchain.tar.gz` → `$HOME/xsdk-gcc`). Não apagar esse release.
  - `re4-check.yml` ("RE4 -> 360 (compilar so, sem linkar)"): compila cada unidade com `powerpc-xsdk-elf-g++`. Resultado no release `re4-check` (`summary.txt`).
  - `re4-link.yml` ("RE4 -> 360 (compilar e linkar)"): constrói libxsdk, vulkan4xenon, SDL-xenon; junta com aurora-xenon e o RE4; linka. Resultado no release **`re4-link`** (`summary.txt`, `link.log`, `configure.log` e **`re4.xex`** quando dá certo). Dispara sozinho em push que toque `re4/**`; leva ~15–17 min.
- Versões fixadas no `re4-link.yml`: xsdk `8c58c7a3…` (o `49307c7` antigo é velho demais para o vulkan4xenon), vulkan4xenon `df25dc50…`, SDL-xenon `adb87a74…`, glslang-xenon `d2f00185…`, aurora-xenon `a526001c…` (branch `xenon`, clonado em `re4/extern/aurora`, não versionado).

## 3. Como trabalhar (ciclo)

1. Editar em `re4/…` (ou na cópia local e copiar).
2. `git push origin re4-port` → o `re4-link` roda.
3. Ler o resultado **por REST** (o `gh release …` usa GraphQL, bloqueado nas sessões do Claude Code):
   ```bash
   gh api repos/j74522823-cmd/xex-fabrica-/releases/tags/re4-link --jq '.assets[]|"\(.id) \(.name)"'
   gh api -H "Accept: application/octet-stream" repos/j74522823-cmd/xex-fabrica-/releases/assets/<id> > summary.txt
   ```
4. Para esperar o run: filtrar pelo nome exato `"RE4 -> 360 (compilar e linkar)"` (o filtro "linkar" também casa com o `re4-check`, "sem linkar", e engana).
5. O `summary.txt` já lista erros comuns, símbolos indefinidos e definições múltiplas; o `link.log` tem os detalhes (`grep "^FAILED" -A5`).

Teste rápido local (compilador x86, `-m32`): `tools/xenon/check_compile.sh <aurora-xenon> <saida>`; só acha erros de C++ (não julga asm PowerPC). Lista de arquivos fora do build: `tools/xenon/excluded.txt`.

## 4. Arquitetura da porta

- **GX → Aurora** (`aurora-xenon`, backend `vulkan4xenon`): não reescrevemos o GX; `include/gx.h` virou wrapper de `<dolphin/gx.h>` do Aurora. Com `TARGET_PC`, `GXWGFifo` não é endereço: usar `GXParam1s16`/`GXCmd1*`. `GXSetArray(attr, data, tamanhoEmBytes, stride, false)` exige o tamanho (Aurora confere índices); ver `include/gx_array.h` (`ModelSectionBytes`, `GRID_VEC_BYTES`).
- **Ordem de include**: o diretório `include` do Aurora vem **antes** do `include` do RE4 (senão os `dolphin/*.h` antigos do RE4 escondem os do Aurora). Não usar `-fsigned-char` (char do PowerPC é unsigned).
- **Código Gekko removido/reescrito em C**: paired singles, GQR, `psq_*`, `CalcSk1_x/x2`, `SINF/COSF/LIMIT_ANGLE`, `SQRTF`, `PSQ_*_S16`. Cache bloqueado (`0xE0000000`) → buffer `g_LockedCache` (`LC_BASE`, `include/gc_compat.h`). `tools/xenon/codemod_asm.py` tirou fixadores de registrador e `asm` de enchimento usados só para casar bytes. `vec.h` agora inclui `<dolphin/mtx.h>` do Aurora (mapeia `PSMTX*`→`MTX*`); `PSMTX44MultVec` implementado em `platforms/xenon/gc_compat.cpp`.
- **Camada de SO** (`platforms/xenon/os_compat.cpp`): o Aurora só declara. Aqui: threads por pthreads com "baton" (uma thread roda por vez; troca só em `OSResume/Suspend/Sleep/Wakeup/Exit`, prioridade menor = mais alta), semáforos, interrupções (contador), `OSReport`/`OSPanic`, stopwatch, console, fontes, VI (`VIWaitForRetrace` dorme 16,6 ms por enquanto). `xsdk` não tem `pthread_exit` → `setjmp/longjmp`.
- **REL → estático**: no GameCube cada módulo (stage/arma/inimigo: 114, 105 compilados aqui) era REL separado e os nomes globais colidem. `tools/xenon/gen_modules.py` lê `config/G4BE08/modules.py` + `rel.json` e gera `modules.cmake` (fontes por módulo), `rel_table.cpp` (id do módulo → `<mod>__prolog/__epilog/__unresolved`) e `rel_unresolved.cpp` (stubs fracos das salas ausentes). No CMake cada módulo é compilado com `-DREL_MODULE=<mod>`, ligado com `ld -r -d --force-group-allocation` e `objcopy` deixa globais só os 3 pontos de entrada (+ `tools/xenon/rel_exports.txt`: símbolos que um REL importava de outro, ficam *fracos*). `OSLink` acha o módulo pelo `info->id` e preenche `prolog/epilog/unresolved` no cabeçalho; `OSUnlink` não faz nada. O jogo ainda lê o `.rel` do disco, só ignora o código.
- **Símbolos legados** (`platforms/xenon/legacy_syms.cpp`): nomes GCC 2.95 (`FlgOnStatus__5EventUl`, `SndCall__F…`, `ScreenReSize__FUsUs`…), `__builtin_new/delete`, `_ctors/_dtors` vazios, `ExceptionInit`, `re4_unresolved`.
- **Mudo**: `platforms/xenon/audio_stubs.cpp` (AX/MIX/SYN/SEQ/ADX/Sofdec/`PC*` → no-op ou -1), gerado dos protótipos reais.
- **Fora do build**: `src/game/*.c` (libc do SN; o xsdk tem newlib), `src/Tools`, `src/tools`, `src/t_*/` (editores de debug), `db_widget.cpp`, `exception.cpp`. `src/lib/texPalette.c` e `fileCache.c` entram (charPipeline, não existe no Aurora).
- **Cuidados que já mordemos**: `static` do original (REL resolvia local entre módulos) precisa virar global quando outro arquivo usa (`QuakeKill`, `EmCatchSubSet`, `Em32_fs_tbl`, `em21_trap_cam`…); `inline` fora da classe não emite símbolo no GCC 15 (`cModel::getPartsPtr`, `isTrans`); template precisa de instanciação explícita (`cManager<cObj>::destroyNow`); linhas `asm(".section …")` soltas quebram CFI, mas as que **definem rótulos** (`r222_k212:`, `r224_zero:`) precisam ficar.

## 5. Estado atual (2026-11-01)

- Compila: 620/620 unidades no compilador real. **Link fecha** e gera `re4.xex` (~24 MB) no release `re4-link`. **Nunca foi executado.** O `xenia_scan` do build avisa de ~481 instruções que o Xenia pula (vêm do newlib, não do RE4); no console real não importa.
- O XEX usa o `int main()` do próprio jogo (`src/game/main.cpp`) como entrada; **não inicializa o Aurora**, então deve falhar logo.

## 6. Próximos passos (ordem sugerida)

1. **`platforms/xenon/main_xenon.cpp`**: `aurora_initialize(...)` (ver `platforms/xenon` do `dusklight-xenon` e `aurora-xenon/examples/simple.c`), depois chamar o jogo. Trocar o `main` do jogo por uma função chamada pelo novo `main` (renomear com `-Dmain=re4_game_main` só em `src/game/main.cpp`).
2. **Disco**: apontar o DVD do Aurora (`AURORA_NOD_PROVIDER=iso`) para a imagem do disco de debug (disco 1; troca de disco não importa). Definir onde o usuário coloca o `.iso`.
3. **Pacing**: ligar `VIWaitForRetrace`/`VISetNextFrameBuffer` ao present do Aurora (hoje só dorme 16,6 ms); GX `GXCopyDisp`/frame boundaries.
4. **Pendências conhecidas**: `GXClearBoundingBox` e `__GXSetIndirectMask` são no-ops; o jogo de overlays e a "bss do DLL" (primeiros 0x80 bytes da estrutura do módulo, ver `read.cpp`) ainda acoplam jogo↔módulo por dados: pode exigir ajuste; salas de outros módulos caem em `re4_unresolved` (HALT) se chamadas; funções `PC*` (link de debug) retornam -1 — checar `file.cpp`.
5. **Memória**: tamanhos dos pools do Aurora estão no `CMakeLists.txt` (`AURORA_*_POOL_SIZE`); dimensionar com o uso real; heap do jogo (`MEM_ALLOC`) × 512 MB.
6. **Mais tarde**: áudio (converter streams e tocar via áudio do xsdk), vídeo (Bink/mp4), disco 2 (st3_*), shader pack do vulkan4xenon (`DUSK_XSDK_GLSL_PACK` no Dusklight) para evitar compilar shader no console, TITLE_ID real (hoje `0x52453420` provisório).

## 7. Armadilhas de ferramenta

- `gh release …` e GraphQL: bloqueados; usar `gh api` REST.
- O hook de "stop" pode reclamar de commit não enviado mesmo já enviado (clone raso sem ref remota): `git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'; git fetch origin re4-port; git branch -u origin/re4-port`.
- Push exige o app do Claude no GitHub instalado na conta com escrita no repositório.
- Mudar o xsdk exige conferir se o release `toolchain-xsdk` ainda serve (hoje o script do compilador só mudou em comentário entre `49307c7` e `8c58c7a`).
