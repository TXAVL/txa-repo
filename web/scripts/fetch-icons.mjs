// Fetches an icon for every package in the index and writes web/public/icons/<Name>.<ext>
// plus web/src/lib/icons.json ({ "<Name>": "<file>" }). Packages that already have a file are skipped, so
// icons are fetched once and the result can be committed; a package with no icon keeps its monogram.
//
// Order of sources (first hit wins):
//   1. Simple Icons (https://simpleicons.org, CC0): the brand's own SVG, coloured.
//   2. The favicon of the package's homepage (Google's favicon service, 128px PNG), the same icon the
//      publisher shows in a browser tab. Rejected when it is the generic globe the service returns for
//      sites it has no icon for.
//
// Brand names, logos and icons belong to their owners; they are shown only to identify the software.
import { mkdir, readFile, writeFile, readdir } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

const root = path.resolve(import.meta.dirname, "..");
const apiDir = process.env.TXA_API_DIR ?? path.resolve(root, "../site/api/txa/v1");
const LIVE = "https://txavl.github.io/txa-repo/api/txa/v1";
const outDir = path.join(root, "public/icons");
const mapFile = path.join(root, "src/lib/icons.json");

// Simple Icons slugs where the package name is not the slug. Several candidates are tried in order.
const SLUGS = {
  Chrome: ["googlechrome"], Firefox: ["firefoxbrowser", "firefox"], Edge: ["microsoftedge"],
  Cloudflared: ["cloudflare"], GitHubCLI: ["github"], GitHubDesktop: ["github"],
  MicrosoftNETSDK: ["dotnet"], MicrosoftNETWindowsDesktopRuntime: ["dotnet"],
  MicrosoftBuildOfOpenJDKWithHotspot17: ["openjdk"], UpdateWatcherForAdoptOpenJDK: ["openjdk"],
  NodeJS: ["nodedotjs"], NVM: ["nodedotjs"], OneDrive: ["microsoftonedrive"], PhysX: ["nvidia"],
  Rustup: ["rust"], SevenZip: ["7zip"], TelegramDesktop: ["telegram"], UnityHub: ["unity"],
  VisualStudioCode: ["visualstudiocode"], VLC: ["vlcmediaplayer", "vlc"], OBSStudio: ["obsstudio"],
  RockstarGamesLauncher: ["rockstargames"], UbisoftConnect: ["ubisoft"], NotepadPlusPlus: ["notepadplusplus"],
  Postman: ["postman"], Obsidian: ["obsidian"], Claude: ["claude"], GIMP: ["gimp"], FFmpeg: ["ffmpeg"],
  VisualStudioCommunity2026: ["visualstudio"], QEMUGuestAgent: ["qemu"],
  DockerDesktop: ["docker"], JetBrainsToolbox: ["jetbrains"], QBittorrent: ["qbittorrent"], KeePassXC: ["keepassxc"],
};

async function getJson(rel) {
  try { return JSON.parse(await readFile(path.join(apiDir, rel), "utf-8")); }
  catch {
    const r = await fetch(`${LIVE}/${rel}`);
    if (!r.ok) throw new Error(`${rel}: ${r.status}`);
    return r.json();
  }
}
const get = async (url) => {
  try { const r = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(15000) }); return r.ok ? r : null; }
  catch { return null; }
};

const index = await getJson("index.json");
await mkdir(outDir, { recursive: true });
const have = new Map((await readdir(outDir)).map((f) => [f.replace(/\.[^.]+$/, ""), f]));

// The generic globe Google returns for a domain it has no icon for.
const globe = await get("https://www.google.com/s2/favicons?domain=txa-no-such-site.invalid&sz=128");
const globeHash = globe ? createHash("sha1").update(Buffer.from(await globe.arrayBuffer())).digest("hex") : "";

const map = {};
let fetched = 0, missing = [];
for (const p of index.packages) {
  const name = p.id.split(".").pop();
  if (have.has(name)) { map[name] = have.get(name); continue; }

  // 1. Simple Icons
  let file = null;
  for (const slug of SLUGS[name] ?? [name.toLowerCase()]) {
    const r = await get(`https://cdn.simpleicons.org/${slug}`);
    if (r && (r.headers.get("content-type") || "").includes("svg")) {
      file = `${name}.svg`;
      await writeFile(path.join(outDir, file), Buffer.from(await r.arrayBuffer()));
      break;
    }
  }
  // 2. Favicon of the homepage
  if (!file) {
    let home = "";
    try {
      const doc = await getJson(`packages/${p.id}.json`);
      const about = Object.values(doc.versions[doc.latest].about)[0];
      home = about.homepage || "";
    } catch { /* no document */ }
    if (home) {
      const host = new URL(home).hostname;
      const r = await get(`https://www.google.com/s2/favicons?domain=${host}&sz=128`);
      if (r) {
        const buf = Buffer.from(await r.arrayBuffer());
        if (createHash("sha1").update(buf).digest("hex") !== globeHash && buf.length > 300) {
          file = `${name}.png`;
          await writeFile(path.join(outDir, file), buf);
        }
      }
    }
  }
  if (file) { map[name] = file; fetched++; } else missing.push(name);
}

await writeFile(mapFile, JSON.stringify(map, null, 2) + "\n");
console.log(`icons: ${Object.keys(map).length} of ${index.packages.length} (new: ${fetched})`);
if (missing.length) console.log(`no icon, monogram used: ${missing.join(", ")}`);
