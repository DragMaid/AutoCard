import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    fs: {
      // The card art lives in the repository's shared assets/ directory, which
      // sits outside web/. Allow Vite to serve it through the public symlink.
      allow: [".."],
    },
  },
});
