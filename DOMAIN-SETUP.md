# Putting Amelia Island Scene on theameliacurrent.com

The site keeps running on GitHub exactly as it does now. Cloudflare just
points the name **theameliacurrent.com** at it. Once it's switched over, the old
`mcgoogs1-wq.github.io/amelia-island-scene` link forwards to the new address,
so anything already shared keeps working.

---

## 1. Add the DNS records in Cloudflare (~5 min)

1. Go to **dash.cloudflare.com** and click **theameliacurrent.com**.
2. In the left sidebar, open **DNS → Records**.
3. If any records already exist with the name `theameliacurrent.com` (or `@`) or
   `www`, delete them. Leave any MX or TXT records alone.
4. Click **Add record** once for each row below.

| Type | Name | IPv4 / IPv6 address, or Target | Proxy status |
|---|---|---|---|
| A | `@` | `185.199.108.153` | **DNS only** |
| A | `@` | `185.199.109.153` | **DNS only** |
| A | `@` | `185.199.110.153` | **DNS only** |
| A | `@` | `185.199.111.153` | **DNS only** |
| AAAA | `@` | `2606:50c0:8000::153` | **DNS only** |
| AAAA | `@` | `2606:50c0:8001::153` | **DNS only** |
| AAAA | `@` | `2606:50c0:8002::153` | **DNS only** |
| AAAA | `@` | `2606:50c0:8003::153` | **DNS only** |
| CNAME | `www` | `mcgoogs1-wq.github.io` | **DNS only** |

> ⚠️ **The one thing that matters most:** Cloudflare turns the orange
> **Proxied** cloud ON by default for every new record. Click the toggle so
> the cloud turns **grey ("DNS only")** before you save each one. If it stays
> orange, GitHub can't confirm the domain or issue the HTTPS certificate.
>
> Cloudflare may warn that a DNS-only record "exposes the IP address." Ignore
> that; those are GitHub's public addresses, not yours.

Leave TTL on **Auto**.

## 2. Wait for the go-ahead, then tell GitHub the domain (~1 min)

**Don't do this step until the records above are working.** The moment you save
a custom domain, GitHub starts forwarding the old link to theameliacurrent.com. If
the domain isn't reachable yet, the site would be down in between. (Claude can
check this for you. Otherwise, wait until https://theameliacurrent.com shows a
GitHub "404" page.)

1. Go to **github.com/mcgoogs1-wq/amelia-island-scene/settings/pages**
2. Under **Custom domain**, type `theameliacurrent.com` (no `www`, no `https://`)
   and click **Save**.
3. Wait for the green **"DNS check successful."**

## 3. Turn on HTTPS (~1 min, after a short wait)

GitHub then requests a free security certificate, which usually takes 15–60
minutes. When **Enforce HTTPS** on the same page becomes clickable, check it.

## 4. Lock the domain to your account (recommended, ~5 min)

This stops anyone else's GitHub site from ever claiming your domain.

1. Go to **github.com/settings/pages** (your account settings, not the repo).
2. Click **Add a domain** and enter `theameliacurrent.com`.
3. GitHub shows a TXT record. In Cloudflare, **Add record** → Type **TXT** →
   paste the **Name** (Cloudflare adds `.theameliacurrent.com` on its own) and the
   **Content** exactly as GitHub shows → Save.
4. Back on GitHub, click **Verify**.

---

**Done.** Share **https://theameliacurrent.com**. `www.theameliacurrent.com` works too.
