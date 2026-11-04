# Using `txacli`, `txapm` and `txacreate` (end-user guide)

This guide shows end users how to **search, install and manage software** with **`txapm`**, **import software automatically from WinGet or from their own PC** with **`txacli`**, and **create their own software repository or contribute to the main one** with **`txacreate`**.

---

## The three command-line tools at a glance

Once TXA is installed you have these global commands in any PowerShell or Command Prompt window:

| Tool | What it is for | Quick examples |
|---|---|---|
| **`txapm`** | Search, silent install, update, uninstall, health check and cache cleanup | `txapm install chrome`<br>`txapm upgrade --all`<br>`txapm doctor` |
| **`txacli`** | Search WinGet, scan the software installed on your PC to build TXA packages automatically, create a private repository and send PRs | `txacli -s PowerToys`<br>`txacli -i -y`<br>`txacli submit C:\my-txa-repo` |
| **`txacreate`** | Contribute software to the TXA repository through a Pull Request (from a download link, a software name or an existing folder) | `txacreate new "GitHub CLI"`<br>`txacreate submit C:\my-txa-repo` |

---

## 1. Everyday software management with `txapm`

### Search and install software
You can install by the **full ID** (`TXAVL.Chrome`) or by a **short name / alias** (`chrome`, `vscode`, `7zip`, `git`...):

```powershell
# Search the TXA repository
txapm search chrome

# Silent install (downloads, verifies SHA-256 and installs without clicking Next)
txapm install chrome
txapm install vscode

# Install but show the installer's progress bar
txapm install obs --progress
```

### Install software that is not in the TXA repository yet (straight through the WinGet bridge)
If a program has not reached the TXA repository yet you can still use `txapm wg` to take it from WinGet, verify its SHA-256 automatically and install it through `txapm`:

```powershell
# Search WinGet from inside txapm
txapm wg search "PowerToys"

# Install a WinGet package directly through txapm
txapm wg install Microsoft.PowerToys
```

### Check what is on your PC and update it
```powershell
# List the packages installed through txapm
txapm list

# List ALL software installed on Windows (marks which ones TXA already has)
txapm list --all

# Check and upgrade everything to the latest version
txapm upgrade --all
```

### Utility commands in `txapm`

| Command | Alias | What it does for you |
|---|---|---|
| `txapm doctor` | `txapm check`, `status` | A full check: Windows version, connection state of every source, the WinGet CLI, your GitHub account and the cache size |
| `txapm clean` | `txapm cache`, `clear` | Deletes temporary installer downloads in `%TEMP%\txa` to free disk space (`txapm clean --all` also removes old logs) |
| `txapm log` | `txapm logs` | Lists the most recent install logs; run `txapm log <app-name>` to read one when you need to track down an error |
| `txapm which <app>` | `txapm where <app>` | Shows where it is installed, the version, CPU architecture, portable folder, the `PATH` entry and the log file path |

---

## 2. Take software from your PC or WinGet automatically with `txacli`

No need to open a browser to hunt for a `.exe`/`.msi` link or compute a SHA-256 by hand: just use **`txacli`**.

### Step 1: Search WinGet
Search by any keyword or by the exact ID:

```powershell
txacli -s "PowerToys"
txacli -s "Microsoft.PowerToys"
# Or:
txacli search "Unity Hub"
```

The result is a clear table with `Id`, `Version` and `Name`:
```text
Found 1 package(s):
  Id                                         Version          Name
  ------------------------------------------------------------------------------
  Microsoft.PowerToys                        0.101.2362.0     PowerToys

To import a package, run:
  txacli Microsoft.PowerToys
```

### Step 2: Create a standard TXA package from any software name
Pass the display name (as shown by `txapm list --all`) or a WinGet ID:

```powershell
# Create one or several packages at once in the manifests/ folder
txacli Microsoft.PowerToys
txacli "GitHub CLI" "GitHub Desktop" "Steam" "Unity Hub"
```

