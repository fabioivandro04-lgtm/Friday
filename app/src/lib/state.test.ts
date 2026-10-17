import { initialState, reduce } from "./state";

test("começa sem ligação", () => {
  expect(initialState.reactor).toBe("offline");
});

test("evento de estado muda o reator", () => {
  expect(reduce(initialState, { type: "state", data: { value: "thinking" } }).reactor).toBe("thinking");
});

test("ligação perdida volta a offline", () => {
  const s = reduce({ ...initialState, reactor: "speaking" }, { type: "connection", data: { connected: false } });
  expect(s.reactor).toBe("offline");
});

test("ligação aberta não finge que já está a ouvir (o Core avisa quando estiver pronto)", () => {
  expect(reduce(initialState, { type: "connection", data: { connected: true } }).reactor).toBe("offline");
});

test("perder a ligação tira o cartão de confirmação", () => {
  const s = reduce(initialState, { type: "confirm_request", data: { id: "a", summary: "x" } });
  expect(reduce(s, { type: "connection", data: { connected: false } }).pending).toBeUndefined();
});

test("transcrições guardam a última frase de cada lado", () => {
  let s = reduce(initialState, { type: "transcript", data: { role: "user", text: "olá" } });
  s = reduce(s, { type: "transcript", data: { role: "assistant", text: "olá, Fábio" } });
  expect(s.lastUser).toBe("olá");
  expect(s.lastAssistant).toBe("olá, Fábio");
});

test("confirm_cleared só remove o pedido com o mesmo id", () => {
  const s = reduce(initialState, { type: "confirm_request", data: { id: "a", summary: "Enviar a João" } });
  expect(s.pending).toEqual({ id: "a", summary: "Enviar a João" });
  expect(reduce(s, { type: "confirm_cleared", data: { id: "b" } }).pending).toEqual(s.pending);
  expect(reduce(s, { type: "confirm_cleared", data: { id: "a" } }).pending).toBeUndefined();
});

test("evento system converte snake_case", () => {
  const s = reduce(initialState, {
    type: "system",
    data: { model: "qwen3:8b", voice: "pt_PT", latency_ms: 900, vram_used_gb: 7.5, error: null },
  });
  expect(s.system).toEqual({ model: "qwen3:8b", voice: "pt_PT", latencyMs: 900, vramGb: 7.5, error: undefined });
});

test("evento desconhecido não muda nada", () => {
  expect(reduce(initialState, { type: "xpto", data: {} })).toBe(initialState);
});

test("agenda e inbox vindos do Core", () => {
  let s = reduce(initialState, {
    type: "agenda",
    data: { connected: true, items: [{ time: "10:00", title: "Reunião", location: "Escritório" }] },
  });
  s = reduce(s, { type: "inbox", data: { connected: true, items: [{ ref: "google:m1", sender: "João", subject: "Hora" }] } });
  expect(s.agenda).toEqual({ connected: true, items: [{ time: "10:00", title: "Reunião", location: "Escritório" }] });
  expect(s.inbox?.items[0].subject).toBe("Hora");
});
