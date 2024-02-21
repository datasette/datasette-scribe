import { argv } from "node:process";
import * as esbuild from "esbuild";

const ctx = await esbuild.context({
  bundle: true,
  minify: true,
  format: "esm",
  jsxFactory: "h",
  jsxFragment: "Fragment",
  outExtension: {
    ".js": ".min.js",
    ".css": ".min.css",
  },
  alias: {
    react: "preact/compat",
    "react-dom": "preact/compat",
  },
  target: ["safari12"],
  outdir: "datasette_scribe/static",
  entryPoints: ["datasette_scribe/frontend/targets/**/index.tsx"],
});

if (argv.find((s) => s === "--watch")) {
  await ctx.watch();
  console.log("watching...");
} else {
  console.log("Building...");
  await ctx.rebuild();
  console.log("done");
  await ctx.dispose();
}
