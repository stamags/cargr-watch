#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""car.gr Morning Brief — daily agent (GitHub Actions edition).
Fetch (ZenRows) -> parse -> diff vs state.json -> email (Resend) -> rewrite state.json.
State lives in state.json in this repo; the workflow commits it back each run."""
import json, re, os, sys, urllib.parse, urllib.request, urllib.error, datetime

ZENROWS_KEY = os.environ["ZENROWS_KEY"]
RESEND_KEY  = os.environ["RESEND_KEY"]
STATE_FILE  = os.environ.get("STATE_FILE", "state.json")
EMAIL_TO    = os.environ.get("EMAIL_TO", "stamags1988@gmail.com")
EMAIL_FROM  = os.environ.get("EMAIL_FROM", "car.gr watch <onboarding@resend.dev>")

# --- Add more searches here anytime (name + car.gr URL) ---
SEARCHES = [
    {"name": "Alfa Romeo Giulia + Stelvio · Πετρέλαιο · 2020+",
     "url": "https://www.car.gr/used-cars/alfa_romeo.html?category=15001&fuel_type=2&make=32458&model=16730&model=18921&registration-from=2020"},
]

TODAY = datetime.date.today().strftime("%d/%m/%Y")

# ---------------- HTTP helpers ----------------
UA = "Mozilla/5.0 (cargr-watch; +https://car.gr) curl/8"

def _req(url, data=None, headers=None, method=None, timeout=120):
    h = {"User-Agent": UA}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), resp.status
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace"), e.code

def zen_fetch(target_url, premium=False):
    # wait=12000: car.gr renders its listings client-side; ~12s lets the JS
    # populate the DOM before ZenRows snapshots it. Without it the markdown
    # comes back empty/partial intermittently. wait adds no credit cost.
    q = {"url": target_url, "apikey": ZENROWS_KEY,
         "js_render": "true", "response_type": "markdown", "wait": "12000"}
    if premium:
        q["premium_proxy"] = "true"; q["proxy_country"] = "gr"
    api = "https://api.zenrows.com/v1/?" + urllib.parse.urlencode(q)
    return _req(api, timeout=180)

def zen_fetch_retry(target_url):
    # Try cheap js_render (reliable with wait) twice; escalate to premium proxy once.
    for _ in range(2):
        body, status = zen_fetch(target_url, premium=False)
        if status == 200 and "classifieds/cars/view" in body:
            return body, status
    return zen_fetch(target_url, premium=True)

# ---------------- parsing ----------------
def parse_listings(md):
    out = {}
    starts = [m.start() for m in re.finditer(r'(?m)^\s*\d{1,2}\.\s\[!\[', md)]
    starts.append(len(md))
    for i in range(len(starts) - 1):
        block = md[starts[i]:starts[i + 1]]
        murl = re.search(r'/classifieds/cars/view/(\d+)-([a-z0-9-]+)', block)
        if not murl:
            continue
        lid, slug = murl.group(1), murl.group(2)
        price_m = re.search(r'([\d\.]+)\s*€', block)
        if not price_m:
            continue
        price = int(price_m.group(1).replace('.', ''))
        title_m = re.search(r'\*\*([^*]+?)\*\*', block)
        title = title_m.group(1).strip() if title_m else 'Αγγελία'
        km_m = re.search(r'([\d\.]+)\s*Km', block)
        km = int(km_m.group(1).replace('.', '')) if km_m else None
        ph = re.search(r'https://static\.car\.gr/' + re.escape(lid) +
                       r'_[A-Za-z0-9_]+\.(?:jpg|jpeg|png|webp)', block) \
             or re.search(r'https://static\.car\.gr/\d+_[A-Za-z0-9_]+\.(?:jpg|jpeg|png|webp)', block)
        photo = ph.group(0) if ph else ''
        locs = re.findall(r'([Α-ΩΆ-Ώ][Α-ΩΆ-Ώα-ωά-ώ.\s]+?\s\d{5})', block)
        location = re.sub(r'\s+', ' ', locs[-1]).strip() if locs else ''
        out[lid] = {"id": lid, "title": title, "price": price, "km": km,
                    "photo": photo, "location": location,
                    "url": "https://www.car.gr/classifieds/cars/view/%s-%s" % (lid, slug)}
    return out

def fetch_all(search_url):
    md1, _ = zen_fetch_retry(search_url)
    tot_m = re.search(r'(\d+)\s*[Αα]γγελ', md1)
    total = int(tot_m.group(1)) if tot_m else None
    items = dict(parse_listings(md1))
    pg = 2
    while total and len(items) < total and pg <= 12:
        sep = '&' if '?' in search_url else '?'
        md, _ = zen_fetch_retry(search_url + sep + "pg=%d" % pg)
        page = parse_listings(md)
        fresh = {k: v for k, v in page.items() if k not in items}
        if not fresh:
            break
        items.update(page)
        pg += 1
    return items, (total or len(items))

# ---------------- state (local file, committed by the workflow) ----------------
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"searches": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")

# ---------------- formatting ----------------
def eur(n):
    return "{:,.0f}".format(n).replace(",", ".") + " €"

def kmfmt(n):
    return ("{:,.0f}".format(n).replace(",", ".") + " χλμ") if n else "—"

def median(xs):
    s = sorted(xs); n = len(s)
    if not n: return 0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) // 2

def row(l):
    img = ('<img src="%s" width="92" height="69" style="border-radius:6px;object-fit:cover;display:block" alt="">' % l["photo"]) if l["photo"] else ""
    return (
      '<tr>'
      '<td style="padding:8px 10px;vertical-align:top">%s</td>'
      '<td style="padding:8px 10px;vertical-align:top">'
        '<div style="font-weight:600;font-size:14px;color:#111"><a href="%s" style="color:#0b6bcb;text-decoration:none">%s</a></div>'
        '<div style="font-size:12px;color:#666;margin-top:2px">%s · %s</div>'
      '</td>'
      '<td style="padding:8px 10px;vertical-align:top;text-align:right;white-space:nowrap;font-weight:700;font-size:15px;color:#111">%s</td>'
      '</tr>'
    ) % (img, l["url"], l["title"], kmfmt(l["km"]), l["location"] or "—", eur(l["price"]))

def tile(label, value):
    return (
      '<td style="padding:14px 8px;text-align:center;background:#f6f8fa;border-radius:10px">'
      '<div style="font-size:11px;letter-spacing:.06em;color:#8a94a3;text-transform:uppercase">%s</div>'
      '<div style="font-size:20px;font-weight:800;color:#111;margin-top:4px">%s</div>'
      '</td>'
    ) % (label, value)

def build_search_html(s, items, prev):
    prices = [l["price"] for l in items.values()]
    lo, hi = (min(prices), max(prices)) if prices else (0, 0)
    med = median(prices)
    baseline = not prev
    new_ids = [i for i in items if i not in prev] if not baseline else []
    changes = []
    for i, l in items.items():
        if i in prev and prev[i] != l["price"]:
            changes.append((l, prev[i], l["price"]))

    ordered = sorted(items.values(), key=lambda l: l["price"])

    parts = []
    parts.append('<div style="font-size:18px;font-weight:800;color:#111;margin:0 0 2px">%s</div>' % s["name"])
    parts.append('<div style="font-size:13px;color:#8a94a3;margin:0 0 14px">Παρακολουθώ %d αγγελίες · %s</div>' % (len(items), TODAY))
    # tiles
    parts.append('<table width="100%%" cellspacing="8" cellpadding="0" style="border-collapse:separate;margin-bottom:16px"><tr>'
                 + tile("Αγγελίες", str(len(items)))
                 + tile("Διάμεση", eur(med))
                 + tile("Εύρος", "%s–%s" % (eur(lo).replace(" €",""), eur(hi))) + '</tr></table>')

    if baseline:
        parts.append('<div style="background:#fff8e1;border:1px solid #ffe08a;border-radius:8px;padding:10px 12px;font-size:13px;color:#8a6d00;margin-bottom:16px">📌 Πρώτη καταγραφή (baseline) — από αύριο θα βλέπεις <b>νέες αγγελίες</b> και <b>αλλαγές τιμών</b>.</div>')
    else:
        # New listings
        if new_ids:
            parts.append('<div style="font-size:15px;font-weight:700;color:#111;margin:6px 0 8px">🆕 Νέες αγγελίες (%d)</div>' % len(new_ids))
            parts.append('<table width="100%%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-bottom:16px">'
                         + ''.join(row(items[i]) for i in new_ids) + '</table>')
        else:
            parts.append('<div style="font-size:13px;color:#8a94a3;margin:6px 0 12px">🆕 Νέες αγγελίες: καμία</div>')
        # Price changes
        if changes:
            parts.append('<div style="font-size:15px;font-weight:700;color:#111;margin:6px 0 8px">💶 Αλλαγές τιμής (%d)</div>' % len(changes))
            crows = []
            for l, oldp, newp in changes:
                arrow = "🔻" if newp < oldp else "🔺"
                col = "#137333" if newp < oldp else "#c5221f"
                diff = eur(abs(newp - oldp))
                crows.append(
                  '<tr>'
                  '<td style="padding:8px 10px;vertical-align:top">%s</td>'
                  '<td style="padding:8px 10px"><div style="font-weight:600;font-size:14px"><a href="%s" style="color:#0b6bcb;text-decoration:none">%s</a></div>'
                  '<div style="font-size:12px;color:#666">%s · %s</div></td>'
                  '<td style="padding:8px 10px;text-align:right;white-space:nowrap">'
                  '<div style="font-size:12px;color:#999;text-decoration:line-through">%s</div>'
                  '<div style="font-weight:700;font-size:15px;color:%s">%s %s <span style="font-size:11px">(%s)</span></div>'
                  '</td></tr>'
                  % (('<img src="%s" width="92" height="69" style="border-radius:6px;object-fit:cover;display:block" alt="">' % l["photo"]) if l["photo"] else "",
                     l["url"], l["title"], kmfmt(l["km"]), l["location"] or "—",
                     eur(oldp), col, arrow, eur(newp), diff))
            parts.append('<table width="100%%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-bottom:16px">' + ''.join(crows) + '</table>')
        else:
            parts.append('<div style="font-size:13px;color:#8a94a3;margin:6px 0 12px">💶 Αλλαγές τιμής: καμία</div>')

    # full list
    parts.append('<div style="font-size:15px;font-weight:700;color:#111;margin:14px 0 8px">📋 Όλες οι αγγελίες (φθηνότερη πρώτα)</div>')
    parts.append('<table width="100%%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;border-top:1px solid #eee">'
                 + ''.join(row(l) for l in ordered)
                 + '</table>')

    summary = {"new": len(new_ids), "changes": len(changes), "baseline": baseline}
    return "".join(parts), summary

def send_email(subject, html):
    payload = json.dumps({"from": EMAIL_FROM, "to": [EMAIL_TO],
                          "subject": subject, "html": html}).encode()
    hdr = {"Authorization": "Bearer %s" % RESEND_KEY, "Content-Type": "application/json"}
    body, status = _req("https://api.resend.com/emails", data=payload, headers=hdr, method="POST")
    return status, body

# ---------------- main ----------------
def main():
    state = load_state()
    state.setdefault("searches", {})
    sections, totals = [], {"new": 0, "changes": 0}
    any_baseline = False
    for s in SEARCHES:
        items, _ = fetch_all(s["url"])
        if not items:
            sections.append('<div style="color:#c5221f">⚠️ Δεν βρέθηκαν αγγελίες για «%s» (πιθανό πρόβλημα fetch).</div>' % s["name"])
            continue
        prev = state["searches"].get(s["name"], {})
        html, summ = build_search_html(s, items, prev)
        sections.append(html)
        totals["new"] += summ["new"]; totals["changes"] += summ["changes"]
        any_baseline = any_baseline or summ["baseline"]
        state["searches"][s["name"]] = {i: l["price"] for i, l in items.items()}

    body = ('<div style="max-width:640px;margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#fff;padding:20px">'
            '<div style="font-size:22px;font-weight:900;color:#111;margin-bottom:2px">🚗 car.gr Morning Brief</div>'
            '<div style="font-size:13px;color:#8a94a3;margin-bottom:20px">%s</div>'
            '%s'
            '<div style="margin-top:24px;padding-top:14px;border-top:1px solid #eee;font-size:11px;color:#b0b7c0">Αυτόματο daily brief · πηγή: car.gr</div>'
            '</div>') % (TODAY, '<div style="height:22px"></div>'.join(sections))

    if any_baseline:
        subj = "🚗 car.gr Morning Brief — %s (baseline)" % TODAY
    else:
        bits = []
        if totals["new"]: bits.append("%d νέες" % totals["new"])
        if totals["changes"]: bits.append("%d αλλαγές τιμής" % totals["changes"])
        tag = (" — " + ", ".join(bits)) if bits else " — καμία αλλαγή"
        subj = "🚗 car.gr Morning Brief — %s%s" % (TODAY, tag)

    status, resp = send_email(subj, body)
    print("EMAIL:", status, resp[:200])
    if status in (200, 201):
        save_state(state)
        print("STATE saved. searches:", {k: len(v) for k, v in state["searches"].items()})
    else:
        print("EMAIL FAILED — state NOT updated.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
