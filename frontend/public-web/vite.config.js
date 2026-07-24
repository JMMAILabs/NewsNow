import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" → rutas relativas, para que funcione servido desde S3/CloudFront.
export default defineConfig({
  plugins: [react()],
  base: "./",
});
