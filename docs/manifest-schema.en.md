# TXA Manifest Specification

The technical reference and the rules for every field of the three manifest cards of a TXA software package (TXA v1).

---

## Overview

Each software release in the TXA repository is described by a folder holding **3 kinds of YAML manifest cards**:

```
manifests/
└── <first_letter>/
    └── <Namespace>/
        └── <AppName>/
            └── <Version_X.Y.Z>/
                ├── core.txa.yaml             # Identity and core metadata card
                ├── build.txa.yaml            # Installer, CPU architecture and switches card
                ├── about.en-US.txa.yaml      # Description card (English)
                └── about.vi-VN.txa.yaml      # Description card (Vietnamese - optional)
```

---

## 1. The core card: `core.txa.yaml`

Defines the package's unique identity across the whole system.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/TXAVL/txa-repo/main/tools/src/txa/schemas/core.schema.json
txa: 1
kind: core
package:
  id: TXAVL.Everything
  version: 1.4.1
  channel: stable
  alias: evt
  aliases:
    - everything
locale:
  default: en-US
tags:
  - search
  - file-search
  - filesystem
```

### Fields:
| Field | Required | Type | Description and limits |
| :--- | :---: | :--- | :--- |
| `txa` | Yes | `int` | Version of the TXA schema specification (currently `1`). |
| `kind` | Yes | `string` | Must be `core`. |
| `package.id` | Yes | `string` | Package identifier: `<Namespace>.<AppName>` (PascalCase). Example: `TXAVL.Everything`. |
| `package.version`| Yes | `string` | Software version: strict SemVer `X.Y.Z` (for example `1.4.1`). |
| `package.channel`| No | `string` | Release channel: `stable` (default) or `beta`. |
| `package.alias` | No | `string` | A short command name so users can type `txapm install <alias>` (lowercase, digits, hyphens, 2-32 characters). |
| `locale.default` | Yes | `string` | The package's main language code (default: `en-US` or `vi-VN`). |
| `tags` | No | `array` | Search keywords (at most 16 tags, lowercase, no special characters). |

---

## 2. The installer and platform card: `build.txa.yaml`

Sets how the installer runs for each CPU architecture on Windows.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/TXAVL/txa-repo/main/tools/src/txa/schemas/build.schema.json
txa: 1
kind: build
ref: TXAVL.Everything@1.4.1
platform:
  os: windows
  min_build: 10.0.17763
scope: machine
targets:
  - arch: x64
    engine: msi
    source:
      url: https://www.voidtools.com/Everything-1.4.1.1032.x64.msi
      sha256: 4E7A80885AAB8566B750C56A2A2B3E7C3C1F4920BCC53777E07F5EEB9E1F7485
      size: 2351104
    switches:
      silent: /qn /norestart
      progress: /qb! /norestart
  - arch: arm64
    engine: exe
    source:
      url: https://www.voidtools.com/Everything-1.4.1.1032.ARM64.zip
      sha256: 23DCA1A64574BF30C9988BBAF5F1D201A0EC7EE9A15E12270AE92A52183CCCC8
      size: 1933207
    switches:
      silent: /s
      progress: /s
```

### Fields:
| Field | Required | Type | Description and limits |
| :--- | :---: | :--- | :--- |
| `ref` | Yes | `string` | Exact reference: `<package.id>@<package.version>`. |
| `platform.min_build`| Yes | `string` | Minimum Windows build, for example `10.0.17763` (Windows 10 1809+). |
| `scope` | Yes | `string` | Install scope: `machine` (whole PC, needs admin rights) or `user` (the current user). |
| `targets` | Yes | `array` | Installers per CPU. **Each architecture (`x64`, `x86`, `arm64`) may be declared at most once**. |
| `targets[].arch` | Yes | `string` | CPU architecture: `x64`, `x86`, `arm64`, `arm`, or `neutral`. |
| `targets[].engine` | Yes | `string` | Installer technology: `inno`, `nsis`, `msi`, `wix`, `exe`, or `portable`. |
| `targets[].source.url` | Yes | `string` | HTTPS link to download the installer directly from the official site. |
| `targets[].source.sha256` | Yes | `string` | SHA-256 hash (64 uppercase hex characters). |
| `targets[].switches.silent` | By type | `string` | Silent install switches (required for `exe`, for example `/S`, `/VERYSILENT`). |

---

## 3. The description card: `about.<lang>.txa.yaml`

Holds the display information, license and description shown to users. Each language is independent (`about.en-US.txa.yaml`, `about.vi-VN.txa.yaml`, and so on).

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/TXAVL/txa-repo/main/tools/src/txa/schemas/about.schema.json
txa: 1
kind: about
ref: TXAVL.Everything@1.4.1
lang: en-US
name: Everything
publisher: voidtools
author: David Carpenter
summary: Everything is a search engine that locates files and folders by filename instantly for Windows.
homepage: https://www.voidtools.com/
license:
  name: MIT
  url: https://www.voidtools.com/License.txt
```

### Fields:
| Field | Required | Type | Description and limits |
| :--- | :---: | :--- | :--- |
| `lang` | Yes | `string` | BCP 47 language code (for example `en-US`, `vi-VN`). Must match the file name. |
| `name` | Yes | `string` | The full display name of the software (for example `Everything`). |
| `publisher` | Yes | `string` | The publisher or the organization that develops it. |
| `summary` | Yes | `string` | A short description (10 to 160 characters) that must not simply repeat the software name. |
| `description` | No | `string` | A detailed description of what the software does (at most 5000 characters). |
| `homepage` | No | `string` | The software's official homepage (must start with `https://`). |
| `license.name` | Yes | `string` | A standard SPDX license id (for example `MIT`, `GPL-3.0-or-later`, `Apache-2.0`, `Proprietary`, `Freeware`). |
| `license.url` | By type | `string` | Link to the license terms (required for `Proprietary` or non-SPDX licenses). |
