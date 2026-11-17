import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발: 허브(uv run python -m sori_hub serve)를 5150 에 띄우고 npm run dev. 허브의 Host 검사를 넘게 changeOrigin.
export default defineConfig({
  plugins: [react()],
  base: "/",
  server: {
    port: 5173,
    proxy: {
      "/hub": { target: "http://127.0.0.1:5150", changeOrigin: true },
      "/v1": { target: "http://127.0.0.1:5150", changeOrigin: true },
    },
  },
  build: { outDir: "dist", assetsDir: "assets", sourcemap: false },
});
