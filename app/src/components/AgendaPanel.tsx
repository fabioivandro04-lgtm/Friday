import type { AgendaItem, Feed } from "../lib/state";
import { Panel } from "./Panel";

export function AgendaPanel({ feed }: { feed?: Feed<AgendaItem> }) {
  return (
    <Panel title="HOJE · AGENDA">
      {!feed?.connected ? (
        <p className="placeholder">Por ligar</p>
      ) : feed.items.length === 0 ? (
        <p className="placeholder">Nada marcado para hoje</p>
      ) : (
        <ul className="list">
          {feed.items.map((e, i) => (
            <li key={i} className="list-row">
              <span className="data muted list-time">{e.time}</span>
              <span>
                {e.title}
                {e.location && <span className="muted"> · {e.location}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="panel-foot">GOOGLE CALENDAR · OUTLOOK</p>
    </Panel>
  );
}
