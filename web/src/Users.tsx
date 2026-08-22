import { useCallback, useEffect, useState } from "react";
import {
  decideUser,
  fetchAssignableDevices,
  fetchUsers,
  setUserCredit,
  setUserDevices,
  setUserRole,
  type AccountUser,
  type AssignableDevice,
  type UserRole,
  type UserStatus,
} from "./api";
import { formatAge } from "./coverage";

/**
 * The networks an account may be tied to.
 *
 * Listed here rather than fetched, because the choice is which company an
 * account belongs to, not which networks happen to have been measured. A
 * newly signed operator should be grantable access before a collector has
 * ever carried their SIM.
 */
const LAO_NETWORKS = ["Lao Telecom", "ETL", "Unitel", "Tplus"] as const;
import type { Strings } from "./i18n";

/**
 * The approval queue — visible only to super admins.
 *
 * Pending accounts come first because deciding them is the only reason to open
 * this page. Everyone else is listed below so that revoking access does not
 * require remembering who has it.
 *
 * The server refuses self-decisions and the removal of the last super admin;
 * those buttons are hidden here as well, so the rule is visible rather than
 * discovered by being told no.
 */
interface Props {
  t: Strings;
  /** So the current account's own row can be shown without its controls. */
  currentUserId: number | null;
}

const STATUS_CLASS: Record<UserStatus, string> = {
  pending: "pill",
  approved: "pill good",
  rejected: "pill bad",
};

