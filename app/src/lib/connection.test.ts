import { backoffDelay, FridayConnection, wsUrlFor, type ClientCallbacks, type PipecatLike } from "./connection";

class FakeClient implements PipecatLike {
  connects: string[] = [];
  mic: boolean[] = [];
  sent: [string, unknown][] = [];
  failNext = false;
  constructor(public cb: ClientCallbacks) {}
  async connect(params: { wsUrl: string }) {
    this.connects.push(params.wsUrl);
    if (this.failNext) {
      this.failNext = false;
      throw new Error("recusado");
    }
    this.cb.onConnected();
  }
  async disconnect() {
    this.cb.onDisconnected();
  }
  enableMic(on: boolean) {
    this.mic.push(on);
  }
  sendClientMessage(type: string, data?: unknown) {
    this.sent.push([type, data]);
  }
}

function setup() {
  const events: any[] = [];
  let client!: FakeClient;
  const conn = new FridayConnection({
    url: "ws://pc:8765/ws?token=t",
    onEvent: (e) => events.push(e),
    createClient: (cb) => (client = new FakeClient(cb)),
  });
  return { conn, events, client: () => client };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("espera cresce e tem limite", () => {
  expect([0, 1, 2, 10].map(backoffDelay)).toEqual([500, 1000, 2000, 10000]);
});

test("URL do WebSocket a partir da página e do token", () => {
  expect(wsUrlFor("https://pc.tail.ts.net", "a b")).toBe("wss://pc.tail.ts.net/ws?token=a%20b");
  expect(wsUrlFor("http://127.0.0.1:8765/", "t")).toBe("ws://127.0.0.1:8765/ws?token=t");
});

test("ligar emite connection true", async () => {
  const { conn, events } = setup();
  await conn.connect();
  expect(events).toContainEqual({ type: "connection", data: { connected: true } });
});

test("queda emite offline e agenda uma só reconexão", async () => {
  const { conn, events, client } = setup();
  await conn.connect();
  client().cb.onDisconnected();
  client().cb.onDisconnected();
  expect(events).toContainEqual({ type: "connection", data: { connected: false } });
  expect(vi.getTimerCount()).toBe(1);
  await vi.advanceTimersByTimeAsync(500);
  expect(client().connects).toHaveLength(2);
});

test("falha ao ligar também reagenda com espera maior", async () => {
  const { conn, client } = setup();
  await conn.connect();
  client().failNext = true;
  client().cb.onDisconnected();
  await vi.advanceTimersByTimeAsync(500); // 2.ª tentativa falha
  expect(client().connects).toHaveLength(2);
  await vi.advanceTimersByTimeAsync(999);
  expect(client().connects).toHaveLength(2);
  await vi.advanceTimersByTimeAsync(1);
  expect(client().connects).toHaveLength(3);
});

test("desligar manualmente não volta a ligar", async () => {
  const { conn } = setup();
  await conn.connect();
  await conn.disconnect();
  expect(vi.getTimerCount()).toBe(0);
});

test("mensagens do servidor seguem para onEvent", async () => {
  const { conn, events, client } = setup();
  await conn.connect();
  client().cb.onServerMessage({ type: "state", data: { value: "thinking" } });
  expect(events).toContainEqual({ type: "state", data: { value: "thinking" } });
});

test("microfone, confirmar e cancelar chegam ao cliente", async () => {
  const { conn, client } = setup();
  await conn.connect();
  conn.setMicEnabled(true);
  conn.confirm("a1");
  conn.cancel();
  expect(client().mic).toEqual([true]);
  expect(client().sent).toEqual([["confirm", { id: "a1" }], ["cancel", {}]]);
});
