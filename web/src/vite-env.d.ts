/// <reference types="vite/client" />

/**
 * Markdown imported for its text, not compiled.
 *
 * `vite/client` already declares `*?raw`, but only once it is referenced —
 * which nothing in this project did until the methods page imported the
 * document the repository keeps, rather than holding a second copy of it.
 */
declare module "*.md?raw" {
  const content: string;
  export default content;
}
