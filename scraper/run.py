import json, os, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.firecrawl.dev/v2/scrape"
MAX_PAGES_PER_PLATFORM = 12
MAX_OFFERS_PER_PLATFORM = 30

PROMO_LINK_WORDS = (
    "promo", "promotion", "promotions", "bonus", "bonuses", "cashback",
    "free-bet", "freebet", "reward", "rewards", "welcome", "reload"
)

PROMO_TITLE_WORDS = (
    "bonus", "bonuses", "cashback", "cash back", "cash-back",
    "free bet", "freebet", "free-bet", "promotion", "promotions",
    "promo", "reward", "rewards", "welcome", "reload",
    "special offer", "daily bonus", "weekly bonus", "deposit bonus",
    "first deposit", "registration bonus", "tuesday bonus", "friday bonus"
)

GENERIC_TITLES = {
    "promotion", "promotions", "promo", "promos", "bonus", "bonuses",
    "deposit", "withdrawal", "sportsbook", "casino", "live casino",
    "racing", "sports", "games", "offers", "offer", "terms and conditions",
    "terms", "rules", "faq", "help", "responsible gaming", "about us",
    "contact us", "login", "register", "registration", "home"
}

NON_PROMO_PATTERNS = (
    r"\bterms?\b", r"\bprivacy\b", r"\brules?\b", r"\bfaq\b",
    r"\bhow to\b", r"\bguide\b", r"\bblog\b", r"\bcontact\b",
    r"\babout us\b", r"\bresponsible\b", r"\blogin\b", r"\bregister\b"
)

NON_OFFICIAL_HOSTS = {
    "dbbetsrilanka.com": "guide/affiliate",
    "888starz.lk": "guide/affiliate",
    "megapari.games": "guide/affiliate",
    "guidebook.melbet.com": "guide/affiliate",
}

def firecrawl(url):
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")

    r = requests.post(
        API,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "url": url,
            "formats": ["markdown", "links"],
            "onlyMainContent": False,
            "waitFor": 2000,
        },
        timeout=90,
    )
    r.raise_for_status()
    data = r.json().get("data", {})
    return data.get("markdown", "") or "", data.get("links", []) or ""

def direct_fallback(url):
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PromotionTracker/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=35,
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    links = []
    host = urlparse(url).netloc.lower()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("http://", "https://")) and urlparse(href).netloc.lower() == host:
            links.append(href)

    text = soup.get_text("\n", strip=True)
    return text, list(dict.fromkeys(links))

def fetch_page(url):
    try:
        return (*firecrawl(url), "firecrawl")
    except Exception as firecrawl_error:
        try:
            md, links = direct_fallback(url)
            if md:
                return md, links, "direct"
        except Exception as direct_error:
            raise RuntimeError(
                f"Firecrawl failed: {firecrawl_error}; direct fallback failed: {direct_error}"
            )
        raise RuntimeError(f"Firecrawl failed: {firecrawl_error}")

def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()

def num(text, patterns):
    text = norm(text)
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", "").replace(" ", ""))
            except ValueError:
                pass
    return None

REJECT_TITLE_WORDS = (
    "terms", "conditions", "rules", "faq", "guide", "information",
    "details", "how to", "learn", "code", "what is", "eligibility",
    "requirements", "claim instructions"
)

def has_promo_title(title):
    h = norm(title).lower()
    if not h or h in GENERIC_TITLES:
        return False
    if any(word in h for word in REJECT_TITLE_WORDS):
        return False
    return any(word in h for word in PROMO_TITLE_WORDS)

