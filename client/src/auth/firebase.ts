import { initializeApp, type FirebaseApp } from "firebase/app";
import { GoogleAuthProvider, getAuth, signInWithPopup, signOut } from "firebase/auth";

/**
 * Sign in through Firebase Authentication.
 *
 * The alternative to the Google button next door, and the reason it exists is
 * not technical. Both routes end with a signed token this platform's server
 * verifies; they differ in who keeps the list of sites allowed to start a
 * sign-in. With the Google button that list belongs to whoever owns the Cloud
 * Console project behind the client id, and a site they have not listed is
 * refused with `origin_mismatch` no matter what this code does. Firebase moves
 * the same list into a console this project owns.
 *
 * None of these values are secret. They identify the Firebase project to
 * Google in exactly the way the client id did, they are readable in any
 * browser that loads this page, and the account is protected by the Authorized
 * domains list and by the server checking the token — never by keeping the
 * configuration quiet.
 */
const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/**
 * Whether this build was given a Firebase project to sign in against.
 *
 * Read at module scope from build-time values, so a build without them keeps
 * the Google button rather than offering a sign-in that cannot work. All four
 * are required: three of them and a missing one is not a degraded sign-in, it
 * is a runtime error inside the SDK.
 */
export const firebaseConfigured = Boolean(
  config.apiKey && config.authDomain && config.projectId && config.appId,
);

let app: FirebaseApp | null = null;

function firebaseAuth() {
  // Created on first use rather than at import: a build with no Firebase
  // configuration must not pay for the SDK's initialisation, or fail in it.
  if (app === null) app = initializeApp(config);
  return getAuth(app);
}

/**
 * Open Google's account chooser and return the id token it ends with.
 *
 * The token goes to this platform's own `/auth/google`, which verifies it and
 * sets the session cookie that everything else here depends on.
 *
 * Firebase's own session is deliberately not kept. It would be a second
 * identity, living in this browser's local storage, that nothing on this site
 * reads and no sign-out here would clear — and this platform is meant to be
 * usable from shared machines, where the next person must not inherit it. The
 * account chooser is forced for the same reason: silently resuming whoever
 * used the machine last is the wrong default for a desk in an office.
 */
export async function signInWithGoogleFirebase(): Promise<string> {
  const auth = firebaseAuth();
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });

  const result = await signInWithPopup(auth, provider);
  const token = await result.user.getIdToken();
  await signOut(auth);
  return token;
}
