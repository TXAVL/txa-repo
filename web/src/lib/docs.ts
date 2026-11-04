// The markdown files in the repository's docs/ folder, rendered at build time so the site and the
// repository never drift apart: edit docs/*.md, the site follows on the next publish.
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { Marked } from "marked";

const dir = path.resolve(process.cwd(), "../docs");

const SHORT: Record<string, [string, string]> = {
  "manifest-schema": ["Đặc tả manifest", "Manifest reference"],
  "winget-import": ["Nhập từ WinGet, kho riêng", "WinGet import, own repo"],
  "github-app": ["Bot riêng cho kho", "Your own repo bot"],
};
const ORDER = ["manifest-schema", "winget-import", "github-app"];

export const slug = (t: string) =>
  t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export interface DocPage {
  slug: string;
  title: { vi: string; en: string };
  short: [string, string];
  html: { vi: string; en: string | null };
  source: { vi: string; en: string | null };
}

// docs/<name>.md is the Vietnamese original, docs/<name>.en.md its English translation (optional).
function render(src: string) {
  const used = new Set<string>();
  const md = new Marked({ gfm: true });
  md.use({
    renderer: {
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        const plain = text.replace(/<[^>]+>/g, "");
        let id = slug(plain) || "s";
        while (used.has(id)) id += "-2";
        used.add(id);
        return `<h${depth} id="${id}">${text}</h${depth}>
`;
      },
      table(token) {
        const head = token.header.map((c) => `<th>${this.parser.parseInline(c.tokens)}</th>`).join("");
        const body = token.rows.map((r) => `<tr>${r.map((c) => `<td>${this.parser.parseInline(c.tokens)}</td>`).join("")}</tr>`).join("");
        return `<div class="md-table"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
`;
      },
      link({ href, title, tokens }) {
        const inner = this.parser.parseInline(tokens);
        const t = title ? ` title="${esc(title)}"` : "";
        // links between the docs files become links between the site's pages
        const doc = href.match(/^(?:\.\/|\.\.\/docs\/|docs\/)?([a-z0-9-]+?)(?:\.en)?\.md(#.*)?$/i);
        if (doc) return `<a href="../${doc[1]}/${doc[2] ?? ""}"${t}>${inner}</a>`;
        return `<a href="${esc(href)}"${t}${/^https?:/.test(href) ? ' rel="noopener"' : ""}>${inner}</a>`;
      },
    },
  });
  const title = (src.match(/^#\s+(.+)$/m)?.[1] ?? "").replace(/`/g, "");
  const body = src.replace(/^#\s+.+\r?\n/, ""); // the first h1 becomes the page title
  return { title, html: md.parse(body) as string };
}

export async function loadDocs(): Promise<DocPage[]> {
  const files = await readdir(dir);
  const names = files.filter((f) => f.endsWith(".md") && !f.endsWith(".en.md")).map((f) => f.replace(/\.md$/, ""));
  names.sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b));
  const gh = "https://github.com/TXAVL/txa-repo/blob/main/docs";
  const pages: DocPage[] = [];
  for (const name of names) {
    const vi = render(await readFile(path.join(dir, `${name}.md`), "utf-8"));
    const hasEn = files.includes(`${name}.en.md`);
    const en = hasEn ? render(await readFile(path.join(dir, `${name}.en.md`), "utf-8")) : null;
    pages.push({
      slug: name,
      title: { vi: vi.title || name, en: en?.title || vi.title || name },
      short: SHORT[name] ?? [vi.title || name, en?.title || vi.title || name],
      html: { vi: vi.html, en: en ? en.html : null },
      source: { vi: `${gh}/${name}.md`, en: hasEn ? `${gh}/${name}.en.md` : null },
    });
  }
  return pages;
}
