import type { Strings } from "./i18n";

export type View = "map" | "overview" | "priority" | "networks" | "collectors";

interface Props {
  view: View;
  strings: Strings;
  open: boolean;
  onSelect: (view: View) => void;
  onClose: () => void;
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
export function Sidebar({ view, strings, open, onSelect, onClose }: Props) {
  const items: Array<{ id: View; label: string; icon: string; hint: string }> = [
    { id: "map", label: strings.navMap, icon: "◉", hint: strings.navMapHint },
    { id: "overview", label: strings.navOverview, icon: "▤", hint: strings.navOverviewHint },
    { id: "priority", label: strings.navPriority, icon: "▲", hint: strings.navPriorityHint },
    { id: "networks", label: strings.navNetworks, icon: "◈", hint: strings.navNetworksHint },
    { id: "collectors", label: strings.navCollectors, icon: "▮", hint: strings.navCollectorsHint },
  ];

  return (
    <>
      {open && <div className="scrim" onClick={onClose} />}

      <aside className={open ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">◆</span>
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
          <p>{strings.sidebarNote}</p>
        </div>
      </aside>
    </>
  );
}
