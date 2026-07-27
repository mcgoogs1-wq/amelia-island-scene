# Amelia Island & Fernandina Beach — weekly dashboard

A single web page that gives you the week at a glance for Amelia Island and
Fernandina Beach:

- 🎶 **Live music this week** — every night's lineup across local venues
  (Sliders, Green Turtle, Salt Life, Sandbar, Mocama, Palace, Boat House…),
  grouped by day.
- 📅 **Other events this week** — trivia, markets, festivals, classes, book
  events, and more.
- 📰 **Local news** — recent Amelia Island / Fernandina Beach headlines from
  multiple outlets, plus official City of Fernandina Beach announcements.
- ☀️ **Weather** — the National Weather Service 7‑day forecast, current
  conditions, and sunrise/sunset.
- 🌊 **Tides** — daily high/low tide times for Fernandina Beach.
- 🍽️ **Restaurants on the Island** — every dining spot on Amelia Island, with
  cuisine and a link, from OpenStreetMap.

Everything is free and needs no accounts or API keys. The page rebuilds itself
on a schedule and also auto-refreshes in your browser every 30 minutes.

---

## Share it online (get a public link)

By default the dashboard is a file on your Mac, which only *you* can open. To get
a link you can send to anyone, it publishes itself to **Netlify** (free) after
each build. One‑time setup:

1. Create a free account at **[netlify.com](https://www.netlify.com/)**.
2. Make an access token: Netlify → your avatar → **User settings** →
   **Applications** → **Personal access tokens** → **New access token** →
   copy the token.
3. Open `config.json` and paste it into `publish` → `netlify_token`
   (replacing `PUT-YOUR-NETLIFY-TOKEN-HERE`).
4. Run `./run_dashboard.sh`. It creates the site and prints the public link
   (something like `https://amelia-island-scene.netlify.app`). Share that link!

After that it re‑publishes automatically on every scheduled rebuild, so the
public page stays current. To turn publishing off, set `publish.enabled` to
`false`. (You can rename the site to a prettier address in the Netlify dashboard.)

---

## How to open it

After a run, the dashboard lives at:

```
output/index.html
```

Double‑click that file to open it in your browser, or **bookmark it** so it's
one click away. (In your browser, the address will start with `file:///…`.)

---

## Run it once, by hand

From this `amelia-dashboard` folder:

```bash
./run_dashboard.sh
```

It fetches everything and rewrites `output/index.html`. Takes a few seconds.

> Want it to pop open in your browser automatically after each run? Set
> `"open_after_run": true` in `config.json`.

---

## Make it update automatically

macOS can rebuild the dashboard for you on a schedule using a "launch agent":

```bash
cp "com.brucemcgoogan.amelia-dashboard.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.brucemcgoogan.amelia-dashboard.plist
```

By default it rebuilds at **7:00 AM and 4:00 PM daily**, and once whenever you
log in. To change the times, edit the `Hour`/`Minute` values in the plist
before copying it.

To turn it off later:

```bash
launchctl unload ~/Library/LaunchAgents/com.brucemcgoogan.amelia-dashboard.plist
```

> Note: the Mac has to be awake at the scheduled time for it to run. The
> browser page also refreshes itself every 30 minutes while it's open, so a
> tab you leave open stays reasonably current on its own.

---

## Where things live

- `amelia_dashboard.py` — the program itself.
- `config.json` — your settings (see below).
- `output/index.html` — the dashboard you open (rebuilt every run).
- `logs/dashboard.log` — a record of each run, handy if something looks off.
- `.venv/` — this project's private Python environment.

---

## Settings (`config.json`)

| Setting | What it does |
|---|---|
| `location_name` | The title shown at the top. |
| `days_ahead` | How many days of music/events/tides to show (default 7). |
| `open_after_run` | `true` to auto‑open the page in your browser after each run. |
| `news.days_back` | How far back to pull news headlines (default 14 days). |
| `news.max_items` | Max number of news headlines to show. |
| `news.exclude` | Words that filter out news noise (obituaries, box scores…). |
| `music.exclude_title` | Words that mean "not music" (trivia, poker, yoga, market…). Any listing whose title contains one is kept out of the music list. |
| `music.exclude_venue` | Places that never host live shows (library, rec center, city hall…). Listings there are kept out of the music list. |
| `restaurants.enabled` | Show the Restaurants section or not. |
| `restaurants.bbox` | The map box searched for restaurants: `[south, west, north, east]`. Default covers Amelia Island. |
| `restaurants.amenities` | Which kinds to include: `restaurant`, `cafe`, `fast_food`. |
| `restaurants.custom` | **Your own restaurants**, added on top of the OpenStreetMap list (see below). |

### Adding your own restaurants

The restaurant list comes from OpenStreetMap, so a brand‑new opening or a spot
that just isn't mapped yet won't appear. To add your own, open `config.json` and
put them in the `restaurants` → `custom` list. Each entry can be **just a name**:

```json
"custom": [
  "The Patio Place",
  "Salty's Snack Shack"
]
```

…or a **full entry** with extra details (all optional except `name`):

```json
"custom": [
  { "name": "The Patio Place", "cuisine": "Seafood", "street": "Centre Street", "url": "https://thepatioplace.com" }
]
```

- `cuisine` and `street` show under the name; leave them out if you don't care.
- `url` is where the card links; if you skip it, the card links to a Google
  search for the name.
- A custom entry with the same name as an OpenStreetMap one **replaces** it, so
  you can also use this to fix a wrong cuisine or add a website.

Your additions always show, even when OpenStreetMap is unreachable. Save the
file and run `./run_dashboard.sh` (or wait for the next scheduled rebuild).

### Removing a restaurant

To drop an OpenStreetMap listing (e.g. a bad or combined map name), add part of
its name to `restaurants` → `exclude`:

```json
"exclude": [ "Amelia Island Paint" ]
```

Any restaurant whose name contains that text (case‑insensitive) is removed. To
"rename" a bad entry, exclude it here and re‑add a clean version in `custom` —
that's exactly how "Amelia Island Paint & Hardware / Tasty's Fresh Burgers" was
split back into just **Tasty's Fresh Burgers**.

### How the music vs. events split works

The free community calendar these listings come from is often sloppy about
categories — a singer playing at a market or the senior center frequently gets
filed under "Other Events" instead of "Live Music." So the dashboard sorts by
**elimination**: a listing is treated as live music **unless** its title is an
obvious non‑music activity (`music.exclude_title` — trivia, bingo, a class, a
market…) **or** it's at a venue that never hosts shows (`music.exclude_venue` —
the library, rec center, city hall…). This favors a complete music list, so
once in a while a non‑performance may slip in.

