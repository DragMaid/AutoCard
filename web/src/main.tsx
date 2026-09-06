/** Entry point: mounts the app. */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

const container = document.getElementById("root");
if (!container) throw new Error("Missing #root element");

/**
 * Waits for the display font before mounting.
 *
 * Card names are sized by measuring them on a canvas, so a face measured in
 * the fallback stack and then rendered in Silkscreen comes out too wide and is
 * clipped. `fonts.ready` alone is not enough: a webfont nothing has used yet
 * is never fetched, so the load has to be asked for explicitly. The race is
 * capped so a blocked or offline font request never holds up the game.
 */
async function fontsSettled(): Promise<void> {
  if (!document.fonts) return;

  const requested = ["400 12px Silkscreen", "700 12px Silkscreen"].map((font) =>
    document.fonts.load(font).catch(() => undefined),
  );

  await Promise.race([
    Promise.all(requested).then(() => document.fonts.ready),
    new Promise((resolve) => setTimeout(resolve, 1500)),
  ]);
}

void fontsSettled().then(() => {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
