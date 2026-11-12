# Notas da engenharia reversa (Bad Ice-Cream, AS3)
- SWF v9, AS3. Classes em `com.nitrome.badicecream.*`. Código ofuscado (lixo antes de saltos): `tools/abc_dump.py` só segue código alcançável.
- Fases: 40 XMLs embutidos. `<t>` = grade RLE (id:contagem). `<i>` = `tipo,x,y|...`. Ver `src/game_ids.hpp`.
- Tile 33 = chão, 32 = bloco sólido, 0 = célula coberta por objeto grande (ex.: Igloo ocupa 60 + 0:3).
- Sprites do Flash viram atlas (`tools/swf_sprites.py` + `tools/bake_atlas.py`): `assets/atlas/atlas.json` -> classe -> animação -> quadros {p,x,y,w,h,ox,oy}.
  ox/oy = posição da origem do clip dentro do recorte; desenhar em (x - ox, y - oy), com (x,y) = canto sup. esq. da célula (gridX*36, gridY*36).
- Animações (labels): Player: {Left,Right,Up,Down}{Stand,Walk,Shoot,Break}, Die, Win. IceTile: Add, Static, ItemInside, Break, QuickBreak, Shine, Melt, Flash.
- Ainda a ler no AS3: regras de Player (atirar/quebrar gelo), IceRay, IceTile (timers), IA de cada Enemy, pontuação/tempo, Level.update.
