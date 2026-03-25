from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import random
import re
import os
import time
from urllib.parse import quote_plus
from datetime import date

app = FastAPI(title="TireTroopers Lead API", version="1.0.0")

# ── CORS — allows your Lovable site to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.tiretroopers.com",
        "https://tiretroopers.com",
        "http://localhost:3000",
        "http://localhost:5173",
        "*"  # remove this line once live if you want stricter security
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ─────────────────────────────────────────────
#  SCORING & HELPERS
# ─────────────────────────────────────────────

HOT_KEYWORDS  = ["fleet","truck","van","transport","hauling","delivery","bus",
                 "excavat","paving","concrete","crane","waste","towing","moving"]
WARM_KEYWORDS = ["landscap","plumb","hvac","electrical","roofing","contractor",
                 "property","service","maintenance","security","courier","irrigation"]

def score_lead(name, category, reviews=0):
    text = (name + " " + category).lower()
    if any(k in text for k in HOT_KEYWORDS):
        warmth, score = "hot", random.randint(78, 95)
    elif any(k in text for k in WARM_KEYWORDS):
        warmth, score = "warm", random.randint(55, 77)
    else:
        warmth, score = "cold", random.randint(30, 54)
    if reviews > 20:
        score = min(score + 8, 98)
    return warmth, score

def segment_from_category(category):
    c = category.lower()
    if any(x in c for x in ["truck","fleet","transport","hauling","bus","waste","courier","delivery","moving","towing"]):
        return "Fleet"
    if any(x in c for x in ["construct","excavat","paving","concrete"]):
        return "Construction"
    if "landscap" in c or "irrigation" in c:
        return "Landscaping"
    if any(x in c for x in ["plumb","hvac","electrical","roofing"]):
        return "Contractor"
    if "property" in c or "realtor" in c:
        return "Realtor"
    return "Contractor"

def reason_from_category(category, name):
    c = category.lower()
    if "truck" in c or "fleet" in c or "transport" in c:
        return f"{name} operates a vehicle fleet — prime candidate for on-site tire service"
    if "excavat" in c or "construct" in c:
        return f"{name} runs construction equipment & trucks — seasonal changeover likely needed"
    if "landscap" in c:
        return f"{name} seasonal business — spring startup means tire swaps for work trucks"
    if "plumb" in c or "hvac" in c or "electrical" in c:
        return f"{name} service vehicles operating daily — convenient on-site tire swap"
    if "roofing" in c or "paving" in c or "concrete" in c:
        return f"{name} heavy work vehicles — mobile service saves downtime"
    if "delivery" in c or "courier" in c:
        return f"{name} delivery fleet — high mileage, regular tire needs"
    if "school bus" in c or "bus" in c:
        return f"{name} passenger vehicles — seasonal swap required"
    if "waste" in c or "towing" in c:
        return f"{name} heavy-duty vehicles — can't go to a shop, mobile service ideal"
    return f"{name} local business with work vehicles — general prospect"

def deduplicate(leads):
    seen = set()
    unique = []
    for lead in leads:
        key = re.sub(r'\s+(ltd|inc|llc|corp|co|bc|limited|group)\.?$', '',
                     lead["business"].lower().strip())
        key = re.sub(r'[^a-z0-9]', '', key)
        if key and key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique

# ─────────────────────────────────────────────
#  SOURCE 1 — Google Places API
# ─────────────────────────────────────────────

def scrape_google_places(categories):
    if not GOOGLE_MAPS_API_KEY:
        return []
    leads = []
    base = "https://maps.googleapis.com/maps/api/place"
    for cat in categories:
        try:
            r = requests.get(f"{base}/textsearch/json", params={
                "query": cat, "key": GOOGLE_MAPS_API_KEY,
                "region": "ca", "language": "en"
            }, timeout=10)
            for place in r.json().get("results", []):
                det = requests.get(f"{base}/details/json", params={
                    "place_id": place.get("place_id",""),
                    "fields": "name,formatted_phone_number,website,formatted_address,rating,user_ratings_total,business_status",
                    "key": GOOGLE_MAPS_API_KEY
                }, timeout=10).json().get("result", {})
                if det.get("business_status") != "OPERATIONAL":
                    continue
                addr = det.get("formatted_address","")
                if "kamloops" not in addr.lower():
                    continue
                name    = det.get("name","")
                reviews = det.get("user_ratings_total", 0)
                warmth, score = score_lead(name, cat, reviews)
                leads.append({
                    "business": name,
                    "name": "",
                    "email": "",
                    "phone": det.get("formatted_phone_number",""),
                    "website": det.get("website",""),
                    "address": addr,
                    "segment": segment_from_category(cat),
                    "warmth": warmth,
                    "score": score,
                    "reason": reason_from_category(cat, name),
                    "rating": f"{det.get('rating','')}★ ({reviews} reviews)" if reviews else "",
                    "source": "Google Places",
                    "date": str(date.today())
                })
                time.sleep(0.3)
        except Exception:
            continue
    return leads

# ─────────────────────────────────────────────
#  SOURCE 2 — Yellow Pages Canada
# ─────────────────────────────────────────────

YP_SEARCHES = [
    ("general-contractors",            "Construction"),
    ("excavating-contractors",         "Construction"),
    ("landscaping",                    "Landscaping"),
    ("trucking",                       "Fleet"),
    ("courier-delivery-service",       "Delivery"),
    ("plumbers",                       "Contractor"),
    ("heating-air-conditioning",       "Contractor"),
    ("roofing-contractors",            "Contractor"),
    ("electricians",                   "Contractor"),
    ("concrete-contractors",           "Construction"),
    ("paving-contractors",             "Construction"),
    ("moving-storage",                 "Fleet"),
    ("towing",                         "Fleet"),
    ("property-management",            "Realtor"),
    ("security-guard-patrol-service",  "Fleet"),
    ("irrigation-systems",             "Landscaping"),
]

