import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    define: {
      "process.env.REACT_APP_BACKEND_URL": JSON.stringify(env.REACT_APP_BACKEND_URL || ""),
      "process.env.PUBLIC_URL": JSON.stringify(""),
    },
    server: {
      host: "0.0.0.0",
      port: 3000,
      allowedHosts: true,
      hmr: { clientPort: 443 },
    },
    build: {
      outDir: "build",
      sourcemap: false,
      chunkSizeWarningLimit: 1500,
    },
  };
});
