// Render review stills: node scripts/stills.mjs 0.6 2.5 9 ...  (seconds)
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import { mkdirSync } from "node:fs";

const serveUrl = await bundle({ entryPoint: "src/index.ts" });
const composition = await selectComposition({ serveUrl, id: "TinCanDemo" });
mkdirSync("out/stills", { recursive: true });
for (const s of process.argv.slice(2).map(Number)) {
  const output = `out/stills/t${s.toFixed(2)}.jpg`;
  await renderStill({ serveUrl, composition, frame: Math.round(s * composition.fps), output, imageFormat: "jpeg", jpegQuality: 85, scale: 0.5 });
  console.log(output);
}
