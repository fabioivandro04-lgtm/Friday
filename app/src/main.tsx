import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Hud } from "./components/Hud";
import { initialState } from "./lib/state";
import "./styles.css";
import { theme } from "./theme";

const vars: Record<string, string> = {
  "--ground": theme.ground,
  "--panel": theme.panel,
  "--border": theme.border,
  "--accent": theme.accent,
  "--warning": theme.warning,
  "--text": theme.text,
  "--muted": theme.muted,
  "--font-ui": theme.fontUi,
  "--font-data": theme.fontData,
};
for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Hud state={initialState} onConfirm={() => {}} onCancel={() => {}} onTalk={() => {}} />
  </StrictMode>,
);
