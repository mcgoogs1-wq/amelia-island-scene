#!/usr/bin/env python3
"""
Amelia Island / Fernandina Beach dashboard.

Fetches this week's live-music schedule, local events, local news, civic
meetings, weather and tides, then writes a single self-contained HTML page
to output/index.html that you open in a browser.

Every source is wrapped so one failing feed never breaks the whole page --
the section just shows a friendly "couldn't load" note instead.

Data sources (all free, no API key):
  * Live music / events : fernandinaconnect.com + allevents.in
  * Local news          : Google News RSS + City of Fernandina "News Flash"
  * Civic meetings      : City of Fernandina calendar (CivicPlus)
  * Weather             : National Weather Service (api.weather.gov)
  * Tides               : NOAA Tides & Currents, station 8720030
"""

from __future__ import annotations

import html
import io
import json
import logging
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
TZ = ZoneInfo("America/New_York")

DEFAULT_CONFIG = {
    "location_name": "Amelia Island & Fernandina Beach",
    "days_ahead": 7,
    "output_file": "output/index.html",
    "open_after_run": False,
    "contact_email": "amelia-island-scene dashboard",
    "publish": {
        # Publish the page to the web (a shareable link) after each build.
        # One-time setup: make a free Netlify account, create a Personal Access
        # Token, and paste it below. See the README.
        "enabled": True,
        "provider": "netlify",
        "site_name": "amelia-island-scene",
        "netlify_token": "PUT-YOUR-NETLIFY-TOKEN-HERE",
    },
    "weather": {"office": "JAX", "gridX": 72, "gridY": 80,
                "lat": 30.6697, "lon": -81.4626},
    "tides": {"station": "8720030"},
    "news": {"google_news": True, "city_newsflash": True,
             "days_back": 14, "max_items": 14,
             "exclude": ["obituary", "legacy.com", "maxpreps", "varsity",
                         "box score", "final score"]},
    "restaurants": {
        "enabled": True,
        # bounding box around Amelia Island: [south, west, north, east]
        "bbox": [30.50, -81.49, 30.73, -81.43],
        "amenities": ["restaurant", "cafe", "fast_food"],
        # Your own additions, merged in on top of the OpenStreetMap list. Each
        # entry can be just a name string, or an object with name + optional
        # cuisine / street / url. See the README.
        "custom": [],
        # Drop OpenStreetMap entries whose name contains any of these (case-
        # insensitive substrings). Handy for bad/combined map listings.
        "exclude": [],
        "overpass_urls": [
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass-api.de/api/interpreter",
            "https://overpass.openstreetmap.ru/api/interpreter",
        ],
    },
    "facts": {
        # Daily rotating history + marine-biology facts pulled from Wikipedia
        # article intros (falls back to a built-in curated set if offline).
        "source": "wikipedia",
        "refresh_days": 7,
        # region-centric articles — inherently local, use the intro
        "history_titles": [
            "Amelia Island", "Fernandina Beach, Florida",
            "Nassau County, Florida", "Fort Clinch", "Fort Clinch State Park",
            "Amelia Island Light", "American Beach, Florida",
            "Amelia Island State Park",
        ],
        # broader people/events — pull the WHOLE article but keep only passages
        # that actually mention the area (see region_terms)
        "history_context_titles": [
            "Gregor MacGregor", "Luis Aury", "David Levy Yulee", "Timucua",
            "Spanish Florida", "History of Florida", "Kingsley Plantation",
            "Fort Caroline", "Cumberland Island", "MaVynee Betsch",
            "Florida Railroad", "Republic of the Floridas",
        ],
        "region_terms": [
            "amelia", "fernandina", "nassau county", "fort clinch",
            "american beach", "isle of eight flags", "st. marys",
            "cumberland sound",
        ],
        "marine_titles": [
            # marine mammals
            "West Indian manatee", "Common bottlenose dolphin",
            "North Atlantic right whale", "Atlantic spotted dolphin",
            "Humpback whale",
            # fish
            "Red drum", "Spotted seatrout", "Sheepshead (fish)",
            "Florida pompano", "Black drum", "Atlantic tarpon", "Common snook",
            "Southern flounder", "Atlantic menhaden", "Flathead grey mullet",
            "Cobia", "King mackerel", "Bluefish", "Red snapper",
            "Atlantic croaker", "Crevalle jack", "Spanish mackerel", "Ladyfish",
            # invertebrates
            "Atlantic horseshoe crab", "Blue crab", "Eastern oyster",
            "Fiddler crab", "Atlantic ghost crab", "Florida stone crab",
            "Whiteleg shrimp", "Cannonball jellyfish", "Ctenophora",
            "Busycon carica", "Sand dollar",
            # birds
            "Brown pelican", "Osprey", "Roseate spoonbill", "Great blue heron",
            "Snowy egret", "American oystercatcher", "Black skimmer",
            "Wood stork", "Laughing gull", "Royal tern", "Willet", "Sanderling",
            "Anhinga", "Painted bunting",
            # key plants & habitat
            "Sporobolus alterniflorus", "Uniola paniculata", "Seagrass",
            "Red mangrove", "Sabal palmetto", "Serenoa", "Salt marsh",
            "Salicornia", "Estuary",
        ],
    },
    "banner": {
        # rotating natural-landscape photo band under the header, from Wikimedia
        # Commons image search (landscape-oriented, filtered for scenery).
        "enabled": True,
        "refresh_days": 7,
        "queries": [
            "Fort Clinch State Park", "Amelia Island State Park",
            "Amelia Island beach", "Fernandina Beach beach",
            "Amelia Island ocean", "Amelia Island marsh",
            "Amelia Island dunes", "Amelia Island Florida nature",
        ],
        "exclude": [
            "map", "diagram", "logo", "seal", "flag", "icon", "plaque", "chart",
            "sign", "museum", "moh", "factory", "paper", "rocktenn", "door",
            "statue", "interior", "battle", " vs ", "painting", "memorial",
            "veterans", "depot", "downtown", "court", "jail", "building",
            "street", " road ", " sr ", "a1a", "portrait", "coat of arms",
            "putt", "school", "rescue", "skate", "airport", "airfield",
            "aircraft", "airplane", "aviation", "earhart", "lockheed", "vega",
            "mill", "smurfit", "westrock", "hospital", "hotel", "resort",
            "golf", "stadium", "parking", "fire ", "high school",
        ],
    },
    "sources": {
        # fernandinaevents.com is a Base44 app with a public JSON API that
        # aggregates the full bar/restaurant live-music schedule (categorized).
        "fernandina_events": True,
        "fernandinaevents_appid": "6a4976813935624ee0d891e4",
        # fernandinaconnect.com broke during a site migration (events DB empty);
        # left off by default. AllEvents is a lighter secondary source.
        "fernandina_connect": False,
        "allevents": True,
    },
    "music": {
        # The free calendar mis-tags many named acts as generic "events". We
        # sort listings into the music section by ELIMINATION: an item is treated
        # as live music unless its title is an obvious non-music activity
        # (exclude_title) or it's at a place that never hosts shows
        # (exclude_venue). This favors a complete music list, so an occasional
        # non-performance may slip in -- tune the two lists below to taste.
        "infer_music": True,
        # Event-type words that mean "not a live show" (matched whole-word).
        "exclude_title": [
            "trivia", "karaoke", "bingo", "quiz", "tournament", "league",
            "points league", "poker", "name that tune", "family feud",
            "cornhole", "darts", "chess", "mahjong", "board game", "game night",
            "line dancing", "dance party", "run", "runs", "run club",
            "run clubs", "5k", "10k", "walk", "ruck", "chug", "hike", "paddle",
            "yoga", "pilates", "barre", "aerobics", "zumba", "spin class",
            "fitness", "workout", "bootcamp", "class", "lesson", "workshop",
            "seminar", "clinic", "course", "meetup", "market", "farmer",
            "farmers", "fair", "expo", "bazaar", "vendor", "pop-up", "popup",
            "sip & shop", "sip and shop", "shop", "sale", "book", "author",
            "reading", "story time", "storytime", "lecture", "brown bag",
            "meeting", "committee", "commission", "hearing", "forum",
            "town hall", "institute", "conference", "symposium", "summit",
            "paint", "craft", "knit", "crochet", "sound bath", "meditation",
            "reiki", "wellness", "blood drive", "cleanup", "clean up",
            "volunteer", "worship", "service", "bible", "prayer", "comedy",
            "tasting", "brunch buffet", "face your fears", "trunk", "car show",
        ],
        # Places that never host a live-music show (whole listing goes to Other).
        "exclude_venue": [
            "rec center", "recreation", "public library", "library", "city hall",
            "ascendance", "pilates", "medi spa", "elementary", "middle school",
            "high school", "ymca", "chamber", "community center", "courthouse",
            "county building", "peck center", "board games",
        ],
        # Known live-music venues (matched in the venue OR the title). A listing
        # at one of these — or with a music keyword below — is treated as music.
        "venues": [
            "green turtle", "sliders", "salt life", "sandbar", "mocama",
            "palace", "boat house", "the surf", "crab trap", "salty pelican",
            "tigre island", "inkwell", "patio at 5th", "courtyard", "down under",
            "pjd", "principal", "ash street", "holy grounds", "seaglass",
            "first love", "decantery", "bar zin", "hammerhead", "locals",
            "story & song", "golf pub", "amelia river", "flying fish",
            "the goat", "otb brews", "brew shed", "brewing", "brewery",
            "brewpub", "taphouse", "tavern", "saloon", "ale house",
        ],
        # Title words that signal a live performance.
        "include_terms": [
            "live music", "live at", "concert", "acoustic", "open mic",
            "jazz", "blues", "tribute", " band", "dj ", "sunset concert",
        ],
    },
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    path = HERE / "config.json"
    if path.exists():
        try:
            user = json.loads(path.read_text())
            _deep_update(cfg, user)
        except Exception as e:  # noqa: BLE001
            logging.warning("Could not read config.json (%s); using defaults", e)
    return cfg


def _deep_update(base: dict, extra: dict) -> None:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def setup_logging() -> None:
    (HERE / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        handlers=[
            logging.FileHandler(HERE / "logs" / "dashboard.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def http_get(url: str, cfg: dict, *, timeout: int = 25) -> requests.Response:
    """GET with a browser-ish User-Agent (NWS requires a UA / contact)."""
    ua = ("AmeliaDashboard/1.0 (%s) Mozilla/5.0 (Macintosh; Intel Mac OS X "
          "10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 "
          "Safari/537.36" % cfg.get("contact_email", ""))
    r = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en-US"},
                     timeout=timeout)
    r.raise_for_status()
    return r


def now_local() -> datetime:
    return datetime.now(TZ)


def parse_utc(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(TZ)
    except Exception:  # noqa: BLE001
        return None


def parse_api_dt(s: str) -> datetime | None:
    """Parse an ISO timestamp; a naive one (no tz) is treated as UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:  # noqa: BLE001
        return None


def fetch_fernandina_events(cfg: dict) -> list[dict]:
    """The full local live-music + events schedule from fernandinaevents.com's
    public Base44 JSON API (events are pre-categorized as Music / Social / ...)."""
    src = cfg.get("sources", {})
    app = src.get("fernandinaevents_appid", "6a4976813935624ee0d891e4")
    fields = ("event_title,event_start,performer_name,performer_type,venue_name,"
              "business_name,primary_category_name,category_name,description,slug")
    q = quote('{"status":"Published"}')
    url = (f"https://fernandinaevents.com/api/apps/{app}/entities/Event?"
           f"q={q}&sort=event_start&limit=1000&fields={fields}")
    r = http_get(url, cfg)
    data = r.json()
    rows = data if isinstance(data, list) else data.get("items", data.get("data", []))
    events: list[dict] = []
    for e in rows:
        start = parse_api_dt(e.get("event_start", ""))
        cat = (e.get("primary_category_name") or e.get("category_name") or "").strip()
        is_music = cat.lower() == "music"
        title = ((e.get("performer_name") if is_music else "")
                 or e.get("event_title") or "(untitled)")
        venue = e.get("venue_name") or e.get("business_name") or ""
        slug = e.get("slug", "")
        # Link out to a web search about the act/event (surfaces the musician's
        # YouTube, socials, etc.) rather than the redundant event-detail page.
        if is_music:
            search = f"{title} musician Amelia Island"
        else:
            search = f"{e.get('event_title') or title} {venue} Fernandina Beach"
        ev_url = "https://www.google.com/search?q=" + quote_plus(search.strip())
        events.append({
            "id": f"fe-{slug or hash((title, e.get('event_start','')))}",
            "title": title,
            "date": start,
            "weekday": start.strftime("%A") if start else "",
            "time_str": start.strftime("%-I:%M %p") if start else "",
            "time_sort": start.timestamp() if start else 0,
            "venue": venue,
            "category_slug": "live-music" if is_music else "other-events",
            "category": "Live Music" if is_music else (cat or "Other Events"),
            "url": ev_url,
            "description": (e.get("description") or "")[:300],
            "source": "FernandinaEvents",
        })
    logging.info("FernandinaEvents: %d events (%d music)", len(events),
                 sum(1 for e in events if e["category_slug"] == "live-music"))
    return events


# --------------------------------------------------------------------------
# Live music + events  (fernandinaconnect.com)
# --------------------------------------------------------------------------

def fetch_fernandina_connect(cfg: dict) -> list[dict]:
    """Return a flat list of upcoming events from fernandinaconnect.com.

    Each event: id, title, date (local), weekday, time_str, time_sort,
    venue, category_slug, category, url, description, source.
    """
    r = http_get("https://fernandinaconnect.com/", cfg)
    text = r.text

    # 1) machine-readable index gives us real start times + category
    index: dict[int, dict] = {}
    m = re.search(r"window\._eventsData\s*=\s*(\[.*?\])\s*;", text, re.S)
    if m:
        for row in json.loads(m.group(1)):
            index[row["id"]] = row

    cm = re.search(r"window\._categoryMap\s*=\s*(\{.*?\})\s*;", text, re.S)
    catmap = json.loads(cm.group(1)) if cm else {}

    # 2) the cards give us clean display fields (title, venue, time, links)
    soup = BeautifulSoup(text, "lxml")
    events: list[dict] = []
    for card in soup.select(".event-card"):
        # id lives in an alpine attribute like x-show="isEventVisible(4864)"
        eid = None
        for val in card.attrs.values():
            mm = re.search(r"isEventVisible\((\d+)\)", str(val))
            if mm:
                eid = int(mm.group(1))
                break
        if eid is None:
            continue

        idx = index.get(eid, {})
        start = parse_utc(idx.get("start_utc", ""))

        title_el = card.select_one(f"#event-title-{eid}") or card.find(
            attrs={"id": re.compile(r"event-title")})
        title = title_el.get_text(" ", strip=True) if title_el else None

        content = card.select_one("div.flex.flex-col") or card
        leaves = [el for el in content.find_all(["span", "a", "p"])
                  if not el.find(recursive=False) and el.get_text(strip=True)]

        time_str = venue = None
        for el in leaves:
            classes = " ".join(el.get("class", []))
            txt = el.get_text(" ", strip=True)
            if time_str is None and re.match(r"^\d{1,2}(:\d{2})?\s*[AP]M", txt):
                time_str = txt
            elif venue is None and "truncate" in classes:
                venue = txt
        # fallback: recover venue from the Google Maps link the card carries
        if not venue:
            g = card.find("a", href=re.compile(r"maps/search"))
            if g:
                mm = re.search(r"query=([^&]+)", g["href"])
                if mm:
                    from urllib.parse import unquote_plus
                    venue = unquote_plus(mm.group(1)).split(",")[0].strip()
        if not title:
            for el in leaves:
                if el.name == "a" and el.get_text(strip=True):
                    title = el.get_text(" ", strip=True)
                    break

        # link: prefer a real "More Info" link over the Google-search fallback
        url = None
        for a in card.find_all("a", href=True):
            href = a["href"]
            if "google.com" in href:
                continue
            url = href
            break
        if not url:
            g = card.find("a", href=re.compile(r"google\.com/search"))
            url = g["href"] if g else "https://fernandinaconnect.com/"

        # description: longest paragraph-ish text that isn't the fields above
        desc = ""
        for p in content.find_all(["p", "div"]):
            if p.find(recursive=False):
                continue
            t = p.get_text(" ", strip=True)
            if len(t) > len(desc) and t not in (title, venue, time_str):
                desc = t

        slug = idx.get("category_slug", "")
        events.append({
            "id": eid,
            "title": title or "(untitled)",
            "date": start,
            "weekday": start.strftime("%A") if start else "",
            "time_str": time_str or (start.strftime("%-I:%M %p") if start else ""),
            "time_sort": start.timestamp() if start else 0,
            "venue": venue or "",
            "category_slug": slug,
            "category": catmap.get(slug, slug.replace("-", " ").title()),
            "url": url,
            "description": desc[:300],
            "source": "FernandinaConnect",
        })
    logging.info("FernandinaConnect: %d events parsed", len(events))
    return events


def fetch_allevents(cfg: dict) -> list[dict]:
    """Events from allevents.in via schema.org JSON-LD. The /music page is
    trusted as live music; the broader /all page is routed through the venue
    classifier so bar gigs get picked up and the rest becomes Other Events."""
    pages = [("https://allevents.in/fernandina-beach/music", "live-music"),
             ("https://allevents.in/fernandina-beach/all", "other-events")]
    events: list[dict] = []
    for url, default_cat in pages:
        try:
            r = http_get(url, cfg)
        except Exception as ex:  # noqa: BLE001
            logging.warning("AllEvents %s failed: %s", url, ex)
            continue
        for block in re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                r.text, re.S):
            try:
                data = json.loads(block)
            except Exception:  # noqa: BLE001
                continue
            for node in (data if isinstance(data, list) else [data]):
                if not isinstance(node, dict) or "Event" not in str(node.get("@type", "")):
                    continue
                start = parse_utc(node.get("startDate", ""))
                loc = node.get("location")
                venue = loc.get("name") if isinstance(loc, dict) else (loc or "")
                venue = html.unescape(venue or "")
                events.append({
                    "id": f"ae-{hash((node.get('name',''), node.get('startDate','')))}",
                    "title": html.unescape(node.get("name", "(untitled)")),
                    "date": start,
                    "weekday": start.strftime("%A") if start else "",
                    "time_str": start.strftime("%-I:%M %p") if start else "",
                    "time_sort": start.timestamp() if start else 0,
                    "venue": venue,
                    "category_slug": default_cat,
                    "category": "Live Music" if default_cat == "live-music" else "Other Events",
                    "url": node.get("url", url),
                    "description": html.unescape(node.get("description") or "")[:300],
                    "source": "AllEvents",
                })
    logging.info("AllEvents: %d events parsed", len(events))
    return events


def within_window(ev: dict, start_day: datetime, end_day: datetime) -> bool:
    d = ev.get("date")
    return bool(d) and start_day <= d <= end_day


def dedupe(events: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    _pref = {"FernandinaEvents": 0, "FernandinaConnect": 1}
    for ev in sorted(events, key=lambda e: (_pref.get(e.get("source"), 2),
                                            e.get("category_slug") != "live-music")):
        d = ev.get("date")
        key = (
            re.sub(r"[^a-z0-9]", "", (ev["title"] or "").lower())[:24],
            d.date().isoformat() if d else "",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def collect_events(cfg: dict) -> tuple[list[dict], list[dict]]:
    """Return (music_events, other_events) within the look-ahead window."""
    today = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + timedelta(days=cfg["days_ahead"], hours=23, minutes=59)

    all_events: list[dict] = []
    if cfg["sources"].get("fernandina_events", True):
        try:
            all_events += fetch_fernandina_events(cfg)
        except Exception as e:  # noqa: BLE001
            logging.warning("FernandinaEvents failed: %s", e)
    if cfg["sources"].get("fernandina_connect", False):
        try:
            all_events += fetch_fernandina_connect(cfg)
        except Exception as e:  # noqa: BLE001
            logging.warning("FernandinaConnect failed: %s", e)
    if cfg["sources"].get("allevents", True):
        try:
            all_events += fetch_allevents(cfg)
        except Exception as e:  # noqa: BLE001
            logging.warning("AllEvents failed: %s", e)

    upcoming = [e for e in all_events if within_window(e, today, end)]
    upcoming = dedupe(upcoming)

    mcfg = cfg.get("music", {})
    infer = mcfg.get("infer_music", True)
    excl_title = [x.lower() for x in mcfg.get("exclude_title", [])]
    venues = [v.lower() for v in mcfg.get("venues", [])]
    include_terms = [t.lower() for t in mcfg.get("include_terms", [])]

    def is_music(e: dict) -> bool:
        title = (e.get("title") or "").lower()
        # a non-music activity (trivia, poker, a market...) is never music,
        # even if a source mis-tagged it. word-boundary so "class" != "classical".
        if any(re.search(r"\b" + re.escape(x) + r"\b", title) for x in excl_title):
            return False
        if e["category_slug"] == "live-music":
            return True  # the source labeled it music -> trust it
        if not infer:
            return False
        # inclusion: treat as music only if it's at a known music venue (checked
        # in the venue OR the title) or the title signals a live performance.
        text = ((e.get("venue") or "") + " " + title).lower()
        return (any(v in text for v in venues)
                or any(k in text for k in include_terms))

    music = sorted((e for e in upcoming if is_music(e)),
                   key=lambda e: e["time_sort"])
    music_ids = {id(e) for e in music}
    other = sorted((e for e in upcoming if id(e) not in music_ids),
                   key=lambda e: e["time_sort"])
    return music, other


# --------------------------------------------------------------------------
# News + civic meetings
# --------------------------------------------------------------------------

def fetch_news(cfg: dict) -> list[dict]:
    news_cfg = cfg["news"]
    items: list[dict] = []

    if news_cfg.get("google_news", True):
        days = news_cfg.get("days_back", 14)
        q = ('https://news.google.com/rss/search?q=%22Amelia+Island%22+OR+'
             '%22Fernandina+Beach%22+when%3A' + str(days) +
             'd&hl=en-US&gl=US&ceid=US:en')
        try:
            feed = feedparser.parse(q)
            for e in feed.entries:
                src = ""
                if e.get("source") and isinstance(e.source, dict):
                    src = e.source.get("title", "")
                raw = e.get("title", "")
                title = re.sub(r"\s*-\s*[^-]+$", "", raw) \
                    if src and raw.endswith(src) else raw
                # drop a trailing section label like " - News" / " - Sports"
                title = re.sub(r"\s*-\s*(News|Sports|Opinion|Local News|"
                               r"Local|Community)\s*$", "", title, flags=re.I)
                items.append({
                    "title": title.strip() or raw,
                    "source": src or "Google News",
                    "link": e.get("link", "#"),
                    "published": _feed_dt(e),
                })
        except Exception as ex:  # noqa: BLE001
            logging.warning("Google News failed: %s", ex)

    if news_cfg.get("city_newsflash", True):
        try:
            r = http_get("https://www.fbfl.us/RSSFeed.aspx?ModID=1&CID=", cfg)
            feed = feedparser.parse(r.text)
            for e in feed.entries:
                items.append({
                    "title": e.get("title", ""),
                    "source": "City of Fernandina Beach",
                    "link": e.get("link", "#"),
                    "published": _feed_dt(e),
                })
        except Exception as ex:  # noqa: BLE001
            logging.warning("City News Flash failed: %s", ex)

    # drop low-value noise (obituaries, high-school box scores, etc.)
    exclude = [x.lower() for x in news_cfg.get("exclude", [])]
    def is_noise(it: dict) -> bool:
        blob = (it["title"] + " " + it["source"]).lower()
        return any(x in blob for x in exclude)

    # newest first, de-duplicated by title
    seen: set[str] = set()
    out: list[dict] = []
    for it in sorted(items, key=lambda i: i["published"] or datetime.min.replace(
            tzinfo=timezone.utc), reverse=True):
        k = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:40]
        if k in seen or not it["title"] or is_noise(it):
            continue
        seen.add(k)
        out.append(it)
    logging.info("News: %d items", len(out))
    return out[: news_cfg.get("max_items", 14)]


def fetch_civic(cfg: dict) -> list[dict]:
    if not cfg.get("civic", {}).get("enabled", True):
        return []
    items: list[dict] = []
    try:
        r = http_get("https://www.fbfl.us/RSSFeed.aspx?ModID=58&CID=", cfg)
        feed = feedparser.parse(r.text)
        for e in feed.entries:
            items.append({
                "title": e.get("title", ""),
                "when": _clean_civic_when(e.get("description", ""))
                        or _fmt_dt(_feed_dt(e)),
                "link": e.get("link", "#"),
                "sort": _feed_dt(e) or datetime.max.replace(tzinfo=timezone.utc),
            })
    except Exception as ex:  # noqa: BLE001
        logging.warning("Civic calendar failed: %s", ex)
    items.sort(key=lambda i: i["sort"])
    logging.info("Civic: %d meetings", len(items))
    return items[: cfg.get("civic", {}).get("max_items", 8)]


def _clean_civic_when(desc: str) -> str:
    """CivicPlus descriptions embed HTML; turn them into one clean line."""
    if not desc:
        return ""
    text = re.sub(r"<[^>]+>", " ", desc)
    text = html.unescape(text)
    text = re.sub(r"Event\s*date:\s*", "", text, flags=re.I)
    text = re.sub(r"Event\s*Time:\s*", "· ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ·").strip()
    return text


def _feed_dt(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).astimezone(TZ)
    return None


# --------------------------------------------------------------------------
# Restaurants (OpenStreetMap Overpass API)
# --------------------------------------------------------------------------

def fetch_restaurants(cfg: dict) -> list[dict]:
    """Every dining spot on Amelia Island via OpenStreetMap's Overpass API.

    Falls back to the last good cached copy if Overpass is unreachable, so the
    section still fills in even when the API is rate-limited.
    """
    rc = cfg.get("restaurants", {})
    if not rc.get("enabled", True):
        return []
    cache = HERE / "data" / "restaurants.json"
    s, w, n, e = rc.get("bbox", [30.50, -81.49, 30.73, -81.43])
    amre = "^(" + "|".join(rc.get("amenities",
                                  ["restaurant", "cafe", "fast_food"])) + ")$"
    query = (f'[out:json][timeout:40];('
             f'node["amenity"~"{amre}"]({s},{w},{n},{e});'
             f'way["amenity"~"{amre}"]({s},{w},{n},{e}););out center tags;')

    endpoints = rc.get("overpass_urls") or [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    ]
    ua = f"AmeliaDashboard/1.0 ({cfg.get('contact_email','')})"
    items: list[dict] = []
    fetched = False
    for url in endpoints:
        try:
            r = requests.post(url, data={"data": query}, timeout=60,
                              headers={"User-Agent": ua})
            r.raise_for_status()
            seen: set[str] = set()
            for el in r.json().get("elements", []):
                t = el.get("tags", {})
                name = (t.get("name") or "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                center = el.get("center") or {}
                lat = el.get("lat", center.get("lat"))
                lon = el.get("lon", center.get("lon"))
                items.append(_restaurant_record(name, t, lat, lon))
            if items:
                logging.info("Restaurants: %d from Overpass (%s)", len(items), url)
                fetched = True
                break
        except Exception as ex:  # noqa: BLE001
            logging.warning("Overpass %s failed: %s", url, ex)

    if not items and cache.exists():
        items = json.loads(cache.read_text())
        logging.info("Restaurants: %d from cache", len(items))

    # fill missing street addresses by reverse-geocoding the coordinates
    # (results cached permanently, so each spot is looked up at most once)
    geo = _load_geocode_cache()
    filled = 0
    for it in items:
        if not it.get("street") and it.get("lat") and it.get("lon"):
            addr = _reverse_address(it["lat"], it["lon"], ua, geo)
            if addr:
                it["street"] = addr
                filled += 1
    if filled:
        _save_geocode_cache(geo)
        logging.info("Restaurants: geocoded %d addresses", filled)
    if fetched or filled:
        cache.write_text(json.dumps(items), encoding="utf-8")

    # drop unwanted OpenStreetMap listings (e.g. bad/combined map names)
    excl = [x.lower() for x in rc.get("exclude", [])]
    if excl:
        before = len(items)
        items = [i for i in items
                 if not any(x in i["name"].lower() for x in excl)]
        if before - len(items):
            logging.info("Restaurants: -%d excluded", before - len(items))

    # merge in the user's own additions (these show even if Overpass is down;
    # a custom entry with the same name overrides the OpenStreetMap one).
    by_name = {i["name"].lower(): i for i in items}
    added = 0
    for entry in rc.get("custom", []):
        rec = _custom_restaurant(entry)
        if rec:
            if rec["name"].lower() not in by_name:
                added += 1
            by_name[rec["name"].lower()] = rec
    items = list(by_name.values())
    if added:
        logging.info("Restaurants: +%d custom additions", added)

    # forward-geocode any entries still without an address (e.g. custom ones
    # with no coordinates) by looking their name up on Amelia Island
    need = [it for it in items if not it.get("street")]
    if need:
        for it in need:
            addr = _forward_address(it["name"], ua, geo)
            if addr:
                it["street"] = addr
        _save_geocode_cache(geo)
        logging.info("Restaurants: forward-geocoded %d addresses", len(need))

    items.sort(key=lambda x: x["name"].lower())
    return items


def _custom_restaurant(entry) -> dict | None:
    """Build a restaurant record from a config entry (a name string, or a
    dict with name + optional cuisine / street / url)."""
    if isinstance(entry, str):
        entry = {"name": entry}
    if not isinstance(entry, dict):
        return None
    name = (entry.get("name") or "").strip()
    if not name:
        return None
    website = entry.get("url") or entry.get("website") or ""
    if website and not website.startswith("http"):
        website = "http://" + website
    url = website or ("https://www.google.com/search?q="
                      + quote_plus(f"{name} Fernandina Beach FL"))
    amenity = entry.get("amenity", "restaurant")
    cuisine = (entry.get("cuisine") or _descriptor_from_name(name)
               or _AMENITY_LABEL.get(amenity, "Restaurant"))
    return {
        "name": name,
        "cuisine": cuisine,
        "street": entry.get("street", "") or "",
        "amenity": amenity,
        "url": url,
        "lat": None,
        "lon": None,
    }


def _restaurant_record(name: str, t: dict, lat=None, lon=None) -> dict:
    # descriptor: OSM cuisine, else guessed from the name, else the kind
    cuisine = ", ".join(
        c.strip().replace("_", " ").title()
        for c in (t.get("cuisine", "") or "").split(";") if c.strip())
    if not cuisine:
        cuisine = _descriptor_from_name(name)
    if not cuisine:
        cuisine = _AMENITY_LABEL.get(t.get("amenity", "restaurant"), "Restaurant")
    # street: house number + street from OSM (reverse-geocoded later if blank)
    num, st = t.get("addr:housenumber", ""), t.get("addr:street", "")
    street = f"{num} {st}".strip() if st else ""
    website = t.get("website") or t.get("contact:website") or ""
    if website and not website.startswith("http"):
        website = "http://" + website
    url = website or ("https://www.google.com/search?q="
                      + quote_plus(f"{name} Fernandina Beach FL"))
    return {
        "name": name.replace(";", " / "),
        "cuisine": cuisine,
        "street": street,
        "amenity": t.get("amenity", "restaurant"),
        "url": url,
        "lat": lat,
        "lon": lon,
    }


_AMENITY_LABEL = {"cafe": "Café", "fast_food": "Fast food",
                  "restaurant": "Restaurant"}

# name-based guesses for spots with no OpenStreetMap cuisine tag
_CUISINE_HINTS = [
    (("pizza", "pizzeria"), "Pizza"),
    (("sushi",), "Sushi"),
    (("taco", "taqueria", "cantina", "mexican", "mezcal", "burrito"), "Mexican"),
    (("thai",), "Thai"),
    (("chinese", "wok", "panda", "szechuan"), "Chinese"),
    (("ramen", "hibachi", "japanese"), "Japanese"),
    (("bbq", "barbecue", "barbeque", "smokehouse", "smoke house"), "Barbecue"),
    (("seafood", "oyster", "crab", "shrimp", "fish camp"), "Seafood"),
    (("coffee", "espresso", "roaster", "roastery"), "Coffee"),
    (("bakery", "bagel", "donut", "doughnut", "patisserie", "cupcake"), "Bakery"),
    (("delicatessen", "deli"), "Deli"),
    (("sandwich", "subs", "hoagie"), "Sandwiches"),
    (("burger",), "Burgers"),
    (("steak", "chophouse", "chop house"), "Steakhouse"),
    (("italian", "trattoria", "ristorante", "pasta"), "Italian"),
    (("cuban",), "Cuban"),
    (("irish",), "Irish"),
    (("ice cream", "creamery", "gelato", "frozen yogurt", "custard"), "Ice Cream"),
    (("diner",), "Diner"),
    (("brewpub", "brewing", "brewery", "taproom", "alehouse"), "Brewpub"),
    (("grill", "tavern", "pub", "saloon"), "Bar & Grill"),
]


def _descriptor_from_name(name: str) -> str:
    n = name.lower()
    for keys, label in _CUISINE_HINTS:
        if any(k in n for k in keys):
            return label
    return ""


def _geocode_cache_path() -> Path:
    return HERE / "data" / "geocode_cache.json"


def _load_geocode_cache() -> dict:
    p = _geocode_cache_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_geocode_cache(cache: dict) -> None:
    try:
        _geocode_cache_path().write_text(json.dumps(cache), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _reverse_address(lat, lon, ua: str, cache: dict) -> str:
    """Street address for a coordinate via OSM Nominatim (cached; throttled)."""
    key = f"{round(float(lat), 5)},{round(float(lon), 5)}"
    if key in cache:
        return cache[key]
    addr = ""
    try:
        time.sleep(1.1)  # Nominatim asks for at most 1 request/second
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2",
                    "addressdetails": 1},
            headers={"User-Agent": ua}, timeout=20)
        r.raise_for_status()
        a = r.json().get("address", {})
        road = a.get("road") or a.get("pedestrian") or a.get("neighbourhood") or ""
        num = a.get("house_number", "")
        addr = f"{num} {road}".strip() if road else ""
    except Exception as ex:  # noqa: BLE001
        logging.warning("Geocode failed for %s: %s", key, ex)
    cache[key] = addr
    return addr


def _forward_address(name: str, ua: str, cache: dict) -> str:
    """Street address for a restaurant name via Nominatim search (cached)."""
    key = "q:" + name.lower()
    if key in cache:
        return cache[key]
    addr = ""
    try:
        time.sleep(1.1)  # Nominatim asks for at most 1 request/second
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{name}, Fernandina Beach, FL", "format": "jsonv2",
                    "addressdetails": 1, "limit": 1,
                    "viewbox": "-81.49,30.73,-81.43,30.50", "bounded": 1},
            headers={"User-Agent": ua}, timeout=20)
        r.raise_for_status()
        res = r.json()
        if res:
            a = res[0].get("address", {})
            road = a.get("road") or a.get("pedestrian") or ""
            num = a.get("house_number", "")
            addr = f"{num} {road}".strip() if road else ""
    except Exception as ex:  # noqa: BLE001
        logging.warning("Forward geocode failed for %s: %s", name, ex)
    cache[key] = addr
    return addr


# --------------------------------------------------------------------------
# Weather (NWS) + tides (NOAA)
# --------------------------------------------------------------------------

def fetch_weather(cfg: dict) -> dict:
    w = cfg["weather"]
    base = f"https://api.weather.gov/gridpoints/{w['office']}/{w['gridX']},{w['gridY']}"
    out: dict = {"current": None, "days": []}
    try:
        periods = http_get(base + "/forecast", cfg).json()["properties"]["periods"]
        out["days"] = periods[:14]
    except Exception as ex:  # noqa: BLE001
        logging.warning("Weather forecast failed: %s", ex)
    try:
        hourly = http_get(base + "/forecast/hourly", cfg).json()["properties"]["periods"]
        if hourly:
            h0 = hourly[0]
            out["current"] = {
                "temp": h0.get("temperature"),
                "unit": h0.get("temperatureUnit", "F"),
                "short": h0.get("shortForecast", ""),
                "wind": f"{h0.get('windSpeed','')} {h0.get('windDirection','')}".strip(),
            }
    except Exception as ex:  # noqa: BLE001
        logging.warning("Weather hourly failed: %s", ex)
    # sunrise / sunset (free, no key)
    try:
        s = http_get(
            f"https://api.sunrise-sunset.org/json?lat={w['lat']}&lng={w['lon']}"
            "&formatted=0", cfg).json()["results"]
        out["sun"] = {
            "sunrise": parse_utc(s["sunrise"]).strftime("%-I:%M %p"),
            "sunset": parse_utc(s["sunset"]).strftime("%-I:%M %p"),
        }
    except Exception:  # noqa: BLE001
        out["sun"] = None
    return out


def fetch_tides(cfg: dict) -> dict:
    station = cfg["tides"]["station"]
    today = now_local()
    end = today + timedelta(days=cfg["days_ahead"])
    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
           f"product=predictions&application=AmeliaDashboard&datum=MLLW&"
           f"station={station}&time_zone=lst_ldt&units=english&interval=hilo&"
           f"format=json&begin_date={today:%Y%m%d}&end_date={end:%Y%m%d}")
    by_day: dict[str, list[dict]] = {}
    try:
        preds = http_get(url, cfg).json().get("predictions", [])
        for p in preds:
            dt = datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
            day = dt.strftime("%Y-%m-%d")
            by_day.setdefault(day, []).append({
                "time": dt.strftime("%-I:%M %p"),
                "type": "High" if p["type"] == "H" else "Low",
                "height": f"{float(p['v']):.1f} ft",
            })
    except Exception as ex:  # noqa: BLE001
        logging.warning("Tides failed: %s", ex)
    return by_day


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------

def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%a %b %-d, %-I:%M %p") if dt else ""


def group_by_day(events: list[dict], days: int) -> list[tuple[str, list[dict]]]:
    today = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    groups: list[tuple[str, list[dict]]] = []
    for i in range(days + 1):
        day = today + timedelta(days=i)
        label = "Today" if i == 0 else ("Tomorrow" if i == 1
                                        else day.strftime("%A"))
        label += day.strftime(" · %b %-d")
        todays = [e for e in events if e["date"] and e["date"].date() == day.date()]
        if todays:
            groups.append((label, todays))
    return groups


# --- fun emoji helpers -----------------------------------------------------

_MUSIC_ICONS = ["🎸", "🎤", "🎷", "🎺", "🪕", "🎻", "🥁", "🎹", "🎶", "🪗"]


def music_icon(title: str) -> str:
    """A stable-but-varied instrument icon, chosen from the title."""
    return _MUSIC_ICONS[sum(map(ord, title or "x")) % len(_MUSIC_ICONS)]


_CAT_ICONS = {
    "active-outdoors": "🏃", "arts-culture": "🎨", "community-civic": "🤝",
    "festivals-parades": "🎉", "food-drink": "🍽️", "games-trivia": "🎲",
    "shopping-markets": "🛍️", "other-events": "📌", "live-music": "🎶",
}


def category_icon(slug: str) -> str:
    return _CAT_ICONS.get(slug, "📌")


# keyword -> emoji, checked in order (most specific first) against title+category
_EVENT_ICON_RULES = [
    (("yoga", "pilates", "barre", "stretch", "meditat", "sound bath"), "🧘"),
    (("5k", "10k", "marathon", "run club", "run clubs", "fun run", "jog"), "🏃"),
    (("hike", "hiking", "trail walk", "nature walk"), "🥾"),
    (("bike", "cycl", "spin class"), "🚴"),
    (("swim", "aqua", "water aerobic"), "🏊"),
    (("workout", "fitness", "bootcamp", "crossfit", "zumba", "aerobic", "exercise"), "💪"),
    (("golf", "putt-putt", "putt putt"), "⛳"),
    (("tennis", "pickleball"), "🎾"),
    (("shotgun", "skeet", "clay", "shooting", "archery"), "🎯"),
    (("trivia", "quiz", "name that tune"), "🧠"),
    (("bingo",), "🔢"),
    (("poker", "cards", "blackjack", "casino"), "🃏"),
    (("chess",), "♟️"),
    (("cornhole", "darts"), "🎯"),
    (("board game", "game night", "dungeons", "mahjong", "games"), "🎲"),
    (("karaoke",), "🎤"),
    (("comedy", "stand-up", "stand up", "improv"), "🤣"),
    (("wine", "vineyard", "winery"), "🍷"),
    (("beer", "brewery", "brewing", "brew ", "ale house", "oktoberfest", "pint"), "🍺"),
    (("coffee", "espresso", "cafe con"), "☕"),
    (("bbq", "cookout", "cook-off", "chili", "food truck", "dinner", "brunch",
      "breakfast", "taste of", "culinary", "chef", "supper"), "🍽️"),
    (("book", "author", "reading", "story time", "storytime", "library", "literary"), "📚"),
    (("paint", "sip & paint", "pottery", "craft", "gallery", "exhibit", "art walk", "arts"), "🎨"),
    (("movie", "film", "cinema", "screening"), "🎬"),
    (("dance", "dancing", "ballet", "line dancing"), "💃"),
    (("theatre", "theater", "musical", "playhouse", "drama", "improv"), "🎭"),
    (("dog", "pet", "puppy", "paws", "k-9", "k9", "canine"), "🐕"),
    (("kid", "children", "family", "youth", "teen", "toddler"), "🧒"),
    (("church", "worship", "prayer", "bible", "faith", "mass", "gospel", "ministry"), "⛪"),
    (("museum", "history", "heritage", "historic", "genealog"), "🏛️"),
    (("cruise", "boat", "sail", "kayak", "paddle", "eco tour", "shark tooth", "fossil"), "⛵"),
    (("trolley", "tour", "walking tour", "ghost tour"), "🚎"),
    (("festival", "fest", "parade", "celebration"), "🎉"),
    (("fundrais", "charity", "benefit", "donat", "volunteer", "food drive", "blood drive"), "❤️"),
    (("meeting", "commission", "council", "government", "city hall", "board of",
      "committee", "hearing", "town hall", "civic"), "🏛️"),
    (("market", "farmers", "vendor", "bazaar", "flea"), "🛍️"),
    (("shop", "sale", "boutique", "pop-up", "pop up"), "🛍️"),
    (("class", "workshop", "seminar", "lesson", "lecture", "learn", "training"), "📖"),
    (("garden", "plant", "nature", "eco", "bird", "wildlife"), "🌿"),
    (("wellness", "spa", "massage", "reiki", "health", "self-care"), "💆"),
    (("holiday", "christmas", "halloween", "fourth of july", "july 4", "new year"), "🎊"),
]

_EVENT_CAT_ICONS = {
    "social": "🥳", "games": "🎲", "exercise": "💪", "markets": "🛍️",
    "government": "🏛️", "arts": "🎨", "community": "🤝", "food": "🍽️",
    "sports": "🏅", "outdoors": "🌲", "kids": "🧒", "wellness": "💆",
}


def _event_icon(e: dict) -> str:
    """Pick an emoji that fits the event, from its title + category."""
    text = ((e.get("title") or "") + " " + (e.get("category") or "")).lower()
    for keys, emoji in _EVENT_ICON_RULES:
        if any(k in text for k in keys):
            return emoji
    cat = (e.get("category") or "").lower()
    for key, emoji in _EVENT_CAT_ICONS.items():
        if key in cat:
            return emoji
    return category_icon(e.get("category_slug", ""))


def weather_emoji(short: str, is_day: bool = True) -> str:
    s = (short or "").lower()
    if any(k in s for k in ("thunder", "tstorm", "storm")):
        return "⛈️"
    if any(k in s for k in ("snow", "sleet", "flurr", "wintry", "ice")):
        return "🌨️"
    if any(k in s for k in ("rain", "shower", "drizzle")):
        return "🌧️"
    if any(k in s for k in ("fog", "haze", "mist", "smoke")):
        return "🌫️"
    if "partly" in s or "mostly sunny" in s:
        return "⛅"
    if any(k in s for k in ("mostly cloudy", "overcast", "cloud")):
        return "☁️"
    if any(k in s for k in ("clear", "sunny", "fair", "hot")):
        return "☀️" if is_day else "🌙"
    if "wind" in s:
        return "🌬️"
    return "☀️" if is_day else "🌙"


def _section(accent: str, icon: str, title: str, body: str,
             lead: str = "", extra: str = "") -> str:
    lead_html = f'<p class="lead">{lead}</p>' if lead else ""
    cls = "card" + (f" {extra}" if extra else "")
    return (f'<section class="{cls}" style="--accent:{accent}">'
            f'<h2><span class="badge">{icon}</span><span>{esc(title)}</span></h2>'
            f'{lead_html}{body}</section>')


# --- daily rotating "learn something" facts (no API needed) ------------------

_HISTORY_FACTS = [
    ("The Isle of Eight Flags", "Amelia Island is the only place in the United States to have flown eight different national flags — French, Spanish, British, Patriot, Green Cross of Florida, Mexican, Confederate, and American — earning it the nickname the “Isle of Eight Flags.”"),
    ("Named for a princess", "The island was named in 1735 by Georgia's founder James Oglethorpe in honor of Princess Amelia, a daughter of Britain's King George II."),
    ("Florida's northeast corner", "Fernandina Beach is the northernmost city on Florida's Atlantic coast, sitting just across the St. Marys River from Georgia."),
    ("Florida's oldest bar", "The Palace Saloon on Centre Street began serving in 1903 and is billed as Florida's oldest continuously operating drinking establishment."),
    ("Birthplace of modern shrimping", "Fernandina Beach is considered the cradle of the modern shrimping industry, where powered shrimp trawlers were pioneered in the early 1900s — still celebrated each spring at the Isle of Eight Flags Shrimp Festival."),
    ("Fort Clinch", "Begun in 1847 at the island's northern tip, brick-walled Fort Clinch was garrisoned during the Civil War and is now the centerpiece of a state park."),
    ("Yulee's railroad", "Senator David Levy Yulee completed the Florida Railroad in 1861, linking Fernandina on the Atlantic to Cedar Key on the Gulf — one of the first rail lines to cross the peninsula."),
    ("A Senate first", "David Levy Yulee, whose name lives on in the nearby town of Yulee, was the first person of Jewish heritage elected to the U.S. Senate."),
    ("A 50-block time capsule", "Downtown Fernandina's roughly 50-block core is a National Historic District, packed with ornate Victorian architecture from the seaport's 1880s boom."),
    ("New Fernandina", "The town was moved south from its original “Old Town” site in the 1850s to meet Yulee's new railroad terminus — today's downtown is sometimes still called “New Fernandina.”"),
    ("The oldest lighthouse", "The Amelia Island Lighthouse, built in 1838 from materials shipped over from an earlier Georgia light, is the oldest existing lighthouse in Florida."),
    ("American Beach", "On the island's south end, American Beach was founded in 1935 by the Afro-American Life Insurance Company as one of the few Atlantic beaches open to Black families during segregation."),
    ("The Beach Lady", "MaVynee Betsch, known as “the Beach Lady,” was a renowned environmentalist who devoted her life to preserving American Beach and its great dune, “NaNa.”"),
    ("Pirates and adventurers", "In 1817 Scottish soldier-of-fortune Gregor MacGregor seized the island and raised the Green Cross of Florida; months later privateer Luis Aury flew a Mexican republican flag over Fernandina."),
    ("Lights, camera, Amelia", "The 1988 film “The New Adventures of Pippi Longstocking” was shot on Amelia Island and around Fernandina Beach."),
    ("A blackwater border", "The St. Marys River marking the Florida–Georgia line is a blackwater river; its tea-colored water is stained by tannins draining from the Okefenokee Swamp."),
    ("A Gilded Age resort", "Before Henry Flagler's railroads pulled tourism south, Fernandina's deep harbor made it a fashionable Gilded Age winter resort reached by steamship."),
    ("Jail turned museum", "The Amelia Island Museum of History is housed in the former Nassau County jail and was one of Florida's first “spoken history” museums."),
    ("The Patriots of 1812", "In 1812 the short-lived “Patriots of Amelia Island,” quietly encouraged by the U.S., raised their own flag in a bid to pry the island from Spain."),
    ("Centre Street", "Downtown's main street was laid out to connect the riverfront harbor directly to the railroad depot, tying ships to trains in the island's heyday."),
]

_MARINE_FACTS = [
    ("Right whale nursery", "The waters off northeast Florida are the only known calving ground for the critically endangered North Atlantic right whale — fewer than 400 remain, and mothers arrive each winter to give birth."),
    ("Loggerheads come home", "Loggerhead sea turtles nest on Amelia Island's beaches each summer, and females return to lay eggs on the very beach where they hatched, navigating partly by Earth's magnetic field."),
    ("The mighty marsh", "Florida's salt marshes, ruled by smooth cordgrass (Spartina), are among the most productive ecosystems on Earth, serving as nurseries for shrimp, crabs, and fish."),
    ("Dolphins that beach themselves", "In the region's tidal creeks, bottlenose dolphins practice rare “strand feeding” — herding fish onto a muddy bank and briefly sliding out of the water to grab them."),
    ("A living fossil", "The Atlantic horseshoe crab has changed little in about 450 million years — older than the dinosaurs — and its blue, copper-based blood is used to test medicines for contamination."),
    ("Gentle sea cows", "Manatees are plant-eating marine mammals that graze on seagrass; because they can't tolerate cold, they crowd into warm springs and power-plant outflows each Florida winter."),
    ("Fiddlers in the mud", "Male fiddler crabs wave one giant claw to court mates and guard their burrows — whole colonies will “fiddle” together across the marsh at low tide."),
    ("Oysters clean the water", "A single adult eastern oyster can filter up to 50 gallons of water a day, and their reefs create habitat for countless other creatures."),
    ("The shrimp's journey", "The white shrimp that made Fernandina famous hatch offshore, ride the tides into the marsh estuaries to grow up, then return to the sea — a life cycle the marsh makes possible."),
    ("Beautiful savory swimmer", "The blue crab's scientific name, Callinectes sapidus, literally means “beautiful savory swimmer” — a nod to its paddle legs and its place on the dinner table."),
    ("Guardians of the dunes", "Sea oats, the tall grasses nodding atop the dunes, are protected by Florida law; their deep roots bind the sand and form the island's first defense against storm surge."),
    ("Where rivers meet the sea", "Estuaries like those around Amelia Island mix fresh river water with salt water, and this brackish blend is the nursery for most commercially important Atlantic fish."),
    ("Ghosts of the beach", "Pale ghost crabs that dart across the sand at night have stalked eyes giving nearly 360-degree vision, and they can lighten or darken to match the beach."),
    ("Seeing with sound", "Bottlenose dolphins use echolocation — rapid clicks whose echoes let them “see” fish even in the region's murky, tannin-stained water."),
    ("Vegetarian turtles", "Green sea turtles, another Florida nester, are unusual reptiles in that adults are mostly vegetarian, grazing on seagrass and algae."),
    ("Slow down for whales", "Right whale calves are so easily struck by ships that seasonal slow-speed zones are enforced along the northeast Florida coast every winter."),
    ("Do the stingray shuffle", "Rays cruise the warm shallows here; shuffling your feet along the bottom instead of stepping down nudges them out of the way and prevents a painful sting."),
    ("Salt-sweating grass", "Spartina marsh grass pushes excess salt out through special glands, and on a hot day you can spot tiny salt crystals sparkling on its blades."),
    ("Pelican power dives", "Brown pelicans plunge bill-first from as high as 60 feet; air sacs beneath their skin cushion the impact and pop them back to the surface."),
    ("Nursery for sharks", "Several shark species use northeast Florida's calm, food-rich estuaries as nurseries, where young sharks grow up safe from larger ocean predators."),
]


def _daily_pick(items: list) -> dict:
    """Deterministically rotate through items by calendar day."""
    return items[now_local().toordinal() % len(items)]


def _daily_pick_fact(items: list) -> dict:
    """Rotate daily, but prefer entries that have a picture so the section
    always shows an image (falls back to the full pool if none do)."""
    withimg = [f for f in items if f.get("image")]
    pool = withimg or items
    return pool[now_local().toordinal() % len(pool)] if pool else {}


# --- rotating landscape banner (Wikimedia Commons image search) --------------

def _commons_images(query: str, ua: str, exclude: list[str], limit: int = 15) -> list[dict]:
    params = {
        "action": "query", "format": "json", "formatversion": 2,
        "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|size|mime", "iiurlwidth": 1400,
    }
    r = requests.get("https://commons.wikimedia.org/w/api.php", params=params,
                     headers={"User-Agent": ua}, timeout=30)
    r.raise_for_status()
    out = []
    for pg in r.json().get("query", {}).get("pages", []):
        ii = (pg.get("imageinfo") or [None])[0]
        if not ii or ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if not (w and h and w >= h * 1.3 and w >= 1200):  # landscape, sizable
            continue
        if any(b in pg.get("title", "").lower() for b in exclude):
            continue
        url = ii.get("thumburl") or ii.get("url")
        if url:
            out.append({"url": url, "descurl": ii.get("descriptionurl")})
    return out


def fetch_banners(cfg: dict) -> list[dict]:
    bc = cfg.get("banner", {})
    if not bc.get("enabled", True):
        return []
    cache = HERE / "data" / "banners_cache.json"
    refresh = bc.get("refresh_days", 7)

    def _read():
        try:
            c = json.loads(cache.read_text())
            return c if c.get("images") else None
        except Exception:  # noqa: BLE001
            return None

    cached = _read() if cache.exists() else None
    if cached:
        try:
            age = now_local().toordinal() - datetime.fromisoformat(
                cached["built"]).toordinal()
        except Exception:  # noqa: BLE001
            age = refresh + 1
        if age < refresh:
            return cached["images"]

    ua = f"AmeliaDashboard/1.0 ({cfg.get('contact_email','')})"
    exclude = [e.lower() for e in bc.get("exclude", [])]
    try:
        cap = bc.get("per_query_cap", 6)
        seen, imgs = set(), []
        for q in bc.get("queries", []):
            added = 0
            for im in _commons_images(q, ua, exclude):
                if im["url"] in seen:
                    continue
                seen.add(im["url"])
                imgs.append(im)
                added += 1
                if added >= cap:
                    break
        if imgs:
            cache.write_text(json.dumps(
                {"built": now_local().date().isoformat(), "images": imgs}))
            logging.info("Banner: %d landscape images from Commons", len(imgs))
            return imgs
    except Exception as ex:  # noqa: BLE001
        logging.warning("Banner images failed: %s", ex)

    return cached["images"] if cached else []


def _banner_html(images: list[dict]) -> str:
    if not images:
        return ""
    b = _daily_pick(images)
    cap = (f'<a class="bcap" href="{esc(b["descurl"])}" target="_blank" '
           f'rel="noopener">📷 Amelia Island · Wikimedia Commons</a>'
           if b.get("descurl") else "")
    return (f'<div class="hero-banner"><img src="{esc(b["url"])}" '
            f'alt="Amelia Island landscape" loading="lazy">{cap}</div>')


def _fact_html(fact: dict) -> str:
    src = (f'<a class="factsrc" href="{esc(fact["url"])}" target="_blank" '
           f'rel="noopener">via Wikipedia ↗</a>' if fact.get("url") else "")
    img = (f'<img class="factimg" src="{esc(fact["image"])}" alt="{esc(fact["title"])}" '
           f'loading="lazy">' if fact.get("image") else "")
    return (f'<div class="factcard">{img}'
            f'<div class="factttl">{esc(fact["title"])}</div>'
            f'<p class="facttxt">{esc(fact["text"])}</p>{src}</div>')


# --- Wikipedia-sourced fact pool (with curated fallback) ---------------------

_ABBR = ["St", "Dr", "Mr", "Mrs", "Ms", "Mt", "No", "vs", "Jr", "Sr", "Inc",
         "Ltd", "approx", "ca", "cf", "al", "Fig", "Gen", "Col", "Capt"]


def _protect_abbr(t: str) -> str:
    """Mask abbreviation periods so they don't look like sentence ends."""
    t = re.sub(r"\b([A-Z])\.", r"\1∙", t)              # initials: U. S. T.
    t = re.sub(r"\b([a-z])\.(?=\s+[a-z])", r"\1∙", t)  # subspecies: m.
    for a in _ABBR:
        t = re.sub(rf"\b{a}\.", a + "∙", t)
    for a in ("e.g", "i.e", "etc"):
        t = t.replace(a + ".", a.replace(".", "∙") + "∙")
    return t


def _clean_text(text: str) -> str:
    text = re.sub(r"\([^)]*[/ˈːˌ][^)]*\)", "", text)  # IPA parentheticals
    text = re.sub(r"\((?:listen|pronounced|born|US|UK)[^)]*\)", "", text, flags=re.I)
    text = re.sub(r"\[[0-9]+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,;:.!?])", r"\1", text)  # tidy space before punctuation


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])",
                     _protect_abbr(_clean_text(text)))
    out = []
    for s in parts:
        s = s.replace("∙", ".").strip()
        if not 25 <= len(s) <= 400 or not re.search(r"[.!?]$", s):
            continue
        if re.search(r"(may refer to|disambiguation|redirects here|coordinates)",
                     s, re.I):
            continue
        out.append(s)
    return out


def _passages_from_extract(text: str, target: int = 430, hardmax: int = 660) -> list[str]:
    """Group sentences into short multi-sentence passages for richer facts."""
    passages, cur = [], ""
    for s in _split_sentences(text):
        if not cur:
            cur = s
        elif len(cur) + 1 + len(s) <= hardmax:
            cur += " " + s
            if len(cur) >= target:
                passages.append(cur)
                cur = ""
        else:
            passages.append(cur)
            cur = s
    if len(cur) >= 140:
        passages.append(cur)
    return passages


def _wiki_extracts(titles: list[str], ua: str, intro: bool = True) -> dict:
    """{title: {"extract": str, "image": url|None}} for each existing article.
    intro=True fetches just the lead section; intro=False the whole article."""
    out = {}
    step = 20 if intro else 1  # full-article extracts must be fetched one at a time
    for i in range(0, len(titles), step):
        params = {
            "action": "query", "format": "json", "formatversion": 2,
            "prop": "extracts|pageimages", "explaintext": 1,
            "redirects": 1, "piprop": "thumbnail", "pithumbsize": 500,
            "titles": "|".join(titles[i:i + step]),
        }
        if intro:
            params["exintro"] = 1
        r = requests.get("https://en.wikipedia.org/w/api.php", params=params,
                         headers={"User-Agent": ua}, timeout=30)
        r.raise_for_status()
        for pg in r.json().get("query", {}).get("pages", []):
            if not pg.get("missing") and pg.get("extract"):
                out[pg["title"]] = {
                    "extract": pg["extract"],
                    "image": (pg.get("thumbnail") or {}).get("source"),
                }
    return out


def _build_facts(titles: list[str], ua: str, intro: bool = True,
                 region_terms: list[str] = None, seen: set = None) -> list[dict]:
    seen = seen if seen is not None else set()
    facts = []
    for title, info in _wiki_extracts(titles, ua, intro=intro).items():
        url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
        for s in _passages_from_extract(info["extract"]):
            if region_terms and not any(t in s.lower() for t in region_terms):
                continue
            k = s[:60].lower()
            if k in seen:
                continue
            seen.add(k)
            facts.append({"title": title, "text": s,
                          "image": info.get("image"), "url": url})
    return facts


def _build_context_facts(titles: list[str], ua: str, region_terms: list[str],
                         seen: set) -> list[dict]:
    """For broad people/events: lead with the article's opening 'who/what'
    sentence, then a passage that ties them to the island/area."""
    facts = []
    for title, info in _wiki_extracts(titles, ua, intro=False).items():
        sents = _split_sentences(info["extract"])
        if not sents:
            continue
        lead = sents[0]
        if not lead.endswith((".", "!", "?")):
            lead += "."
        url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
        for p in _passages_from_extract(info["extract"], target=300, hardmax=470):
            if not any(t in p.lower() for t in region_terms):
                continue
            text = p if lead.lower() in p.lower() else f"{lead} {p}"
            k = text[:70].lower()
            if k in seen:
                continue
            seen.add(k)
            facts.append({"title": title, "text": text,
                          "image": info.get("image"), "url": url})
    return facts


def _facts_fallback() -> dict:
    return {
        "history": [{"title": t, "text": x, "url": None, "image": None}
                    for t, x in _HISTORY_FACTS],
        "marine": [{"title": t, "text": x, "url": None, "image": None}
                   for t, x in _MARINE_FACTS],
    }


def fetch_facts(cfg: dict) -> dict:
    fc = cfg.get("facts", {})
    if fc.get("source", "wikipedia") != "wikipedia":
        return _facts_fallback()
    cache = HERE / "data" / "facts_cache.json"
    refresh = fc.get("refresh_days", 7)

    def _read_cache():
        try:
            c = json.loads(cache.read_text())
            if c.get("history") and c.get("marine"):
                return c
        except Exception:  # noqa: BLE001
            return None
        return None

    cached = _read_cache() if cache.exists() else None
    if cached:
        try:
            age = now_local().toordinal() - datetime.fromisoformat(
                cached["built"]).toordinal()
        except Exception:  # noqa: BLE001
            age = refresh + 1
        if age < refresh:
            return {"history": cached["history"], "marine": cached["marine"]}

    ua = f"AmeliaDashboard/1.0 ({cfg.get('contact_email','')})"
    region = [t.lower() for t in fc.get("region_terms", [])]
    try:
        hseen: set = set()
        history = _build_facts(fc.get("history_titles", []), ua, seen=hseen)
        history += _build_context_facts(fc.get("history_context_titles", []),
                                        ua, region, hseen)
        marine = _build_facts(fc.get("marine_titles", []), ua)
        pools = {"history": history, "marine": marine}
        if pools["history"] and pools["marine"]:
            cache.write_text(json.dumps(
                {"built": now_local().date().isoformat(), **pools}))
            logging.info("Facts: %d history, %d marine from Wikipedia",
                         len(history), len(marine))
            return pools
    except Exception as ex:  # noqa: BLE001
        logging.warning("Wikipedia facts failed: %s", ex)

    if cached:
        logging.info("Facts: using cached pool")
        return {"history": cached["history"], "marine": cached["marine"]}
    logging.info("Facts: using curated fallback")
    return _facts_fallback()


def render_html(cfg: dict, data: dict) -> str:
    loc = esc(cfg["location_name"])
    generated = now_local().strftime("%A, %B %-d, %Y · %-I:%M %p ET")
    days = cfg["days_ahead"]

    # --- header weather/tide strip ---
    cur = data["weather"].get("current")
    sun = data["weather"].get("sun")
    strip = []
    if cur:
        strip.append(f'<span class="chip"><span class="ci">'
                     f'{weather_emoji(cur["short"])}</span> {esc(cur["temp"])}°'
                     f'{esc(cur["unit"])} · {esc(cur["short"])}</span>')
    if cur and cur.get("wind"):
        strip.append(f'<span class="chip"><span class="ci">💨</span> '
                     f'{esc(cur["wind"])}</span>')
    if sun:
        strip.append(f'<span class="chip"><span class="ci">🌅</span> '
                     f'Sunrise {esc(sun["sunrise"])}</span>')
        strip.append(f'<span class="chip"><span class="ci">🌇</span> '
                     f'Sunset {esc(sun["sunset"])}</span>')
    today_key = now_local().strftime("%Y-%m-%d")
    todays_tides = data["tides"].get(today_key, [])
    if todays_tides:
        tide_txt = " · ".join(
            f'{t["type"]} {t["time"]}' for t in todays_tides)
        strip.append(f'<span class="chip"><span class="ci">🌊</span> '
                     f'{esc(tide_txt)}</span>')
    strip_html = "".join(strip) or '<span class="chip muted">Live conditions unavailable</span>'

    # --- live music (hero) ---  (no category tags: it's all music here)
    music_html = _render_event_days(data["music"], days, show_tags=False,
                                    icon_kind="music",
                                    empty="No live-music listings found for the week.")
    # --- other events ---
    events_html = _render_event_days(data["events"], days, show_tags=True,
                                     icon_kind="category",
                                     empty="No other events listed this week.")

    # --- news ---
    if data["news"]:
        rows = []
        for it in data["news"]:
            when = _fmt_dt(it["published"])
            rows.append(
                f'<li><a href="{esc(it["link"])}" target="_blank" rel="noopener">'
                f'{esc(it["title"])}</a>'
                f'<span class="meta">{esc(it["source"])}'
                f'{" · " + esc(when) if when else ""}</span></li>')
        news_html = '<ul class="linklist">' + "".join(rows) + "</ul>"
    else:
        news_html = '<p class="muted">News feed unavailable right now.</p>'

    # --- restaurants ---
    restaurants_html = _render_restaurants(data["restaurants"])

    # --- weather 7-day ---
    # pair each daytime period with its following night into one day-block
    blocks: list[dict] = []
    cur = None
    for p in data["weather"]["days"]:
        if p.get("isDaytime", True):
            cur = {"label": p.get("name", ""), "day": p, "night": None}
            blocks.append(cur)
        elif cur and cur["night"] is None and cur["day"] is not None:
            cur["night"] = p
        else:  # a leading night period (e.g. "Tonight") with no daytime part
            cur = {"label": p.get("name", ""), "day": None, "night": p}
            blocks.append(cur)

    def _whalf(p: dict, is_day: bool) -> str:
        emoji = weather_emoji(p.get("shortForecast", ""), is_day)
        cls = "whalf wday" if is_day else "whalf wnight"
        return (f'<div class="{cls}"><div class="wplabel">'
                f'{"Day" if is_day else "Night"}</div>'
                f'<div class="wemoji">{emoji}</div>'
                f'<div class="wtemp">{esc(p.get("temperature",""))}°</div>'
                f'<div class="wshort">{esc(p.get("shortForecast",""))}</div></div>')

    wcards = []
    for b in blocks:
        halves = ""
        if b["day"]:
            halves += _whalf(b["day"], True)
        if b["night"]:
            halves += _whalf(b["night"], False)
        wcards.append(f'<div class="wcard"><div class="wname">{esc(b["label"])}'
                      f'</div><div class="wsplit">{halves}</div></div>')
    weather_html = ('<div class="wgrid">' + "".join(wcards) + "</div>"
                    if wcards else '<p class="muted">Forecast unavailable.</p>')

    # --- tides table ---
    trows = []
    for i in range(days + 1):
        day = (now_local() + timedelta(days=i))
        key = day.strftime("%Y-%m-%d")
        tides = data["tides"].get(key, [])
        if not tides:
            continue
        label = "Today" if i == 0 else day.strftime("%a %b %-d")
        cells = " ".join(
            f'<span class="tide {t["type"].lower()}">'
            f'{"▲" if t["type"]=="High" else "▼"} {esc(t["time"])} '
            f'<em>{esc(t["height"])}</em></span>' for t in tides)
        trows.append(f'<div class="trow"><div class="tday">{esc(label)}</div>'
                     f'<div class="tcells">{cells}</div></div>')
    tides_html = ("".join(trows) if trows
                  else '<p class="muted">Tide predictions unavailable.</p>')

    shows = len(data["music"])

    def _panel(key: str, inner: str) -> str:
        return f'<div class="panel" data-panel="{key}">{inner}</div>'

    # Tab bar. "weather" is the default view; "all" shows every panel stacked
    # (the original long-scroll view).
    tabs_def = [
        ("weather", "🌤️", "Weather &amp; Tides"),
        ("music", "🎶", "Live Music"),
        ("events", "📅", "Events"),
        ("eats", "🍽️", "Bars &amp; Restaurants"),
        ("news", "📰", "News"),
        ("learn", "📜", "Island &amp; Sea"),
        ("all", "🗂️", "Everything"),
    ]
    tabbar = '<nav class="tabbar">' + "".join(
        f'<button class="tabbtn{" active" if key == "weather" else ""}" '
        f'data-tab="{key}"><span class="tabico">{ico}</span>{label}</button>'
        for key, ico, label in tabs_def) + '</nav>'

    body = (
        _banner_html(data.get("banners", []))
        + tabbar
        + _panel("weather",
                 '<div class="cols2">'
                 + _section("#f4a11a", "☀️", "Weather", weather_html)
                 + _section("#048ba8", "🌊", "Tides", tides_html,
                            lead="High &amp; low tides · Fernandina Beach")
                 + '</div>')
        + _panel("music",
                 _section("#2f8fd4", "🎶", "Live Music This Week", music_html,
                          lead=f"{shows} shows over the next {days} days across "
                               f"local venues 🎉", extra="hero"))
        + _panel("events",
                 _section("#9b5de5", "📅", "Other Events This Week", events_html))
        + _panel("news",
                 _section("#00a6fb", "📰", "Local News", news_html,
                          lead="Fresh Amelia Island &amp; Fernandina Beach headlines."))
        + _panel("learn",
                 '<div class="cols2">'
                 + _section("#b07d3f", "📜", "Island History",
                            _fact_html(_daily_pick_fact(data["facts"]["history"])),
                            lead="A local history nugget, refreshed daily.")
                 + _section("#1fbfa9", "🐚", "Florida Marine Life",
                            _fact_html(_daily_pick_fact(data["facts"]["marine"])),
                            lead="Fish, mammals, birds, invertebrates &amp; plants "
                                 "— a new one daily.")
                 + '</div>')
        + _panel("eats",
                 _section("#2f6f9e", "🍽️", "Bars and Restaurants", restaurants_html,
                          lead="Every bar and restaurant on the island — tap a card "
                               "for details, or filter by type below."))
        + _TABS_JS
    )
    return _html_page(loc, esc(generated), strip_html, body)


_TABS_JS = """<script>
(function(){
  var btns=[].slice.call(document.querySelectorAll('.tabbtn'));
  var panels=[].slice.call(document.querySelectorAll('.panel'));
  if(!btns.length||!panels.length) return;
  function show(key, scroll){
    panels.forEach(function(p){
      var on=(key==='all')||(p.getAttribute('data-panel')===key);
      p.style.display=on?'':'none';
    });
    btns.forEach(function(b){
      b.classList.toggle('active', b.getAttribute('data-tab')===key);
    });
    try{ history.replaceState(null,'','#'+key); }catch(e){}
    if(scroll) window.scrollTo({top:0,behavior:'smooth'});
  }
  btns.forEach(function(b){
    b.addEventListener('click',function(){ show(b.getAttribute('data-tab'), true); });
  });
  var want=(location.hash||'').replace('#','');
  var ok=btns.some(function(b){ return b.getAttribute('data-tab')===want; });
  show(ok?want:'weather', false);
})();
</script>"""


# broad cuisine buckets for the filter chips: (label, slug, matching keywords)
_RCATEGORIES = [
    ("American", "american", ["american", "burger", "steak", "chophouse"]),
    ("Seafood", "seafood", ["seafood", "oyster", "crab", "fish"]),
    ("Pizza", "pizza", ["pizza"]),
    ("Italian", "italian", ["italian", "pasta"]),
    ("Mexican & Latin", "latin", ["mexican", "latin", "cuban"]),
    ("Asian", "asian", ["thai", "chinese", "japanese", "sushi", "bao",
                        "ramen", "asian", "noodle"]),
    ("Indian", "indian", ["indian"]),
    ("BBQ & Southern", "bbq", ["bbq", "barbecue", "southern", "smokehouse"]),
    ("Bar & Brewpub", "bar", ["bar", "pub", "brewpub", "tavern", "saloon",
                              "brew", "irish", "cocktail"]),
    ("Café & Bakery", "cafe", ["cafe", "café", "coffee", "bakery", "ice cream",
                               "creamery", "donut", "dessert"]),
    ("Breakfast & Brunch", "brunch", ["breakfast", "brunch", "diner", "bistro"]),
    ("Deli & Sandwiches", "deli", ["deli", "sandwich", "sub"]),
    ("Carryout & Market", "market", ["carryout", "market", "prepared"]),
]


_ASIAN_MARKERS = ("japanese", "hibachi", "teppanyaki", "sushi", "korean",
                  "thai", "chinese", "ramen", "asian", "bao", "noodle")


def _restaurant_cats(cuisine: str) -> list[str]:
    c = (cuisine or "").lower()
    # "Latin/South/Central American" is not American-food; don't let the word
    # "american" inside it trip the American bucket.
    c_american = (c.replace("latin american", "").replace("south american", "")
                  .replace("central american", ""))
    asian_context = any(a in c for a in _ASIAN_MARKERS)
    slugs = []
    for _label, slug, keys in _RCATEGORIES:
        if slug == "american":
            text = c_american
            # a steakhouse that's actually Asian (hibachi) belongs under Asian
            if asian_context:
                keys = [k for k in keys if k not in ("steak", "chophouse")]
        else:
            text = c
        if any(k in text for k in keys):
            slugs.append(slug)
    return slugs or ["other"]


def _render_restaurants(items: list[dict]) -> str:
    if not items:
        return '<p class="muted">Restaurant list unavailable right now.</p>'
    type_label = {"cafe": "Café", "fast_food": "Fast food"}
    cards = []
    counts: dict[str, int] = {}
    for r in items:
        cats = _restaurant_cats(r["cuisine"])
        for s in cats:
            counts[s] = counts.get(s, 0) + 1
        tag = r["cuisine"] or type_label.get(r["amenity"], "")
        tag_html = f'<span class="rtag">{esc(tag)}</span>' if tag else ""
        meta = (f'<div class="rmeta">{esc(r["street"])}</div>'
                if r.get("street") else "")
        yelp = ("https://www.yelp.com/search?find_desc="
                + quote_plus(r["name"]) + "&find_loc="
                + quote_plus("Fernandina Beach, FL"))
        cards.append(
            f'<div class="rcard" data-cats="{esc(" ".join(cats))}">'
            f'<a class="rname" href="{esc(r["url"])}" target="_blank" '
            f'rel="noopener">{esc(r["name"])}</a>{tag_html}{meta}'
            f'<a class="ryelp" href="{esc(yelp)}" target="_blank" '
            f'rel="noopener">Yelp ↗</a></div>')

    total = len(items)
    chips = [f'<button class="rf active" data-cat="all">All ({total})</button>']
    for label, slug, _keys in _RCATEGORIES:
        if counts.get(slug):
            chips.append(f'<button class="rf" data-cat="{slug}">'
                         f'{esc(label)} ({counts[slug]})</button>')
    if counts.get("other"):
        chips.append(f'<button class="rf" data-cat="other">Other '
                     f'({counts["other"]})</button>')

    bar = (f'<div class="rbar"><div class="rcount"><strong id="r-count">{total}'
           f'</strong> locations</div><div class="rfilters">'
           + "".join(chips) + '</div></div>')
    grid = '<div class="rgrid" id="rgrid">' + "".join(cards) + "</div>"
    return bar + grid + _RESTAURANT_JS


_RESTAURANT_JS = """<script>
(function(){
  var grid=document.getElementById('rgrid');
  if(!grid) return;
  var cards=[].slice.call(grid.querySelectorAll('.rcard'));
  var btns=[].slice.call(document.querySelectorAll('.rf'));
  var countEl=document.getElementById('r-count');
  btns.forEach(function(b){
    b.addEventListener('click',function(){
      btns.forEach(function(x){x.classList.remove('active');});
      b.classList.add('active');
      var cat=b.getAttribute('data-cat'), shown=0;
      cards.forEach(function(c){
        var cats=' '+(c.getAttribute('data-cats')||'')+' ';
        var match=(cat==='all')||cats.indexOf(' '+cat+' ')>=0;
        c.style.display=match?'':'none';
        if(match) shown++;
      });
      if(countEl) countEl.textContent=shown;
    });
  });
})();
</script>"""


def _render_event_days(events: list[dict], days: int, empty: str,
                       show_tags: bool = True, icon_kind: str = "category") -> str:
    groups = group_by_day(events, days)
    if not groups:
        return f'<p class="muted">{esc(empty)}</p>'
    out = []
    for label, evs in groups:
        rows = []
        for e in evs:
            icon = (music_icon(e["title"]) if icon_kind == "music"
                    else _event_icon(e))
            venue = f' <span class="at">@ {esc(e["venue"])}</span>' if e["venue"] else ""
            cat = (f'<span class="tag">{esc(e["category"])}</span>'
                   if show_tags and e["category"]
                   and e["category_slug"] != "live-music" else "")
            rows.append(
                f'<li><span class="time">{esc(e["time_str"])}</span>'
                f'<span class="ico">{icon}</span>'
                f'<span class="ev"><a href="{esc(e["url"])}" target="_blank" '
                f'rel="noopener">{esc(e["title"])}</a>{venue} {cat}</span></li>')
        out.append(f'<div class="day"><h3>{esc(label)}</h3>'
                   f'<ul class="events">' + "".join(rows) + "</ul></div>")
    return "".join(out)


_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600;700;800&'
    'family=Fredoka:wght@500;600;700&family=Nunito:wght@400;600;700;800&'
    'display=swap" rel="stylesheet">'
)

