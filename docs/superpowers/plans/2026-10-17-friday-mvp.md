# Friday MVP (Parte 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assistente de voz "Friday" em tempo real (PT-PT/EN) que corre no PC do utilizador, com app de desktop estilo HUD (direção B).

**Architecture:** Um serviço Python (`core/`, "Friday Core") corre um pipeline Pipecat (VAD → faster-whisper → LLM via Ollama/OpenRouter → Piper) exposto por FastAPI/WebSocket. As nossas peças (configuração, persona, ferramentas, memória, confirmações, autenticação, métricas) ficam em módulos Python pequenos e testáveis sem GPU; o Pipecat só as liga. O cliente (`app/`) é React + Vite empacotado com Tauri 2 para desktop e servido pelo Core como PWA para o telemóvel.

**Tech Stack:** Python 3.11, uv, pytest, ruff, Pipecat (`pipecat-ai`), FastAPI, faster-whisper, Ollama, Piper, SQLite + sqlite-vec, fastembed, ddgs, nvidia-ml-py · TypeScript, React 18, Vite, Vitest, Tauri 2, `@pipecat-ai/client-js` + `@pipecat-ai/websocket-transport`.

**Spec:** `docs/superpowers/specs/2026-10-17-friday-mvp-design.md`

## Global Constraints

- Custo 0 € por defeito: tudo local; OpenRouter só se `[llm.cloud]` tiver chave.
- Python `>=3.11,<3.13`; dependências Python com versão **exata** (`==`) em `core/pyproject.toml`, fixadas na última versão estável no momento da implementação. O mesmo para `app/package.json` (sem `^`).
- Modelos padrão: STT `large-v3-turbo`; LLM `qwen3:8b` (alternativa `qwen3:14b`), modo "thinking" desligado; TTS Piper, uma voz `pt_PT` e uma voz `en_US`/`en_GB`.
- Línguas suportadas: `pt` (sempre PT-PT) e `en`.
- Respostas faladas: 1 a 3 frases, sem listas nem markdown.
- Ações que alteram algo exigem confirmação explícita; nenhuma ferramenta executa comandos de sistema.
- Ligações aceites só de `127.0.0.1`/`::1` e da rede Tailscale `100.64.0.0/10`, com token de emparelhamento.
- Segredos só em `core/.env` (no `.gitignore`); configuração em `core/friday.toml`.
- Objetivo de latência (fim da fala → primeiro som): ≤ 1,3 s, medido.
- Frase de espera se o LLM demorar mais de 2 s: `"Deixa-me ver…"` (PT) / `"Let me check…"` (EN).
- Texto da UI em PT-PT; estados do reator: `A OUVIR`, `A PENSAR`, `A FALAR`, `SEM LIGAÇÃO`.
- Testes de CI correm sem GPU; testes que precisam de GPU/modelos têm o marcador `@pytest.mark.gpu` e são ignorados no CI.

## Review Focus

- O utilizador interrompe ou diz outra coisa enquanto há uma ação pendente → a ação **não** é executada e expira (teste na Task 3).
- Respostas de confirmação ambíguas ("talvez", "não sei", silêncio) → contam como **não** confirmado (teste na Task 3).
- Frases curtas ("sim", "ok") ou deteção de língua com pouca confiança → mantém a língua anterior em vez de trocar de voz (teste na Task 8).
- A ligação cai a meio de uma resposta → o cliente mostra `SEM LIGAÇÃO` e volta a ligar com espera crescente, sem duplicar ligações (teste na Task 11).
- A pesquisa web devolve texto enorme ou falha → o resultado é cortado/convertido numa frase de erro, sem bloquear a conversa (teste na Task 4).

---

## File Structure

```
core/
  pyproject.toml            # uv project, ruff, pytest config (marker "gpu")
  friday.example.toml       # configuração de exemplo, comentada em PT
  .env.example              # OPENROUTER_API_KEY=, FRIDAY_TOKEN=
  src/friday/
    config.py               # carregar friday.toml → dataclasses
    persona.py              # prompt de sistema PT-PT / EN
    ptpt.py                 # deteção de formas do Brasil (frases de controlo)
    tools/registry.py       # Tool, ToolRegistry, esquema de function calling
    tools/confirm.py        # ações pendentes e interpretação do "sim/não"
    tools/web_search.py     # pesquisa DuckDuckGo
    memory/store.py         # SQLite + sqlite-vec
    memory/tools.py         # ferramentas remember / recall
    llm/providers.py        # Ollama / OpenRouter (API compatível com OpenAI) + fallback
    voice/language.py       # escolha da língua por frase
    voice/pipeline.py       # montagem do pipeline Pipecat
    voice/events.py         # eventos para a UI (estado, transcrição, confirmação, sistema)
    metrics.py              # latência por etapa, VRAM
    server/auth.py          # token e lista de IPs permitidos
    server/app.py           # FastAPI: /health, /pair, /ws, PWA estática
    __main__.py             # `python -m friday`
  scripts/bench_latency.py  # medição com áudios gravados
  tests/                    # espelha src/friday/
app/
  package.json, vite.config.ts, index.html
  src/
    theme.ts                # cores e fontes do desenho B
    components/Reactor.tsx, Hud.tsx, AgendaPanel.tsx, EmailPanel.tsx,
               SystemPanel.tsx, ConfirmCard.tsx, Transcript.tsx
    lib/connection.ts       # cliente Pipecat + reconexão
    lib/state.ts            # reducer de eventos → estado da UI
  src-tauri/                # Tauri 2, atalho global Ctrl+Espaço
docs/
  manual-test.md            # guião de teste manual
  ptpt-control-phrases.md   # frases de controlo
.github/workflows/ci.yml
README.md
```

