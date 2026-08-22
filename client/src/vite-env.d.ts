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

/**
 * Build-time configuration this app reads from `import.meta.env`.
 *
 * Declared rather than left to `vite/client`'s permissive index signature, so
 * that a misspelt variable is a type error at build time instead of an
 * `undefined` that only shows up as a broken sign-in in the browser.
 */
interface ImportMetaEnv {
  /** Where the API lives, when it is not the same origin. */
  readonly VITE_API_BASE?: string;
  /** The dev server's proxy target; see vite.config.ts. */
  readonly VITE_API_TARGET?: string;
  /** The basemap style, overridable per deployment. */
  readonly VITE_MAP_STYLE?: string;
  /** Firebase Authentication — see src/auth/firebase.ts. Public by design. */
  readonly VITE_FIREBASE_API_KEY?: string;
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string;
  readonly VITE_FIREBASE_PROJECT_ID?: string;
  readonly VITE_FIREBASE_APP_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