### Step 3: Scan everything installed on your PC (`scan` / `-i`)
Want to know which programs on your PC are not in the TXA repository yet?

```powershell
# Just list the programs on your PC that can be added to TXA
txacli scan

# Scan and pick programs by number (for example: 1,3,5 or all)
txacli -i

# Scan and add EVERYTHING without asking again
txacli -i -y
```

---

## 3. Build your own software repository (`myrepo`) and contribute to the main one

### Create a private repository on your PC or intranet
You can use `txacli` to gather the programs you like into your own folder (for example `C:\my-txa-repo`), generate the REST API (`C:\my-txa-api`) and attach it to `txapm` with **a single command**:

```powershell
# Option 1: create the manifests + build the API + attach it to txapm source in one command
txacli Postman.Postman -o C:\my-txa-repo --build-api --api-out C:\my-txa-api --add-source myrepo
```

Or step by step:
```powershell
# 1. Import the package into your own repository folder
txacli Postman.Postman -o C:\my-txa-repo --build-api --api-out C:\my-txa-api

# 2. Add the repository to txapm
txapm source add myrepo C:\my-txa-repo

# 3. Search or install from your own repository
txapm search postman -s myrepo
txapm install postman -s myrepo
```

> **A note on the `-s <source-name>` flag:**
> When you type `txapm search chrome -s myrepo`, `txapm` **searches only inside `myrepo`**. If `myrepo` only holds `Postman`, the command says it found nothing in `myrepo` and hints that `TXAVL.Chrome` lives in the main `txa` source. To search every source at once, drop `-s myrepo`:
> ```powershell
> txapm search chrome
> ```

### Send a package from your repository to the main TXA repository (`submit`)
After creating a package in `C:\my-txa-repo` (or `C:\my-txa-api`) you can open a Pull Request to the main repository at any time. The `submit` command finds every package inside the folder you pass:

```powershell
# Pass the repository root or the API folder directly, both work!
txacli submit C:\my-txa-repo
# Or:
txacreate submit C:\my-txa-repo
txacreate submit C:\my-txa-api

# To only check validity (without opening a Pull Request on GitHub):
txacreate submit C:\my-txa-repo --dry-run
```

---

## 4. `txacli` reference

| Command / flag | Meaning | Example |
|---|---|---|
| `txacli <name/ID ...>` | Convert one or more WinGet packages into TXA manifests | `txacli Postman.Postman "GitHub CLI"` |
| `txacli -s <keyword>` | Search software in the WinGet repository | `txacli -s PowerToys` |
| `txacli scan` | List software installed on your PC that TXA does not have | `txacli scan` |
| `txacli -i [-y]` | Scan the PC and import software into the repository automatically | `txacli -i -y` |
| `-o <folder>` | Choose the folder that receives the output `manifests/` | `txacli Git.Git -o C:\my-txa-repo` |
| `--build-api` | Generate the static `txa.v1` REST API after the import | `txacli Git.Git --build-api` |
| `--api-out <folder>` | Folder for the static REST API (default: `dist/api`) | `--api-out C:\my-txa-api` |
| `--add-source <name>` | Register the repository folder in `txapm source` | `--add-source myrepo` |
| `--submit` | Open a Pull Request on GitHub right after the import | `txacli Postman.Postman --submit` |
| `--txacreate` | Run the full `txacreate new` flow (downloads the real file and checks the PE) | `txacli "GitHub CLI" --txacreate` |
| `--dry-run` | A trial run: validates but writes no files and opens no PR | `txacli Postman.Postman --dry-run` |
| `txacli submit <folder>` | Open a Pull Request for a release folder, a repository folder or an API folder | `txacli submit C:\my-txa-repo` |
| `txacli validate <folder>` | Run the 14 vetting checks on any folder | `txacli validate C:\my-txa-repo --offline` |
| `txacli build-api` | Generate the `txa.v1` REST API from a repository folder | `txacli build-api -r C:\my-txa-repo -o C:\my-txa-api` |
