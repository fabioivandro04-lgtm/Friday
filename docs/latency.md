# Latência medida

Objetivo da especificação: **≤ 1,3 s** entre o fim da tua fala e o primeiro som da resposta.

Como medir (no PC com a RTX 4060 Ti, com o Core a correr):

```bash
cd core
uv run python -m friday            # noutro terminal
uv run python -m scripts.bench_latency --audio-dir recordings --runs 5
```

Grava 5–10 perguntas curtas em `core/recordings/*.wav` (16 kHz, mono), metade em
PT e metade em EN. Corre uma vez com `local_model = "qwen3:8b"` e outra com
`"qwen3:14b"` e preenche a tabela.

| Modelo | Mediana cliente (ms) | p90 cliente (ms) | Mediana Core (ms) | Notas |
|---|---|---|---|---|
| qwen3:8b | _por medir_ | | | |
| qwen3:14b | _por medir_ | | | |
| OpenRouter (opcional) | _por medir_ | | | |
