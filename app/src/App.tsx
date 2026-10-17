import { useEffect, useMemo, useReducer, useRef, useState, type FormEvent } from "react";
import { Hud } from "./components/Hud";
import { createPipecatClient, FridayConnection, wsUrlFor, type ClientCallbacks, type PipecatLike } from "./lib/connection";
import { createPushToTalk } from "./lib/ptt";
import { loadSettings, normaliseCoreUrl, saveSettings, type Settings } from "./lib/settings";
import { initialState, reduce } from "./lib/state";
import { registerGlobalShortcut } from "./lib/tauri";

type Props = { createClient?: (cb: ClientCallbacks) => PipecatLike };

export function App({ createClient = createPipecatClient }: Props) {
  const [settings, setSettings] = useState<Settings>(() => loadSettings());
  const save = (s: Settings) => {
    saveSettings(s);
    setSettings(s);
  };
  return settings.token ? (
    <Connected settings={settings} createClient={createClient} onRepair={() => save({ ...settings, token: "" })} />
  ) : (
    <Pairing
      initial={settings}
      onDone={save}
    />
  );
}

function Connected({
  settings,
  createClient,
  onRepair,
}: {
  settings: Settings;
  createClient: Props["createClient"] & {};
  onRepair: () => void;
}) {
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
    void conn.connect().then(() => {
      if (settings.alwaysListening) conn.setMicEnabled(true);
    });
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
      talking={talking || !!settings.alwaysListening}
      hint={settings.alwaysListening ? "DIZ “FRIDAY” PARA FALARES" : undefined}
      onRepair={onRepair}
    />
  );
}

function Pairing({ initial, onDone }: { initial: Settings; onDone: (s: Settings) => void }) {
  const [coreUrl, setCoreUrl] = useState(initial.coreUrl);
  const [token, setToken] = useState("");
  const [alwaysListening, setAlwaysListening] = useState(!!initial.alwaysListening);
  const [error, setError] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const url = normaliseCoreUrl(coreUrl);
    if (!url) return setError("Endereço inválido. Exemplo: http://127.0.0.1:8765");
    if (!token.trim()) return setError("Falta o token.");
    onDone({ coreUrl: url, token: token.trim(), alwaysListening });
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
      <label className="check">
        <input type="checkbox" checked={alwaysListening} onChange={(e) => setAlwaysListening(e.target.checked)} />
        Sempre à escuta (diz “Friday”; ativa [wake] no friday.toml)
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="btn btn-primary">
        Ligar
      </button>
    </form>
  );
}
