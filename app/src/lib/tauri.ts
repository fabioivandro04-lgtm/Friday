// Atalho global Ctrl+Shift+Espaço (Cmd+Shift+Espaço no Mac) (funciona mesmo com a janela da Friday em segundo plano).
// Só existe dentro da app Tauri; no browser não faz nada.

type Unregister = () => void;

export async function registerGlobalShortcut(onPress: () => void, onRelease: () => void): Promise<Unregister> {
  if (!("__TAURI_INTERNALS__" in window)) return () => {};
  const { register, unregister } = await import("@tauri-apps/plugin-global-shortcut");
  const shortcut = "CommandOrControl+Shift+Space";
  try {
    await register(shortcut, (event) => (event.state === "Pressed" ? onPress() : onRelease()));
  } catch (e) {
    // Outro programa já usa o atalho: continua a funcionar com a janela em primeiro plano.
    console.warn("Atalho global indisponível:", e);
    return () => {};
  }
  return () => void unregister(shortcut);
}