---

### Task 1: Core scaffold, configuração e CI

**Files:**
- Create: `core/pyproject.toml`, `core/friday.example.toml`, `core/.env.example`, `core/src/friday/__init__.py`, `core/src/friday/config.py`, `.gitignore`, `.github/workflows/ci.yml`
- Test: `core/tests/test_config.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Config` com campos `stt: SttConfig`, `llm: LlmConfig`, `tts: TtsConfig`, `server: ServerConfig`, `memory: MemoryConfig`.
  - `SttConfig(model: str = "large-v3-turbo", device: str = "cuda")`
  - `LlmConfig(local_model: str = "qwen3:8b", ollama_url: str = "http://localhost:11434/v1", cloud_model: str | None = None, cloud_api_key: str | None = None, slow_threshold_s: float = 2.0)`
  - `TtsConfig(voice_pt: str, voice_en: str)` (caminhos para os ficheiros `.onnx` do Piper)
  - `ServerConfig(host: str = "0.0.0.0", port: int = 8765, token: str | None = None)`
  - `MemoryConfig(db_path: str = "friday.db", min_similarity: float = 0.35)`
  - `load_config(path: Path, env: Mapping[str, str] = os.environ) -> Config`

- [ ] **Step 1: Write the failing tests**

```python
def test_defaults_when_file_has_only_tts(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "pt.onnx"\nvoice_en = "en.onnx"\n')
    cfg = load_config(p, env={})
    assert cfg.llm.local_model == "qwen3:8b"
    assert cfg.stt.model == "large-v3-turbo"
    assert cfg.server.port == 8765
    assert cfg.llm.cloud_api_key is None

def test_env_overrides_secrets(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n[llm]\ncloud_model = "x/y"\n')
    cfg = load_config(p, env={"OPENROUTER_API_KEY": "k", "FRIDAY_TOKEN": "t"})
    assert cfg.llm.cloud_api_key == "k"
    assert cfg.server.token == "t"

def test_missing_tts_voices_raises(tmp_path):
    p = tmp_path / "friday.toml"; p.write_text("")
    with pytest.raises(ValueError, match="voice_pt"):
        load_config(p, env={})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: friday.config`)

- [ ] **Step 3: Implement `load_config` in `core/src/friday/config.py`**

Use `tomllib`. Secrets come only from `env` (`OPENROUTER_API_KEY`, `FRIDAY_TOKEN`), never from the TOML. `friday.example.toml` documents every key in PT-PT. `.gitignore` covers `core/.env`, `*.db`, `core/models/`, `node_modules/`, `app/dist/`, `app/src-tauri/target/`. Register the pytest marker `gpu` in `pyproject.toml`. The CI workflow runs `uv run ruff check`, `uv run pytest -m "not gpu"` in `core/` and `npm ci && npm test` in `app/` (the app job is added in Task 10).

- [ ] **Step 4: Run tests and lint**

Run: `cd core && uv run pytest -v && uv run ruff check`
Expected: 3 passed; ruff clean

- [ ] **Step 5: Commit**

```bash
git add .gitignore .github core
git commit -m "feat(core): scaffold Friday Core with config loading and CI"
```

---

### Task 2: Persona e verificação de PT-PT

**Files:**
- Create: `core/src/friday/persona.py`, `core/src/friday/ptpt.py`, `docs/ptpt-control-phrases.md`
- Test: `core/tests/test_persona.py`, `core/tests/test_ptpt.py`

**Interfaces:**
- Produces:
  - `system_prompt(lang: Literal["pt", "en"], memory_context: str = "") -> str`
  - `find_brazilianisms(text: str) -> list[str]` (devolve as formas encontradas, em minúsculas)

- [ ] **Step 1: Write the failing tests**

```python
def test_pt_prompt_rules():
    p = system_prompt("pt")
    assert "Friday" in p
    assert "português de Portugal" in p
    assert "1 a 3 frases" in p
    assert "confirma" in p.lower()

def test_en_prompt_is_english():
    assert "European Portuguese" not in system_prompt("en")
    assert "1-3 sentences" in system_prompt("en")

def test_memory_context_is_included():
    assert "prefere reuniões de manhã" in system_prompt("pt", "O Fábio prefere reuniões de manhã.")

@pytest.mark.parametrize("text,found", [
    ("Você está no ônibus?", ["você", "ônibus"]),
    ("Estou fazendo isso no celular", ["estou fazendo", "celular"]),
    ("Estás no autocarro? Liga-me do telemóvel.", []),
])
def test_find_brazilianisms(text, found):
    assert find_brazilianisms(text) == found
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_persona.py tests/test_ptpt.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

`persona.py`: two fixed templates. PT template states: name Friday; speaks European Portuguese (use "tu", "estás", "autocarro", "telemóvel", "pequeno-almoço", "a fazer" instead of gerúndio); answers in 1 a 3 frases faladas, no lists or markdown; always confirma before sending, deleting or scheduling; tom eficiente com humor seco; then a "Memória:" block when `memory_context` is non-empty. EN template mirrors it ("1-3 sentences"). `ptpt.py`: ordered list of BR forms (`você`, `ônibus`, `celular`, `trem`, `café da manhã`, `banheiro`, plus regex `\b(estou|está|estamos|estão) \w+ndo\b` for gerúndio) returning matches in order of appearance. `docs/ptpt-control-phrases.md` lists 20 control prompts (e.g. "Como vou para o aeroporto de autocarro?") used in the manual check.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_persona.py tests/test_ptpt.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/persona.py core/src/friday/ptpt.py core/tests docs/ptpt-control-phrases.md
git commit -m "feat(core): add Friday persona prompts and PT-PT checker"
```

