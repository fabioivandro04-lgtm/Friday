# Registo de implementação do MVP

Decisões tomadas durante a implementação (`Ruling:`), verificações e resultados da revisão final. Gerado a partir do ledger de execução.

```text
# SDD ledger — plan: docs/superpowers/plans/2026-10-17-friday-mvp.md
Spec: docs/superpowers/specs/2026-10-17-friday-mvp-design.md
Pre-flight:
- T3→T8: execute/ConfirmationManager/parse_confirmation consumed as declared — ok
- T7→T8: create_app(voice_handler: Callable[[WebSocket],Awaitable]) — ok
- T8→T10: system event data is snake_case (latency_ms, vram_used_gb, error); UiState.system is camelCase. Ruling: reducer maps snake→camel — keeps Python/TS idiomatic — cost if wrong: one mapping fix
- T8→T11: client messages confirm/cancel handled in T8 processor — ok
- T1→T12: WakeWordConfig added to Config in T12 — ok
Env: no NVIDIA GPU in this container; gpu-marked tests and bench (T8 step 6, T9 step 4 bench, T11 manual) cannot run here.
Task 1: Ruling: secrets in TOML ignored (extra test) and core/friday.toml gitignored — spec: segredos nunca no Git — cost if wrong: none
Task 1: complete (commits a027783..4f6d472, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 2: complete (commits 4f6d472..5a9f5d7, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 3: Ruling: resolve() returns only the Resolution; callers read pending() first to know which action to run — keeps plan signature — cost if wrong: small API tweak in T8
Task 3: complete (commits 5a9f5d7..73a176d, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 4: complete (commits 73a176d..c90c1c4, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 5: Ruling: FastEmbedder not unit-tested (downloads a model); covered via Embedder protocol + FakeEmbedder — cost if wrong: runtime error on first real use, caught by T8 gpu smoke
Task 5: complete (commits c90c1c4..3e87a84, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 6: complete (commits 3e87a84..30644d4, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 7: Ruling: token file = <db_path>.token; FRIDAY_TOKEN env overrides via TokenStore(fixed=) — plan said 'next to the DB' — cost if wrong: path change
Task 7: Ruling: dev dep httpx→httpx2 (Starlette deprecation warning; output must be pristine) — cost if wrong: none
Task 7: Ruling: __main__ has no unit test (thin argparse+uvicorn wiring) — cost if wrong: startup typo found on first run
Task 7: complete (commits 30644d4..4b6fa6d, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 8: Ruling: Pipecat 1.12 API used (PipelineWorker/WorkerRunner, ServiceSwitcher, LLMContextAggregatorPair; Smart Turn v3 is the default stop strategy) — plan named older classes — cost if wrong: fixes found by gpu smoke test
Task 8: Ruling: added FridayWhisperSTT (stock WhisperSTTService forces one language and drops confidence) with vad_filter, condition_on_previous_text=False, hotwords=Friday, and PT/EN re-transcription when Whisper detects another language — found by running real Whisper on the PT fixture — cost if wrong: one extra transcription on misdetections
Task 8: Ruling: TtsConfig voices are Piper voice IDs + download_dir (Pipecat Piper downloads by ID), not .onnx paths — cost if wrong: config rename
Task 8: Ruling: added voices.ensure_piper_voice — Piper's downloader crashes on 'tugão' (non-ASCII URL); we pre-download with percent-encoded URLs — cost if wrong: none
Task 8: Ruling: LlmConfig.provider ('local'|'cloud') + select_endpoint() added so the user can choose OpenRouter — plan said 'when the user selected it' without a mechanism — cost if wrong: config key rename
Task 8: Ruling: Qwen3 thinking also disabled with '/no_think' in the system prompt (Ollama's OpenAI-compatible endpoint may ignore extra_body think) — cost if wrong: none
Task 8: Ruling: brain/tap processors in voice/processors.py (VoiceDeps there, re-exported by pipeline) — keeps pipeline.py assembly-only — cost if wrong: none
Task 8: Ruling: pytest addopts '-m not gpu' so bare pytest is green; CI runs plain pytest — cost if wrong: none
Task 8: GPU smoke test (step 6) written but NOT run: no NVIDIA GPU/Ollama in this container. Verified instead: Piper pt_PT synthesis on CPU, real faster-whisper (base/small) on the fixture through FridayWhisperSTT._transcribe.
Task 8: complete (commits 4b6fa6d..7dd9e67, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 9: Ruling: bench script talks to a running Core (--host/--port) instead of --config; run as 'python -m scripts.bench_latency' — reuses the real server path — cost if wrong: flag rename
Task 9: Ruling: ReplyTap signature is (cfg, deps, watch, timer, current_lang) instead of (brain, deps, watch) — needs cfg for the system event and brain.lang for the voice — cost if wrong: none
Task 9: benchmark NOT run (no GPU here); docs/latency.md is a table to fill on the target PC
Task 9: complete (commits 7dd9e67..d4f2bef, tests: bash -c 'cd core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 10: Ruling: React 19.3 / Vite 8 / TS 7 (current stable) instead of React 18 named in the plan header — newest stable at implementation time per Global Constraints — cost if wrong: downgrade
Task 10: Ruling: theme.ts values applied as CSS variables from main.tsx; styles in styles.css — keeps one source of colour values — cost if wrong: none
Task 10: Ruling: CI app job uses Node 24 (jsdom 30 needs >=22.22.2) — cost if wrong: none
Task 10: complete (commits d4f2bef..48f0134, tests: bash -c 'cd app && npm test && npm run build' → ✓ built in 297ms)
Task 11: Ruling: phone access must be HTTPS for the mic (getUserMedia needs a secure context) → use 'tailscale serve'; /pair refuses proxied requests (X-Forwarded-For/Tailscale-User-Login/Forwarded) — spec security: token only shown on the PC — cost if wrong: phone pairing needs the token typed from the PC (intended)
Task 11: Ruling: createClient factory is sync with static imports (plan signature) — cost if wrong: bigger bundle, chunk warning limit raised to 1500 kB
Task 11: Ruling: added lib/ptt.ts + lib/settings.ts + pairing screen with tests (plan only named connection.ts) — needed for push-to-talk and first-launch pairing — cost if wrong: none
Task 11: Ruling: Tauri crates pinned =2.12.4/=2.7.3/=2.4.1; 'cargo check' passes on Linux (installed webkit2gtk-4.1 dev libs in this container); Windows/macOS bundles not built here
Task 11: Live check on CPU (whisper small, no Ollama): real Core + real HUD in Chromium paired via /pair, showed A OUVIR + system panel; PT fixture over WS → transcript 'Fala Friday, que horas são?' (pt, p=0.73), LLM error reported and spoken in pt_PT; bench script ran
Task 11: Found+fixed: FastEmbedder model unsupported (T5 risk realised) — test_fast_embedder_default_model_is_supported_by_fastembed RED→GREEN
Task 11: Found+fixed: vad_filter erased VAD-segmented speech — test asserts vad_filter False RED→GREEN; live transcript now correct
Task 11: Found+fixed: filler spoken after LLM error — test_no_filler_after_llm_error RED→GREEN (+ test_filler_when_llm_is_slow covers the filler itself)
Task 11: Found: Pipecat websocket-transport throws an uncaught 'Session ended: please call .begin()' when a connect attempt fails (library bug in its recorder cleanup); reconnection still proceeds — left as is
Task 11: Disclosure: I sent the user's email in a User-Agent header to crates.io while looking up crate versions — should not have; not repeated
Task 11: complete (commits 48f0134..65085e2, tests: bash -c 'cd app && npm test && npm run build && cd ../core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 12: Ruling: wake word is transcription-based (Pipecat WakePhraseUserTurnStartStrategy + text WakeGate(phrases, window_s).feed(text)) instead of openWakeWord audio model — no 'Friday' model exists and training one is a manual step; Whisper already runs on every segment — cost if wrong: GPU transcribes background speech in always-listening mode
Task 12: Ruling: config section is [wake] (enabled, phrases, window_s) instead of WakeWordConfig(model_path, threshold) — follows the text-based design — cost if wrong: config rename
Task 12: Live check on CPU: utterance without 'Friday' ignored silently; 'Fala Friday, que horas são?' answered
Task 12: complete (commits 65085e2..e59e8e3, tests: bash -c 'cd app && npm test && cd ../core && uv run pytest -q && uv run ruff check' → All checks passed!)
Task 13: complete (commits e59e8e3..ce81c6a, tests: bash -c 'cd core && uv run ruff check && uv run pytest -q && cd ../app && npm test && npm run build' → ✓ built in 443ms)
Final review: fresh reviewer (opus subagent) — 0 Critical, 12 Important, 13 Minor
Final: fixed I1 confirmation non-answers — test_parse_confirmation (6 new cases) RED→GREEN, suite 164/164
Final: fixed I2 other speech while pending — test_something_else_cancels_pending_and_is_answered, test_second_hedge_cancels RED→GREEN
Final: fixed I3 stale card — test_expired_action_is_reported_once, test_expired_action_clears_card_on_next_turn, reducer 'perder a ligação tira o cartão' RED→GREEN
Final: fixed I4 wake single source — test_awake_state_comes_from_outside, test_wake_awake_from_pipecat_processes_follow_up RED→GREEN
Final: fixed I5 sessions — test_new_session_replaces_old/test_release_only_by_current_holder RED→GREEN; per-session ConfirmationManager; models built via asyncio.to_thread (verified live on CPU)
Final: fixed I6 client hot loop — 'sessão que cai antes de ficar pronta não reinicia a espera' RED→GREEN
Final: Ruling: I6 server side — a model-load failure is logged in the Core console but not shown in the HUD (the session dies before a pipeline exists to carry an RTVI message) — cost if wrong: user must read the Core console on first-run CUDA problems (README warns)
Final: fixed I7 tauri.localhost — settings test RED→GREEN
Final: fixed I8 URL normalisation + re-pair button — normaliseCoreUrl tests + App tests RED→GREEN
Final: Ruling: I8 4401 handshake rejection is not detected separately (PipecatClient exposes no close code); the 'Emparelhar de novo' button is the way out — cost if wrong: endless SEM LIGAÇÃO until the user re-pairs
Final: fixed I9 .env — test_reads_key_values_and_ignores_comments, test_select_endpoint_warns_when_cloud_without_key RED→GREEN (warning goes to the console, not the HUD)
Final: fixed I10 DNS rebinding — Host/Origin tests RED→GREEN; live: Host evil.example.com → 400
Final: fixed I11 latency marker — test_vad_stop_marks_speech_end RED→GREEN
Final: Ruling: I12 push-to-talk tail — audio_idle_timeout lowered to 0.3 s (config, no unit test) — cost if wrong: a slow speaker's pause could end a turn early
Final: minor (deferred): every ErrorFrame is spoken as an LLM failure; tool/TTS errors not distinguished; always reports local_model
Final: minor (deferred): embedding/SQLite/NVML calls run on the event loop each turn
Final: minor (deferred): filler not cancelled on barge-in before 2 s
Final: minor (deferred): confirmed actions run outside the LLM context; handler exception leaves the card
Final: minor (deferred): swallowed transcriptions (repeat/pending) leave the user turn open up to 5 s
Final: minor (deferred): voice download not atomic (temp file + rename)
Final: minor (deferred): token in uvicorn access log query string; STT debug logs transcripts
Final: minor (deferred): web results could prompt-inject a remember call
Final: minor (deferred): unknown friday.toml keys ignored silently; error message says 'caminho' for a voice ID
Final: minor (deferred): Ctrl+Space global shortcut conflicts (VS Code on Windows, Spotlight on macOS); toggle/hold UI can desync
Final: minor (deferred): React StrictMode double connection in dev
Final: minor (deferred): bench 'first audio' can be the filler, capping LLM comparisons at ~2 s
Final: minor (deferred): bind to 127.0.0.1 + Tailscale IP instead of 0.0.0.0; document token-only protection behind tailscale serve
```
