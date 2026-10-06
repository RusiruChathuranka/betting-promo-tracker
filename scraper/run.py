import json, os, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.firecrawl.dev/v2/scrape"

PROMO_LINK_WORDS = (
    "promo", "promotion", "promotions", "bonus", "bonuses", "cashback",
    "free-bet", "freebet", "reward", "rewards", "welcome", "reload"
)

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
            "onlyMainContent": True,
        },
        timeout=90,
    )
    r.raise_for_status()
    data = r.json().get("data", {})
    return data.get("markdown", "") or "", data.get("links", []) or []

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

def classify(title, body):
    t = norm(f"{title} {body}").lower()
    h = norm(title).lower()

    # Title is deliberately weighted more heavily than body text.
    if any(x in h for x in ["cashback", "cash back", "cash-back"]):
        return "cashback"
    if any(x in h for x in ["free bet", "freebet", "free-bet"]):
        return "free_bet"
    if any(x in h for x in ["racing bonus", "horse racing", "turf"]):
        return "racing_bonus"
    if any(x in h for x in ["reload", "re-deposit", "redeposit"]):
        return "reload_bonus"
    if any(x in h for x in ["welcome", "new customer", "new user", "first deposit", "first-deposit", "registration"]):
        return "new_customer"
    if "deposit" in h:
        return "deposit_bonus"

    if any(x in t for x in ["cashback", "cash back", "cash-back"]):
        return "cashback"
    if any(x in t for x in ["free bet", "freebet", "free-bet"]):
        return "free_bet"
    if any(x in t for x in ["reload", "re-deposit", "redeposit"]):
        return "reload_bonus"
    if any(x in t for x in ["welcome", "new customer", "new user", "first deposit", "first-deposit", "registration"]):
        return "new_customer"
    if any(x in t for x in ["racing bonus", "horse racing", "turf"]):
        return "racing_bonus"
    if "deposit" in t:
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

    # Some modern sites render promotion cards without markdown headings.
    # If heading extraction produced little data, create bounded candidates
    # around lines that look like promotion titles.
    if len(sections) <= 1 and markdown:
        candidates = []
        raw = [norm(x) for x in lines if norm(x)]
        for i, line in enumerate(raw):
            if re.search(r"bonus|cashback|free bet|freebet|promotion|offer|reward|deposit", line, re.I):
                body = " ".join(raw[i:i + 8])
                candidates.append((line[:180], body[:2500]))
        if candidates:
            sections.extend(candidates)

    # Remove obvious navigation/footer noise and duplicate candidates.
    out = []
    seen = set()
    for title, body in sections:
        title = norm(title)
        body = norm(body)
        key = (title.lower(), body[:300].lower())
        if not title or key in seen:
            continue
        if len(title) < 3:
            continue
        if title.lower() in {"promotions", "promotion", "bonuses", "bonus", "terms and conditions"} and len(body) < 100:
            continue
        seen.add(key)
        out.append((title, body))
    return out

def extract(platform, url, markdown):
    rows = []

    for title, body in parse_sections(markdown):
        text = norm(f"{title} {body}")

        if not re.search(
            r"bonus|cashback|free bet|freebet|promotion|offer|deposit|reward|wager|welcome|reload",
            text,
            re.I,
        ):
            continue

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

        rows.append({
            "id": hashlib.sha1(f"{platform}|{title}|{url}".encode()).hexdigest()[:12],
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
            "source_text": body[:2500],
        })

    return rows

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

    # Preserve order and cap crawling so one source cannot explode the run.
    return list(dict.fromkeys(out))[:12]

def main():
    cfg = json.loads((ROOT / "config/platforms.json").read_text())
    now = datetime.now(timezone.utc).isoformat()

    all_rows = []
    errors = []

    for p in cfg["platforms"]:
        visited = set()
        queue = list(p["urls"])

        while queue:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                md, links = firecrawl(url)
                if not md:
                    raise RuntimeError("Firecrawl returned no markdown")

                rows = extract(p["name"], url, md)
                for r in rows:
                    r["last_checked"] = now
                    r["score"] = score(r)
                all_rows.extend(rows)

                # Discover individual promotion/bonus detail pages.
                for link in discovered_links(url, links):
                    if link not in visited:
                        queue.append(link)

            except Exception as e:
                errors.append({
                    "platform": p["name"],
                    "url": url,
                    "error": str(e),
                })

    # Deduplicate within a run.
    dedup = {r["id"]: r for r in all_rows}
    all_rows = list(dedup.values())

    # Comparable cluster = promotion type + customer segment + sport.
    # This prevents, for example, a cashback offer being compared with a
    # first-deposit bonus just because both apply to cricket.
    for r in all_rows:
        r["cluster_key"] = "|".join([
            r["category"],
            r["customer_type"],
            r["sport"],
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
        }, indent=2),
        encoding="utf-8",
    )

    history_path = ROOT / "data/history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    history.append({
        "timestamp": now,
        "count": len(all_rows),
        "promotions": all_rows,
    })
    history = history[-60:]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    print(
        f"Collected {len(all_rows)} promotions from "
        f"{len(cfg['platforms'])} platforms; {len(errors)} source errors."
    )

if __name__ == "__main__":
    main()
