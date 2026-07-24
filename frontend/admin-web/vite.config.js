import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Puerto 5174 para poder levantar las dos apps a la vez (la pública usa 5173).
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { port: 5174 },
});
