import json, os, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.firecrawl.dev/v2/scrape"

def firecrawl(url):
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")
    r = requests.post(API, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"url": url, "formats": ["markdown"], "onlyMainContent": True}, timeout=90)
    r.raise_for_status()
    return r.json().get("data", {}).get("markdown", "") or ""

def num(text, patterns):
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try: return float(m.group(1).replace(",", ""))
            except ValueError: pass
    return None

def classify(text):
    t=text.lower()
    if any(x in t for x in ["cashback","cash back","cash-back"]): return "cashback"
    if any(x in t for x in ["free bet","freebet","free-bet"]): return "free_bet"
    if any(x in t for x in ["racing bonus","horse racing","turf"]): return "racing_bonus"
    if any(x in t for x in ["welcome","new customer","new user","first deposit","first-deposit"]): return "new_customer"
    if any(x in t for x in ["reload","re-deposit","redeposit"]): return "reload_bonus"
    if "deposit" in t: return "deposit_bonus"
    if any(x in t for x in ["cricket","football","soccer","tennis","rugby","basketball","badminton","f1"]): return "sports_bonus"
    return "other"

def sport(text):
    t=text.lower()
    for s, keys in {
        "Cricket":["cricket"],"Football":["football","soccer"],"Tennis":["tennis"],
        "Racing":["racing","horse"],"Rugby":["rugby"],"Basketball":["basketball"],
        "Badminton":["badminton"],"F1":["formula 1","f1"]
    }.items():
        if any(k in t for k in keys): return s
    return "All Sports"

def parse_sections(markdown):
    # Headings are treated as candidate promotion titles; the following block is its evidence.
    lines=markdown.splitlines()
    sections=[]; title=None; buf=[]
    for line in lines:
        if re.match(r"^#{1,4}\s+", line):
            if title and buf: sections.append((title," ".join(buf)))
            title=re.sub(r"^#{1,4}\s+","",line).strip()
            buf=[]
        elif line.strip():
            buf.append(line.strip())
    if title and buf: sections.append((title," ".join(buf)))
    return sections

def extract(platform, url, markdown):
    rows=[]
    for title, body in parse_sections(markdown):
        text=f"{title} {body}"
        if not re.search(r"bonus|cashback|free bet|promotion|offer|deposit|reward|wager", text, re.I):
            continue
        bonus_pct=num(text,[r"(\d{1,3})\s*%\s*(?:deposit\s*)?bonus",r"bonus[^%]{0,40}(\d{1,3})\s*%"])
        max_bonus=num(text,[r"(?:up to|max(?:imum)?)[^\d]{0,20}(?:lkr|rs\.?|₹)?\s*([\d,]+)",r"(?:lkr|rs\.?)[\s:]*([\d,]+)[^\n]{0,40}(?:max|maximum|up to)"])
        min_deposit=num(text,[r"(?:minimum|min)\s+deposit[^\d]{0,20}(?:lkr|rs\.?)*\s*([\d,]+)",r"(?:deposit)[^\d]{0,15}(?:lkr|rs\.?)*\s*([\d,]+)"])
        wagering=num(text,[r"(\d+(?:\.\d+)?)\s*x\s*(?:wager|rollover|turnover)",r"(?:wagering|rollover)[^\d]{0,20}(\d+(?:\.\d+)?)\s*x"])
        odds=num(text,[r"(?:minimum|min)\s+odds[^\d]{0,20}(\d+(?:\.\d+)?)",r"odds[^\d]{0,10}(\d+(?:\.\d+)?)"])
        days=num(text,[r"(\d+)\s*(?:days|day)"])
        category=classify(text)
        rows.append({
            "id": hashlib.sha1(f"{platform}|{title}|{url}".encode()).hexdigest()[:12],
            "platform": platform, "title": title, "category": category,
            "sport": sport(text), "bonus_percent": bonus_pct, "max_bonus_lkr": max_bonus,
            "min_deposit_lkr": min_deposit, "wagering_x": wagering, "min_odds": odds,
            "validity_days": days, "source_url": url, "source_text": body[:2500]
        })
    return rows

def score(r):
    # Transparent heuristic; missing mechanics do not receive a bonus or penalty.
    parts=[]
    if r["bonus_percent"] is not None: parts.append(min(r["bonus_percent"]/100,1)*20)
    if r["max_bonus_lkr"] is not None: parts.append(min(r["max_bonus_lkr"]/100000,1)*25)
    if r["wagering_x"] is not None: parts.append(max(0,1-r["wagering_x"]/12)*20)
    if r["min_deposit_lkr"] is not None: parts.append(max(0,1-r["min_deposit_lkr"]/20000)*10)
    if r["min_odds"] is not None: parts.append(max(0,1-r["min_odds"]/5)*10)
    if r["validity_days"] is not None: parts.append(min(r["validity_days"]/30,1)*5)
    return round(sum(parts),1)

def main():
    cfg=json.loads((ROOT/"config/platforms.json").read_text())
    now=datetime.now(timezone.utc).isoformat()
    all_rows=[]
    errors=[]
    for p in cfg["platforms"]:
        for url in p["urls"]:
            try:
                md=firecrawl(url)
                rows=extract(p["name"],url,md)
                for r in rows:
                    r["last_checked"]=now; r["score"]=score(r)
                all_rows.extend(rows)
            except Exception as e:
                errors.append({"platform":p["name"],"url":url,"error":str(e)})
    # Deduplicate within a run.
    dedup={r["id"]:r for r in all_rows}
    all_rows=list(dedup.values())
    # Cluster comparable offers by mechanics, customer segment and sport.
    for r in all_rows:
        r["cluster_key"]="|".join([r["category"],r["sport"]])
        r["cluster_label"]=r["category"].replace("_"," ").title()+" · "+r["sport"]
    all_rows.sort(key=lambda x:(x["cluster_key"],-x["score"]))
    (ROOT/"data").mkdir(exist_ok=True)
    (ROOT/"data/promotions.json").write_text(json.dumps({"updated_at":now,"promotions":all_rows,"errors":errors},indent=2),encoding="utf-8")
    history_path=ROOT/"data/history.json"
    history=json.loads(history_path.read_text()) if history_path.exists() else []
    history.append({"timestamp":now,"count":len(all_rows),"promotions":all_rows})
    history=history[-60:]
    history_path.write_text(json.dumps(history,indent=2),encoding="utf-8")
    print(f"Collected {len(all_rows)} promotions; {len(errors)} source errors.")

if __name__=="__main__":
    main()
