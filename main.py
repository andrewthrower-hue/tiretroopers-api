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
HUNTER_API_KEY      = os.getenv("HUNTER_API_KEY", "")

# ─────────────────────────────────────────────
#  EMAIL FINDER — Hunter.io + Website Scraping
# ─────────────────────────────────────────────

def extract_domain(website: str) -> str:
    """Pull clean domain from a website URL."""
    if not website:
        return ""
    website = re.sub(r'^https?://(www\.)?', '', website.lower().strip())
    return website.split('/')[0].strip()

def find_email_on_website(website: str) -> str:
    """Scan a business website for any listed email address."""
    if not website:
        return ""
    try:
        url = website if website.startswith('http') else 'https://' + website
        r = requests.get(url, timeout=8, headers=HEADERS)
        if r.status_code != 200:
            return ""
        # Find all email addresses on the page
        emails = re.findall(
            r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
            r.text
        )
        # Filter out common non-contact emails
        skip = ['noreply','no-reply','example','test','spam','privacy','support@wordpress']
        for email in emails:
            if not any(s in email.lower() for s in skip):
                return email.lower()
    except Exception:
        pass
    return ""

def find_email_hunter(domain: str, company: str) -> str:
    """Use Hunter.io to find email for a domain."""
    if not HUNTER_API_KEY or not domain:
        return ""
    try:
        # First try domain search
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "company": company,
                "api_key": HUNTER_API_KEY,
                "limit": 3,
                "type": "generic"
            },
            timeout=10
        )
        data = r.json()
        emails = data.get("data", {}).get("emails", [])
        if emails:
            # Prefer generic emails like info@, contact@, admin@
            for e in emails:
                val = e.get("value","")
                prefix = val.split("@")[0].lower()
                if any(p in prefix for p in ["info","contact","admin","hello","office","sales","service"]):
                    return val
            return emails[0].get("value","")

        # Fallback: email finder with just domain
        r2 = requests.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain": domain,
                "api_key": HUNTER_API_KEY
            },
            timeout=10
        )
        data2 = r2.json()
        return data2.get("data", {}).get("email", "")
    except Exception:
        return ""

def enrich_lead_email(lead: dict) -> dict:
    """Try to find email for a lead using website scraping then Hunter.io."""
    if lead.get("email"):
        return lead  # already has one

    website = lead.get("website", "")
    domain  = extract_domain(website)

    # Step 1 — scrape their website for email (free)
    if website:
        email = find_email_on_website(website)
        if email:
            lead["email"] = email
            lead["email_source"] = "website"
            return lead

    # Step 2 — Hunter.io lookup (uses API credits)
    if domain and HUNTER_API_KEY:
        email = find_email_hunter(domain, lead.get("business",""))
        if email:
            lead["email"] = email
            lead["email_source"] = "hunter.io"
            return lead

    lead["email_source"] = ""
    return lead

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

    # Enrich top leads with emails
    top_leads = all_leads[:limit]
    print(f"Enriching {len(top_leads)} leads with emails...")
    enriched = []
    for lead in top_leads:
        try:
            lead = enrich_lead_email(lead)
        except Exception:
            pass
        enriched.append(lead)
        time.sleep(0.3)

    found = sum(1 for l in enriched if l.get("email"))

    return {
        "total": len(enriched),
        "emails_found": found,
        "scraped_at": str(date.today()),
        "leads": enriched
    }

@app.get("/leads/quick")
def get_leads_quick():
    """Faster endpoint — Yellow Pages only, enriched with emails."""
    leads = scrape_yellowpages()
    leads = deduplicate(leads)
    leads.sort(key=lambda x: -x["score"])

    # Enrich with emails — website scrape first, Hunter.io fallback
    print(f"Enriching {len(leads)} leads with email addresses...")
    enriched = []
    for lead in leads:
        try:
            lead = enrich_lead_email(lead)
        except Exception:
            pass
        enriched.append(lead)
        time.sleep(0.3)  # be polite

    found = sum(1 for l in enriched if l.get("email"))
    print(f"Found emails for {found}/{len(enriched)} leads")

    return {
        "total": len(enriched),
        "emails_found": found,
        "leads": enriched
    }


@app.get("/leads/enrich/{domain}")
def enrich_single(domain: str, company: str = ""):
    """Look up email for a single domain — useful for manual enrichment."""
    email = find_email_hunter(domain, company) or find_email_on_website("https://" + domain)
    return {"domain": domain, "email": email or "not found"}

# ─────────────────────────────────────────────
#  EMAIL GENERATION & SENDING
# ─────────────────────────────────────────────

from pydantic import BaseModel
from typing import Optional

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
RESEND_API_KEY    = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL        = os.getenv("FROM_EMAIL", "andrew@tiretroopers.com")
OWNER_NAME        = os.getenv("OWNER_NAME", "Andrew")
BUSINESS_NAME     = os.getenv("BUSINESS_NAME", "Tire Troopers")
BUSINESS_PHONE    = os.getenv("BUSINESS_PHONE", "")

