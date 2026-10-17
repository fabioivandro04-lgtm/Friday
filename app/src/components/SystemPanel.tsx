import type { UiState } from "../lib/state";
import { Panel } from "./Panel";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="row">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function SystemPanel({ system }: { system: UiState["system"] }) {
  return (
    <Panel title="SISTEMA">
      <div className="data">
        <Row label="Modelo" value={system.model ?? "—"} />
        <Row label="Voz" value={system.voice ?? "—"} />
        <Row label="Latência" value={system.latencyMs != null ? `${system.latencyMs} ms` : "—"} />
        <Row label="VRAM" value={system.vramGb != null ? `${system.vramGb} / 16 GB` : "—"} />
      </div>
      {system.error && (
        <p className="error" role="alert">
          {system.error}
        </p>
      )}
    </Panel>
  );
}
