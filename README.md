# Amelia Island Scene

A single web page that gives you the week at a glance for Amelia Island and
Fernandina Beach, organized into tabs:

- 🌤️ **Weather & Tides** (the opening view): the National Weather Service 7‑day
  forecast, current conditions, sunrise/sunset, and daily high/low tides.
- 🎶 **Live Music**: every night's lineup across local venues, grouped by day.
- 📅 **Events**: trivia, markets, festivals, classes, and more.
- 🍽️ **Bars & Restaurants**: every spot on the island, filterable by type, each
  with a Yelp link.
- 📰 **News**: recent local headlines plus City of Fernandina Beach updates.
- 📜 **Island & Sea**: a daily island-history story and a daily Florida marine
  life profile, each with a photo.
- 🗂️ **Everything**: all of the above on one long page.

Everything is free and needs no paid accounts or API keys.

---

## The live site

**https://theameliacurrent.com** (anyone can open it; the original
`mcgoogs1-wq.github.io/amelia-island-scene` link forwards there)

It runs entirely on GitHub's servers, so your Mac can be off. Twice a day
GitHub rebuilds the page with fresh data and republishes it. That's the
`.github/workflows/build.yml` file. Open pages also refresh themselves every
30 minutes. See `CLOUD-SETUP.md` for how it was set up.

**To change something** (add a restaurant, etc.): edit `config.json`, then in
GitHub Desktop click **Commit to main → Push origin**. The site rebuilds itself
within a few minutes.

**To refresh it right now:** on github.com open the repo's **Actions** tab →
**Build & publish Amelia Island Scene** → **Run workflow**.

---

## Preview it on your Mac (optional)

From this `amelia-dashboard` folder:

```bash
./run_dashboard.sh
```

That builds `output/index.html`, which you can double‑click to open. This is
only a local preview; it doesn't change the live site.

---

## Where things live

- `amelia_dashboard.py`: the program itself.
- `config.json`: your settings (see below).
- `.github/workflows/build.yml`: the twice-daily cloud rebuild.
- `data/`: cached restaurant addresses, history/marine articles, and photos.
- `output/index.html`: the local preview (not uploaded).
- `logs/dashboard.log`: a record of local runs.
- `.venv/`: this project's private Python environment (local only).

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
file, then commit and push it from GitHub Desktop to update the live site.

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

- Live music & events: [Fernandina Events](https://fernandinaevents.com/live-music)
  (primary) and [AllEvents](https://allevents.in/fernandina-beach/music)
- Island history & marine life: [Wikipedia](https://en.wikipedia.org/);
  banner photos: [Wikimedia Commons](https://commons.wikimedia.org/)
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