_CSS = """
  :root{
    --bg1:#fff8ee; --bg2:#e6f5fb; --ink:#243b4a; --muted:#6b8393;
    --card:#ffffff; --line:#ece2d2; --accent:#ff6b6b;
    --shadow:0 2px 6px rgba(36,59,74,.07),0 12px 30px rgba(36,59,74,.08);
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg1:#0b1620; --bg2:#0a1a24; --ink:#e9f0f5; --muted:#9fb4c1;
           --card:#152230; --line:#26384a;
           --shadow:0 2px 6px rgba(0,0,0,.4),0 14px 34px rgba(0,0,0,.42); }
  }
  *{ box-sizing:border-box; }
  body{ margin:0; color:var(--ink);
    background:linear-gradient(160deg,var(--bg1),var(--bg2)); background-attachment:fixed;
    font-family:"Nunito",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    font-size:17px; line-height:1.55; -webkit-font-smoothing:antialiased; }
  .wrap{ max-width:1440px; margin:0 auto; padding:20px 24px 72px; }
  @media (max-width:640px){ .wrap{ padding:16px 14px 60px; } }

  .tabbar{ position:sticky; top:0; z-index:30; margin:18px 0 2px; padding:10px 12px;
    display:flex; flex-wrap:wrap; gap:8px; justify-content:center;
    background:color-mix(in srgb, var(--card) 86%, transparent);
    -webkit-backdrop-filter:saturate(150%) blur(10px);
    backdrop-filter:saturate(150%) blur(10px);
    border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); }
  .tabbtn{ font-family:"Fredoka",sans-serif; font-weight:600; font-size:.88rem;
    cursor:pointer; border:1px solid var(--line); background:var(--card);
    color:var(--muted); padding:7px 15px; border-radius:999px;
    display:inline-flex; align-items:center; gap:7px; white-space:nowrap;
    transition:background .12s, color .12s, border-color .12s; }
  .tabbtn:hover{ color:var(--ink); border-color:#2f8fd4; }
  .tabbtn.active{ background:#17475a; border-color:#17475a; color:#fff; }
  .tabico{ font-size:1.1em; line-height:1; }
  @media (max-width:640px){ .tabbtn{ font-size:.8rem; padding:6px 11px; } }

  header.top{ position:relative; border-radius:22px; overflow:hidden; color:#fff;
    background:linear-gradient(135deg,#0e2633 0%,#17475a 60%,#1d5866 100%);
    box-shadow:var(--shadow); padding:32px 30px 52px; }
  .top-inner{ position:relative; z-index:2; }
  header.top h1{ font-family:"Poppins",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    font-weight:800; margin:0; font-size:2.5rem; line-height:1.06; letter-spacing:-.022em; }
  header.top .sub{ margin-top:9px; font-weight:600; font-size:.95rem; opacity:.82;
    letter-spacing:.005em; }
  .strip{ display:flex; flex-wrap:wrap; gap:9px; margin-top:16px; }
  .chip{ background:rgba(255,255,255,.24); border:1px solid rgba(255,255,255,.4);
    color:#fff; padding:6px 14px; border-radius:999px; font-size:.88rem; font-weight:700;
    white-space:nowrap; display:inline-flex; align-items:center; gap:5px; }
  .chip.muted{ opacity:.9; }
  .ci{ font-size:1.45em; line-height:1;
    filter:drop-shadow(0 1px 2px rgba(0,0,0,.35)); }
  .wave{ position:absolute; left:0; right:0; bottom:-1px; z-index:1; line-height:0; }
  .wave svg{ display:block; width:100%; height:40px; }
  .wave svg path{ fill:var(--bg1); }

  .hero-banner{ position:relative; margin-top:16px; border-radius:20px; overflow:hidden;
    box-shadow:var(--shadow); border:1px solid var(--line); background:var(--line); }
  .hero-banner img{ display:block; width:100%; height:300px; object-fit:cover; }
  @media (max-width:900px){ .hero-banner img{ height:230px; } }
  .bcap{ position:absolute; right:10px; bottom:9px; background:rgba(0,0,0,.5); color:#fff;
    font-size:.72rem; font-weight:700; padding:4px 10px; border-radius:999px;
    text-decoration:none; }
  .bcap:hover{ background:rgba(0,0,0,.68); }
  @media (max-width:520px){ .hero-banner img{ height:175px; } }

  section.card{ position:relative; background:var(--card); border:1px solid var(--line);
    border-top:5px solid var(--accent); border-radius:20px; padding:20px 22px; margin-top:20px;
    box-shadow:var(--shadow); }
  section.card>h2{ font-family:"Fredoka",sans-serif; font-weight:600; margin:0 0 6px;
    font-size:1.42rem; display:flex; align-items:center; gap:12px; }
  .badge{ display:inline-flex; align-items:center; justify-content:center;
    width:42px; height:42px; border-radius:50%; font-size:1.25rem; flex:0 0 auto;
    background:color-mix(in srgb, var(--accent) 18%, transparent);
    box-shadow:inset 0 0 0 2px color-mix(in srgb, var(--accent) 38%, transparent); }
  .lead{ color:var(--muted); font-size:.92rem; font-weight:700; margin:2px 0 14px; }
  .hero{ border-top-width:7px; }

  .day{ margin-top:16px; }
  .day:first-of-type{ margin-top:4px; }
  .day h3{ display:inline-block; margin:0 0 8px; font-family:"Fredoka",sans-serif;
    font-weight:600; font-size:.8rem; text-transform:uppercase; letter-spacing:.05em;
    color:var(--accent); background:color-mix(in srgb,var(--accent) 15%, transparent);
    padding:4px 13px; border-radius:999px; }
  ul.events{ list-style:none; margin:0; padding:0; }
  ul.events li{ display:flex; align-items:baseline; gap:10px; padding:9px 8px;
    border-radius:12px; border-bottom:1px dashed var(--line); transition:background .15s; }
  ul.events li:last-child{ border-bottom:none; }
  ul.events li:hover{ background:color-mix(in srgb,var(--accent) 8%, transparent); }
  .time{ flex:0 0 76px; color:var(--accent); font-weight:800; font-size:.8rem;
    font-variant-numeric:tabular-nums; }
  .ico{ flex:0 0 auto; font-size:1.1rem; }
  .ev{ flex:1; }
  .ev a{ color:var(--ink); text-decoration:none; font-weight:800; }
  .ev a:hover{ color:var(--accent); }
  .at{ color:var(--muted); font-weight:700; }
  .tag{ display:inline-block; font-family:"Fredoka",sans-serif; font-size:.64rem;
    text-transform:uppercase; letter-spacing:.04em; font-weight:600;
    background:color-mix(in srgb,var(--accent) 13%, transparent); color:var(--accent);
    padding:2px 9px; border-radius:999px; margin-left:5px; vertical-align:2px; }

  ul.linklist{ list-style:none; margin:0; padding:0; }
  ul.linklist li{ padding:11px 2px; border-bottom:1px solid var(--line); }
  ul.linklist li:last-child{ border-bottom:none; }
  ul.linklist a{ color:var(--ink); text-decoration:none; font-weight:800; }
  ul.linklist a:hover{ color:var(--accent); }
  .meta{ display:block; color:var(--muted); font-size:.82rem; font-weight:700; margin-top:3px; }

  .wgrid{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:12px;
    grid-auto-rows:1fr; }
  .wcard{ border:1px solid var(--line); border-radius:16px; overflow:hidden; background:var(--card);
    display:flex; flex-direction:column; }
  .wname{ font-size:.74rem; font-weight:800; text-transform:uppercase; letter-spacing:.05em;
    color:var(--ink); text-align:center; padding:8px 6px 6px; }
  .wsplit{ display:flex; flex:1; }
  .whalf{ flex:1; padding:9px 8px 12px; text-align:center;
    display:flex; flex-direction:column; justify-content:center; align-items:center; }
  .wday{ background:linear-gradient(170deg,#fff4d9,#ffe6b3); color:#5a4526; }
  .wnight{ background:linear-gradient(170deg,#183a56,#0c2033); color:#e4eef8; }
  .wplabel{ font-size:.6rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em;
    opacity:.7; }
  .whalf .wemoji{ font-size:1.7rem; line-height:1.25; margin:2px 0 1px; }
  .whalf .wtemp{ font-family:"Fredoka",sans-serif; font-size:1.2rem; font-weight:700; }
  .whalf .wshort{ font-size:.68rem; font-weight:700; line-height:1.25; opacity:.9; margin-top:2px; }

  .trow{ display:flex; gap:12px; padding:10px 0; border-bottom:1px solid var(--line); }
  .trow:last-child{ border-bottom:none; }
  .tday{ flex:0 0 96px; font-weight:800; font-size:.86rem; }
  .tcells{ display:flex; flex-wrap:wrap; gap:7px 10px; }
  .tide{ font-size:.83rem; font-weight:800; padding:2px 10px; border-radius:999px; }
  .tide.high{ color:#0b7285; background:rgba(34,184,196,.16); }
  .tide.low{ color:#2f9e93; background:rgba(47,158,147,.15); }
  .tide em{ font-style:normal; opacity:.78; }

  .factcard{ display:flow-root; border-left:4px solid var(--accent); padding:2px 0 2px 14px; }
  .factimg{ float:left; width:120px; height:120px; object-fit:cover; border-radius:12px;
    border:1px solid var(--line); background:var(--line); margin:2px 14px 8px 0; }
  .factttl{ font-family:"Fredoka",sans-serif; font-weight:600; font-size:1.05rem;
    color:var(--accent); margin-bottom:5px; }
  .facttxt{ margin:0; font-size:.95rem; line-height:1.6; max-width:78ch; }
  @media (max-width:520px){ .factimg{ width:92px; height:92px; margin:2px 12px 6px 0; } }
  .factsrc{ display:inline-block; margin-top:9px; font-size:.76rem; font-weight:800;
    color:var(--accent); text-decoration:none; opacity:.85; }
  .factsrc:hover{ text-decoration:underline; }
  .rbar{ display:flex; flex-wrap:wrap; align-items:center; gap:8px 16px; margin-bottom:14px; }
  .rcount{ font-family:"Fredoka",sans-serif; font-size:1.05rem; color:var(--ink); }
  .rcount strong{ color:var(--accent); font-size:1.25rem; }
  .rfilters{ display:flex; flex-wrap:wrap; gap:7px; }
  .rf{ font-family:"Nunito",sans-serif; font-weight:800; font-size:.78rem; cursor:pointer;
    border:1px solid var(--line); background:var(--card); color:var(--muted);
    padding:5px 12px; border-radius:999px; transition:background .12s,color .12s,border-color .12s; }
  .rf:hover{ border-color:var(--accent); color:var(--accent); }
  .rf.active{ background:var(--accent); border-color:var(--accent); color:#fff; }
  .rgrid{ display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:11px; }
  .rcard{ display:flex; flex-direction:column; align-items:flex-start;
    border:1px solid var(--line); border-radius:14px; padding:11px 14px;
    transition:transform .12s, box-shadow .12s, border-color .12s;
    background:linear-gradient(160deg, color-mix(in srgb,var(--accent) 9%, var(--card)), var(--card)); }
  .rcard:hover{ transform:translateY(-2px); box-shadow:var(--shadow);
    border-color:color-mix(in srgb,var(--accent) 45%, var(--line)); }
  .rname{ font-weight:800; color:var(--ink); line-height:1.25; text-decoration:none; }
  .rname:hover{ color:var(--accent); text-decoration:underline; }
  .rtag{ display:inline-block; margin-top:6px; font-family:"Fredoka",sans-serif; font-size:.62rem;
    text-transform:uppercase; letter-spacing:.04em; font-weight:600;
    background:color-mix(in srgb,var(--accent) 14%, transparent); color:var(--accent);
    padding:2px 9px; border-radius:999px; }
  .rmeta{ color:var(--muted); font-size:.78rem; font-weight:700; margin-top:5px; }
  .ryelp{ margin-top:9px; font-size:.72rem; font-weight:800; color:var(--accent);
    text-decoration:none; border:1px solid color-mix(in srgb,var(--accent) 35%, transparent);
    padding:2px 10px; border-radius:999px; }
  .ryelp:hover{ background:color-mix(in srgb,var(--accent) 14%, transparent); }

  .muted{ color:var(--muted); font-weight:700; }
  @media (min-width:760px){
    .cols2{ display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:start; }
    .cols2>section{ margin-top:20px; }
  }
  footer{ text-align:center; color:var(--muted); font-size:.82rem; font-weight:700;
    margin-top:30px; line-height:1.7; }
  footer a{ color:var(--accent); text-decoration:none; }
"""

