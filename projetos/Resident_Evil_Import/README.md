# re4coop: coop local em tela dividida no Xbox 360 (xsdk)

Projeto de fã, sem fins lucrativos e para uso pessoal. Dois jogadores andam pela fazenda,
com câmera por cima do ombro, mira e tiro. O mapa vem de um arquivo .glb que você já tem.

## O que já funciona (testado no PC)

- Conversor `.glb → .rfm`: junta 368 primitivas em 50 lotes por textura e grava texturas ARGB8 com mipmaps, já em big-endian.
- Colisão com a própria malha do mapa: chão, degraus de até 45 cm, rampas e paredes.
- Controles no estilo RE4: andar como tanque, correr, giro rápido de 180°, mirar parado e atirar.
- Câmera por cima do ombro que encurta quando bate em parede.
- Tela dividida em cima e embaixo (1280×360 cada), mantendo o mesmo campo de visão horizontal.
- O jogador 2 entra apertando START no segundo controle.

## Controles

| Ação | Botão |
|---|---|
| Andar / girar | Analógico esquerdo |
| Correr | Segurar A enquanto anda |
| Giro de 180° | Para trás + B |
| Olhar em volta | Analógico direito |
| Mirar | Segurar LT (ou LB) |
| Atirar | RT (ou RB) enquanto mira |
| Jogador 2 entra / sai | START / BACK no controle 2 |
| Sair do jogo | BACK + START no controle 1 |

## Passo a passo

### 1. Converter o mapa (no PC, Python 3 com numpy e Pillow)

```
pip install numpy pillow
python3 tools/convert_map.py 3.glb farm.rfm
```

O `farm.rfm` já vai pronto no pacote, então só precisa rodar isso se trocar de mapa.
Para outro mapa, use `--root NomeDoNo` para escolher o nó do cenário.

### 2. Testar a lógica no PC (opcional)

```
make test MAP=farm.rfm
```

### 3. Preparar o xsdk (Debian, nativo ou no WSL)

Siga o `docs/GETTING_STARTED.md` do xsdk. Em resumo:

```
git clone https://github.com/xenosworks/xsdk.git ~/xsdk
cd ~/xsdk && PREFIX=$HOME/xsdk-gcc WORK=$HOME/xsdk-gcc-work JOBS=$(nproc) tools/toolchain/build.sh
make -j$(nproc) && make samples
```

Antes de mexer neste projeto, rode o sample `hello` no console. Assim você confirma que o console e o toolchain estão funcionando.

### 4. Ajustar `src/render_xsdk.c`, o único arquivo que não pude testar

Escrevi esse arquivo com os nomes de função da documentação do xsdk, mas não consegui
abrir o `include/xsdk/gpu.h`. Os nomes de tipos, campos e enums foram deduzidos e
estão marcados com `XSDK:` no código. Para conferir:

1. Abra `include/xsdk/gpu.h` e o sample do cubo em `samples/`, que usa `cube.vert` e `cube.frag`.
2. Para cada `XSDK:`, troque pelo nome real: `XsdkShader`, `XsdkTexture`, struct do layout de vértice, formato ARGB8, sampler, profundidade, viewport e tipo de primitiva.
3. Veja como o sample inclui os shaders gerados por `xsdk_add_shaders` e ajuste os `#include "map_vert.h"`.
4. Em `main_xsdk.c`, confirme `XINPUT_STATE` e o modo 720p em `xsdk_present_open`.

Se der erro de compilação, me mande a saída junto com o `gpu.h` (ou o sample do cubo) e eu corrijo.

### 5. Compilar e mandar para o console

```
cmake -B build-xbox -G Ninja -DCMAKE_TOOLCHAIN_FILE=$HOME/xsdk/cmake/xsdk.cmake
cmake --build build-xbox
curl -T build-xbox/re4coop.xex --ftp-create-dirs ftp://<console>/Hdd1/re4coop/ --user <user>:<senha>
curl -T farm.rfm ftp://<console>/Hdd1/re4coop/ --user <user>:<senha>
```

Abra `Hdd1/re4coop/re4coop.xex` pela dashboard. O log fica em `Hdd1/re4coop/re4coop.log`.
Dá para testar antes no Xenia Canary, mas o resultado que vale é o do console.

## Estrutura

```
tools/convert_map.py   conversor .glb → .rfm
src/map.c              leitura do .rfm
src/collision.c        grade de colisão: chão, paredes e raio
src/game.c             jogadores, controles, câmera e tela dividida
src/draw_scene.c       o que desenhar em cada tela
src/render_xsdk.c      chamadas de GPU do xsdk  ← ajustar com o gpu.h
src/main_xsdk.c        entrada, controles e loop
shaders/map.vert/.frag textura, luz do sol e neblina
tests/                 simulador e testes no PC
```

## Próximos passos

- Inimigos que perseguem os jogadores (por enquanto como formas simples)
- Vida, dano, munição e recarga
- Mira laser, sons de tiro e passos
- Texturas DXT1 para gastar cerca de 1/8 da memória
