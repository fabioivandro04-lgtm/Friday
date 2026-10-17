import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import type { ClientCallbacks, PipecatLike } from "./lib/connection";

beforeEach(() => localStorage.clear());

function fakeFactory() {
  const made: { cb: ClientCallbacks; urls: string[]; mic: boolean[] }[] = [];
  const createClient = (cb: ClientCallbacks): PipecatLike => {
    const entry = { cb, urls: [] as string[], mic: [] as boolean[] };
    made.push(entry);
    return {
      async connect(p) {
        entry.urls.push(p.wsUrl);
        cb.onConnected();
      },
      async disconnect() {},
      enableMic(on) {
        entry.mic.push(on);
      },
      sendClientMessage() {},
    };
  };
  return { made, createClient };
}

test("sem token pede emparelhamento", () => {
  render(<App createClient={fakeFactory().createClient} />);
  expect(screen.getByLabelText("Endereço do Core")).toBeInTheDocument();
  expect(screen.getByLabelText("Token")).toBeInTheDocument();
  expect(screen.getByText(/\/pair/)).toBeInTheDocument();
});

test("depois de emparelhar liga ao Core e mostra o HUD", async () => {
  const f = fakeFactory();
  render(<App createClient={f.createClient} />);
  await userEvent.clear(screen.getByLabelText("Endereço do Core"));
  await userEvent.type(screen.getByLabelText("Endereço do Core"), "http://127.0.0.1:8765");
  await userEvent.type(screen.getByLabelText("Token"), "abc");
  await userEvent.click(screen.getByRole("button", { name: "Ligar" }));
  expect(await screen.findByText("A OUVIR")).toBeInTheDocument();
  expect(f.made[0].urls).toEqual(["ws://127.0.0.1:8765/ws?token=abc"]);
  expect(JSON.parse(localStorage.getItem("friday.settings")!).token).toBe("abc");
});

test("modo sempre à escuta liga o microfone e muda a dica", async () => {
  const f = fakeFactory();
  render(<App createClient={f.createClient} />);
  await userEvent.type(screen.getByLabelText("Token"), "abc");
  await userEvent.click(screen.getByLabelText(/Sempre à escuta/));
  await userEvent.click(screen.getByRole("button", { name: "Ligar" }));
  expect(await screen.findByText(/DIZ “FRIDAY”/)).toBeInTheDocument();
  expect(f.made[0].mic).toEqual([true]);
});
