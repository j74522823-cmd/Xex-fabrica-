# Status (2026-11-12)
- Jogo compila na fábrica de XEX (GitHub Actions) e roda no Xbox 360: título, fases, som, coop (START no controle 2).
- Dados: `runtime_data.zip` (gerado por `tools/export_runtime.py` a partir de `assets/`). Extrair em `data/` ao lado do .xex.
- Regras decifradas do bytecode AS3: veja `NOT_FINISH_YET.md` (a lista "O que falta" ali está desatualizada: desenho, áudio e backend Xbox já existem).
- Código: `src/` (motor, renderer, jogo), `platform_xbox360.cpp` (backend xsdk), `README.md` (build/dados).
- Log do console: `badicecream.log` ao lado do .xex.
- Suposições ainda não confirmadas: ids de tile de chão, velocidade de kiwi/pera, FPS (25), papel do tile invisível.
- Ainda não testadas por uma pessoa: as 40 fases e o balanceamento.
