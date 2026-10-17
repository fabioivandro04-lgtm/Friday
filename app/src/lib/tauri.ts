// Atalho global Ctrl+Espaço (funciona mesmo com a janela da Friday em segundo plano).
// Só existe dentro da app Tauri; no browser não faz nada.

type Unregister = () => void;

export async function registerGlobalShortcut(onPress: () => void, onRelease: () => void): Promise<Unregister> {
  if (!("__TAURI_INTERNALS__" in window)) return () => {};
  const { register, unregister } = await import("@tauri-apps/plugin-global-shortcut");
  const shortcut = "CommandOrControl+Space";
  await register(shortcut, (event) => (event.state === "Pressed" ? onPress() : onRelease()));
  return () => void unregister(shortcut);
}
