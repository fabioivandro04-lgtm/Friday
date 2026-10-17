import { createPushToTalk } from "./ptt";

const key = (type: string, init: Partial<KeyboardEventInit>) => new KeyboardEvent(type, { code: "Space", ...init });

test("Ctrl+Espaço liga o microfone enquanto está premido", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.onKeyDown(key("keydown", { ctrlKey: true }));
  ptt.onKeyDown(key("keydown", { ctrlKey: true, repeat: true }));
  ptt.onKeyUp(key("keyup", { ctrlKey: true }));
  expect(mic).toEqual([true, false]);
});

test("soltar o Ctrl primeiro também desliga", () => {
  const mic: boolean[] = [];
  const ptt = createPushToTalk((on) => mic.push(on));
  ptt.onKeyDown(key("keydown", { ctrlKey: true }));
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
