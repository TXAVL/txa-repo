# Your own repository bot: the `txa-repo` GitHub App

By default the bot comments as `github-actions[bot]`. Create a **GitHub App** and the comments, labels and
statuses appear under their own name (`txa-repo[bot]`) with their own logo.
It is optional: until the App is installed the workflow uses the default token and everything keeps working.

## 1. Create the App

1. Open <https://github.com/settings/apps/new> (signed in as the `TXAVL` account).
2. Fill in:
   - **GitHub App name**: `txa-repo` (names are global; if it is taken use `txa-repo-bot`).
   - **Homepage URL**: `https://github.com/TXAVL/txa-repo`
   - **Webhook**: untick **Active** (this App does not need to receive webhooks).
3. **Repository permissions** (leave everything else as *No access*):

   | Permission | Level | Used for |
   |---|---|---|
   | Actions | Read and write | re-running the checks after the agreement is accepted |
   | Checks | Read and write | the 16 numbered checks in the merge box |
   | Commit statuses | Read and write | `txa/verified`, `txa/agreement` |
   | Contents | Read and write | turning on auto-merge |
   | Issues | Read and write | comments, labels, deleting the `@txa-repo agree` comment |
   | Pull requests | Read and write | reading PRs, merging them |
   | Metadata | Read-only | (granted automatically) |

4. **Where can this GitHub App be installed?** → *Only on this account*. Press **Create GitHub App**.
5. On the new App page note the **App ID**; scroll to **Private keys** → **Generate a private key**
   (a `.pem` file is downloaded). Under **Display information** upload the logo.

## 2. Install the App on the repository

App page → **Install App** → `TXAVL` → **Only select repositories** → choose `txa-repo` → Install.

## 3. Put the key into secrets (without exposing it)

```powershell
.\scripts\setup-app.ps1 -AppId 1234567 -KeyFile C:\Users\admin\Downloads\txa-repo.2026-10-27.private-key.pem
```

The script only runs `gh secret set TXA_APP_ID` and `gh secret set TXA_APP_PRIVATE_KEY` (it reads the key from the
file and never prints it). Delete the `.pem` file from your PC afterwards.

## 4. Check it

Open a new PR: the bot's comment must show the name `txa-repo` with a **bot** label. If it still shows `github-actions`,
check that both secrets exist (`gh secret list`) and that the App is installed on `txa-repo`.

Bonus: because the App merges PRs with its own permissions, that merge counts as a real push and triggers
`TXA Publish API` by itself.
