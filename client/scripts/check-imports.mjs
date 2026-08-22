/**
 * Refuse any import that reaches outside client/.
 *
 * Cloned from ../web/scripts/check-imports.mjs — see that file's comment for
 * the failure this catches: the client image is built with `client` as its
 * Docker context, so an import climbing above this directory resolves
 * everywhere except the one place that matters, and fails minutes later in
 * the image build instead of in the fast job that is quick to run and easy
 * to read.
 *
 *     node scripts/check-imports.mjs
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const client = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(client, "src");

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
    if (!target.startsWith(client)) {
      escapes.push(`${relative(client, file)} -> ${specifier}`);
    }
  }
}

if (escapes.length) {
  console.error("Imports reaching outside client/ (the Docker build context):\n");
  for (const line of escapes) console.error(`  ${line}`);
  console.error(
    "\nThe client image is built with `client` as its context, so these files\n" +
      "do not exist in the container. Move the file inside client/ rather than\n" +
      "widening the context.",
  );
  process.exit(1);
}

console.log("No imports escape client/.");
