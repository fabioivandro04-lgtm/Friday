// Push-to-talk: o microfone só está ligado enquanto Ctrl+Shift+Espaço estiver premido.
// (Ctrl+Espaço sozinho é do VS Code no Windows e do Spotlight no Mac.)

export function createPushToTalk(setMic: (on: boolean) => void) {
  let held = false;
  let toggled = false;
  return {
    onKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space" || !e.ctrlKey || !e.shiftKey || e.repeat || held) return;
      e.preventDefault?.();
      held = true;
      setMic(true);
    },
    onKeyUp(e: KeyboardEvent) {
      if (!held || (e.code !== "Space" && !e.code.startsWith("Control") && !e.code.startsWith("Shift"))) return;
      held = false;
      setMic(false);
    },
    // Botão do microfone (e atalho global do Tauri, que só dá "premido" e "solto").
    press() {
      if (!held) {
        held = true;
        setMic(true);
      }
    },
    release() {
      if (held) {
        held = false;
        setMic(false);
      }
    },
    toggle() {
      toggled = !toggled;
      setMic(toggled);
    },
  };
}
