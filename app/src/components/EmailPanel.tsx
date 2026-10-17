import type { Feed, InboxItem } from "../lib/state";
import { Panel } from "./Panel";

export function EmailPanel({ feed }: { feed?: Feed<InboxItem> }) {
  return (
    <Panel title="EMAIL · POR LER">
      {!feed?.connected ? (
        <p className="placeholder">Por ligar</p>
      ) : feed.items.length === 0 ? (
        <p className="placeholder">Sem emails por ler</p>
      ) : (
        <ul className="list">
          {feed.items.map((m) => (
            <li key={m.ref} className="list-mail">
              <span className="muted list-sender">{m.sender.replace(/<.*>/, "").trim() || m.sender}</span>
              <span>{m.subject}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