If you see something in the wrong section, fix it with one word:

- A non‑music event showing up **in Music** → add a word from its title to
  `music.exclude_title`, or its venue to `music.exclude_venue`.
- A real show stuck **in Other Events** → it means a word in its title matched
  `music.exclude_title`; remove or narrow that word.

---

## Where the data comes from

- Live music & events: [FernandinaConnect](https://fernandinaconnect.com/) and
  [AllEvents](https://allevents.in/fernandina-beach/music)
- News: Google News (aggregating local outlets) and the
  [City of Fernandina Beach](https://www.fbfl.us/)
- Weather: [National Weather Service](https://www.weather.gov/) (api.weather.gov)
- Tides: [NOAA Tides & Currents](https://tidesandcurrents.noaa.gov/stationhome.html?id=8720030),
  station 8720030 (Fernandina Beach)
- Restaurants: [OpenStreetMap](https://www.openstreetmap.org/copyright) via the
  Overpass API (the list is cached in `data/restaurants.json`, so it still shows
  even if Overpass is temporarily down). Missing **addresses** are filled in by
  reverse‑geocoding each spot's location with OSM Nominatim (cached once in
  `data/geocode_cache.json`), and a missing **descriptor** is guessed from the
  name (Pizza, Sushi, BBQ…) or falls back to the type (Restaurant / Café /
  Fast food).

*For personal use. Event details, prices, and availability can change — always
double‑check with the venue.*
