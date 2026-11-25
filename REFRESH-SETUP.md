# Keeping The Amelia Current fresh (every 30 minutes)

GitHub's own timer runs this site's rebuilds 6-12 hours late. A direct "run
now" request isn't delayed, so a tiny free script on Cloudflare (the
`amelia-refresh` Worker, code in `cloudflare-worker/amelia-refresh.js`) sends one
every 30 minutes. GitHub's hourly timer stays on as a backup, so the site never
goes completely stale even if this stops working.

You do this once, in three parts (~10 minutes).

---

## Part 1: Create the Worker on Cloudflare (code is on your clipboard)

1. Go to **dash.cloudflare.com** and sign in.
2. In the left sidebar choose **Compute (Workers) → Workers & Pages**
   (the label varies slightly).
3. Click **Create**, then **Create Worker** (or "Start with Hello World").
4. Name it `amelia-refresh` and click **Deploy**.
5. Click **Edit code**. Select everything in the editor (**Cmd + A**), then
   paste (**Cmd + V**) to replace it with the script. If the clipboard has
   changed, the script is in the project folder at
   `cloudflare-worker/amelia-refresh.js`.
6. Click **Deploy** (top right).

## Part 2: Make a GitHub key that can only start rebuilds

1. Go to **github.com/settings/personal-access-tokens/new**.
2. **Token name:** `amelia-refresh`.
3. **Expiration:** 1 year. (Put a reminder in your calendar; see below.)
4. **Repository access:** choose **Only select repositories**, then pick
   **amelia-island-scene**.
5. **Permissions → Repository permissions:** find **Actions** and set it to
   **Read and write**. Leave every other permission alone.
6. Click **Generate token** and **copy the token** (shown only once).

## Part 3: Give the key to the Worker, and set the schedule

1. Back on Cloudflare, open your `amelia-refresh` Worker.
2. Go to **Settings → Variables and Secrets → Add**.
   - **Type:** Secret
   - **Variable name:** `GITHUB_TOKEN` (exactly, capitals)
   - **Value:** paste the token from Part 2
   - Click **Deploy** / **Save**.
3. Still under **Settings**, open **Trigger Events** (or **Triggers**) →
   **Add → Cron Triggers**, enter `*/30 * * * *` and save.

That's it. Within 30 minutes a new run appears on GitHub's Actions tab labelled
**workflow_dispatch**, and the site updates itself.

---

## Good to know

- **The key can do very little.** It can start (or cancel) rebuilds of this one
  repository. It can't read or change the code, other repositories, or your
  account.
- **When the key expires** (in a year), GitHub emails you. Make a new one the same
  way and replace the `GITHUB_TOKEN` secret. Until then the hourly backup timer
  still runs, just late.
- **To pause the 30-minute refresh**, delete the cron trigger on the Worker.
- **Cost:** free. Cloudflare's free plan covers this many times over.
