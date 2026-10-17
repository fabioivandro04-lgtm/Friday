# Friday

Assistente pessoal de voz, em tempo real, que corre no teu PC. Fala português de
Portugal e inglês, deixa-te interrompê-la, pesquisa na internet e lembra-se do que
lhe dizes. Interface estilo HUD, para Windows e Mac, e acessível no telemóvel.

- **Friday Core** (`core/`): Python. Ouve (faster-whisper), pensa (Ollama ou
  OpenRouter) e fala (Piper), tudo em streaming com o [Pipecat](https://github.com/pipecat-ai/pipecat).
- **App** (`app/`): React + Tauri. É só ecrã, microfone e altifalante; liga-se ao Core.

Especificação: [`docs/superpowers/specs/2026-10-17-friday-mvp-design.md`](docs/superpowers/specs/2026-10-17-friday-mvp-design.md)

## Requisitos

| Para | Precisas de |
|---|---|
| Core | PC com GPU NVIDIA (testado para RTX 4060 Ti 16 GB), [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com) |
| App de desktop | [Node.js 24](https://nodejs.org), [Rust](https://rustup.rs) (só para gerar o instalador) |
| Telemóvel | [Tailscale](https://tailscale.com) no PC e no telemóvel |

## 1. Instalar o Core

```bash
git clone https://github.com/fabioivandro04-lgtm/Friday.git
cd Friday/core
uv sync
ollama pull qwen3:8b            # o "cérebro" local (~5 GB)
cp friday.example.toml friday.toml
```

As vozes Piper (`pt_PT-tugão-medium` e `en_GB-alan-medium`) e o modelo do Whisper
são descarregados automaticamente na primeira conversa.

**GPU no Windows.** O faster-whisper precisa das bibliotecas cuBLAS e cuDNN 9 do
CUDA 12. A forma mais simples é `uv pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"`
e garantir que as pastas `bin` desses pacotes estão no `PATH`
([instruções do faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu)).
Se não quiseres tratar disso já, põe `device = "cpu"` em `[stt]` no `friday.toml`
(funciona, mas mais devagar).

Arrancar:

```bash
uv run python -m friday
```

O Core fica em `http://127.0.0.1:8765`. O token de emparelhamento está em
`http://127.0.0.1:8765/pair` (só abre neste PC).

## 2. App de desktop

Em desenvolvimento:

```bash
cd app
npm ci
npm run tauri dev
```

Gerar o instalador (`.msi`/`.exe` no Windows, `.dmg` no Mac):

```bash
npm run tauri build
```

Na primeira vez, a app pede o endereço do Core (`http://127.0.0.1:8765`) e o
token de `/pair`. Depois:

- **Mantém Ctrl+Shift+Espaço** para falar (funciona mesmo com a janela em segundo plano), ou
- carrega no botão do microfone, ou
- ativa **Sempre à escuta** e diz "Friday" (precisa de `[wake] enabled = true` no `friday.toml`).

Na app do Mac, aponta para o IP Tailscale do PC em vez de `127.0.0.1`.

## 3. Telemóvel (pelo browser)

O browser só deixa usar o microfone em HTTPS, por isso usa o `tailscale serve`:

```bash
cd app && npm run build          # o Core serve esta interface em /
tailscale serve --bg 8765
```

No telemóvel (com o Tailscale ligado), abre `https://<nome-do-pc>.<tailnet>.ts.net`,
cola o token que vês em `http://127.0.0.1:8765/pair` **no PC**, e adiciona a página
ao ecrã inicial.

## 4. Ligar o email e a agenda

A Friday lê a agenda e os emails por ler, marca eventos e envia/responde a emails.
Antes de marcar ou enviar, **pergunta sempre** ("Confirmas?") e mostra o cartão no HUD.

### Google (Gmail + Google Calendar)

1. Em <https://console.cloud.google.com>, cria um projeto e ativa a **Gmail API** e a
   **Google Calendar API**.
2. Em *APIs e serviços → Ecrã de consentimento OAuth*, escolhe "Externo" e adiciona o
   teu email como utilizador de teste.
3. Em *Credenciais → Criar credenciais → ID do cliente OAuth*, escolhe
   **Aplicação para computador** e descarrega o JSON para `core/secrets/client_secret.json`.
4. Corre `uv run python -m friday connect google` e faz login no browser.

### Outlook / Microsoft 365

1. Em <https://portal.azure.com> → *Microsoft Entra ID → Registos de aplicações → Novo registo*.
   Tipos de conta: "contas em qualquer diretório e contas Microsoft pessoais".
2. Em *Autenticação*, ativa **Permitir fluxos de clientes públicos**.
3. Copia o *Application (client) ID* para `[integrations] microsoft_client_id` no `friday.toml`.
4. Corre `uv run python -m friday connect microsoft` e segue o código que aparece.

Reinicia o Core: os painéis Agenda e Email passam a mostrar os teus dados.

Experimenta: "O que tenho amanhã?", "Tenho emails importantes?", "Marca café com o
João amanhã às 15h", "Responde ao João a dizer que chego às três".

## Opções no `friday.toml`

| Opção | Para quê |
|---|---|
| `[llm] local_model = "qwen3:14b"` | Mais inteligente, um pouco mais lento (cabe nos 16 GB) |
| `[llm] provider = "cloud"` + `cloud_model` | Usar o OpenRouter; põe `OPENROUTER_API_KEY=` em `core/.env` |
| `[wake] enabled = true` | Modo sempre à escuta com a palavra "Friday" |
| `[stt] device = "cpu"` | Sem GPU (mais lento) |
| `[integrations] timezone` | Fuso horário (padrão `Europe/Lisbon`) |
| `[integrations] default_provider` | Conta para enviar/marcar: `google` ou `microsoft` |

## Medir a latência

O objetivo é ≤ 1,3 s entre acabares de falar e a Friday começar a responder.
Ver [`docs/latency.md`](docs/latency.md).

## Testes

```bash
cd core && uv run pytest && uv run ruff check     # Core (sem GPU)
cd core && uv run pytest -m gpu                    # ponta a ponta, no PC com GPU e Ollama
cd app && npm test && npm run build                # App
```

Teste manual completo: [`docs/manual-test.md`](docs/manual-test.md).

## Segurança

- O Core só aceita ligações deste PC e da tua rede Tailscale, com token.
- O token só é mostrado no próprio PC.
- A Friday pede sempre confirmação antes de enviar, apagar ou marcar alguma coisa.
- Nenhuma ferramenta executa comandos no sistema.
- Chaves de API ficam em `core/.env`, fora do Git.
