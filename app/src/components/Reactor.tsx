import type { ReactorState } from "../lib/state";
import { theme } from "../theme";

const LABELS: Record<ReactorState, string> = {
  listening: "A OUVIR",
  thinking: "A PENSAR",
  speaking: "A FALAR",
  offline: "SEM LIGAÇÃO",
};

export function Reactor({ state }: { state: ReactorState }) {
  const color = state === "offline" ? theme.offline : theme.accent;
  const animated = state !== "offline";
  return (
    <div className="reactor-wrap">
      <div className={`reactor ${animated ? `reactor--${state}` : ""}`} aria-hidden="true">
        <div className="ring ring-b" style={{ borderTopColor: color, borderBottomColor: color }} />
        <div className="ring ring-a" style={{ borderColor: color, borderLeftColor: "transparent" }} />
        <div className="core" style={{ borderColor: color, boxShadow: animated ? `0 0 28px ${color}` : "none" }} />
      </div>
      <div className="reactor-label" style={{ color }} role="status">
        {LABELS[state]}
      </div>
    </div>
  );
}
