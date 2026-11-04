import { defineConfig } from "astro/config";

// Served from https://txavl.github.io/txa-repo/ (GitHub Pages project site).
export default defineConfig({
  site: "https://txavl.github.io",
  base: "/txa-repo/",
  trailingSlash: "ignore",
  build: { assets: "assets" },
  compressHTML: true,
});
