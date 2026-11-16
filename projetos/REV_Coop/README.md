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
