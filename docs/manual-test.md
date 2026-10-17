# Teste manual da Friday (MVP)

Corre no PC com a RTX 4060 Ti, com o Ollama a correr e o Core arrancado
(`uv run python -m friday`). Marca cada linha quando passar.

## Critérios de sucesso da especificação

- [ ] **Conversa PT-PT.** Mantém Ctrl+Espaço e diz "Olá Friday, que horas são?".
  O reator passa por A OUVIR → A PENSAR → A FALAR e a resposta vem em português de Portugal.
- [ ] **Conversa EN e troca de voz.** Diz "What is the capital of Australia?".
  A resposta vem em inglês, com a voz inglesa (painel Sistema: `en_GB-alan-medium`).
- [ ] **Interrupção.** Pede "Conta-me uma história longa" e fala por cima a meio.
  A Friday para logo e ouve-te.
- [ ] **Pesquisa web.** "Pesquisa o tempo em Lisboa amanhã." A resposta usa dados atuais.
- [ ] **Memória.** "Lembra-te de que prefiro reuniões de manhã." Reinicia o Core.
  "Quando é que prefiro ter reuniões?" → responde "de manhã".
- [ ] **Latência.** O painel Sistema mostra a latência; corre `scripts/bench_latency.py`
  e preenche [`latency.md`](latency.md). Objetivo: mediana ≤ 1300 ms.
- [ ] **Telemóvel.** Com `tailscale serve --bg 8765`, abre o endereço `https://…ts.net`
  no telemóvel, emparelha e tem uma conversa.
- [ ] **PT-PT.** Diz as 20 frases de [`ptpt-control-phrases.md`](ptpt-control-phrases.md).
  Nenhuma resposta usa formas do Brasil (`find_brazilianisms(resposta) == []`) e o sotaque
  soa a Portugal.

## Comportamentos de segurança e erros

- [ ] **Confirmação.** Pede uma ação que altere algo (quando existir uma ferramenta assim,
  na Parte 2). Aparece o cartão de confirmação; "talvez" → volta a perguntar; "não" → cancela;
  "sim" ou clicar em Enviar → executa.
- [ ] **Interromper durante a pergunta de confirmação** cancela a ação.
- [ ] **Sem internet.** Desliga a rede e pede uma pesquisa: a Friday diz que a pesquisa
  não está disponível e continua a conversar.
- [ ] **Ollama parado.** Fecha o Ollama: o painel Sistema mostra o erro e a Friday diz
  "O modelo local não está a responder."
- [ ] **Core parado.** Para o Core: a app mostra SEM LIGAÇÃO. Volta a arrancá-lo: a app
  liga-se sozinha.
- [ ] **Token.** Abrir `/pair` a partir do telemóvel (via Tailscale) dá 403.

## Modo sempre à escuta (opcional)

- [ ] Com `[wake] enabled = true` e a opção "Sempre à escuta" na app: falar sem dizer
  "Friday" não tem resposta; "Friday, que horas são?" tem.
