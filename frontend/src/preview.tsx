/**
 * Entry point for the hosted preview build.
 *
 * Identical to `main.tsx` except that it installs the recorded API bundle
 * before the app mounts, so `api/client.ts` replays it instead of calling a
 * backend that is not there.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Imported raw and parsed: a ~800 KB object literal is markedly slower to
// evaluate as JavaScript than the same bytes through JSON.parse.
import bundle from "./preview-fixtures.json?raw";
import App from "./App";
import { StoreProvider } from "./state/store";
import "./index.css";

window.__PORTPULSE_FIXTURES__ = JSON.parse(bundle);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StoreProvider>
      <App />
    </StoreProvider>
  </StrictMode>,
);
