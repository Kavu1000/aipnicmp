import { BrandMark } from "./BrandMark";
import type { AccountUser } from "./api";
import type { Strings } from "./i18n";

export type View = "map" | "overview" | "priority" | "networks" | "collectors" | "users";

interface Props {
  view: View;
  strings: Strings;
  open: boolean;
  onSelect: (view: View) => void;
  onClose: () => void;
  /** Null when sign-in is disabled for local development. */
  user: AccountUser | null;
  onSignOut: () => void;
}

/**
 * Primary navigation.
 *
 * Ordered by who is asking. A citizen wants the map; a ministry wants the
 * overview and the priority list; an operator wants their own network; whoever
 * is running the pilot wants to know the phones are still reporting. Putting
 * the map first keeps the public face of the project one click from the front
 * door rather than buried under administration.
 */
export function Sidebar({ view, strings, open, onSelect, onClose, user, onSignOut }: Props) {
  const items: Array<{ id: View; label: string; icon: string; hint: string }> = [
    { id: "map", label: strings.navMap, icon: "◉", hint: strings.navMapHint },
    { id: "overview", label: strings.navOverview, icon: "▤", hint: strings.navOverviewHint },
    { id: "priority", label: strings.navPriority, icon: "▲", hint: strings.navPriorityHint },
    { id: "networks", label: strings.navNetworks, icon: "◈", hint: strings.navNetworksHint },
    { id: "collectors", label: strings.navCollectors, icon: "▮", hint: strings.navCollectorsHint },
  ];

  // Deciding who may sign in is a super admin's job, so it is a super admin's
  // menu item. The server refuses the endpoints regardless — this only keeps
  // the page from advertising a door that will not open.
  if (user?.role === "super_admin") {
    items.push({ id: "users", label: strings.navUsers, icon: "◍", hint: strings.navUsersHint });
  }

  return (
    <>
      {open && <div className="scrim" onClick={onClose} />}

      <aside className={open ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <BrandMark />
          </span>
          <span className="brand-text">
            <strong>AI-PNICMP</strong>
            <em>{strings.brandSubtitle}</em>
          </span>
        </div>

        <nav>
          {items.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "nav-item on" : "nav-item"}
              onClick={() => {
                onSelect(item.id);
                onClose();
              }}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span className="nav-label">
                {item.label}
                <em>{item.hint}</em>
              </span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <a className="get-app" href="/download/coverage-collector.apk" download>
            {strings.getApp}
          </a>

          {user && (
            <div className="sidebar-account">
              {user.picture_url && <img src={user.picture_url} alt="" width={28} height={28} />}
              <span className="sidebar-account-text">
                <strong>{user.name ?? user.email}</strong>
                <em>{user.email}</em>
              </span>
              <button className="sidebar-signout" onClick={onSignOut}>
                {strings.signOut}
              </button>
            </div>
          )}

          <p>{strings.sidebarNote}</p>
        </div>
      </aside>
    </>
  );
}
