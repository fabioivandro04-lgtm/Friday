import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { initialState, type UiState } from "../lib/state";
import { Hud } from "./Hud";

function renderHud(state: Partial<UiState>, handlers: Partial<Parameters<typeof Hud>[0]> = {}) {
  const props = {
    state: { ...initialState, ...state },
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    onTalk: vi.fn(),
    ...handlers,
  };
  render(<Hud {...props} />);
  return props;
}

test("mostra o estado do reator em PT", () => {
  renderHud({ reactor: "listening" });
  expect(screen.getByText("A OUVIR")).toBeInTheDocument();
});

test.each([
  ["thinking", "A PENSAR"],
  ["speaking", "A FALAR"],
  ["offline", "SEM LIGAÇÃO"],
] as const)("estado %s → %s", (reactor, label) => {
  renderHud({ reactor });
  expect(screen.getByText(label)).toBeInTheDocument();
});

test("agenda e email com dados", () => {
  renderHud({
    agenda: { connected: true, items: [{ time: "10:00", title: "Reunião de equipa", location: "Escritório" }] },
    inbox: { connected: true, items: [{ ref: "google:m1", sender: "João", subject: "Confirmação" }] },
  });
  expect(screen.getByText("Reunião de equipa")).toBeInTheDocument();
  expect(screen.getByText("10:00")).toBeInTheDocument();
  expect(screen.getByText("Confirmação")).toBeInTheDocument();
});

test("contas ligadas mas vazias", () => {
  renderHud({ agenda: { connected: true, items: [] }, inbox: { connected: true, items: [] } });
  expect(screen.getByText("Nada marcado para hoje")).toBeInTheDocument();
  expect(screen.getByText("Sem emails por ler")).toBeInTheDocument();
});

test("agenda e email ainda por ligar", () => {
  renderHud({});
  expect(screen.getAllByText("Por ligar")).toHaveLength(2);
});

test("painel sistema mostra latência, VRAM e erro", () => {
  renderHud({ system: { model: "qwen3:8b", voice: "pt_PT", latencyMs: 900, vramGb: 7.5, error: "Modelo local indisponível" } });
  expect(screen.getByText("qwen3:8b")).toBeInTheDocument();
  expect(screen.getByText("900 ms")).toBeInTheDocument();
  expect(screen.getByText("7.5 / 16 GB")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Modelo local indisponível");
});

test("cartão de confirmação chama os handlers", async () => {
  const props = renderHud({ pending: { id: "a1", summary: "Enviar mensagem a João" } });
  expect(screen.getByText("Enviar mensagem a João")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
  expect(props.onConfirm).toHaveBeenCalledWith("a1");
  await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(props.onCancel).toHaveBeenCalled();
});

test("sem pedido pendente não há cartão", () => {
  renderHud({});
  expect(screen.queryByRole("button", { name: "Enviar" })).not.toBeInTheDocument();
});

test("botão do microfone chama onTalk", async () => {
  const props = renderHud({ reactor: "listening" });
  await userEvent.click(screen.getByRole("button", { name: "Falar com a Friday" }));
  expect(props.onTalk).toHaveBeenCalled();
});

test("mostra as últimas frases", () => {
  renderHud({ lastUser: "que horas são?", lastAssistant: "São dez e meia." });
  expect(screen.getByText(/que horas são\?/)).toBeInTheDocument();
  expect(screen.getByText(/São dez e meia\./)).toBeInTheDocument();
});
