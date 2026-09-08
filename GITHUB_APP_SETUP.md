# GitHub App setup — one-time, manual

This repo's workflows need to read and write files in the private `investing-partner-data`
repo. `GITHUB_TOKEN` (the default, automatic token every workflow gets) can only touch the repo
the workflow runs in — reaching a second repo needs its own credential. This repo uses a GitHub
App installation token, minted fresh on every run via
[`actions/create-github-app-token`](https://github.com/actions/create-github-app-token), rather
than a personal access token, because the installation token expires in an hour on its own —
there's nothing to remember to rotate except the App's private key itself, occasionally, on your
own schedule.

This part can't be scripted end to end — creating a GitHub App and downloading its private key
has to happen in your own browser session. Everything below is a one-time setup.

## 1. Create the App

1. Go to **Settings → Developer settings → GitHub Apps → New GitHub App**
   (or directly: `https://github.com/settings/apps/new`).
2. Fill in:
   - **GitHub App name**: something unique, e.g. `investing-partner-data-bridge`.
   - **Homepage URL**: the `Investing-Partner` repo URL (anything valid works — not used
     functionally).
   - **Webhook**: uncheck "Active" — this App doesn't need webhooks.
   - **Repository permissions → Contents**: **Read and write**.
   - Leave every other permission at "No access".
   - **Where can this GitHub App be installed?**: "Only on this account" is fine.
3. Click **Create GitHub App**.
4. On the App's settings page, note the **Client ID** near the top (starts with `Iv23...`) — this
   is what the workflows call `DATA_APP_CLIENT_ID`. (The numeric "App ID" also works if you'd
   rather use that — `create-github-app-token`'s `app-id` input still accepts it, it's just the
   older/deprecated name for the same idea.)
5. Scroll to **Private keys → Generate a private key**. This downloads a `.pem` file once —
   GitHub does not store a copy you can re-download later. Keep it somewhere safe until step 3
   below.

## 2. Install the App on the private data repo

1. On the same App settings page, go to **Install App** (left sidebar).
2. Install it on your account, and when asked which repositories, choose
   **Only select repositories** → `investing-partner-data`. Do **not** install it on the public
   `Investing-Partner` repo — it doesn't need to touch that one.

## 3. Add secrets to the public repo

In `Investing-Partner` → **Settings → Secrets and variables → Actions → New repository secret**,
add:

| Secret name | Value |
|---|---|
| `DATA_APP_CLIENT_ID` | The Client ID from step 1.4 |
| `DATA_APP_PRIVATE_KEY` | The full contents of the `.pem` file from step 1.5, pasted as-is (including the `-----BEGIN/END-----` lines) |

These are the only two new secrets. The following existed on the old single-repo setup and need
to be re-added here too — GitHub does not let you copy secret values between repos, even as the
owner, so they have to be re-entered from your own records (a secret manager, your Gmail app
password settings, etc.), not looked up:

| Secret name | Where it comes from |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` on your Pro plan |
| `GMAIL_USERNAME` | Your sending Gmail address |
| `GMAIL_APP_PASSWORD` | A Gmail [App Password](https://myaccount.google.com/apppasswords), not your normal password |
| `MAIL_TO` | Where reports get emailed |

Also install the **Claude Code** GitHub App (`https://github.com/apps/claude`) on
`Investing-Partner` if it isn't already — `claude-code-action@v1` needs it for OIDC, separately
from the App created above.

## 4. Verify

Run any workflow manually (Actions tab → pick one → **Run workflow**) and check the "checkout
private data repo" step succeeds. If it fails with an auth error, double check the App is
installed on `investing-partner-data` specifically (step 2) and that `DATA_APP_PRIVATE_KEY`
was pasted with no extra leading/trailing whitespace stripped or added.
