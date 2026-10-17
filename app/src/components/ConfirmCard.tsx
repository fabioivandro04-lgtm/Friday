export function ConfirmCard({
  pending,
  onConfirm,
  onCancel,
}: {
  pending: { id: string; summary: string };
  onConfirm: (id: string) => void;
  onCancel: () => void;
}) {
  return (
    <div className="confirm" role="group" aria-label="Confirmação de ação">
      <div className="confirm-title">CONFIRMAR AÇÃO</div>
      <div className="confirm-summary">{pending.summary}</div>
      <div className="confirm-actions">
        <button type="button" className="btn" onClick={onCancel}>
          Cancelar
        </button>
        <button type="button" className="btn btn-primary" onClick={() => onConfirm(pending.id)}>
          Enviar
        </button>
      </div>
    </div>
  );
}
