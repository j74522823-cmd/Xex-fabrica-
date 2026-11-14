# Recompilação fiel dos Bad Ice-Cream — plano técnico

## Objetivo aprovado

A adaptação para Xbox 360 deve parecer o jogo Flash original, não um remake inspirado nele. Preservar apresentação, fases, personagens, animações, tempos, regras, inimigos, áudio e cooperação sempre que os arquivos permitirem. As mudanças visíveis devem se limitar ao necessário para controles, tela, armazenamento e integração com o console.

## Fontes recebidas em 14/11/2026

Os dois SWFs enviados pelo usuário foram inspecionados localmente:

| Medida | Bad Ice-Cream 1 | Bad Ice-Cream 2 |
|---|---:|---:|
| Versão SWF | 9 | 10 |
| Tamanho comprimido | 1.752.286 bytes | 2.578.510 bytes |
| Tamanho descomprimido declarado | 2.593.853 bytes | 3.658.526 bytes |
| FPS declarado no cabeçalho | 30 | 30 |
| Frames da timeline principal | 144 | 121 |
| Entradas SymbolClass nomeadas | 469 | 884 |
| Tags DefineSprite | 671 | 1.205 |
| Definições de bitmap | 2.304 | 4.016 |
| Tags DefineSound | 26 | 52 |
| Bloco ABC DoABC2 | 388.903 bytes | 529.250 bytes |

Foram encontrados 355 nomes SymbolClass presentes nos dois arquivos. Isso identifica bons candidatos para compartilhamento, mas não prova que suas timelines, dados internos ou comportamentos sejam idênticos.

## Ferramenta de inspeção

A ferramenta tools/compare_swfs.py compara dois SWFs comprimidos CWS/FWS, registra os nomes SymbolClass, conta tags e extrai os blocos DoABC para análise posterior.

Uso:

~~~sh
python3 tools/compare_swfs.py Bad-Ice-Cream.swf bad_ice_cream_2.swf --out swf_analysis
python3 tools/abc_dump.py swf_analysis/game1_00.abc swf_analysis/game1_disassembly.txt
python3 tools/abc_dump.py swf_analysis/game2_00.abc swf_analysis/game2_disassembly.txt
~~~

A ferramenta não traduz ActionScript automaticamente. O disassembly precisa ser analisado e convertido por subsistemas, com testes comparativos.

## Estratégia de conversão

1. **Inventário e extração:** imagens, formas/vetores, sprites com timelines, fontes, sons, botões e símbolos de ambos os SWFs.
2. **Análise de bytecode:** mapear classes, campos, métodos, eventos, temporizadores, colisões, IA, regras de gelo, frutas, pontuação, transições e coop.
3. **Modelo de equivalência:** cada comportamento original recebe uma referência de classe/método e um teste que compare entradas e resultados esperados.
4. **Runtime comum C++:** relógio fixo de 30 Hz inicialmente (confirmado pelo cabeçalho), eventos, animação, colisão, áudio, input e renderização.
5. **Módulos específicos:** regras e conteúdo exclusivos do primeiro e do segundo jogo continuam separados; recursos e sistemas só são compartilhados depois de comparar as implementações.
6. **Camada Xbox 360:** mapeamento de controles, apresentação 16:9 sem deformar sprites, áudio e save.
7. **Validação:** comparar screenshots, sequência de frames, posições, tempos, sons e resultados de fases com os SWFs originais. Depois compilar e testar em hardware.

## Limites conhecidos / não declarar como pronto

- 355 nomes iguais não significam 355 implementações intercambiáveis.
- O bloco ABC ainda precisa ser disassemblado e analisado; a ferramenta existente é um disassembler mínimo, não um decompilador completo para ActionScript legível.
- A extração atual do projeto existente é uma base parcial. Não foi demonstrado ainda que todos os vetores, timelines e símbolos de interface dos dois jogos estejam exportados fielmente.
- A base Xbox existente contém lógica reconstruída e suposições documentadas; não deve ser chamada de recompilação 1:1.
- Não há ainda build de uma conversão fiel dos dois SWFs nem teste comparativo em console.

## Critério de sucesso

Não basta abrir e parecer semelhante. A conversão deve reproduzir a mesma sequência de gameplay sob as mesmas entradas: movimentos, ataques de gelo, colisões, comportamento dos inimigos, coleta, pontuação, vitória/derrota, animações, áudio e coop. Só depois disso podemos chamar o resultado de adaptação quase 1:1.

## Auditoria de temporização — 14/11/2026

Os cabeçalhos dos dois arquivos fornecidos declaram 30 FPS para a timeline raiz (campo FIXED8: 7680 / 256 = 30). Isso foi confirmado lendo os bytes dos próprios arquivos, não inferido dos símbolos.

Há uma diferença importante no port atual: `src/engine.hpp` define `FPS = 25`, e `World::timeBonus()` usa a hipótese `121 * FPS`. Portanto, não se deve simplesmente trocar o motor para 30 Hz com base no cabeçalho SWF. O FPS da timeline controla avanço de frames/timelines Flash; o passo da simulação pode ser controlado separadamente por Timer, ENTER_FRAME, setInterval ou acumulador próprio.

### Verificação necessária antes de alterar FPS

1. No ABC dos dois SWFs, localizar o bootstrap do jogo e os métodos que iniciam o loop principal.
2. Identificar se o jogo usa ENTER_FRAME, Timer, setInterval ou outro agendador.
3. Rastrear os contadores usados em movimento, IA, gelo, frutas, animações e bônus de tempo.
4. Distinguir tempo de gameplay de avanço das timelines dos MovieClips.
5. Só então definir um tick fixo e uma conversão de frames que preserve a duração observada.

Até essa análise, manter `FPS = 25` no port atual como hipótese histórica documentada, e registrar 30 FPS como taxa declarada das timelines originais. Não afirmar equivalência temporal ainda.