---

### Task 3: Registo de ferramentas e confirmações

**Files:**
- Create: `core/src/friday/tools/__init__.py`, `core/src/friday/tools/registry.py`, `core/src/friday/tools/confirm.py`
- Test: `core/tests/tools/test_registry.py`, `core/tests/tools/test_confirm.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Tool: name: str; description: str; parameters: dict; handler: Callable[..., Awaitable[str]]; mutating: bool = False; summary: Callable[[dict], str] | None = None` (`summary` gera o texto do cartão de confirmação)
  - `class ToolRegistry: register(tool: Tool) -> None; get(name: str) -> Tool; schemas() -> list[dict]` (formato OpenAI `{"type": "function", "function": {...}}`); `register` rejeita nomes repetidos com `ValueError`.
  - `@dataclass class PendingAction: id: str; tool: str; args: dict; summary: str; created_at: float`
  - `class ConfirmationManager(ttl_s: float = 60.0, clock: Callable[[], float] = time.monotonic)`: `propose(tool: Tool, args: dict) -> PendingAction`; `pending() -> PendingAction | None`; `resolve(answer: str) -> Literal["confirmed", "rejected", "unclear"]`; `cancel() -> None`; `confirm_by_id(action_id: str) -> PendingAction | None` (clique em Enviar).
  - `async def execute(registry: ToolRegistry, confirmations: ConfirmationManager, name: str, args: dict) -> str`: ferramentas não mutáveis correm logo; mutáveis devolvem `"PENDENTE: <summary>. Pergunta ao utilizador se confirma."` e criam a ação pendente.
  - `parse_confirmation(answer: str) -> Literal["confirmed", "rejected", "unclear"]`

- [ ] **Step 1: Write the failing tests**

```python
async def test_read_only_tool_runs_immediately(): ...
    # registry with echo tool → execute(...) == "eco: oi"; confirmations.pending() is None

async def test_mutating_tool_requires_confirmation():
    # send tool with handler that appends to a list
    result = await execute(reg, conf, "send", {"to": "João"})
    assert result.startswith("PENDENTE:")
    assert sent == []
    assert conf.pending().tool == "send"

@pytest.mark.parametrize("answer,expected", [
    ("sim", "confirmed"), ("Sim, envia", "confirmed"), ("yes", "confirmed"), ("confirmo", "confirmed"),
    ("não", "rejected"), ("cancela", "rejected"), ("no", "rejected"),
    ("talvez", "unclear"), ("não sei", "unclear"), ("", "unclear"),
])
def test_parse_confirmation(answer, expected):
    assert parse_confirmation(answer) == expected

def test_pending_action_expires():
    t = [0.0]; conf = ConfirmationManager(ttl_s=60, clock=lambda: t[0])
    conf.propose(send_tool, {}); t[0] = 61
    assert conf.pending() is None

def test_cancel_on_interrupt_never_executes(): ...
    # propose, cancel(), then confirm_by_id(old_id) is None

def test_duplicate_tool_name_rejected(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/tools -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement registry, `ConfirmationManager`, `execute` and `parse_confirmation`**

`parse_confirmation`: normalise (lowercase, strip accents and punctuation); "não sei"/"talvez" checked first → `unclear`; then rejection words (`não`, `nao`, `cancela`, `cancelar`, `no`, `stop`) → `rejected`; then confirmation words (`sim`, `confirmo`, `envia`, `podes`, `yes`, `ok`, `go`) → `confirmed`; otherwise `unclear`. Only one pending action at a time; a new `propose` replaces the old one. Async tests use `pytest-asyncio` in auto mode.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/tools -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/tools core/tests/tools
git commit -m "feat(core): add tool registry with confirmation gate for mutating actions"
```

---

### Task 4: Pesquisa na internet

**Files:**
- Create: `core/src/friday/tools/web_search.py`
- Test: `core/tests/tools/test_web_search.py`

**Interfaces:**
- Consumes: `Tool` (Task 3)
- Produces: `make_web_search_tool(search: Callable[[str, int], list[dict]] | None = None, max_chars: int = 1500, timeout_s: float = 6.0) -> Tool` — nome `web_search`, parâmetro `query: str`, `mutating=False`. `search` padrão usa `ddgs.DDGS().text(query, max_results=n)`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_formats_results():
    tool = make_web_search_tool(search=lambda q, n: [{"title": "T", "body": "B", "href": "https://x"}])
    out = await tool.handler(query="tempo Lisboa")
    assert "T" in out and "B" in out and "https://x" in out

async def test_truncates_long_results():
    big = [{"title": "T", "body": "x" * 10_000, "href": "h"}]
    out = await make_web_search_tool(search=lambda q, n: big, max_chars=1500).handler(query="q")
    assert len(out) <= 1500

async def test_failure_becomes_message():
    def boom(q, n): raise RuntimeError("rede")
    out = await make_web_search_tool(search=boom).handler(query="q")
    assert out == "ERRO: a pesquisa não está disponível neste momento."

