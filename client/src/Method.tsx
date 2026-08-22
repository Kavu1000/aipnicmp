import { useMemo } from "react";
// Inside src/ rather than in docs/ at the repository root, and that is not a
// filing preference. The web image is built with `web` as its Docker context,
// so a path reaching outside this directory resolves in a local build and does
// not exist in the container — which is exactly how it failed: green tests, a
// clean local `npm run build`, and a broken image build. Keep every import in
// this app inside web/.
import source from "./content/METHOD.md?raw";
import type { Strings } from "./i18n";

/**
 * The methods note, rendered from the file the repository keeps.
 *
 * Imported rather than retyped so there is one document, not a copy that
 * drifts. `web/src/content/METHOD.md` is what a reviewer is pointed at; this is
 * the same text, in the product, one click from the map it describes.
 *
 * A markdown library would be a dependency for one page, and this project keeps
 * its dependency list to maplibre and React. So the parser below handles
 * exactly the subset the document uses — headings, paragraphs, rules, bullets,
 * tables, bold and code — and nothing else. If the document grows a construct
 * that is not here, it renders as plain text rather than as markup: visibly
 * wrong to whoever added it, rather than silently swallowed.
 */

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "rule" };

function splitRow(line: string): string[] {
  return line
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

function parse(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  const flush = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      flush();
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flush();
      blocks.push({
        kind: "heading",
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2],
      });
      continue;
    }

    if (/^-{3,}$/.test(trimmed)) {
      flush();
      blocks.push({ kind: "rule" });
      continue;
    }

    // A table is a header row, a divider of dashes, then body rows. Checked
    // together because a lone pipe-separated line is not a table.
    if (trimmed.startsWith("|") && /^\|[\s:|-]+\|$/.test((lines[i + 1] ?? "").trim())) {
      flush();
      const head = splitRow(trimmed);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitRow(lines[i].trim()));
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: "table", head, rows });
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flush();
      const items: string[] = [];
      while (i < lines.length) {
        const item = lines[i].trim();
        if (/^[-*]\s+/.test(item)) {
          items.push(item.replace(/^[-*]\s+/, ""));
          i += 1;
        } else if (item && !/^(#{1,3}\s|[-*]\s|\|)/.test(item) && lines[i].startsWith("  ")) {
          // A wrapped continuation of the bullet above it.
          items[items.length - 1] += ` ${item}`;
          i += 1;
        } else {
          break;
        }
      }
      i -= 1;
      blocks.push({ kind: "list", items });
      continue;
    }

    paragraph.push(trimmed);
  }

  flush();
  return blocks;
}

/**
 * Inline markup, as React nodes rather than injected HTML.
 *
 * Never dangerouslySetInnerHTML: this file is a build-time import today, and
 * the day somebody points it at anything editable, escaping is the only thing
 * standing between a document and a script tag.
 */
function inline(text: string, keyPrefix: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    return <span key={key}>{part}</span>;
  });
}

export function Method({ t }: { t: Strings }) {
  const blocks = useMemo(() => parse(source), []);

  return (
    <article className="method">
      {/* The document is in English only. Saying so beats a reader assuming the
          Lao is somewhere they have not looked. */}
      <p className="method-language">{t.methodLanguageNote}</p>

      {blocks.map((block, index) => {
        const key = `b${index}`;
        switch (block.kind) {
          case "heading": {
            const Tag = `h${block.level}` as "h1" | "h2" | "h3";
            return <Tag key={key}>{inline(block.text, key)}</Tag>;
          }
          case "rule":
            return <hr key={key} />;
          case "list":
            return (
              <ul key={key}>
                {block.items.map((item, n) => (
                  <li key={`${key}-${n}`}>{inline(item, `${key}-${n}`)}</li>
                ))}
              </ul>
            );
          case "table":
            return (
              // Wrapped so a wide table scrolls inside the page rather than
              // making the whole page scroll sideways.
              <div className="method-table" key={key}>
                <table>
                  <thead>
                    <tr>
                      {block.head.map((cell, n) => (
                        <th key={`${key}-h${n}`}>{inline(cell, `${key}-h${n}`)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={`${key}-r${r}`}>
                        {row.map((cell, c) => (
                          <td key={`${key}-r${r}c${c}`}>{inline(cell, `${key}-r${r}c${c}`)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return <p key={key}>{inline(block.text, key)}</p>;
        }
      })}
    </article>
  );
}
