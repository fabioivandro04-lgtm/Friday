# Friday — Partes 2 a 4: integrações, proatividade e telemóvel

- **Data:** 2026-10-17
- **Estado:** aprovado pelo utilizador ("faz tudo e não pergunta nada")
- **Base:** MVP da Parte 1 (`2026-10-17-friday-mvp-design.md`)

## Parte 2 — Integrações (Gmail, Google Calendar, Outlook)

### Objetivo
A Friday lê a agenda e o email, marca eventos e envia emails, sempre com
confirmação antes de alterar alguma coisa. Os painéis Agenda e Email do HUD
passam a mostrar dados reais.

### Decisões
- **Google:** OAuth "aplicação de desktop" (`google-auth-oauthlib`,
  `InstalledAppFlow`). O utilizador cria um `client_secret.json` na Google
  Cloud Console uma vez e corre `python -m friday connect google`. Âmbitos:
  `calendar.events`, `gmail.readonly`, `gmail.send`.
- **Microsoft (Outlook):** MSAL, cliente público com *device code*
  (`python -m friday connect microsoft`). O utilizador regista uma app no Azure
  e põe o `client_id` em `[microsoft]`. Âmbitos: `Calendars.ReadWrite`,
  `Mail.Read`, `Mail.Send`.
- **Tokens** em `core/secrets/` (fora do Git, permissões 0600).
- **APIs REST via `httpx`** (Calendar v3, Gmail v1, Microsoft Graph), com um
  `TokenSource` injetável — testável com `respx`, sem bibliotecas pesadas.
- **Modelo comum:** `CalendarEvent` e `MailSummary`; um `IntegrationHub` junta
  os fornecedores ligados (agenda ordenada, caixa de entrada por data).
- **Ferramentas:** `agenda` (ler), `create_event` (**mutável**), `inbox` (ler),
  `read_email` (ler), `send_email` e `reply_email` (**mutáveis**).
- **Data e hora:** o prompt de sistema passa a incluir a data, hora e fuso
  (`[general] timezone = "Europe/Lisbon"`), para o LLM calcular "amanhã às 15h".
- **HUD:** o Core envia eventos `agenda` e `inbox` ao ligar, a cada 5 minutos e
  depois de marcar/enviar.

## Parte 3 — Proatividade (Telegram, lembretes, resumo diário, chamadas)

- **Telegram (grátis):** bot com *long polling* (sem servidor público). Só
  aceita o `chat_id` configurado. Texto e notas de voz (transcritas pelo
  Whisper) passam pelo mesmo agente e ferramentas; respostas em texto.
  Confirmações funcionam igual ("sim"/"não").
- **Agente de texto:** ciclo de *function calling* com o cliente OpenAI sobre o
  mesmo endpoint (Ollama/OpenRouter), reutilizando ferramentas, memória e
  confirmações.
- **Lembretes:** ferramenta `remind_me(quando, texto)` guardada em SQLite; o
  agendador dispara no Telegram (e diz em voz se houver sessão ativa).
- **Resumo diário:** à hora configurada (`[briefing] time = "08:00"`), agenda +
  emails importantes + tempo (Open-Meteo, grátis) → mensagem no Telegram.
- **Chamadas (opcional, pago):** Twilio. O Core gera TwiML que liga a chamada a
  um WebSocket de *Media Streams* com o mesmo pipeline de voz
  (`TwilioFrameSerializer`, 8 kHz). Precisa de URL pública (Tailscale Funnel).
  Pedidos da Twilio são validados pela assinatura `X-Twilio-Signature` e o
  WebSocket por um token de uso único. O resumo diário pode ser por chamada.

## Parte 4 — Telemóvel

- A interface já é uma PWA servida pelo Core; acrescenta-se um *service worker*
  para a instalar no ecrã inicial e abrir sem a barra do browser.
- Notificações no telemóvel chegam pelo Telegram (Parte 3).
- App nativa (Tauri mobile) fica fora: exige Android Studio/Xcode e não traz
  nada que a PWA + Telegram não cubram.

## Segurança
- Ações que alteram algo (marcar, enviar, responder) passam sempre pelo
  `ConfirmationManager`, em voz, no HUD e no Telegram.
- Telegram: só o `chat_id` do utilizador; tudo o resto é ignorado.
- Twilio: assinatura validada; o número a ligar vem só da configuração.
- Conteúdo de emails e páginas web é tratado como dados: as ferramentas
  devolvem-no delimitado e o prompt avisa o LLM para não seguir instruções
  vindas desse conteúdo.

## Testes
- Cada integração com `respx` (HTTP simulado), sem contas reais.
- Agente de texto com um LLM falso (respostas e chamadas de ferramentas
  programadas).
- Telegram e Twilio com HTTP simulado; assinatura Twilio com o exemplo oficial.
- Sem contas reais nesta máquina: a ligação real ao Google/Microsoft/Telegram/
  Twilio fica para o teste manual no PC do utilizador.