async def test_timeout_becomes_message(): ...
    # search that sleeps 1s with timeout_s=0.05 → same ERRO message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/tools/test_web_search.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `make_web_search_tool`**

Run the blocking `search` in `asyncio.to_thread` under `asyncio.wait_for(timeout_s)`; up to 5 results formatted as `"- {title}: {body} ({href})"`, then cut to `max_chars`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/tools/test_web_search.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/tools/web_search.py core/tests/tools/test_web_search.py
git commit -m "feat(core): add web search tool with timeout and truncation"
```

---

### Task 5: Memória

**Files:**
- Create: `core/src/friday/memory/__init__.py`, `core/src/friday/memory/store.py`, `core/src/friday/memory/tools.py`
- Test: `core/tests/memory/test_store.py`, `core/tests/memory/test_tools.py`

**Interfaces:**
- Consumes: `Tool` (Task 3), `MemoryConfig` (Task 1)
- Produces:
  - `class Embedder(Protocol): dim: int; def embed(self, texts: list[str]) -> list[list[float]]`
  - `class FastEmbedder(Embedder)` — `fastembed` com `"intfloat/multilingual-e5-small"` (384 dimensões), CPU.
  - `class MemoryStore(db_path: str, embedder: Embedder, min_similarity: float = 0.35)`: `add_fact(text: str) -> bool` (False se já existir um facto quase igual, similaridade ≥ 0.92); `search(query: str, k: int = 3) -> list[str]` (só acima de `min_similarity`); `log_turn(role: Literal["user","assistant"], text: str) -> None`; `context_for(query: str) -> str` (factos unidos por `"\n"`, string vazia se nenhum).
  - `make_memory_tools(store: MemoryStore) -> list[Tool]` — `remember(fact: str)` e `recall(query: str)`, ambos `mutating=False` (memória própria da Friday).

- [ ] **Step 1: Write the failing tests** (com um `FakeEmbedder` determinístico em `tests/memory/conftest.py`, que mapeia palavras-chave para vetores fixos)

```python
def test_add_and_search(store):
    store.add_fact("O Fábio prefere reuniões de manhã")
    assert store.search("quando gosto de reuniões?") == ["O Fábio prefere reuniões de manhã"]

def test_unrelated_query_returns_nothing(store):
    store.add_fact("O Fábio prefere reuniões de manhã")
    assert store.search("receita de bacalhau") == []

def test_near_duplicate_not_stored_twice(store):
    assert store.add_fact("O Fábio prefere reuniões de manhã") is True
    assert store.add_fact("O Fábio prefere reuniões de manhã.") is False

def test_persists_across_instances(tmp_path, fake_embedder): ...
    # add with one MemoryStore, search with a new one on the same db_path

def test_context_for_empty_is_blank(store):
    assert store.context_for("qualquer coisa") == ""

async def test_remember_tool(store):
    remember, recall = make_memory_tools(store)
    assert await remember.handler(fact="Gosto de café") == "Guardado."
    assert "Gosto de café" in await recall.handler(query="café")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/memory -v`
Expected: FAIL

- [ ] **Step 3: Implement `MemoryStore` and the tools**

Tables: `facts(id INTEGER PRIMARY KEY, text TEXT, created_at REAL)`, virtual table `facts_vec USING vec0(embedding float[<dim>])` keyed by `facts.id`, and `turns(id, role, text, created_at)`. Cosine similarity on L2-normalised vectors. `remember` returns `"Guardado."` or `"Já sabia."`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/memory -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/memory core/tests/memory
git commit -m "feat(core): add local SQLite vector memory and memory tools"
```

---

### Task 6: Fornecedores de LLM (local e OpenRouter) e frase de espera

**Files:**
- Create: `core/src/friday/llm/__init__.py`, `core/src/friday/llm/providers.py`
- Test: `core/tests/llm/test_providers.py`

**Interfaces:**
- Consumes: `LlmConfig` (Task 1)
- Produces:
  - `@dataclass(frozen=True) class LlmEndpoint: base_url: str; model: str; api_key: str; extra_body: dict`
  - `local_endpoint(cfg: LlmConfig) -> LlmEndpoint` (Ollama, `api_key="ollama"`, `extra_body={"think": False}`)
  - `cloud_endpoint(cfg: LlmConfig) -> LlmEndpoint | None` (`https://openrouter.ai/api/v1`; `None` sem chave ou sem modelo; `extra_body={"provider": {"sort": "latency"}}`)
  - `filler_phrase(lang: Literal["pt","en"]) -> str` → `"Deixa-me ver…"` / `"Let me check…"`
  - `class SlowResponseWatch(threshold_s: float, clock=time.monotonic)`: `start() -> None`; `first_token() -> None`; `should_say_filler() -> bool` (True uma única vez, quando passou o limite sem primeiro token)

- [ ] **Step 1: Write the failing tests**

```python
def test_local_endpoint_disables_thinking():
    ep = local_endpoint(LlmConfig())
    assert ep.base_url == "http://localhost:11434/v1"
    assert ep.model == "qwen3:8b"
    assert ep.extra_body == {"think": False}

def test_cloud_endpoint_none_without_key():
    assert cloud_endpoint(LlmConfig(cloud_model="a/b")) is None

def test_cloud_endpoint_with_key():
    ep = cloud_endpoint(LlmConfig(cloud_model="a/b", cloud_api_key="k"))
    assert ep.base_url == "https://openrouter.ai/api/v1" and ep.api_key == "k"

def test_filler_said_once_after_threshold():
    t = [0.0]; w = SlowResponseWatch(2.0, clock=lambda: t[0]); w.start()
    t[0] = 1.9; assert w.should_say_filler() is False
    t[0] = 2.1; assert w.should_say_filler() is True
    assert w.should_say_filler() is False

def test_no_filler_after_first_token(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/llm -v`
Expected: FAIL

