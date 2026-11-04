// Reads the txa.v1 API that `txaci build-api` writes to site/api/txa/v1/ (the workflow builds this page
// right after it). Without a local copy (e.g. `npm run dev` on a fresh clone) it falls back to the
// published API so the page always has real data.
import { readFile } from "node:fs/promises";
import path from "node:path";

const LIVE = "https://txavl.github.io/txa-repo/api/txa/v1";

export interface Pkg {
  id: string;
  alias: string | null;
  aliases: string[];
  latest: string;
  versions: string[];
  name: string;
  publisher: string;
  summary: string;
  summaries: Record<string, string>;
  tags: string[];
  arches: string[];
}
export interface Pending {
  id: string;
  version: string;
  name?: string;
  url?: string;
  pr?: number;
}
interface Doc<T> {
  generated: string;
  count: number;
  packages: T[];
}

async function load<T>(name: string): Promise<Doc<T>> {
  const dir = process.env.TXA_API_DIR ?? path.resolve(process.cwd(), "../site/api/txa/v1");
  try {
    return JSON.parse(await readFile(path.join(dir, name), "utf-8"));
  } catch {
    const res = await fetch(`${LIVE}/${name}`);
    if (!res.ok) throw new Error(`cannot read ${name}: ${res.status}`);
    return (await res.json()) as Doc<T>;
  }
}

export async function loadIndex() {
  return load<Pkg>("index.json");
}
export async function loadPending() {
  try {
    return await load<Pending>("pending.json");
  } catch {
    return { generated: "", count: 0, packages: [] as Pending[] };
  }
}

// --- categories -------------------------------------------------------------------------------
// Tags in the manifests are free text, so categories come from a short list of rules over the
// tags, with explicit entries for the packages that have no useful tags. New packages need no edit:
// anything unmatched lands in "tools".
export const CATEGORIES = [
  { id: "dev", vi: "Lập trình", en: "Development" },
  { id: "browser", vi: "Trình duyệt", en: "Browsers" },
  { id: "media", vi: "Âm thanh, video, ảnh", en: "Audio, video, images" },
  { id: "games", vi: "Game", en: "Games" },
  { id: "social", vi: "Liên lạc và AI", en: "Chat and AI" },
  { id: "system", vi: "Hệ thống và mạng", en: "System and network" },
  { id: "tools", vi: "Tiện ích", en: "Utilities" },
] as const;
export type CategoryId = (typeof CATEGORIES)[number]["id"];

const BY_NAME: Record<string, CategoryId> = {
  canhcutteamlauncher: "games",
  garena: "games",
  ohmyposh: "dev",
  telegramdesktop: "social",
  txawinsetup: "system",
  winscp: "system",
  cloudflared: "system",
  physx: "games",
  vigembus: "games",
  obsstudio: "media",
  everything: "tools",
  powertoys: "tools",
  obsidian: "tools",
  onedrive: "tools",
};
const RULES: [CategoryId, RegExp][] = [
  ["browser", /^(browser)$/],
  ["games", /^(game|games|gaming|game-launcher|gamestream)$/],
  ["social", /^(chat|chatbot|ai|llm|voice-chat)$/],
  ["media", /^(audio|video|media|image|photo|recording|music-streaming|streaming|screenshot)$/],
  ["dev", /^(developer|develop|development|programming|runtime|vcs|git|java|dotnet|sdk|rust|rustlang|python|javascript|nodejs|editor|api|gcc|unity|unity3d)$/],
  ["system", /^(virtualization|vm|ssh|installer|deployment|reverse-proxy|shell|emulator|driver)$/],
];

export function categorize(p: Pkg): CategoryId {
  const name = p.id.split(".").pop()!.toLowerCase();
  if (BY_NAME[name]) return BY_NAME[name];
  const tags = new Set(p.tags.map((t) => t.toLowerCase()));
  for (const [cat, re] of RULES) for (const t of tags) if (re.test(t)) return cat;
  return "tools";
}

/** Stable pale hue per package for the monogram tile. */
export function hueOf(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}
