# RE4 Xenon — renderizador nativo próprio

Branch: `re4-xenon-native`
Base de código do jogo: descompilação G4BE08/Adonis.
Objetivo: preservar a lógica do RE4 e **recriar a renderização para o Xbox 360**, sem implementar um tradutor GX nem depender do Aurora GX para desenhar.

## Decisão

Não construir uma camada de compatibilidade GX->Vulkan. O GX do GameCube serve apenas como referência para entender o que cada sistema do jogo espera visualmente. O novo renderizador será implementado diretamente em Vulkan4Xenon, que dirige o Xenos.

A lógica do jogo (IA, entidades, fases, física, inventário, eventos e dados) deve ser preservada sempre que possível. Os pontos de chamada gráficos serão migrados por partes para o renderizador nativo. Até cada grupo estar convertido, a versão completa do jogo não estará pronta para executar com o renderizador novo.

## Primeiro código criado

- `platforms/xenon/re4_xenon_gfx.h`
- `platforms/xenon/re4_xenon_gfx.cpp`
- O novo arquivo foi adicionado ao target `re4` em `CMakeLists.txt`.
- Implementação inicial usa Vulkan diretamente: cria instância, dispositivo, display surface, swapchain, render pass, framebuffers, command buffers, semáforos e fence.
- `re4_xenon_gfx_clear_frame(r,g,b,a)` limpa e apresenta um frame com cor escolhida.
- Logs usam o prefixo `[RE4-GFX]` para identificar cada etapa.

**Limite atual:** este primeiro módulo é um teste de fundação do renderizador; ainda não está ligado ao loop do jogo nem desenha modelos/texturas do RE4. Não substituirá o XEX existente até compilar e ser testado no console.

## Arquitetura do renderizador novo

1. **Display e apresentação:** swapchain, sincronização, resolução, clear e present.
2. **Geometria:** buffers de vértices/índices, formatos de posição/normal/UV/cor e draws.
3. **Transformações:** matrizes de mundo, câmera e projeção.
4. **Materiais e texturas:** conversão dos formatos originais, upload e sampling.
5. **Iluminação e materiais:** luzes, fog, blending, alpha test, depth e culling.
6. **Combinação de materiais:** reproduzir os resultados visuais necessários do TEV com shaders Vulkan escritos para o jogo; não traduzir comandos GX em tempo real.
7. **Sistemas especiais:** sombras, água, efeitos, partículas, transparências e pós-processamento.

## Sequência de integração

- **R0 — inicialização nativa:** Vulkan4Xenon cria o dispositivo e apresenta uma cor de teste.
- **R1 — triângulo:** pipeline gráfico e shaders próprios, sem Aurora GX.
- **R2 — textura:** carregar uma textura de teste e exibi-la.
- **R3 — modelo:** carregar geometria real de um recurso RE4 e desenhar com câmera simples.
- **R4 — cena:** cenário e objetos estáticos de uma sala/área do jogo.
- **R5 — materiais:** iluminação, transparência, fog e shaders por família de material.
- **R6 — integração:** substituir chamadas gráficas do jogo gradualmente, mantendo IA, gameplay e dados originais.

## Regras

- Não escrever stubs que fingem renderizar; cada etapa precisa de evidência visual no console.
- Não remover os arquivos GX originais: ficam como documentação da semântica e referência de comportamento.
- Não alterar gameplay para contornar defeitos gráficos.
- Não declarar o renderer novo integrado até que uma cena real do RE4 seja apresentada.
- Manter a trilha de diagnóstico do boot separada da trilha do renderizador.

## Lacunas já observadas no Aurora GX

A auditoria anterior encontrou, em `xenosworks/aurora-xenon`, funções de cópia de framebuffer sem implementação, incluindo `GXCopyDisp`, além de operações de configuração de cópia e bounding box parciais. Isso ajuda a explicar por que não devemos depender do caminho GX existente, mas não prova que essas funções sejam a causa do marcador MAIN_XENON ausente. O novo renderer evita essa dependência para o desenho; a inicialização e leitura de disco ainda precisam de integração própria.

## Estado honesto

O módulo Vulkan inicial foi escrito e adicionado ao build, mas a compilação automática está em andamento. Ainda não há XEX testado com ele, nem cena do RE4 renderizada. O próximo passo é corrigir eventuais erros do build e fechar R0 antes de implementar shaders/triângulo.