def promotion_evidence(title, body):
    h = norm(title).lower()
    t = norm(f"{title} {body}").lower()

    if h in GENERIC_TITLES:
        return False, "generic page title"

    if any(word in h for word in REJECT_TITLE_WORDS):
        return False, "informational/terms title"

    mechanics = 0
    if re.search(r"\b\d{1,3}\s*%\b", t):
        mechanics += 1
    if re.search(r"\b(?:lkr|rs\.?)\s*[\d,]+\b", t):
        mechanics += 1
    if re.search(r"\b(?:up to|max(?:imum)?)\b", t):
        mechanics += 1
    if re.search(r"\b\d+(?:\.\d+)?\s*x\b", t):
        mechanics += 1
    if re.search(r"\b(?:cashback|cash back|free bet|free spins|bonus|reward)\b", t):
        mechanics += 1
    if re.search(r"\b(?:claim|eligible|valid for|validity|qualify)\b", t):
        mechanics += 1
    if re.search(r"\b(?:minimum|min)\s+deposit\b", t):
        mechanics += 1

    # A title by itself is not enough unless it clearly names an offer.
    clear_offer_title = (
        bool(re.search(r"\b\d{1,3}\s*%\b", h))
        or bool(re.search(r"\b(?:lkr|rs\.?)\s*[\d,]+\b", h))
        or any(word in h for word in (
            "cashback", "free bet", "freebet", "welcome bonus",
            "deposit bonus", "reload", "daily bonus", "weekly bonus",
            "special offer", "registration bonus", "first deposit",
            "tuesday bonus", "friday bonus"
        ))
    )

    if clear_offer_title:
        return True, "clear offer title"

    if mechanics >= 3 and re.search(r"\b(?:offer|bonus|promotion|promo|reward|deposit|cashback)\b", t):
        return True, "multiple promotion mechanics"

    return False, "insufficient promotion evidence"

def classify(title, body):
    h = norm(title).lower()
    t = norm(f"{title} {body}").lower()

    if any(x in h for x in ["cashback", "cash back", "cash-back"]):
        return "cashback"
    if any(x in h for x in ["free bet", "freebet", "free-bet"]):
        return "free_bet"
    if any(x in h for x in ["racing bonus", "horse racing", "turf"]):
        return "racing_bonus"
    if any(x in h for x in ["reload", "re-deposit", "redeposit"]):
        return "reload_bonus"
    if any(x in h for x in ["welcome", "new customer", "new user", "first deposit", "first-deposit", "registration bonus"]):
        return "new_customer"
    if "deposit bonus" in h or ("deposit" in h and "bonus" in h):
        return "deposit_bonus"

    if any(x in t for x in ["cashback", "cash back", "cash-back"]):
        return "cashback"
    if any(x in t for x in ["free bet", "freebet", "free-bet"]):
        return "free_bet"
    if any(x in t for x in ["reload", "re-deposit", "redeposit"]):
        return "reload_bonus"
    if any(x in t for x in ["welcome", "new customer", "new user", "first deposit", "first-deposit", "registration bonus"]):
        return "new_customer"
    if any(x in t for x in ["racing bonus", "horse racing", "turf"]):
        return "racing_bonus"
    if "deposit" in t and "bonus" in t:
        return "deposit_bonus"
    if any(x in t for x in ["cricket", "football", "soccer", "tennis", "rugby", "basketball", "badminton", "formula 1", "f1"]):
        return "sports_bonus"
    return "other"

def sport(text):
    t = text.lower()
    for s, keys in {
        "Cricket": ["cricket"],
        "Football": ["football", "soccer"],
        "Tennis": ["tennis"],
        "Racing": ["racing", "horse racing", "horse"],
        "Rugby": ["rugby"],
        "Basketball": ["basketball"],
        "Badminton": ["badminton"],
        "F1": ["formula 1", "f1"],
    }.items():
        if any(k in t for k in keys):
            return s
    return "All Sports"

def customer_type(title, body, category):
    t = norm(f"{title} {body}").lower()

    if any(x in t for x in [
        "new customer", "new customers", "new user", "new users",
        "new player", "new players", "newly registered", "first deposit",
        "first-time", "first time", "welcome bonus", "registration bonus"
    ]):
        return "new_customer"

    if any(x in t for x in [
        "all users", "all customers", "all players", "every user", "every player"
    ]):
        return "all_users"

    if category in {"reload_bonus", "cashback"} or any(x in t for x in [
        "existing customer", "existing customers", "existing user", "existing users",
        "regular players", "loyal customers", "loyalty"
    ]):
        return "existing_or_eligible"

    return "eligible_users"

