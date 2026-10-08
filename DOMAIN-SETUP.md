# Putting Amelia Island Scene on your own domain

Below, replace **YOURDOMAIN.com** with the domain you bought. The site keeps
running on GitHub exactly as it does now. You're just giving it a nicer
address. Your old `mcgoogs1-wq.github.io/amelia-island-scene` link will
automatically forward to the new one, so anything you've already shared keeps
working.

---

## 1. Add the DNS records at your registrar (~5 min)

Log in where you bought the domain and find **DNS** (it may be called "DNS
Records", "Manage DNS", "Advanced DNS", or "DNS Zone").

**First, delete any records the registrar added for you** on `@` or `www`.
These are usually a "parked" or "coming soon" page, or a "forwarding/redirect"
rule. They will conflict with GitHub. Leave any MX or TXT records alone; those
are for email.

Then add these records:

| Type | Host / Name | Value / Points to |
|---|---|---|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| AAAA | `@` | `2606:50c0:8000::153` |
| AAAA | `@` | `2606:50c0:8001::153` |
| AAAA | `@` | `2606:50c0:8002::153` |
| AAAA | `@` | `2606:50c0:8003::153` |
| CNAME | `www` | `mcgoogs1-wq.github.io` |

- `@` means the bare domain (YOURDOMAIN.com). Some registrars want the field left
  blank instead of `@`.
- Leave TTL at the default.
- The AAAA rows are optional (they're for IPv6), but they're recommended.
- **Using Cloudflare?** Set every one of these records to **"DNS only"** (grey
  cloud), not "Proxied" (orange cloud). Otherwise GitHub can't issue the HTTPS
  certificate.

## 2. Tell GitHub the domain (~1 min)

1. Go to **github.com/mcgoogs1-wq/amelia-island-scene/settings/pages**
2. Under **Custom domain**, type `YOURDOMAIN.com` (no `www`, no `https://`) and
   click **Save**.
3. GitHub runs a DNS check. It shows a green **"DNS check successful"** once your
   records have spread, which usually takes a few minutes and occasionally up
   to a few hours. Until then it may say the domain is "improperly
   configured". That's normal while you wait.

## 3. Turn on HTTPS (~1 min, after a short wait)

Once the DNS check passes, GitHub requests a free security certificate. That
usually takes 15–60 minutes. When the **Enforce HTTPS** checkbox on the same
page becomes clickable, check it. That's the padlock in the browser.

## 4. Lock the domain to your account (recommended, ~5 min)

This stops anyone else's GitHub site from ever claiming your domain.

1. Go to **github.com/settings/pages** (your account settings, not the repo).
2. Click **Add a domain**, enter `YOURDOMAIN.com`.
3. GitHub shows one **TXT** record. Add it at your registrar exactly as shown,
   then click **Verify**.

---

**Then you're done.** Share **https://YOURDOMAIN.com** with anyone. Both
`YOURDOMAIN.com` and `www.YOURDOMAIN.com` work, and both forward to the same
site.
