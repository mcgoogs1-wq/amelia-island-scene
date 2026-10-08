# Putting The Amelia Current in the cloud (GitHub Pages)

This makes the site rebuild and re-publish **every hour on GitHub's servers**,
so your shared link stays current even when your Mac is off. It's free, and it
needs **only a GitHub account** — no other services, tokens, or passwords.

Everything technical is already set up in this folder. You have 3 short steps.

---

## Step 1 — Put the code on GitHub (no command line)

1. Create a free account at **github.com**.
2. Download **GitHub Desktop** from **desktop.github.com**, install it, and sign
   in with your GitHub account.
3. In GitHub Desktop: **File → Add Local Repository…** and choose this folder
   (`amelia-dashboard`).
4. Click **Publish repository**. Name it `amelia-island-scene`, make sure
   **"Keep this code private" is UNCHECKED** (Pages needs a public repo on the
   free plan), and click **Publish**.

## Step 2 — Turn on GitHub Pages

1. On github.com, open your new `amelia-island-scene` repository.
2. Go to **Settings → Pages** (left sidebar).
3. Under **Build and deployment → Source**, choose **GitHub Actions**. That's it
   — nothing else to fill in.

## Step 3 — Run it once

1. In the repo, click the **Actions** tab.
2. Pick **"Build & publish The Amelia Current"** on the left, then
   **Run workflow → Run workflow**.
3. Wait a minute or two. When it finishes (green check), your site is live at:

   **`https://YOUR-USERNAME.github.io/amelia-island-scene/`**

   (You can also find the link under **Settings → Pages**.)

**Share that link with anyone.** From now on it refreshes itself every hour, around the clock — no Mac required.

---

### Changing things later
Edit `config.json` (restaurants, etc.), then in GitHub Desktop: **Commit to
main → Push origin**. The site rebuilds automatically within a minute.

### Notes
- If nobody touches the repo for ~60 days, GitHub pauses the daily schedule; any
  commit or a manual **Run workflow** wakes it back up.
- Prefer a private repo or a prettier domain instead of GitHub Pages? Netlify is
  an alternative (the code already supports it) — just ask.
