# Friday — MVP (Parte 1): núcleo de voz e app de desktop

- **Data:** 2026-10-17
- **Estado:** em revisão
- **Âmbito:** Parte 1 de 4 (ver "Roadmap")

## 1. Objetivo

Construir a **Friday**, uma assistente pessoal de IA estilo "Jarvis/FRIDAY" do
Tony Stark, para uso pessoal do Fábio:

- conversa por **voz ao vivo**, rápida e com interrupções (não é "gravar →
  enviar → esperar");
- fala **português de Portugal** e **inglês**, escolhendo a língua
  automaticamente;
- corre no **PC do utilizador, a custo zero**, enquanto o PC está ligado;
- tem uma **interface minimalista estilo HUD** (direção "B").

### Critérios de sucesso do MVP

1. Uma conversa de voz em PT-PT e outra em EN funcionam de ponta a ponta no
   desktop.
2. O tempo entre o fim da fala do utilizador e o primeiro som da resposta é
   **medido** e fica, como objetivo, em **≤ 1,3 s** no hardware alvo.
3. O utilizador consegue **interromper** a Friday a meio de uma frase e ela
   para e volta a ouvir.
4. A Friday consegue **pesquisar na internet** e responder com o resultado.
5. A Friday **lembra-se** de factos ditos em conversas anteriores.
6. Funciona também no **browser do telemóvel** através do Tailscale.
7. Escrita e voz em **PT-PT** (sem formas do Brasil) na lista de frases de
   controlo.

### Restrições

- **Hardware alvo:** RTX 4060 Ti 16 GB VRAM, 16 GB RAM, Windows (também Mac
  como cliente).
- **Custo:** 0 € no MVP. Serviços pagos (OpenRouter, ElevenLabs, Twilio) são
  opcionais e ativados por configuração.
- **Disponibilidade:** só funciona com o PC ligado (aceite pelo utilizador).

## 2. Arquitetura

```
 App Friday (Windows / Mac)        Telemóvel (browser/PWA)
   interface B (HUD)                  mesma interface
          │                                 │
          └── áudio ao vivo (WebSocket) ── Tailscale (fora de casa)
                         │
          ┌──────────────▼──────────────────────────────┐
          │   FRIDAY CORE — corre no PC (Python)         │
          │                                              │
          │  Pipecat (pipeline de voz em tempo real)     │
          │   VAD → STT → LLM → TTS (tudo em streaming)  │
          │                                              │
          │  Agente: ferramentas (pesquisa, memória)     │
          │  Memória: SQLite local                       │
          └──────────────────────────────────────────────┘
```

Princípios:

1. **Um só cérebro** (Friday Core) no PC; as apps são clientes leves
   (microfone, altifalante, ecrã).
2. **Streaming em todas as etapas:** a Friday começa a falar antes de acabar
   de gerar a resposta completa.
3. **Interrupção (barge-in)** suportada desde o início.
4. **Peças trocáveis por configuração** (`friday.toml`): STT, LLM, TTS e
   pesquisa podem ser locais ou na cloud sem reescrever código.

## 3. Componentes

| Componente | Escolha | Onde | Memória aprox. |
|---|---|---|---|
| Ativação | openWakeWord ("Friday") + atalho Ctrl+Espaço | cliente / CPU | mínima |
| Deteção de fala e fim de vez | Silero VAD + Smart Turn (Pipecat) | CPU | mínima |
| Ouvir (STT) | faster-whisper `large-v3-turbo`, deteção de língua por frase | GPU | ~2 GB VRAM |
| Pensar (LLM) | Ollama: **Qwen3 8B** (padrão) ou **Qwen3 14B**; modo "thinking" desligado | GPU | ~6 / ~9–10 GB VRAM |
| Falar (TTS) | Piper: uma voz `pt_PT` e uma voz inglesa | CPU | mínima |
| Memória | SQLite + sqlite-vec + modelo pequeno de embeddings multilíngue | CPU | ~0,5 GB RAM |
| Pesquisa web | DuckDuckGo (sem chave); Tavily opcional | internet | — |
| LLM na cloud (opcional) | OpenRouter, via API compatível com OpenAI | internet | — |

Orçamento de VRAM com o modelo de 14B: cerca de 12 GB de 16 GB.

### 3.1 Friday Core (Python 3.11)

- **Servidor:** FastAPI com endpoint WebSocket para áudio e eventos de UI.
- **Pipeline de voz:** Pipecat, com transporte WebSocket.
- **Agente:** lógica de *function calling* sobre o LLM, com registo de
  ferramentas. Cada ferramenta declara se é **só de leitura** ou se **altera
  algo**.
- **Memória:** guarda conversas e factos; antes de cada resposta recupera as
  memórias relevantes.
- **Configuração:** `friday.toml` (modelos, vozes, fornecedores, portas);
  segredos em `.env` (nunca no Git).

### 3.2 App de desktop (Tauri 2 + React/TypeScript)

- Implementa a **interface B**: reator animado ao centro, painel Agenda à
  esquerda, painéis Email e Sistema à direita, e cartão de confirmação de ações.
- Estados do reator: **A OUVIR**, **A PENSAR**, **A FALAR** e **SEM LIGAÇÃO**
  (cinzento).
- Painel **Sistema:** modelo ativo, voz, latência medida da última resposta e
  uso de VRAM.
- No MVP, os painéis Agenda e Email mostram "Por ligar" (ficam ativos na
  Parte 2).
- Instaladores para Windows e Mac. A app do Mac liga-se ao Core no PC.
- Desenho de referência: <https://claude.ai/artifact/GAT3SXPTiEyCo7VjP1e2ud>
  (artboard "B · HUD com painéis").

### 3.3 Telemóvel

- A mesma interface React, servida pelo Core como página web (PWA), acedida
  através do Tailscale.

### 3.4 Personalidade (prompt de sistema)

- Português **de Portugal** ("estás", "autocarro", "telemóvel"), com regras
  explícitas contra formas do Brasil; inglês quando o utilizador fala inglês.
- Respostas **curtas e faladas** (1 a 3 frases, sem listas nem markdown).
- **Pergunta sempre antes de** enviar, apagar ou marcar algo.
- Tom eficiente, com algum humor seco.

## 4. Fluxo de uma conversa

1. **Ativação** por wake word ou atalho; o reator passa a A OUVIR.
2. O cliente envia o áudio do microfone em blocos pequenos por WebSocket.
3. O VAD e o Smart Turn detetam o fim da fala; o Whisper transcreve e deteta a
   língua. A transcrição aparece no HUD; o reator passa a A PENSAR.
4. O agente envia ao LLM o pedido, as memórias relevantes e as ferramentas.
   - Se o LLM pede uma ferramenta, o Core executa-a e devolve o resultado.
   - Se a ferramenta **altera algo**, a ação fica pendente: aparece o cartão
     de confirmação e a Friday pergunta em voz alta. Só executa com "sim" ou
     clique em Enviar.
5. O texto da resposta é dividido em frases à medida que chega; cada frase vai
   para o Piper e é tocada logo. O reator passa a A FALAR.
6. Se o utilizador fala durante a resposta, o áudio para de imediato e o ciclo
   volta ao passo 3.
7. No fim de cada troca, factos úteis são extraídos e guardados na memória.

## 5. Tratamento de erros

| Situação | Comportamento |
|---|---|
| LLM local demora mais de ~2 s | Frase de espera curta ("Deixa-me ver…"); se o OpenRouter estiver configurado, pode passar para ele |
| Sem internet | Continua com o modelo local e avisa que a pesquisa não está disponível |
| Ollama ou GPU falha | Erro visível no painel Sistema; tenta reiniciar o modelo |
| Cliente perde a ligação ao Core | Reator cinzento, "Sem ligação ao PC", reconexão automática |
| PC a dormir | O telemóvel mostra "Friday offline" (acordar à distância fica fora do MVP) |
| Transcrição duvidosa | Pede para repetir em vez de adivinhar, sobretudo antes de ações |
| Ferramenta falha | Explica numa frase e continua a conversa |

## 6. Segurança

- O Core só aceita ligações locais e da rede Tailscale, com um token criado no
  primeiro emparelhamento.
- **Nenhuma** ferramenta executa comandos de sistema (shell) no MVP.
- Chaves de API em `.env` local, fora do Git.
- Ações que alteram algo exigem sempre confirmação explícita.

## 7. Testes

- **Unitários e de integração:** agente, memória e ferramentas testados com um
  LLM falso, sem GPU, para correrem depressa e no CI.
- **Medição de latência:** script com áudios gravados (PT e EN) que mede cada
  etapa e o tempo até à primeira voz; serve para comparar Qwen3 8B, Qwen3 14B e
  OpenRouter.
- **Teste de PT-PT:** lista de frases de controlo verificada na escrita do LLM
  e ouvida na voz.
- **Guião manual:** conversa, interrupção, pesquisa e confirmação de ação, a
  correr no PC do utilizador.

## 8. Fora do âmbito do MVP

- Gmail, Google Calendar e Outlook (Parte 2).
- Telegram, updates proativos e chamadas telefónicas (Parte 3).
- App nativa de telemóvel (Parte 4).
- Servidor sempre ligado (VPS), acordar o PC à distância.
- Execução de comandos no sistema.

## 9. Roadmap

1. **Parte 1 — este documento:** núcleo de voz e app de desktop.
2. **Parte 2:** integrações (Gmail, Google Calendar, Outlook) e memória mais
   rica.
3. **Parte 3:** proatividade (agendador, Telegram; chamadas via Twilio se
   compensar).
4. **Parte 4:** app nativa de telemóvel.

Cada parte tem a sua própria especificação e o seu plano de implementação.

## 10. Pontos a confirmar durante a implementação

- Qualidade das vozes `pt_PT` do Piper; se for fraca, avaliar alternativas
  locais ou ElevenLabs (pago, opcional).
- Qualidade do PT-PT escrito pelo Qwen3 8B e 14B (frases de controlo).
- Latência real de cada etapa na RTX 4060 Ti (script de medição).
- Desempenho do wake word "Friday" com o sotaque do utilizador.
