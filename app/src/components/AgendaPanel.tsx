import { Panel } from "./Panel";

// Fica ativo na Parte 2 (Google Calendar / Outlook).
export function AgendaPanel() {
  return (
    <Panel title="HOJE · AGENDA">
      <p className="placeholder">Por ligar</p>
      <p className="panel-foot">GOOGLE CALENDAR · OUTLOOK</p>
    </Panel>
  );
}
