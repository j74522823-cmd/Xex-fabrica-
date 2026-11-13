# RE4 Xenon — plano da camada gráfica própria

Branch de trabalho: `re4-xenon-native`
Base: `debug/re4-boot-trace`
Objetivo: preservar a lógica de jogo da descompilação G4BE08/Adonis e isolar/substituir, de forma incremental, a implementação gráfica usada no Xbox 360.

## Decisão de arquitetura

Não remover o GX nem reescrever o renderizador antes de medir o que já funciona.

O estado atual já encaminha as chamadas GX do jogo para o Aurora (`aurora::gx`), com `AURORA_GFX_BACKEND=vulkan4xenon`. Portanto, a hipótese "GX inteiro está quebrado" ainda não está demonstrada. O gargalo pode estar em inicialização do XEX, criação do dispositivo/backend, tradução de estados GX, upload de texturas, shaders/TEV, sincronização de quadros ou em operações GX ausentes.

A camada `platforms/xenon/gc_compat.cpp` atual não é um renderizador: contém compatibilidade matemática/cache e utilitários de lista/string. Ela deve permanecer separada do futuro backend gráfico.

## Inventário confirmado no código

- `CMakeLists.txt`: força `AURORA_GFX_BACKEND=vulkan4xenon`, adiciona Aurora e vincula `aurora::gx`, `aurora::gd`, `aurora::vi` e `vulkan4xenon`.
- `include/gx.h`: o build Xenon prioriza os headers GX do Aurora.
- `src/game/gx_sub.cpp`: usa estado GX, projeção ortográfica, TEV, descritores de vértice e `GXBegin` para desenhar o fundo.
- `src/game/libgpu.cpp`: constrói primitivas (triângulos, quadriláteros, linhas) através de chamadas GX.
- `main_xenon.cpp`: inicializa Aurora com backend Vulkan e abre a imagem ISO antes de entrar em `re4_game_main()`.
- `docs/360-port.md` registra `GXClearBoundingBox` e `__GXSetIndirectMask` como no-ops e aponta `GXSetArray` como ponto que exige validação em runtime.
- O estado anterior também marca `GXCopyDisp`/`GXDrawDone` e o ciclo VI/frame como não revisados em console.

## Regras para a nova implementação

1. Preservar `src/game/**` e os dados/estruturas da descompilação sempre que possível.
2. Não substituir chamadas GX em massa nem editar a lógica de gameplay para contornar problemas gráficos.
3. Toda substituição deve ficar atrás de uma interface Xenon, ou em compatibilidade pequena e documentada.
4. Manter Aurora como backend de referência enquanto a alternativa não provar que desenha corretamente no hardware.
5. Não declarar um recurso "implementado" apenas porque compila: exigir evidência no console (log e imagem/tela).
6. Não misturar o diagnóstico da entrada do XEX com o diagnóstico de renderização.

## Etapas e critérios de aceite

### G0 — preservar a base e separar a branch
- Esta branch foi criada sem alterar a branch de diagnóstico.
- Nenhuma alteração de gameplay ou GX foi feita nesta etapa.

### G1 — auditoria das chamadas GX
- Enumerar as APIs GX chamadas pelo jogo e seus usos.
- Cruzar com as implementações do Aurora e classificar: suportada, parcial, no-op, desconhecida.
- Priorizar chamadas usadas no primeiro frame e no desenho do fundo, antes de cobrir efeitos raros.
- Saída esperada: tabela de cobertura com arquivo/linha e evidência da implementação.

### G2 — teste gráfico mínimo independente
- Criar um pequeno alvo de teste Xenon que inicialize o backend e desenhe: limpeza de tela, triângulo de cor sólida e textura simples.
- Testar separadamente inicialização, upload de textura, estado de blend/depth e apresentação.
- O teste não deve iniciar a lógica do RE4; assim, uma falha não fica confundida com o boot do jogo.

### G3 — adaptadores de compatibilidade
- Implementar somente as lacunas confirmadas em G1/G2.
- Preferir adaptar a semântica GX ao backend existente antes de criar outro renderer.
- Se Aurora/vulkan4xenon não atender a uma operação essencial, definir interface própria `re4_gfx` e implementar essa operação para Xenon.

### G4 — reconectar o jogo
- Primeiro desenhar fundo/cena simples.
- Depois câmera, geometria, textura, iluminação/TEV e efeitos por grupos.
- Só então retomar o loop completo e o gameplay.

## Não fazer ainda

- Não apagar nem substituir `include/dolphin/gx*` ou `src/lib/GX*` em bloco.
- Não remover Aurora/vulkan4xenon antes de existir um teste alternativo funcional.
- Não alterar ISO, RELs, lógica de inimigos, física ou controles para tratar um problema que ainda não foi localizado.
- Não prometer que o crash atual é causado pelo GX: o log atual ainda precisa provar que a entrada Xenon e a inicialização Aurora foram alcançadas.

## Próxima tarefa técnica

Executar G1: produzir a lista real das APIs GX usadas pelo RE4 e comparar com as implementações da branch `xenon` de `xenosworks/aurora-xenon`. A primeira lista de prioridade é o caminho do primeiro frame: init GX, viewport/projeção, descriptors/arrays, TEV, textura, draw, copy/present e sincronização VI.