- [ ] **Step 3: Implement the module** (pure data and logic; the Pipecat services that use these endpoints are created in Task 8)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/llm -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/llm core/tests/llm
git commit -m "feat(core): add local/OpenRouter LLM endpoints and slow-response filler"
```

---

### Task 7: Servidor, autenticação e emparelhamento

**Files:**
- Create: `core/src/friday/server/__init__.py`, `core/src/friday/server/auth.py`, `core/src/friday/server/app.py`, `core/src/friday/__main__.py`
- Test: `core/tests/server/test_auth.py`, `core/tests/server/test_app.py`

**Interfaces:**
- Consumes: `Config` (Task 1)
- Produces:
  - `is_allowed_ip(ip: str) -> bool` — `127.0.0.1`, `::1`, `100.64.0.0/10`.
  - `class TokenStore(path: Path)`: `get_or_create() -> str` (`secrets.token_urlsafe(32)`, guardado em ficheiro com permissões `0o600`); `check(token: str) -> bool` (`hmac.compare_digest`).
  - `create_app(cfg: Config, voice_handler: Callable[[WebSocket], Awaitable[None]] | None = None, static_dir: Path | None = None) -> FastAPI` com:
    - `GET /health` → `{"status": "ok"}` (sem token, só IPs permitidos)
    - `GET /pair` → `{"token": ...}` **apenas** a partir de `127.0.0.1`/`::1` (o PC mostra o token para colar no telemóvel)
    - `WS /ws?token=...` → recusa (código 4401) sem token válido ou IP não permitido; senão delega em `voice_handler`
    - PWA estática em `/` se `static_dir` existir
  - `python -m friday` lê `core/friday.toml` e arranca o uvicorn.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("ip,ok", [
    ("127.0.0.1", True), ("::1", True), ("100.101.5.9", True),
    ("192.168.1.20", False), ("8.8.8.8", False), ("not-an-ip", False),
])
def test_is_allowed_ip(ip, ok):
    assert is_allowed_ip(ip) is ok

def test_token_persists_and_checks(tmp_path): ...

def test_health_ok(client): assert client.get("/health").json() == {"status": "ok"}

def test_pair_only_from_localhost(app_factory):
    # TestClient with client=("100.101.5.9", 1234) → 403; with ("127.0.0.1", 1234) → 200 and token

def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws?token=wrong"): pass
    assert e.value.code == 4401

def test_ws_with_token_calls_handler(app_factory): ...
    # voice_handler records it was called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/server -v`
Expected: FAIL

- [ ] **Step 3: Implement `auth.py`, `create_app` and `__main__.py`**