class EmailRequest(BaseModel):
    business:    str
    contact:     Optional[str] = ""
    email:       str
    phone:       Optional[str] = ""
    segment:     Optional[str] = ""
    reason:      Optional[str] = ""
    template:    Optional[str] = "seasonal"   # seasonal | fleet | intro | followup | promo
    preview_only: Optional[bool] = True        # True = just return email, False = actually send

def generate_email_with_claude(lead: EmailRequest) -> dict:
    """Call Claude API to write a personalized email."""
    first_name = lead.contact.split()[0] if lead.contact else "there"

    template_guide = {
        "seasonal":  "seasonal tire changeover — spring is here, time to swap winter tires, we come to them",
        "fleet":     "fleet service pitch — reduce downtime, we come to their yard or job site",
        "intro":     "warm cold intro — first touch, friendly, curious about their needs",
        "followup":  "gentle follow-up — brief, reference previous message, low pressure",
        "promo":     "special offer — $20 off first changeover, valid this month only",
    }.get(lead.template, "seasonal tire changeover")

    prompt = f"""You are writing a real sales email for {OWNER_NAME}, owner of {BUSINESS_NAME} — a mobile tire service in Kamloops, BC.

RECIPIENT:
- Business: {lead.business}
- Contact name: {lead.contact or 'unknown'}
- Segment: {lead.segment}
- Why they are a lead: {lead.reason}

YOUR BUSINESS ({BUSINESS_NAME}):
- You come to THEM — no shop visit needed
- Serve Kamloops, Sun Peaks, Chase, Merritt
- Fast, affordable, available weekdays and weekends
- Phone: {BUSINESS_PHONE}
- Email: {FROM_EMAIL}

EMAIL GOAL: {template_guide}

RULES:
- Open with "Hi {first_name}," 
- Reference their specific business and situation naturally
- Sound like a real local person, not a salesperson
- One clear call to action at the end (reply or call)
- Under 150 words
- Plain text only, no markdown, no bullet points
- Sign off: {OWNER_NAME} | {BUSINESS_NAME} | {BUSINESS_PHONE} | {FROM_EMAIL}
- Do NOT write a subject line in the body

Write only the email body."""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )
        data = res.json()
        body = data["content"][0]["text"].strip()
    except Exception as e:
        # Fallback template if Claude fails
        body = f"""Hi {first_name},

Hope things are going well at {lead.business}! I'm {OWNER_NAME} from {BUSINESS_NAME} — we're a mobile tire service based in Kamloops, meaning we come right to your location for changeovers, replacements, or repairs. No shop trips needed.

{f"I noticed {lead.reason.lower()} — sounds like we could save you some hassle this season." if lead.reason else "We work with a lot of local businesses and thought you might find it useful."}

Worth a quick chat? Happy to swing by for a free look.

{OWNER_NAME}
{BUSINESS_NAME}
{BUSINESS_PHONE}
{FROM_EMAIL}"""

    # Generate subject line
    subject_map = {
        "seasonal":  f"Tire Changeover for {lead.business} — We Come to You",
        "fleet":     f"Mobile Tire Service for {lead.business}'s Fleet",
        "intro":     f"Local Mobile Tire Service — {lead.business}",
        "followup":  f"Following Up — Tire Service for {lead.business}",
        "promo":     f"$20 Off First Changeover — {lead.business}",
    }
    subject = subject_map.get(lead.template, f"Mobile Tire Service for {lead.business}")

    return {"subject": subject, "body": body}


def send_via_resend(to_email: str, subject: str, body: str) -> bool:
    """Send email through Resend."""
    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": f"{BUSINESS_NAME} <{FROM_EMAIL}>",
                "to": [to_email],
                "subject": subject,
                "text": body,   # plain text = better deliverability
            },
            timeout=15
        )
        return res.status_code == 200
    except Exception:
        return False


@app.post("/email/generate")
def generate_email(req: EmailRequest):
    """Generate a personalized email. Set preview_only=false to also send it."""
    if not req.email or "@" not in req.email:
        return JSONResponse(status_code=400, content={"error": "Valid email address required"})

    result = generate_email_with_claude(req)

    if req.preview_only:
        return {
            "status": "preview",
            "to": req.email,
            "subject": result["subject"],
            "body": result["body"]
        }

    # Actually send
    if not RESEND_API_KEY:
        return JSONResponse(status_code=500, content={"error": "RESEND_API_KEY not configured"})

    sent = send_via_resend(req.email, result["subject"], result["body"])

    return {
        "status": "sent" if sent else "failed",
        "to": req.email,
        "subject": result["subject"],
        "body": result["body"]
    }


@app.post("/email/send")
def send_email(req: EmailRequest):
    """Generate AND send immediately."""
    req.preview_only = False
    return generate_email(req)
