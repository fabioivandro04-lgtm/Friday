export function Transcript({ user, assistant }: { user?: string; assistant?: string }) {
  return (
    <div className="transcript">
      {user && <p className="transcript-user">Tu · “{user}”</p>}
      {assistant && <p className="transcript-assistant">Friday · {assistant}</p>}
    </div>
  );
}
