import { Link } from "react-router-dom";
import { useSession } from "../session/SessionProvider";
import type { Strings } from "../i18n";

/**
 * Says what this map is and, for a visitor who is not signed in, that
 * signing in exists. Nothing to say once they are: this app's whole map is
 * the same public dataset either way (see App.tsx's note), so a banner
 * still advertising "sign in" to somebody already signed in would be
 * advertising nothing.
 */
export function PreviewBanner({ t }: { t: Strings }) {
  const { session } = useSession();
  if (session?.authenticated) return null;

  return (
    <div className="preview-banner">
      <span className="preview-badge">🔓 {t.previewBadge}</span>
      <span className="preview-body">{t.previewBannerBody}</span>
      <Link className="preview-signin" to="/signin">
        {t.previewSignIn} →
      </Link>
    </div>
  );
}
