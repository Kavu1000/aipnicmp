/**
 * Refuse any import that reaches outside web/.
 *
 * The web image is built with `web` as its Docker context, so the container
 * never sees the rest of the repository. An import climbing above this
 * directory therefore resolves everywhere except the one place that matters:
 * `npm run build` passes locally, the CI web-build job passes because the
 * checkout has the whole repo, and the image build fails minutes later with a
 * module-not-found for a file that is plainly right there.
 *
 * That happened once, to a methods note imported from docs/. This makes the
 * next one fail in the build that is quick to run and easy to read.
 *
 *     node scripts/check-imports.mjs
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(web, "src");

/** Every static or dynamic import specifier, and every re-export. */
const SPECIFIER =
  /(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|import\s*['"]([^'"]+)['"]/g;

function* files(directory) {
  for (const entry of readdirSync(directory)) {
    const path = resolve(directory, entry);
    if (statSync(path).isDirectory()) yield* files(path);
    else if (/\.(ts|tsx|js|jsx|css)$/.test(entry)) yield path;
  }
}

const escapes = [];
for (const file of files(source)) {
  const text = readFileSync(file, "utf8");
  for (const match of text.matchAll(SPECIFIER)) {
    const specifier = match[1] ?? match[2] ?? match[3];
    // Only relative paths can climb out; bare specifiers are packages.
    if (!specifier?.startsWith(".")) continue;
    // Query suffixes such as ?raw are Vite's, not part of the path.
    const target = resolve(dirname(file), specifier.split("?")[0]);
    if (!target.startsWith(web)) {
      escapes.push(`${relative(web, file)} -> ${specifier}`);
    }
  }
}

if (escapes.length) {
  console.error("Imports reaching outside web/ (the Docker build context):\n");
  for (const line of escapes) console.error(`  ${line}`);
  console.error(
    "\nThe web image is built with `web` as its context, so these files do not\n" +
      "exist in the container. Move the file inside web/ rather than widening\n" +
      "the context.",
  );
  process.exit(1);
}

console.log("No imports escape web/.");
