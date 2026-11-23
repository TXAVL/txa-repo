# Integrating TXA into your application

An app released through the TXA repository can detect that it was installed with `txapm` and, when a new
version exists, call `txapm` to update instead of using its own updater.

Tiếng Việt: [app-integration.md](app-integration.md)

## Detecting whether you were installed by TXA

```powershell
txapm which TXAVL.TDrop --json
```

The command always exits with code 0 and prints one line of JSON:

```json
{"managed": true, "id": "TXAVL.TDrop", "version": "0.3.2", "newest": "0.3.3", "update_available": true, "pinned": false, "dir": null, "source": "txa"}
```

| Field | Meaning |
|---|---|
| `managed` | `true` if the package is in `txapm`'s install list |
| `version` / `newest` | installed version / newest version in the source the package was installed from |
| `update_available` | whether a newer version exists |
| `pinned` | the user pinned the version (`txapm pin add`) |
| `dir` | install folder (portable packages only) |
| `source` | the source the package was installed from |

For a package not installed by TXA, `managed` is `false` and the other fields are `null` / `false`.

## Updating

When `update_available` is `true` and `pinned` is `false`, the app runs the command below and exits so the
installer can overwrite its files:

```powershell
txapm upgrade TXAVL.TDrop
```

## Choosing a version

`--version` accepts a full number or a prefix and takes the newest match:

```powershell
txapm install dotnet-sdk-8 --version 8        # newest 8.x.y in the repository
txapm install vs2022 --version 17.10          # newest 17.10.x
txapm install vs2022 --version 17.10.5        # exactly this one
```

Without `--version` the newest version is always used.

## Desktop shortcut

A package can declare `shortcut` (`name`, `exe`) in its `build` card. `txapm` does not create the shortcut; it uses `exe` to check that the program exists after the install and installs once more if an old uninstaller removed it. See [manifest-schema.en.md](manifest-schema.en.md).
