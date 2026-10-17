import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // O Tauri espera uma porta fixa em desenvolvimento.
  server: { port: 5173, strictPort: true },
  // App local: o tamanho do bundle (cliente Pipecat) não importa.
  build: { chunkSizeWarningLimit: 1500 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
