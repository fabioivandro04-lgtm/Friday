import { useEffect, useMemo, useReducer, useRef, useState, type FormEvent } from "react";
import { Hud } from "./components/Hud";
import { createPipecatClient, FridayConnection, wsUrlFor, type ClientCallbacks, type PipecatLike } from "./lib/connection";
import { createPushToTalk } from "./lib/ptt";
import { loadSettings, saveSettings, type Settings } from "./lib/settings";
import { initialState, reduce } from "./lib/state";
import { registerGlobalShortcut } from "./lib/tauri";

type Props = { createClient?: (cb: ClientCallbacks) => PipecatLike };

export function App({ createClient = createPipecatClient }: Props) {
  const [settings, setSettings] = useState<Settings>(() => loadSettings());
  return settings.token ? (
    <Connected settings={settings} createClient={createClient} />
  ) : (
    <Pairing
      initial={settings}
      onDone={(s) => {
        saveSettings(s);
        setSettings(s);
      }}
    />
  );
}

function Connected({ settings, createClient }: { settings: Settings; createClient: Props["createClient"] & {} }) {
  const [state, dispatch] = useReducer(reduce, initialState);
  const connRef = useRef<FridayConnection | null>(null);
  const ptt = useMemo(() => createPushToTalk((on) => connRef.current?.setMicEnabled(on)), []);
  const [talking, setTalking] = useState(false);

  useEffect(() => {
    const conn = new FridayConnection({
      url: wsUrlFor(settings.coreUrl, settings.token),
      onEvent: dispatch,
      createClient,
    });
    connRef.current = conn;
    void conn.connect();
    return () => {
      void conn.disconnect();
    };
  }, [settings, createClient]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => ptt.onKeyDown(e);
    const up = (e: KeyboardEvent) => ptt.onKeyUp(e);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    const unregister = registerGlobalShortcut(ptt.press, ptt.release);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      void unregister.then((fn) => fn());
    };
  }, [ptt]);

  return (
    <Hud
      state={state}
      onConfirm={(id) => connRef.current?.confirm(id)}
      onCancel={() => connRef.current?.cancel()}
      onTalk={() => {
        ptt.toggle();
        setTalking((t) => !t);
      }}
      talking={talking}
    />
  );
}

function Pairing({ initial, onDone }: { initial: Settings; onDone: (s: Settings) => void }) {
  const [coreUrl, setCoreUrl] = useState(initial.coreUrl);
  const [token, setToken] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (coreUrl.trim() && token.trim()) onDone({ coreUrl: coreUrl.trim(), token: token.trim() });
  };
  return (
    <form className="pairing" onSubmit={submit}>
      <div className="brand">F.R.I.D.A.Y.</div>
      <p className="muted">
        No PC onde corre o Core, abre <code>http://127.0.0.1:8765/pair</code> e copia o token.
      </p>
      <label>
        Endereço do Core
        <input value={coreUrl} onChange={(e) => setCoreUrl(e.target.value)} inputMode="url" />
      </label>
      <label>
        Token
        <input value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
      </label>
      <button type="submit" className="btn btn-primary">
        Ligar
      </button>
    </form>
  );
}