def scrape_yellowpages():
    leads = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for yp_cat, segment in YP_SEARCHES:
        url = f"https://www.yellowpages.ca/search/si/1/{quote_plus(yp_cat)}/Kamloops+BC"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            listings = (soup.select("div.listing__content") or
                        soup.select("div[class*='listing']") or
                        soup.select("article"))
            for item in listings[:15]:
                name_el = (item.select_one("a.listing__name") or
                           item.select_one("[class*='name'] a") or
                           item.select_one("h3 a") or item.select_one("h2 a"))
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                phone_el = (item.select_one("[class*='phone']") or
                            item.select_one("span[itemprop='telephone']"))
                phone = phone_el.get_text(strip=True) if phone_el else ""
                addr_el = (item.select_one("[class*='address']") or
                           item.select_one("span[itemprop='streetAddress']"))
                address = addr_el.get_text(strip=True) if addr_el else "Kamloops, BC"
                warmth, score = score_lead(name, yp_cat)
                leads.append({
                    "business": name, "name": "", "email": "",
                    "phone": phone, "website": "", "address": address,
                    "segment": segment, "warmth": warmth, "score": score,
                    "reason": reason_from_category(yp_cat, name),
                    "rating": "", "source": "Yellow Pages CA",
                    "date": str(date.today())
                })
        except Exception:
            continue
        time.sleep(random.uniform(1.0, 2.0))
    return leads

# ─────────────────────────────────────────────
#  SOURCE 3 — Canada411
# ─────────────────────────────────────────────

C411_SEARCHES = [
    ("Trucking",               "Fleet"),
    ("Construction",           "Construction"),
    ("Landscaping",            "Landscaping"),
    ("Excavating",             "Construction"),
    ("Plumbing",               "Contractor"),
    ("Roofing",                "Contractor"),
    ("Electrical Contractors", "Contractor"),
    ("Courier Service",        "Fleet"),
    ("Paving",                 "Construction"),
    ("Towing",                 "Fleet"),
    ("Moving",                 "Fleet"),
    ("Security Services",      "Fleet"),
]

def scrape_canada411():
    leads = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for biz_type, segment in C411_SEARCHES:
        url = f"https://www.canada411.ca/search/si/1/{quote_plus(biz_type)}/Kamloops+BC/"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            items = (soup.select("div.listing") or
                     soup.select("[class*='result']") or
                     soup.select("article"))
            for item in items[:12]:
                name_el = (item.select_one("[class*='business-name']") or
                           item.select_one("h3") or item.select_one("h2") or
                           item.select_one("a[class*='name']"))
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                phone_el = (item.select_one("[class*='phone']") or
                            item.select_one("a[href^='tel:']"))
                phone = ""
                if phone_el:
                    phone = phone_el.get_text(strip=True)
                    if not phone and phone_el.get("href"):
                        phone = phone_el["href"].replace("tel:","")
                addr_el = item.select_one("[class*='address'], [class*='street']")
                address = addr_el.get_text(strip=True) if addr_el else "Kamloops, BC"
                warmth, score = score_lead(name, biz_type)
                leads.append({
                    "business": name, "name": "", "email": "",
                    "phone": phone, "website": "", "address": address,
                    "segment": segment, "warmth": warmth, "score": score,
                    "reason": reason_from_category(biz_type, name),
                    "rating": "", "source": "Canada411",
                    "date": str(date.today())
                })
        except Exception:
            continue
        time.sleep(random.uniform(1.0, 2.0))
    return leads

# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "TireTroopers Lead API is running 🛞"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/leads")
def get_leads(
    segment: str = Query(default="all", description="Filter by segment"),
    warmth:  str = Query(default="all", description="hot | warm | cold | all"),
    limit:   int = Query(default=100,   description="Max leads to return")
):
    """
    Scrape and return real Kamloops leads.
    Call from Lovable: GET https://your-railway-url.railway.app/leads
    """
    all_leads = []

    # Run all scrapers
    all_leads.extend(scrape_google_places([
        "construction company Kamloops BC",
        "trucking company Kamloops BC",
        "landscaping company Kamloops BC",
        "delivery service Kamloops BC",
        "excavating contractor Kamloops BC",
        "plumbing company Kamloops BC",
        "HVAC contractor Kamloops BC",
        "roofing contractor Kamloops BC",
        "electrical contractor Kamloops BC",
        "fleet management Kamloops BC",
        "paving company Kamloops BC",
        "concrete contractor Kamloops BC",
        "towing company Kamloops BC",
        "moving company Kamloops BC",
        "school bus company Kamloops BC",
    ]))

    all_leads.extend(scrape_yellowpages())
    all_leads.extend(scrape_canada411())

    # Deduplicate and sort
    all_leads = deduplicate(all_leads)
    all_leads.sort(key=lambda x: -x["score"])

    # Filter
    if segment.lower() != "all":
        all_leads = [l for l in all_leads if l["segment"].lower() == segment.lower()]
    if warmth.lower() != "all":
        all_leads = [l for l in all_leads if l["warmth"].lower() == warmth.lower()]

    return {
        "total": len(all_leads[:limit]),
        "scraped_at": str(date.today()),
        "leads": all_leads[:limit]
    }

@app.get("/leads/quick")
def get_leads_quick():
    """Faster endpoint — Yellow Pages only, no Google Places."""
    leads = scrape_yellowpages()
    leads = deduplicate(leads)
    leads.sort(key=lambda x: -x["score"])
    return {"total": len(leads), "leads": leads}