IP check via `ipaddress`; any request from a disallowed IP gets 403 from a middleware. The token file lives next to the DB (`friday.token`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/server -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/server core/src/friday/__main__.py core/tests/server
git commit -m "feat(core): add FastAPI server with IP allowlist and token pairing"
```

---

### Task 8: Pipeline de voz (Pipecat)

**Files:**
- Create: `core/src/friday/voice/__init__.py`, `core/src/friday/voice/language.py`, `core/src/friday/voice/events.py`, `core/src/friday/voice/pipeline.py`
- Test: `core/tests/voice/test_language.py`, `core/tests/voice/test_events.py`, `core/tests/voice/test_pipeline_gpu.py` (`@pytest.mark.gpu`)

**Interfaces:**
- Consumes: `Config` (1), `system_prompt` (2), `ToolRegistry`, `execute`, `ConfirmationManager`, `parse_confirmation` (3), `make_web_search_tool` (4), `MemoryStore`, `make_memory_tools` (5), `local_endpoint`, `cloud_endpoint`, `SlowResponseWatch`, `filler_phrase` (6), `create_app(voice_handler=...)` (7)
- Produces:
  - `choose_language(detected: str | None, probability: float, text: str, previous: Literal["pt","en"]) -> Literal["pt","en"]` — mantém `previous` se `detected` não for `pt`/`en`, se `probability < 0.6` ou se `text` tiver menos de 3 palavras.
  - Eventos para a UI (`events.py`), enviados como mensagens de servidor RTVI com `type` e `data`:
    - `state(value: Literal["listening","thinking","speaking"]) -> dict`
    - `transcript(role: Literal["user","assistant"], text: str) -> dict`
    - `confirm_request(action: PendingAction) -> dict` (`id`, `summary`)
    - `confirm_cleared(action_id: str) -> dict`
    - `system(model: str, voice: str, latency_ms: int | None, vram_used_gb: float | None, error: str | None = None) -> dict` (`error` mostra falhas do Ollama/GPU no painel Sistema)
  - `async def run_voice_session(websocket: WebSocket, cfg: Config, deps: VoiceDeps) -> None` e `@dataclass class VoiceDeps: registry: ToolRegistry; confirmations: ConfirmationManager; memory: MemoryStore`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("detected,prob,text,prev,expected", [
    ("en", 0.95, "what is the weather tomorrow", "pt", "en"),
    ("pt", 0.95, "que tempo vai fazer amanhã", "en", "pt"),
    ("en", 0.95, "ok", "pt", "pt"),
    ("en", 0.40, "what is the weather tomorrow", "pt", "pt"),
    ("es", 0.99, "qué tiempo hace mañana", "pt", "pt"),
    (None, 0.0, "", "en", "en"),
])
def test_choose_language(detected, prob, text, prev, expected):
    assert choose_language(detected, prob, text, prev) == expected

def test_event_shapes():
    assert state("thinking") == {"type": "state", "data": {"value": "thinking"}}
    assert transcript("user", "olá")["data"] == {"role": "user", "text": "olá"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/voice -m "not gpu" -v`
Expected: FAIL

- [ ] **Step 3: Implement `language.py` and `events.py`**

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/voice -m "not gpu" -v`
Expected: all passed

- [ ] **Step 5: Implement `run_voice_session` in `pipeline.py`**

Pin `pipecat-ai` with the extras for `silero`, `whisper`, `openai`, `piper`, `websocket`, and check every class name below against the pinned version's docs before writing code. Pipeline, in order:
1. `FastAPIWebsocketTransport` (the serializer the Pipecat JS websocket transport expects), with `SileroVADAnalyzer` and the Smart Turn analyzer; interruptions enabled.
2. `WhisperSTTService(model=cfg.stt.model, device=cfg.stt.device)` with automatic language detection.
3. A small processor that, for each final transcription: calls `choose_language`; if the text is empty or Whisper's average log-probability is below −1.0, says `"Podes repetir?"` / `"Could you repeat that?"` instead of answering; if `confirmations.pending()` exists, resolves it with `parse_confirmation` (on `confirmed`, runs the tool; on `rejected`, cancels; on `unclear`, asks again) instead of sending the text to the LLM; on new user speech while a response is playing, calls `confirmations.cancel()`; refreshes the system message with `system_prompt(lang, memory.context_for(text))`; logs the turn in memory; emits `transcript` and `state("thinking")`. It also handles the client messages `confirm` (`{"id"}` → `confirm_by_id`, run the tool, emit `confirm_cleared`) and `cancel` (`cancel()`, emit `confirm_cleared`).
4. `OpenAILLMService` built from `local_endpoint(cfg.llm)` (or `cloud_endpoint` when configured and the user selected it), with every tool in `registry.schemas()` registered as a function whose handler calls `execute(...)`; a `PENDENTE:` result also emits `confirm_request`. A `SlowResponseWatch` pushes `filler_phrase(lang)` as TTS text once. If the LLM service errors (Ollama down), emit `system(..., error="Modelo local indisponível")` and say it in one sentence.
5. Two Piper TTS services (`cfg.tts.voice_pt`, `cfg.tts.voice_en`) behind Pipecat's service switcher, set by the language chosen in step 3; if the pinned version has no switcher, a processor that holds both and forwards text frames to the active one.
6. Transport output, then the assistant context aggregator; emit `state("speaking")` when bot audio starts, `state("listening")` when it stops, and `transcript("assistant", ...)` with the final text.
`server/app.py` `__main__` wires `create_app(cfg, voice_handler=lambda ws: run_voice_session(ws, cfg, deps))`.

- [ ] **Step 6: Write and run the GPU smoke test**

`test_pipeline_gpu.py`: start the app with `TestClient`, open `/ws` with the token, send a 16 kHz PCM recording `tests/voice/fixtures/ola_friday_pt.wav` ("Olá Friday, que horas são?"), and assert that a `transcript` event with role `user` containing `"friday"` and at least one audio frame arrive within 10 s.

Run: `cd core && uv run pytest tests/voice -m gpu -v` (on the target PC with Ollama running and `qwen3:8b` pulled)
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add core/src/friday/voice core/tests/voice core/src/friday/server/app.py core/src/friday/__main__.py
git commit -m "feat(core): assemble real-time voice pipeline with tools, memory and confirmations"
```

---

### Task 9: Métricas de latência e script de medição

**Files:**
- Create: `core/src/friday/metrics.py`, `core/scripts/bench_latency.py`
- Modify: `core/src/friday/voice/pipeline.py` (emit `system` events after each reply)
- Test: `core/tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `class TurnTimer(clock=time.monotonic)`: `mark(stage: Literal["speech_end","stt_done","llm_first_token","tts_first_audio"]) -> None`; `report() -> dict[str, int]` (ms desde `speech_end` para cada etapa marcada, mais `total_ms` = `tts_first_audio`); `reset() -> None`
  - `vram_used_gb() -> float | None` (via `nvidia-ml-py`; `None` sem GPU NVIDIA)
  - `bench_latency.py --config friday.toml --audio-dir recordings/ --runs 5` imprime uma tabela por etapa (mediana e p90) e o `total_ms`, e falha (código 1) se a mediana do total for > 1300.

- [ ] **Step 1: Write the failing tests**

```python
def test_turn_timer_report():
    t = [10.0]; tt = TurnTimer(clock=lambda: t[0])
    tt.mark("speech_end"); t[0] = 10.25; tt.mark("stt_done")
    t[0] = 10.6; tt.mark("llm_first_token"); t[0] = 10.7; tt.mark("tts_first_audio")
    assert tt.report() == {"stt_done": 250, "llm_first_token": 600, "tts_first_audio": 700, "total_ms": 700}

def test_report_without_audio_has_no_total(): ...

def test_vram_none_without_nvidia(monkeypatch): ...  # pynvml init raises → None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_metrics.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `metrics.py`, mark the four stages in the pipeline, emit `system(...)` after each reply, and write `bench_latency.py`** (it connects to `/ws` like a client and streams each `.wav` in real time)

- [ ] **Step 4: Run tests, then the benchmark on the target PC**

Run: `cd core && uv run pytest tests/test_metrics.py -v` → passed
Run: `cd core && uv run python scripts/bench_latency.py --config friday.toml --audio-dir recordings --runs 5` with `qwen3:8b` and again with `qwen3:14b`
Expected: table printed; record both results in `docs/latency.md`

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/metrics.py core/scripts core/tests/test_metrics.py core/src/friday/voice/pipeline.py docs/latency.md
git commit -m "feat(core): add per-stage latency metrics and benchmark script"
```

---

### Task 10: App — interface HUD (direção B)

**Files:**
- Create: `app/package.json`, `app/vite.config.ts`, `app/index.html`, `app/src/main.tsx`, `app/src/theme.ts`, `app/src/lib/state.ts`, `app/src/components/{Hud,Reactor,AgendaPanel,EmailPanel,SystemPanel,ConfirmCard,Transcript}.tsx`
- Modify: `.github/workflows/ci.yml` (job `app`: `npm ci && npm test && npm run build`)
- Test: `app/src/lib/state.test.ts`, `app/src/components/Hud.test.tsx`

**Interfaces:**
- Consumes: the event shapes from Task 8 (`state`, `transcript`, `confirm_request`, `confirm_cleared`, `system`)
- Produces:
  - `type ReactorState = "listening" | "thinking" | "speaking" | "offline"`
  - `type UiState = { reactor: ReactorState; lastUser?: string; lastAssistant?: string; pending?: { id: string; summary: string }; system: { model?: string; voice?: string; latencyMs?: number; vramGb?: number; error?: string } }`
  - `initialState: UiState` (`reactor: "offline"`)
  - `reduce(state: UiState, event: { type: string; data: any } | { type: "connection"; data: { connected: boolean } }) -> UiState`
  - `<Hud state={UiState} onConfirm={(id: string) => void} onCancel={() => void} onTalk={() => void} />`

- [ ] **Step 1: Write the failing tests** (Vitest + Testing Library)

```ts
test("state event sets reactor", () => {
  expect(reduce(initialState, { type: "state", data: { value: "thinking" } }).reactor).toBe("thinking");
});
test("disconnect sets offline", () => {
  const s = reduce({ ...initialState, reactor: "speaking" }, { type: "connection", data: { connected: false } });
  expect(s.reactor).toBe("offline");
});
test("confirm_cleared removes pending only when ids match", () => { /* ... */ });
test("unknown event leaves state unchanged", () => { /* ... */ });

test("HUD labels", () => {
  render(<Hud state={{ ...initialState, reactor: "listening" }} ... />);
  expect(screen.getByText("A OUVIR")).toBeInTheDocument();
  expect(screen.getAllByText("Por ligar")).toHaveLength(2); // Agenda e Email
});
test("offline label", () => { /* reactor "offline" → "SEM LIGAÇÃO" */ });
test("confirm card buttons call handlers", () => { /* "Enviar" → onConfirm(id); "Cancelar" → onCancel */ });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && npm test`
Expected: FAIL

- [ ] **Step 3: Implement `state.ts`, `theme.ts` and the components**

Follow the design reference (artboard "B · HUD com painéis", link in the spec): ground `#05080C`, panels `#081016` with border `#16212B`, accent `#4FD1E8` (one constant in `theme.ts`), text `#E6EEF3`, muted `#8A97A6`; fonts Chakra Petch (UI) and IBM Plex Mono (data). Reactor labels: `A OUVIR`, `A PENSAR`, `A FALAR`, `SEM LIGAÇÃO` (grey, no animation); animations off under `prefers-reduced-motion`. Layout wraps to one column at phone width. Agenda and Email panels show `Por ligar`; System panel shows model, voice, latency (ms), VRAM (`[n] / 16 GB`) and, when present, `system.error` in the accent-free warning colour `#F2A541`.

- [ ] **Step 4: Run tests and build**

Run: `cd app && npm test && npm run build`
Expected: all passed; `app/dist/` built

- [ ] **Step 5: Commit**

```bash
git add app .github/workflows/ci.yml
git commit -m "feat(app): add HUD interface (design B) with UI state reducer"
```

---

### Task 11: App — ligação de voz, reconexão, atalho e PWA

**Files:**
- Create: `app/src/lib/connection.ts`, `app/src-tauri/` (Tauri 2 project, plugin `global-shortcut`), `app/public/manifest.webmanifest`
- Modify: `app/src/main.tsx`, `core/src/friday/__main__.py` (serve `app/dist` as `static_dir`)
- Test: `app/src/lib/connection.test.ts`

**Interfaces:**
- Consumes: `reduce`, `UiState` (Task 10); `WS /ws?token=`, `GET /pair` and event shapes (Tasks 7–8)
- Produces:
  - `backoffDelay(attempt: number) -> number` — `min(500 * 2 ** attempt, 10_000)` ms
  - `class FridayConnection(opts: { url: string; token: string; onEvent: (e) => void; createClient?: () => PipecatLike; setTimer?: typeof setTimeout })`: `connect(): Promise<void>`; `disconnect(): void`; `setMicEnabled(on: boolean): void`; `confirm(id: string): void`; `cancel(): void` (sends client messages `confirm` / `cancel`, handled by the Task 8 processor via `confirm_by_id` / `cancel`)

- [ ] **Step 1: Write the failing tests** (with a fake `PipecatLike` and fake timers)

```ts
test("backoff grows and caps", () => {
  expect([0, 1, 2, 10].map(backoffDelay)).toEqual([500, 1000, 2000, 10000]);
});
test("drop emits offline and schedules one reconnect", () => {
  // fake client fires "disconnected" twice → onEvent got {type:"connection",data:{connected:false}};
  // only one pending reconnect timer exists
});
test("manual disconnect does not reconnect", () => { /* ... */ });
test("server messages are forwarded to onEvent", () => { /* ... */ });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && npm test -- connection`
Expected: FAIL

- [ ] **Step 3: Implement `FridayConnection`, wire it in `main.tsx`, add Tauri and the PWA manifest**

Use `@pipecat-ai/client-js` with `@pipecat-ai/websocket-transport` (verify names against the pinned versions). First launch asks for the Core address and the token (shown by `GET /pair` on the PC); store both in `localStorage`. Push-to-talk: hold `Ctrl+Space` (Tauri global shortcut on desktop, keydown/keyup in the browser) or click the mic button; it toggles `setMicEnabled`. Tauri config builds Windows (`msi`) and macOS (`dmg`) bundles, product name `Friday`. The Core serves `app/dist` at `/` when it exists.

- [ ] **Step 4: Run tests and a manual end-to-end check**

Run: `cd app && npm test && npm run build` → passed
Manual: `cd core && uv run python -m friday`, then `cd app && npm run tauri dev`; hold Ctrl+Space, say "Olá Friday, pesquisa o tempo em Lisboa amanhã" → reactor goes A OUVIR → A PENSAR → A FALAR and the answer is spoken in PT-PT; stop the Core → app shows SEM LIGAÇÃO; start it again → reconnects on its own.

- [ ] **Step 5: Commit**

```bash
git add app core/src/friday/__main__.py
git commit -m "feat(app): connect HUD to Friday Core with push-to-talk, reconnect and PWA"
```

---

### Task 12: Palavra de ativação "Friday" (opcional, desligada por defeito)

**Files:**
- Create: `core/src/friday/voice/wakeword.py`
- Modify: `core/src/friday/config.py` (`WakeWordConfig(enabled: bool = False, model_path: str | None = None, threshold: float = 0.5)`), `core/src/friday/voice/pipeline.py`, `app/src/main.tsx` (mode "always listening")
- Test: `core/tests/voice/test_wakeword.py`

**Interfaces:**
- Produces: `class WakeGate(detector: Callable[[bytes], float], threshold: float, listen_window_s: float = 8.0, clock=time.monotonic)`: `feed(chunk: bytes) -> bool` (True while the gate is open); `close() -> None`

- [ ] **Step 1: Write the failing tests**

```python
def test_gate_opens_on_score_above_threshold(): ...
def test_gate_closes_after_window(): ...      # fake clock, 8 s without speech → closed
def test_gate_stays_closed_below_threshold(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/voice/test_wakeword.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `WakeGate`** with `openwakeword` as the real detector when `enabled` and `model_path` are set; audio before the gate opens is dropped. A pretrained "Friday" model does not exist: `README.md` (Task 13) explains how to train one with openWakeWord's training notebook.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/voice/test_wakeword.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/src/friday/voice/wakeword.py core/src/friday/config.py core/src/friday/voice/pipeline.py core/tests/voice/test_wakeword.py app/src/main.tsx
git commit -m "feat: add optional 'Friday' wake word gate"
```

---

### Task 13: Documentação de instalação e teste manual

**Files:**
- Create: `README.md`, `docs/manual-test.md`

- [ ] **Step 1: Write `README.md` (PT-PT)**

Sections: o que é a Friday; requisitos (Windows/Mac, GPU NVIDIA para o Core, Node 22, uv, Ollama); instalação passo a passo (`ollama pull qwen3:8b`, descarregar as vozes Piper `pt_PT` e inglesa para `core/models/`, copiar `friday.example.toml` → `friday.toml`, `uv sync`, `uv run python -m friday`, `npm ci && npm run tauri dev`); emparelhar o telemóvel (instalar Tailscale nos dois, abrir `http://<ip-tailscale-do-pc>:8765`, colar o token de `/pair`); ativar o OpenRouter (opcional); treinar a palavra "Friday" (opcional); medir a latência (`scripts/bench_latency.py`).

- [ ] **Step 2: Write `docs/manual-test.md`**

Checklist mapping to the spec's success criteria: conversa PT-PT; conversa EN e troca automática de voz; interrupção a meio da frase; pesquisa web; memória ("lembra-te que prefiro reuniões de manhã" → reiniciar o Core → "quando prefiro reuniões?"); acesso pelo telemóvel via Tailscale; as 20 frases de `docs/ptpt-control-phrases.md` sem formas do Brasil (correr `find_brazilianisms` nas respostas); confirmação com uma ferramenta de teste mutável; desligar a internet → conversa continua; desligar o Core → SEM LIGAÇÃO.

- [ ] **Step 3: Verify everything**

Run: `cd core && uv run ruff check && uv run pytest -m "not gpu"` and `cd app && npm test && npm run build`
Expected: all green

- [ ] **Step 4: Commit**

```bash
git add README.md docs/manual-test.md
git commit -m "docs: add setup guide and manual test checklist"
```
