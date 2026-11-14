import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 1420, strictPort: true },
  build: {
    outDir: "dist/frontend",
    manifest: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "react",
              test: /node_modules\/(react|react-dom|scheduler)\//,
              priority: 30,
            },
            {
              name: "motion",
              test: /node_modules\/(motion|framer-motion|motion-dom|motion-utils)\//,
              priority: 20,
            },
            {
              name: "ui",
              test: /node_modules\/(@radix-ui|radix-ui|cmdk|lucide-react|sonner)\//,
              priority: 10,
            },
            {
              name: "data",
              test: /node_modules\/(@tanstack|zustand)\//,
              priority: 10,
            },
          ],
        },
      },
    },
  },
  test: { environment: "jsdom", setupFiles: "./src/test-setup.ts" },
});
