# Port para Xbox 360 (xsdk + aurora-xenon)

Estado: **esqueleto**. Nada disso foi compilado com o toolchain real do xsdk (GCC 15, `powerpc-xsdk-elf`) nem rodou no
console. Os números abaixo vêm de um GCC 13 x86 com `-m32` (`tools/xenon/check_compile.sh`).

## Ideia

Não reescrever o GX. O RE4 passa a linkar contra o **Aurora** (`xenosworks/aurora-xenon`, branch `xenon`), que já traz:
GX (TEV -> shaders do Xenos via vulkan4xenon), VI, PAD, DVD (imagem ISO de GameCube), CARD, MTX e OS.
O que o Aurora substitui no RE4: `src/lib/GX*`, `OS*`, `DVD*`, `CARD*`, `Pad*`, `vi`, `mtx*`, `ai`, `ar`, `arq`.
O que sobra de `src/lib` e ainda não tem destino: CRI (`adx_*`, `sfd_*`, `mpv_*`...), AX/DSP/`syn*` (áudio) e o runtime SN.

## O que foi mudado no código (git log tem o diff)

- `include/gx.h`: o header "enxuto" do ProDG foi trocado por `#include <dolphin/gx.h>` do Aurora (original em
  `include/gx_prodg_orig.h.txt`). Adiciona `GXMatrixIndex1u8` (via `GXParam1u8`), declara `GXSetTevIndBumpXYZ` e deixa
  `GXClearBoundingBox` / `__GXSetIndirectMask` como **no-ops** (o Aurora não implementa; revisar).
- `include/types.h`: com `TARGET_PC` usa os mesmos typedefs do Aurora (`int32_t`...), sem ele mantém os originais.
- `src/game/mes.cpp`, `src/game/dbmodule.cpp`: escritas diretas no FIFO (`GXWGFifo->s16 = x`) viraram `GXParam1s16(x)`.
  No Aurora com `TARGET_PC`, `GXWGFifo` não é endereço de memória: o stream é por software (`lib/gx/fifo.cpp`).
- `joy.h`, `event.h`, `xml.h`, `dbg_tool.h`, `snd_sdk.h`, `os_vi.h`: declarações próprias de `memcpy`/`atoi`/`sprintf`/
  `strcmp`/`pow`/`strcpy`/`OSPanic` trocadas por includes da libc / do Aurora (davam conflito de especificação de exceção).
- `include/dolphin/vi/vitypes.h`, `vifuncs.h`: agora só incluem `<dolphin/vi.h>` do Aurora.
- `dvd.h`, `snd_sdk.h`: `#include <dolphin/arq.h>`.

## Resultado do teste de compilação (GCC 13 x86, -m32, -c, headers do Aurora)

658 unidades fora de `src/lib`:

| Etapa | Compilam |
|---|---|
| Só com os headers do Aurora | 512 |
| + `tools/xenon/codemod_asm.py` (tira truques de asm que só existiam pra reproduzir o compilador SN byte a byte) e `fabsf` -> `__builtin_fabsf` | **631** |

O que o codemod remove (96 arquivos): 124 `register T x asm("rN"/"frN")` (fixação de registrador), 155 `asm("" : ...)` sem
código (enchimento de scheduling, comentados "COMPILER-DIFF"), e o macro `PSQ_L_U8_TO` (usava `psq_l`, que o Xenon não tem:
vira conversão u8 -> f32 em C). Não muda o comportamento, só a alocação de registradores.

Sobram 27, a maioria sem relação com o jogo:

| Quantas | O quê | Ação |
|---|---|---|
| 4 | `sscanf.c`, `sprintf.c`, `fprintf.c`... (`__builtin_saveregs`, varargs do GCC 2.95) | tirar do build: o newlib do xsdk já tem |
| 6 | `memset_2`, `yz2asm`, `t_event`... asm de função inteira em assembly Gekko | ver com o compilador PPC; se não montar, reescrever em C |
| 3+3 | clobbers `"fr2"`, `"r3"` e `"=f"` em `math_sub.cpp`, `main.cpp`, `scheduler.cpp`, `dbmodule`, `esp08`, `shape` | nomes de registrador do SN; no GCC PowerPC é `f2` etc. Confirmar com o compilador PPC |
| 3 | `lineSpace` privado em `r20e`, `r224`, `r307` (`mes.h`) | tornar o membro público |
| 4+2+1 | editores de debug (`src/tools`), `db_port`, `db_mod` | fora do build por enquanto |
| 1 | `exception.cpp` | fora do build |
| 1 | `t_esp.cpp` (crash do próprio GCC x86) | rever com o GCC 15 |

## Como rodar com o compilador de verdade (Fábrica de XEX)

`.github/workflows/re4-check.yml` (copiar para o `.github/workflows/` do Xex-fabrica-, com esta pasta como `re4/` sem `orig/`):
baixa o compilador da release `toolchain-xsdk` que a Fábrica já guarda, clona o aurora-xenon, roda
`tools/xenon/check_compile_ppc.sh` e publica `summary.txt` + logs na release `re4-check`. Não linka nada.
**Não foi testado com o compilador PowerPC real**; a lógica do script foi testada só no GCC x86.

## Problemas conhecidos

1. **`GXSetArray`** (resolvido nos 6 arquivos de jogo; `src/lib` não entra no build). O Aurora exige o tamanho em bytes e
   confere cada índice contra ele (`AURORA_ASSERT` em `command_processor.cpp`): tamanho pequeno demais aborta no draw.
   Posição = `nVtx * stride`, normal = `nNrm * stride`, grade de água/areia = `GRID_VEC_BYTES(p)`. Cor e UV não têm
   contagem no cabeçalho do modelo: `ModelSectionBytes()` (`include/gx_array.h`) usa a distância até a próxima seção do bin.
   `le` = `false` (dados big-endian). Falta validar rodando.
2. **`GXClearBoundingBox` / `__GXSetIndirectMask`**: no-op por enquanto.
3. **Áudio e vídeo**: ~80 símbolos sem destino (`AX*`, `AXFX*`, `MIX*`, `ADX*`, `SFD*`...). Decisão do usuário: começar
   mudo e depois converter (música e vídeo, ex.: para mp4).
4. **Overlays REL**: o jogo carrega 114 RELs; no 360 precisam ser linkados estaticamente (as unidades já são compiladas
   do `src/`, falta resolver símbolos duplicados entre módulos).
5. **Disco**: o Aurora lê um disco; o jogo usa dois (disc 2 = 4 RELs das ilhas). Não ligar a troca de disco, montar as duas
   imagens como uma só.
6. **Memória**: CPU e GPU dividem 512 MB. Dimensionar pools do Aurora (já no `CMakeLists.txt`).
7. **`char`**: não usar `-fsigned-char` (Dusklight usa; o SN em PowerPC usava `char` sem sinal).
8. **Chamadas `PC*`** (`PCinit`, `PCopen`...): E/S com o PC do kit de debug; remover.

## Próximos passos

1. Rodar o workflow `re4-check` (acima) e tratar o que sobrar.
2. Resolver `GXSetArray` chamada por chamada.
3. Primeiro link: `main_xenon.cpp` + stubs para o áudio/vídeo; ver o que sobra de símbolos indefinidos.
4. Tela preta com o loop do jogo rodando, depois sala, jogador e câmera.

## Update: Gekko code in C
- `CalcSk1_x/x2`, `SINF/COSF/LIMIT_ANGLE`, `SQRTF`, `PSQ_*_S16` rewritten in C; GQR setup asm removed; locked cache = `g_LockedCache` (`LC_BASE`, include/gc_compat.h, platforms/xenon/gc_compat.cpp).
- Host check: 644 of 658 units compile. The rest: `tools/xenon/excluded.txt` (not built) plus `memset_2.cpp` and `yz2asm.cpp` (whole-function PPC asm; only the real PPC compiler can judge them).
- Next: run the `re4-check` workflow with the real xsdk compiler (needs the project pushed to the Xex-fabrica repo).