_WAVE = ('<div class="wave"><svg viewBox="0 0 1200 40" preserveAspectRatio="none">'
         '<path d="M0,22 C160,42 360,4 600,22 C840,40 1040,4 1200,22 '
         'L1200,40 L0,40 Z"/></svg></div>')


def _html_page(loc: str, generated: str, strip_html: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="1800">
<title>{loc} — This Week</title>
{_FONTS}
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="top-inner">
      <h1>{loc}</h1>
      <div class="sub">Your week at a glance · updated {generated}</div>
      <div class="strip">{strip_html}</div>
    </div>
    {_WAVE}
  </header>
  {body}
  <footer>
    🎶 Live music &amp; events from <a href="https://fernandinaconnect.com/" target="_blank" rel="noopener">FernandinaConnect</a>
    &amp; <a href="https://allevents.in/fernandina-beach/music" target="_blank" rel="noopener">AllEvents</a> ·
    📰 news via Google News &amp; the City of Fernandina Beach ·
    ☀️ weather from <a href="https://www.weather.gov/" target="_blank" rel="noopener">NWS</a> ·
    🌊 tides from <a href="https://tidesandcurrents.noaa.gov/stationhome.html?id=8720030" target="_blank" rel="noopener">NOAA</a> ·
    🍽️ restaurants © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors ·
    📜🐚 daily facts from <a href="https://www.wikipedia.org/" target="_blank" rel="noopener">Wikipedia</a> (CC BY-SA).<br>
    This page refreshes itself every 30 minutes · for personal use, details can change.
  </footer>
</div>
</body>
</html>"""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def publish_site(cfg: dict) -> None:
    """Publish output/ to the web via Netlify's API (no extra software needed).
    Creates the site on first run; deploys the current build every time."""
    pub = cfg.get("publish", {})
    if not pub.get("enabled") or pub.get("provider") != "netlify":
        return
    # token: config first, else the NETLIFY_AUTH_TOKEN env var (used in the cloud)
    token = (pub.get("netlify_token") or "").strip()
    if not token or token.startswith("PUT-"):
        token = os.environ.get("NETLIFY_AUTH_TOKEN", "").strip()
    if not token:
        logging.info("Publish: no Netlify token set yet; skipping (see README)")
        return
    hdr = {"Authorization": f"Bearer {token}"}
    state = HERE / "data" / "netlify_site.json"
    try:
        # site id: env (cloud) > saved state (local) > create a new site
        env_site = os.environ.get("NETLIFY_SITE_ID", "").strip()
        saved = json.loads(state.read_text()) if state.exists() else {}
        if env_site:
            site_id, site_url = env_site, ""
        elif saved.get("id"):
            site_id, site_url = saved["id"], saved.get("url", "")
        else:
            body = {"name": pub.get("site_name", "amelia-island-scene")}
            r = requests.post("https://api.netlify.com/api/v1/sites",
                              headers=hdr, json=body, timeout=30)
            if r.status_code >= 400:  # name likely taken -> let Netlify pick one
                r = requests.post("https://api.netlify.com/api/v1/sites",
                                  headers=hdr, json={}, timeout=30)
            r.raise_for_status()
            s = r.json()
            site_id, site_url = s["id"], (s.get("ssl_url") or s.get("url") or "")
            state.write_text(json.dumps({"id": site_id, "url": site_url}))

        out_dir = (HERE / cfg["output_file"]).parent
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out_dir.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(out_dir))
        r = requests.post(
            f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
            headers={**hdr, "Content-Type": "application/zip"},
            data=buf.getvalue(), timeout=180)
        r.raise_for_status()
        url = r.json().get("ssl_url") or r.json().get("url") or site_url
        logging.info("Published to %s", url)
        print(f"🌐 Live at: {url}")
    except Exception as ex:  # noqa: BLE001
        logging.warning("Publish failed: %s", ex)


def main() -> int:
    setup_logging()
    cfg = load_config()
    logging.info("=== Amelia dashboard run start ===")

    music, events = collect_events(cfg)
    data = {
        "music": music,
        "events": events,
        "news": fetch_news(cfg),
        "facts": fetch_facts(cfg),
        "banners": fetch_banners(cfg),
        "restaurants": fetch_restaurants(cfg),
        "weather": fetch_weather(cfg),
        "tides": fetch_tides(cfg),
    }
    logging.info("Collected: %d music, %d events, %d news, %d restaurants",
                 len(music), len(events), len(data["news"]),
                 len(data["restaurants"]))

    out_path = HERE / cfg["output_file"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(cfg, data), encoding="utf-8")
    logging.info("Wrote %s", out_path)

    publish_site(cfg)

    if cfg.get("open_after_run"):
        import subprocess
        subprocess.run(["open", str(out_path)], check=False)

    print(f"\n✅ Dashboard written to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
