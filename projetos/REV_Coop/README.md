# REV Coop — ferramentas de análise

Área de trabalho para a investigação de coop na campanha de **Resident Evil Revelations HD (Xbox 360)**.

## Estado atual

- `main.c`: diagnóstico separado para verificar se o XSdk detecta os índices de controle 0 e 1. Não altera o jogo; ainda precisa de compilação e teste no console.
- `tools/ppc_minidisasm.c`: disassembler mínimo para palavras PowerPC 32-bit big-endian, útil para inspecionar pequenos trechos de código extraídos do executável.
- O projeto Ghidra e o `default.xex` original não estão neste repositório. Endereços anotados anteriormente são pistas até serem confirmados no binário.

## Compilar o disassembler no PC

Com GCC ou Clang:

```sh
cc -std=c99 -Wall -Wextra -O2 -o ppc_minidisasm tools/ppc_minidisasm.c
```

## Uso

```sh
./ppc_minidisasm trecho.bin 0 828DD1B0 24
```

Argumentos:
1. arquivo binário contendo bytes PowerPC em big-endian;
2. offset hexadecimal dentro do arquivo;
3. endereço virtual hexadecimal correspondente ao primeiro byte;
4. quantidade de instruções de 4 bytes.

A entrada deve ser um trecho bruto de código já extraído. O programa **não** abre XEX, não remove compressão, não resolve imports/relocations e não substitui o Ghidra.


## Busca de referências a funções

A ferramenta `tools/ppc_find_refs.py` procura branches diretos PowerPC
(`b`, `bl`, `bc`, `bcl`) que apontem para um endereço virtual:

```sh
python3 tools/ppc_find_refs.py trecho.bin 82000000 828DD1B0
```

O primeiro endereço é a VA correspondente ao início do trecho bruto. A busca
não encontra chamadas indiretas por registradores (`bctr`/`bctrl`), tabelas
de ponteiros ou referências de dados. Portanto, resultado zero não prova que
uma função não tenha chamadores.

O teste automático também verifica uma branch relativa sintética, além das
instruções básicas do disassembler.

## Próximas etapas de engenharia reversa

1. Confirmar o caminho de leitura/escrita do estado consultado por `isCoop()`.
2. Identificar o ciclo de vida do segundo jogador no Raid Mode.
3. Mapear a inicialização de jogador/parceiro na campanha.
4. Comparar os fluxos antes de propor qualquer alteração no XEX.

## Regras de evidência

- Separar endereço relatado, endereço verificado e hipótese.
- Não concluir que a campanha aceita dois jogadores só porque existe um flag global ou código de parceiro.
- Preservar a cópia original do XEX.
- Não alterar áudio/dublagem nesta etapa.
- Nenhum patch é considerado funcional sem teste no Xbox 360 real.


## Protótipo: alternar controle entre dois personagens

Os arquivos `src/rev_control_router.h` e `src/rev_control_router.c`
implementam a lógica independente de alternância do controle único:

- inicia com o jogador principal (índice 0);
- uma pressão nova do botão configurado alterna para o parceiro (índice 1);
- manter o botão pressionado não alterna repetidamente;
- outra pressão, depois de soltar, retorna ao jogador principal.

Teste local:

```sh
cc -std=c99 -Wall -Wextra -Werror -Iprojetos/REV_Coop/src \
  projetos/REV_Coop/src/rev_control_router.c \
  projetos/REV_Coop/tests/test_control_router.c -o /tmp/test_rev_router
/tmp/test_rev_router
```

**Limite importante:** isso é a camada de roteamento de input, não a criação
do segundo personagem. Ainda falta ligar `active_player` ao caminho real de
atualização de input dos personagens do jogo. O botão definitivo também deve
ser escolhido após confirmar quais botões estão livres na campanha.


## Entrada local única → personagem selecionado

O módulo `src/rev_local_input.h/.c` acrescenta uma camada acima do roteador:
recebe um único snapshot do controle local, verifica o botão de alternância e
entrega esse mesmo snapshot a um callback associado ao ator lógico selecionado
(0 = principal, 1 = parceiro). Não consulta um segundo controle e não exige
rede ou System Link.

O despachante também remove `switch_button_mask` da cópia entregue ao ator. Assim, o botão usado para alternar não dispara simultaneamente uma ação normal do personagem no mesmo frame. Os demais botões, analógicos e gatilhos são preservados.

O adaptador específico do jogo deverá:
1. ler o controle local uma vez por frame;
2. converter botões, analógicos e gatilhos para `RevPadInput`;
3. chamar `rev_local_input_dispatch`;
4. no callback, encaminhar o input para a rotina real de atualização do ator
   selecionado.

Teste local do despachante:

```sh
cc -std=c99 -Wall -Wextra -Werror -Iprojetos/REV_Coop/src \
  projetos/REV_Coop/src/rev_control_router.c \
  projetos/REV_Coop/src/rev_local_input.c \
  projetos/REV_Coop/tests/test_local_input.c -o /tmp/test_rev_local_input
/tmp/test_rev_local_input
```

**Ainda não integrado ao Revelations:** o callback de teste prova apenas a
seleção e o encaminhamento lógico. Falta localizar no XEX a função real que
consome o input de cada personagem e confirmar como o ator parceiro é criado
na campanha. O módulo não deve ser ligado a endereços especulativos.
