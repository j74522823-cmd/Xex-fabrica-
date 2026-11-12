# Sistema de passwords — Bad Ice-Cream

**Status: proposta de implementação; ainda não existe código de geração ou leitura de passwords.**

## Objetivo

Permitir que a pessoa continue do progresso alcançado sem depender de perfil Xbox, HD, memória interna ou sistema de save. A senha é anotada e digitada manualmente.

## Primeira versão (simples)

1. Ao concluir uma fase, o jogo mostra uma password na tela de vitória.
2. No menu, a opção **Continuar por password** abre uma tela de entrada.
3. A senha recupera a próxima fase desbloqueada e o modo (solo ou coop).
4. Senhas inválidas mostram uma mensagem e permitem tentar novamente.

## Formato

- Código curto, preferencialmente numérico, para ser digitado com o controle.
- Incluir uma pequena validação para detectar erros de digitação.
- Não guardar pontuação, inventário ou configurações na primeira versão.
- A validação serve para detectar erros, não para segurança ou proteção contra edição.

## Regras

- Completar a fase N libera a fase N+1.
- A senha de solo continua em solo; a de coop continua em coop.
- A campanha concluída pode gerar uma senha especial de finalização.
- Se uma senha antiga for usada, o jogo retoma o progresso correspondente àquela senha.

## Fora do escopo inicial

- Salvar automaticamente no armazenamento do Xbox.
- Vincular a senha a perfil, console ou dispositivo.
- Sincronização online.
- Senhas diferentes por personagem.

## Próxima etapa técnica

Implementar a geração/validação em uma função portátil, independente da plataforma Xbox; depois criar a tela de digitação usando o direcional e START. Só então integrar o fluxo à tela de vitória e ao menu. Testar no host antes de tentar compilar para Xbox 360.
