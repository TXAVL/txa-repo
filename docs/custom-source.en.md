# Custom sources and hosting your own repository

Besides the official `txa` source you can add your own: internal company software, your team's own builds…
A source only has to serve the same `txa.v1` REST API (two static JSON files), or simply be a folder containing `manifests/`.

Tiếng Việt: [custom-source.md](custom-source.md)

## Managing sources with `txapm source`

| Goal | Command |
|---|---|
| List sources | `txapm source` |
| Add an HTTPS source | `txapm source add company https://pkgs.company.com/api/txa/v1` |
| Add a folder source (network drive, personal machine) | `txapm source add internal \\server\share\txa` |
| Private source that needs a token | `txapm source add company <url> --token-env COMPANY_TOKEN` |
| Allow installers hosted on a LAN server | `txapm source add company <url> --allow-lan` |
| Disable / enable a source | `txapm source disable txa` · `txapm source enable txa` |
| Remove a source | `txapm source remove company` |
| Refresh / back up the configuration | `txapm source update` · `txapm source export` |
| Back to default (only `txa`) | `txapm source reset` |
| Search / install from one source only | `txapm search app -s company` · `txapm install App -s company` |

- Sources are asked in order: `txa` first, then the ones you added. If the same Id exists in several sources,
  TXA stops and asks you to choose with `-s <source>` so nothing is installed by mistake.
- A package remembers which source it came from, so `txapm upgrade` always takes the new version from that source.
- Tokens are never written to the config file: TXA stores only the **environment variable name** and sends the
  token only to that source's own server.
- A source must use HTTPS (except `http://localhost` for testing).

## Hosting a repository

1. Create a folder with `manifests/<letter>/<Namespace>/<AppName>/<X.Y.Z>/` (write the cards quickly with
   `txacreate new <url> --dry-run --out <folder>`; the card layout is in
   [manifest-schema.en.md](manifest-schema.en.md)).
2. Use it as a folder right away: `txapm source add internal D:\txa-repo`. Or generate the static REST API:
   ```powershell
   txaci build-api --root D:\txa-repo --out D:\txa-repo-site
   ```
3. Put `D:\txa-repo-site` on any HTTPS server (IIS, nginx, GitHub Pages, S3…), then
   `txapm source add company https://<server>/api/txa/v1`.

## Including the 16-step validation bot

Fork `TXAVL/txa-repo`, change the namespace in `policy.txa.yaml`, then run:

```powershell
scripts\setup-github.ps1 -Owner <organization>
```

The script configures labels, `CODEOWNERS` and branch protection. For a bot with its own name instead of
`github-actions`, see [github-app.en.md](github-app.en.md).
