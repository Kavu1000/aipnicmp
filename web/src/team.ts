/**
 * The people behind the platform, shown on the sign-in screen.
 *
 * EDIT THIS FILE to change the credits — it is plain data on purpose, so that
 * updating a name needs no knowledge of React and no database migration.
 *
 * The names below are PLACEHOLDERS. Replace them before showing the platform
 * to anyone: crediting the wrong people, or leaving "Name Surname" on a
 * competition entry, is worse than crediting nobody.
 *
 * `role` is optional; leave it out and only the name is shown. `lao` is the
 * name in Lao script, used when the interface language is Lao — omit it and
 * the Latin name is used for both.
 */

export interface Person {
  name: string;
  lao?: string;
  role?: string;
  roleLao?: string;
}

/** Who built it. */
export const TEAM: Person[] = [
  { name: "Name Surname", role: "Project lead" },
  { name: "Name Surname", role: "Backend and data" },
  { name: "Name Surname", role: "Android collector" },
  { name: "Name Surname", role: "Web and cartography" },
];

/** Who advised it. */
export const ADVISORS: Person[] = [
  { name: "Name Surname", role: "Faculty advisor" },
  { name: "Name Surname", role: "Technical advisor" },
];

/** Shown under the credits. Institution, competition, year. */
export const AFFILIATION = "Faculty of Engineering, National University of Laos";

export function personName(person: Person, language: string): string {
  return (language === "lo" && person.lao) || person.name;
}

export function personRole(person: Person, language: string): string | undefined {
  return (language === "lo" && person.roleLao) || person.role;
}
