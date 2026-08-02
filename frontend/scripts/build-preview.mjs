#!/usr/bin/env node
/**
 * Build the hosted preview as one self-contained fragment.
 *
 * The artifact host wraps the output in its own document skeleton and enforces
 * a CSP that blocks every external request, so this emits body content with the
 * stylesheet and bundle inlined — no separate assets, no fonts, no tiles.
 */

import { build } from "vite";
import { readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, "..");
const outDir = join(frontend, "dist-preview");
const target =
  process.argv[2] ?? join(here, "..", "..", "preview", "portpulse-preview.html");

const escapeForScript = (text) => text.replace(/<\/script>/gi, "<\\/script>");

async function main() {
  await rm(outDir, { recursive: true, force: true });

  await build({
    root: frontend,
    // Everything ships in one file, so hashed asset URLs are pointless.
    base: "./",
    define: { "import.meta.env.VITE_FORCE_SVG_MAP": '"1"' },
    build: {
      outDir,
      emptyOutDir: true,
      cssCodeSplit: false,
      assetsInlineLimit: 100_000_000,
      modulePreload: { polyfill: false },
      rollupOptions: {
        input: join(frontend, "index.preview.html"),
        output: {
          // A single chunk keeps the inliner honest: nothing can be requested
          // at runtime if nothing was emitted separately.
          inlineDynamicImports: true,
          entryFileNames: "app.js",
          assetFileNames: "app[extname]",
        },
      },
    },
    logLevel: "warn",
  });

  const [js, css] = await Promise.all([
    readFile(join(outDir, "app.js"), "utf8"),
    readFile(join(outDir, "app.css"), "utf8"),
  ]);

  const html = `<style>
/* PortPulse preview — self-contained. The product commits to a single warm-paper
   identity, so the page opts out of the viewer's dark theme rather than
   inverting a palette that carries operational meaning (green / amber / red). */
:root { color-scheme: light; }
:root, :root[data-theme="dark"], :root[data-theme="light"] { background: #F7F4EE; }
${css}
</style>

<div id="root"></div>

<script type="module">
${escapeForScript(js)}
</script>
`;

  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html, "utf8");
  await rm(outDir, { recursive: true, force: true });

  const kb = Buffer.byteLength(html) / 1024;
  console.log(`Wrote ${target} — ${kb.toLocaleString("en-US", { maximumFractionDigits: 0 })} KB, self-contained.`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
