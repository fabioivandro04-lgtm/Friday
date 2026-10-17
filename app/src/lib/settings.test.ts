import { loadSettings, normaliseCoreUrl, saveSettings } from "./settings";

beforeEach(() => localStorage.clear());

test("sem nada guardado, usa a origem da página quando servida pelo Core", () => {
  expect(loadSettings("https://pc.tail.ts.net")).toEqual({ coreUrl: "https://pc.tail.ts.net", token: "" });
});

test("no Tauri ou no Vite dev, sugere o Core local", () => {
  expect(loadSettings("tauri://localhost").coreUrl).toBe("http://127.0.0.1:8765");
  expect(loadSettings("http://tauri.localhost").coreUrl).toBe("http://127.0.0.1:8765"); // Windows
  expect(loadSettings("http://localhost:5173").coreUrl).toBe("http://127.0.0.1:8765");
});

test("guarda e volta a ler", () => {
  saveSettings({ coreUrl: "http://127.0.0.1:8765", token: "abc" });
  expect(loadSettings("http://x").token).toBe("abc");
});

test("localStorage indisponível não rebenta", () => {
  const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("bloqueado");
  });
  expect(loadSettings("http://127.0.0.1:8765").token).toBe("");
  spy.mockRestore();
});

test.each([
  ["100.64.1.2:8765", "http://100.64.1.2:8765"],
  ["friday-pc:8765", "http://friday-pc:8765"],
  ["  https://pc.tail.ts.net/  ", "https://pc.tail.ts.net"],
  ["http://127.0.0.1:8765", "http://127.0.0.1:8765"],
])("normaliza o endereço %s", (input, expected) => {
  expect(normaliseCoreUrl(input)).toBe(expected);
});

test.each(["", "http://", "não é um url"])("rejeita o endereço %j", (input) => {
  expect(normaliseCoreUrl(input)).toBeNull();
});
