import { defineConfig } from "astro/config";

// The site is published as a GitHub Pages project site: every URL starts with the base.
export default defineConfig({
  site: "https://henriquemayer.github.io",
  base: "/TuxedoFinance",
  trailingSlash: "always",
});
