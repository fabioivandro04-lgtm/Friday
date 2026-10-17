import { createPushToTalk } from "./ptt";

const key = (type: string, init: Partial<KeyboardEventInit>) => new KeyboardEvent(type, { code: "Space", ...init });

test("Ctrl+Shift+Espaço liga o microfone enquanto está premido", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.onKeyDown(key("keydown", { ctrlKey: true, shiftKey: true }));
  ptt.onKeyDown(key("keydown", { ctrlKey: true, shiftKey: true, repeat: true }));
  ptt.onKeyUp(key("keyup", { ctrlKey: true, shiftKey: true }));
  expect(mic).toEqual([true, false]);
});

test("soltar o Ctrl primeiro também desliga", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.onKeyDown(key("keydown", { ctrlKey: true, shiftKey: true }));
  ptt.onKeyUp(new KeyboardEvent("keyup", { code: "ControlLeft" }));
  expect(mic).toEqual([true, false]);
});

test("Espaço sem Ctrl não faz nada", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.onKeyDown(key("keydown", {}));
  ptt.onKeyUp(key("keyup", {}));
  expect(mic).toEqual([]);
});

test("toggle do botão alterna", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.toggle();
  ptt.toggle();
  expect(mic).toEqual([true, false]);
});

test("Ctrl+Espaço sozinho já não fala (é do VS Code e do Spotlight)", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.onKeyDown(key("keydown", { ctrlKey: true }));
  expect(mic).toEqual([]);
});
