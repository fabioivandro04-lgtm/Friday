import type { UiState } from "../lib/state";
import { AgendaPanel } from "./AgendaPanel";
import { ConfirmCard } from "./ConfirmCard";
import { EmailPanel } from "./EmailPanel";
import { Reactor } from "./Reactor";
import { SystemPanel } from "./SystemPanel";
import { Transcript } from "./Transcript";

export type HudProps = {
  state: UiState;
  onConfirm: (id: string) => void;
  onCancel: () => void;
  onTalk: () => void;
  talking?: boolean;
  hint?: string;
  onRepair?: () => void;
};

export function Hud({ state, onConfirm, onCancel, onTalk, talking = false, hint, onRepair }: HudProps) {
  return (
    <div className="hud">
      <header className="hud-header">
        <div className="brand">F.R.I.D.A.Y.</div>
        <div className="header-right">
          <span className="muted data">PT-PT · EN</span>
          {onRepair && (
            <button type="button" className="link" onClick={onRepair}>
              Emparelhar de novo
            </button>
          )}
        </div>
      </header>
      <div className="hud-body">
        <div className="col-side">
          <AgendaPanel feed={state.agenda} />
        </div>
        <main className="col-main">
          <Reactor state={state.reactor} />
          <Transcript user={state.lastUser} assistant={state.lastAssistant} />
          {state.pending && <ConfirmCard pending={state.pending} onConfirm={onConfirm} onCancel={onCancel} />}
          <button type="button" className="mic" aria-label="Falar com a Friday" aria-pressed={talking} onClick={onTalk}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          </button>
          <p className="hint">{hint ?? "MANTÉM CTRL + SHIFT + ESPAÇO PARA FALAR"}</p>
        </main>
        <div className="col-side">
          <EmailPanel feed={state.inbox} />
          <SystemPanel system={state.system} />
        </div>
      </div>
    </div>
  );
}
