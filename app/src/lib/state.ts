// Estado da interface, alimentado pelos eventos do Friday Core.

export type ReactorState = "listening" | "thinking" | "speaking" | "offline";

export type UiState = {
  reactor: ReactorState;
  lastUser?: string;
  lastAssistant?: string;
  pending?: { id: string; summary: string };
  system: { model?: string; voice?: string; latencyMs?: number; vramGb?: number; error?: string };
};

export type CoreEvent = { type: string; data: any };

export const initialState: UiState = { reactor: "offline", system: {} };

const REACTOR_STATES: ReactorState[] = ["listening", "thinking", "speaking"];

export function reduce(state: UiState, event: CoreEvent): UiState {
  const d = event.data ?? {};
  switch (event.type) {
    case "connection":
      // Ligado não é pronto: o Core manda "state" quando estiver mesmo a ouvir.
      // Ao perder a ligação, o pedido pendente foi cancelado no Core.
      return d.connected ? state : { ...state, reactor: "offline", pending: undefined };
    case "state":
      return REACTOR_STATES.includes(d.value) ? { ...state, reactor: d.value } : state;
    case "transcript":
      return d.role === "user" ? { ...state, lastUser: d.text } : { ...state, lastAssistant: d.text };
    case "confirm_request":
      return { ...state, pending: { id: d.id, summary: d.summary } };
    case "confirm_cleared":
      return state.pending?.id === d.id ? { ...state, pending: undefined } : state;
    case "system":
      return {
        ...state,
        system: {
          model: d.model,
          voice: d.voice,
          latencyMs: d.latency_ms ?? undefined,
          vramGb: d.vram_used_gb ?? undefined,
          error: d.error ?? undefined,
        },
      };
    default:
      return state;
  }
}