def parse_sections(markdown):
    lines = markdown.splitlines()
    sections = []
    title = None
    buf = []

    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{1,4}\s+", stripped):
            if title and buf:
                sections.append((title, " ".join(buf)))
            title = re.sub(r"^#{1,4}\s+", "", stripped).strip()
            buf = []
        elif stripped:
            buf.append(stripped)

    if title and buf:
        sections.append((title, " ".join(buf)))

    # Promotion cards on modern pages often have no markdown headings.
    # Only promote lines that look like actual offer names; generic page
    # content is deliberately not converted into promotions.
    if len(sections) <= 1:
        raw = [norm(x) for x in lines if norm(x)]
        for i, line in enumerate(raw):
            if not has_promo_title(line):
                continue
            body = " ".join(raw[i:i + 16])
            sections.append((line[:180], body[:3500]))

    out = []
    seen = set()
    for title, body in sections:
        title = norm(title)
        body = norm(body)
        if not title or len(title) < 3 or len(title) > 180:
            continue
        key = (title.lower(), body[:400].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((title, body))
    return out

def extract(platform, url, markdown):
    rows = []
    rejected = 0

    for title, body in parse_sections(markdown):
        is_promo, reason = promotion_evidence(title, body)
        if not is_promo:
            rejected += 1
            continue

        text = norm(f"{title} {body}")

        bonus_pct = num(text, [
            r"(\d{1,3})\s*%\s*(?:deposit\s*)?(?:match\s*)?bonus",
            r"(\d{1,3})\s*%\s*(?:up to|max)",
            r"bonus[^%]{0,60}(\d{1,3})\s*%",
        ])
        max_bonus = num(text, [
            r"(?:up to|max(?:imum)?(?:\s+bonus)?)[^\d]{0,30}(?:lkr|rs\.?)[\s:]*([\d\s,]+)",
            r"(?:lkr|rs\.?)\s*([\d\s,]+)[^\d]{0,40}(?:max(?:imum)?|up to)",
            r"up to\s*([\d\s,]+)\s*(?:lkr|rs\.?)",
        ])
        min_deposit = num(text, [
            r"(?:minimum|min)\s+deposit[^\d]{0,30}(?:lkr|rs\.?)?\s*([\d\s,]+)",
            r"deposit\s+(?:of\s+)?(?:lkr|rs\.?)\s*([\d\s,]+)",
            r"deposit\s+([\d\s,]+)\s*(?:lkr|rs\.?)",
        ])
        wagering = num(text, [
            r"(\d+(?:\.\d+)?)\s*x\s*(?:wager|rollover|turnover)",
            r"(?:wagering|rollover|turnover)[^\d]{0,30}(\d+(?:\.\d+)?)\s*x",
        ])
        odds = num(text, [
            r"(?:minimum|min)\s+odds[^\d]{0,20}(\d+(?:\.\d+)?)",
            r"odds[^\d]{0,10}(\d+(?:\.\d+)?)",
        ])
        validity_days = num(text, [
            r"(\d+)\s*(?:days|day)",
            r"valid[^\d]{0,20}(\d+)\s*(?:days|day)",
        ])
        cash_conversion = num(text, [
            r"(?:cash conversion|max(?:imum)? cash conversion)[^\d]{0,20}(\d+(?:\.\d+)?)\s*x",
        ])

        category = classify(title, body)
        customer = customer_type(title, body, category)
        host = urlparse(url).netloc.lower()
        source_type = NON_OFFICIAL_HOSTS.get(host, "official/public")

        rows.append({
            "id": hashlib.sha1(f"{platform}|{norm(title).lower()}".encode()).hexdigest()[:12],
            "platform": platform,
            "title": title,
            "category": category,
            "customer_type": customer,
            "sport": sport(text),
            "bonus_percent": bonus_pct,
            "max_bonus_lkr": max_bonus,
            "min_deposit_lkr": min_deposit,
            "wagering_x": wagering,
            "min_odds": odds,
            "cash_conversion_x": cash_conversion,
            "validity_days": validity_days,
            "source_url": url,
            "source_type": source_type,
            "source_text": body[:2500],
            "quality_status": "validated",
            "quality_reason": reason,
        })

    return rows, rejected

def score(r):
    parts = []
    if r["bonus_percent"] is not None:
        parts.append(min(r["bonus_percent"] / 100, 1) * 20)
    if r["max_bonus_lkr"] is not None:
        parts.append(min(r["max_bonus_lkr"] / 100000, 1) * 25)
    if r["wagering_x"] is not None:
        parts.append(max(0, 1 - r["wagering_x"] / 12) * 20)
    if r["min_deposit_lkr"] is not None:
        parts.append(max(0, 1 - r["min_deposit_lkr"] / 20000) * 10)
    if r["min_odds"] is not None:
        parts.append(max(0, 1 - r["min_odds"] / 5) * 10)
    if r["validity_days"] is not None:
        parts.append(min(r["validity_days"] / 30, 1) * 5)
    return round(sum(parts), 1)

def discovered_links(source_url, links):
    source_host = urlparse(source_url).netloc.lower()
    out = []
    for link in links:
        if not isinstance(link, str) or not link.startswith(("http://", "https://")):
            continue
        parsed = urlparse(link)
        if parsed.netloc.lower() != source_host:
            continue
        path = (parsed.path + "?" + parsed.query).lower()
        if not any(word in path for word in PROMO_LINK_WORDS):
            continue
        if link.rstrip("/") == source_url.rstrip("/"):
            continue
        out.append(link)
    return list(dict.fromkeys(out))[:8]

def main():
    cfg = json.loads((ROOT / "config/platforms.json").read_text())
    now = datetime.now(timezone.utc).isoformat()

    all_rows = []
    errors = []
    rejected_count = 0
    source_stats = []

    for p in cfg["platforms"]:
        visited = set()
        queue = list(p["urls"])
        pages_checked = 0
        platform_rows = []

        while queue and pages_checked < MAX_PAGES_PER_PLATFORM:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            pages_checked += 1

            try:
                md, links, method = fetch_page(url)
                if not md:
                    raise RuntimeError("Scraper returned no page text")

                rows, rejected = extract(p["name"], url, md)
                rejected_count += rejected

                for r in rows:
                    r["last_checked"] = now
                    r["scrape_method"] = method
                    r["score"] = score(r)
                    platform_rows.append(r)

                for link in discovered_links(url, links):
                    if link not in visited and link not in queue:
                        queue.append(link)

            except Exception as e:
                errors.append({
                    "platform": p["name"],
                    "url": url,
                    "error": str(e),
                })

        # De-duplicate repeated copies of the same offer across source pages.
        dedup = {}
        for r in platform_rows:
            key = (r["platform"], norm(r["title"]).lower())
            existing = dedup.get(key)
            if existing is None or len(r["source_text"]) > len(existing["source_text"]):
                dedup[key] = r

        platform_rows = sorted(
            dedup.values(),
            key=lambda r: r["score"],
            reverse=True,
        )[:MAX_OFFERS_PER_PLATFORM]
        all_rows.extend(platform_rows)
        source_stats.append({
            "platform": p["name"],
            "pages_checked": pages_checked,
            "offers_found": len(platform_rows),
            "errors": sum(1 for e in errors if e["platform"] == p["name"]),
        })

    for r in all_rows:
        r["cluster_key"] = "|".join([
            r["category"], r["customer_type"], r["sport"],
        ])
        r["cluster_label"] = " · ".join([
            r["category"].replace("_", " ").title(),
            r["customer_type"].replace("_", " ").title(),
            r["sport"],
        ])

    all_rows.sort(key=lambda x: (x["cluster_key"], -x["score"]))

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data/promotions.json").write_text(
        json.dumps({
            "updated_at": now,
            "promotions": all_rows,
            "errors": errors,
            "source_stats": source_stats,
            "rejected_count": rejected_count,
            "quality": {
                "validated_only": True,
                "promotion_rule": "Offer must have a promotional title or multiple explicit promotion mechanics.",
            },
        }, indent=2),
        encoding="utf-8",
    )

    history_path = ROOT / "data/history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    history.append({
        "timestamp": now,
        "count": len(all_rows),
        "rejected_count": rejected_count,
        "promotions": all_rows,
    })
    history = history[-60:]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    print(
        f"Collected {len(all_rows)} validated promotions from "
        f"{len(cfg['platforms'])} platforms; {len(errors)} source errors; "
        f"{rejected_count} low-confidence candidates excluded."
    )

if __name__ == "__main__":
    main()