export function Users({ t, currentUserId }: Props) {
  const [users, setUsers] = useState<AccountUser[]>([]);
  const [pending, setPending] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // Set while a super admin is choosing which network an account belongs to.
  // Which collector account is having its handsets chosen, and what is on
  // offer. Loaded when the picker opens rather than with the page: a list of
  // every enrolled device is not something the users table needs.
  const [pendingDevices, setPendingDevices] = useState<{
    id: number;
    chosen: Set<string>;
  } | null>(null);
  const [assignable, setAssignable] = useState<AssignableDevice[]>([]);

  const [pendingOperator, setPendingOperator] = useState<{
    id: number;
    current: string | null;
  } | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const body = await fetchUsers(signal);
      setUsers(body.users);
      setPending(body.pending);
      setError(null);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof Error ? cause.message : "could not load users");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const apply = async (id: number, action: () => Promise<AccountUser>) => {
    setBusyId(id);
    try {
      const updated = await action();
      setUsers((current) => current.map((user) => (user.id === id ? updated : user)));
      setPending((count) => (updated.status === "pending" ? count : Math.max(0, count - 1)));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not update this account");
    } finally {
      setBusyId(null);
    }
  };

  const superAdmins = users.filter(
    (user) => user.role === "super_admin" && user.status === "approved",
  ).length;

  if (loaded && users.length === 0 && !error) {
    return <p className="empty">{t.usersNone}</p>;
  }

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{t.usersTitle}</h2>
          <p>{t.usersSubtitle}</p>
        </div>
        {pending > 0 && (
          <span className="pill">{t.usersPendingCount.replace("%N%", String(pending))}</span>
        )}
      </header>

      {error && <p className="caveat">{error}</p>}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t.usersPerson}</th>
              <th>{t.usersRole}</th>
              <th>{t.usersStatus}</th>
              <th>{t.usersCredit}</th>
              <th>{t.usersRequested}</th>
              <th>{t.usersActions}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const isSelf = user.id === currentUserId;
              // The server enforces both of these; hiding the controls makes
              // the rule visible instead of something you discover by trying.
              const isLastSuperAdmin =
                user.role === "super_admin" && user.status === "approved" && superAdmins <= 1;
              const locked = isSelf || isLastSuperAdmin || busyId === user.id;

              return (
                <tr key={user.id} className={user.status === "rejected" ? "muted-row" : undefined}>
                  <td>
                    <span className="user-cell">
                      {user.picture_url && (
                        <img src={user.picture_url} alt="" width={28} height={28} />
                      )}
                      <span>
                        <span className="device-name">
                          {user.name ?? user.email}
                          {isSelf && ` · ${t.usersYou}`}
                        </span>
                        <span className="device-meta">{user.email}</span>
                      </span>
                    </span>
                  </td>

                  <td>
                    <select
                      className="select"
                      value={user.role}
                      disabled={locked}
                      onChange={(event) => {
                        const role = event.target.value as UserRole;
                        // A network account must name its network, and the
                        // server refuses one that does not. Choosing it here,
                        // in the same action, means the account is never left
                        // scoped to nothing.
                        if (role === "operator") {
                          setPendingOperator({ id: user.id, current: user.scoped_operator ?? null });
                          return;
                        }
                        apply(user.id, () => setUserRole(user.id, role));
                      }}
                      aria-label={t.usersRole}
                    >
                      <option value="admin">{t.usersRoleAdmin}</option>
                      <option value="super_admin">{t.usersRoleSuperAdmin}</option>
                      <option value="operator">{t.usersRoleOperator}</option>
                      <option value="collector">{t.usersRoleCollector}</option>
                    </select>

                    {/* Which network, shown wherever the role is. An operator
                        row that did not say so would look like an ordinary
                        account with less access for no visible reason. */}
                    {user.role === "operator" && (
                      <span className="device-meta">
                        {user.scoped_operator ?? t.usersNoNetwork}
                      </span>
                    )}
                  </td>

                  <td>
                    <span className={STATUS_CLASS[user.status]}>{t[statusKey(user.status)]}</span>
                  </td>

                  {/* Credit is not access, so it is its own control. Ticking
                      this publishes a name and portrait on the sign-in page;
                      granting admin never does that on its own, and removing
                      admin never erases somebody from work they did. */}
                  <td>
                    {user.role === "collector" ? (
                      /* Ticking a box here decides whose movements somebody
                         may look at, so it is its own action rather than a
                         side effect of the role change above it. */
                      <button
                        className="link"
                        disabled={busyId === user.id}
                        onClick={() => {
                          void fetchAssignableDevices()
                            .then((body) => {
                              setAssignable(body.devices);
                              setPendingDevices({
                                id: user.id,
                                chosen: new Set(
                                  body.devices
                                    .filter((d) => d.owner_user_id === user.id)
                                    .map((d) => d.install_id),
                                ),
                              });
                            })
                            .catch(() => undefined);
                        }}
                      >
                        {t.usersDevicesButton}
                      </button>
                    ) : user.role === "operator" ? (
                      <span className="device-meta">—</span>
                    ) : (
                      <label className="credit-toggle">
                        <input
                          type="checkbox"
                          checked={user.show_in_credits ?? false}
                          disabled={busyId === user.id}
                          onChange={(event) =>
                            apply(user.id, () =>
                              setUserCredit(
                                user.id,
                                event.target.checked,
                                user.credit_title ?? null,
                              ),
                            )
                          }
                        />
                        <input
                          className="select credit-title"
                          type="text"
                          defaultValue={user.credit_title ?? ""}
                          placeholder={t.usersCreditTitle}
                          disabled={busyId === user.id}
                          onBlur={(event) => {
                            const title = event.target.value.trim();
                            if (title === (user.credit_title ?? "")) return;
                            apply(user.id, () =>
                              setUserCredit(user.id, user.show_in_credits ?? false, title),
                            );
                          }}
                          aria-label={t.usersCreditTitle}
                        />
                      </label>
                    )}
                  </td>

                  <td className="small">{formatAge(user.requested_at, "—")}</td>

                  <td>
                    <div className="user-actions">
                      {user.status !== "approved" && (
                        <button
                          className="button-approve"
                          disabled={locked}
                          onClick={() => apply(user.id, () => decideUser(user.id, "approved"))}
                        >
                          {t.usersApprove}
                        </button>
                      )}
                      {user.status !== "rejected" && (
                        <button
                          className="button-reject"
                          disabled={locked}
                          onClick={() => apply(user.id, () => decideUser(user.id, "rejected"))}
                        >
                          {t.usersReject}
                        </button>
                      )}
                    </div>
                    {isLastSuperAdmin && !isSelf && (
                      <span className="device-meta">{t.usersLastSuperAdmin}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pendingDevices && (
        <div className="operator-picker" role="dialog" aria-label={t.usersChooseDevices}>
          <div className="operator-picker-card">
            <h3>{t.usersChooseDevices}</h3>
            <p>{t.usersChooseDevicesWhy}</p>

            <div className="device-picker-list">
              {assignable.map((device) => {
                // Held by somebody else: shown rather than hidden, so the
                // reason it cannot be picked is visible instead of puzzling.
                const takenBy =
                  device.owner_user_id != null && device.owner_user_id !== pendingDevices.id
                    ? device.owner_user_id
                    : null;
                const chosen = pendingDevices.chosen.has(device.install_id);
                return (
                  <label
                    key={device.install_id}
                    className={takenBy ? "device-option taken" : "device-option"}
                  >
                    <input
                      type="checkbox"
                      checked={chosen}
                      disabled={takenBy !== null}
                      onChange={(event) => {
                        const next = new Set(pendingDevices.chosen);
                        if (event.target.checked) next.add(device.install_id);
                        else next.delete(device.install_id);
                        setPendingDevices({ ...pendingDevices, chosen: next });
                      }}
                    />
                    <span className="legend-text">
                      <strong>{device.model ?? device.install_id}</strong>
                      <em>
                        {device.manufacturer ? `${device.manufacturer} · ` : ""}
                        {device.records_accepted.toLocaleString()} · {formatAge(device.last_seen_at, "—")}
                        {takenBy !== null && ` · ${t.usersDeviceTaken}`}
                      </em>
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="operator-picker-options">
              <button
                className="button-approve"
                onClick={() => {
                  const { id, chosen } = pendingDevices;
                  setPendingDevices(null);
                  apply(id, async () => {
                    await setUserDevices(id, [...chosen]);
                    // The assignment is not on the user row, so the row does
                    // not change — refetch rather than invent one.
                    const body = await fetchUsers();
                    return body.users.find((u) => u.id === id)!;
                  });
                }}
              >
                {t.usersSave}
              </button>
            </div>

            <button className="link" onClick={() => setPendingDevices(null)}>
              {t.cancel}
            </button>
          </div>
        </div>
      )}

      {pendingOperator && (
        <div className="operator-picker" role="dialog" aria-label={t.usersChooseNetwork}>
          <div className="operator-picker-card">
            <h3>{t.usersChooseNetwork}</h3>
            <p>{t.usersChooseNetworkWhy}</p>
            <div className="operator-picker-options">
              {LAO_NETWORKS.map((network) => (
                <button
                  key={network}
                  className={
                    network === pendingOperator.current
                      ? "operator-option chosen"
                      : "operator-option"
                  }
                  onClick={() => {
                    const { id } = pendingOperator;
                    setPendingOperator(null);
                    apply(id, () => setUserRole(id, "operator", network));
                  }}
                >
                  {network}
                </button>
              ))}
            </div>
            <button className="link" onClick={() => setPendingOperator(null)}>
              {t.cancel}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function statusKey(status: UserStatus): "usersStatusPending" | "usersStatusApproved" | "usersStatusRejected" {
  if (status === "approved") return "usersStatusApproved";
  if (status === "rejected") return "usersStatusRejected";
  return "usersStatusPending";
}
