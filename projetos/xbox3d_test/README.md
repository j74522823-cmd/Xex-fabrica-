# XSDK 3D Test — primeiro quadrado 3D

Projeto independente para o Xbox 360, compilado pela Fábrica de XEX com o XSDK.

## Primeira versão
- Um quadrado 3D feito com dois triângulos.
- Rotação nos eixos X e Y pelo analógico esquerdo.
- Fundo azul escuro.
- Vértices coloridos; sem textura, áudio, física ou cenário.
- XEX independente: `xbox3d_test.xex`.

## Controles
- Analógico esquerdo: girar o quadrado.
- BACK: sair do teste.

## Build
O workflow `.github/workflows/xex.yml` detecta esta pasta por seu `CMakeLists.txt`, compila os shaders GLSL e gera o XEX com o XSDK.

## Estado
Código inicial preparado para o primeiro build PowerPC/XSDK. A compilação do GitHub Actions precisa ser verificada; depois o XEX ainda precisa ser testado no Xbox 360 real. Nenhum funcionamento no console é presumido.

A Fábrica executa o workflow automaticamente quando este projeto recebe alterações em `projetos/**`.
