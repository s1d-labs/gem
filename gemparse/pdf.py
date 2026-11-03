"""GeM bid document (bidplus.gem.gov.in/showbidDocument/<id>) -> dict. Handles the 2018-style English template and
the bilingual (Hindi/English) template.

Text comes from `pdftotext -layout`: each header field is a block of lines with the label on the left and the value
in a right-hand column, either side may wrap. Consignee rows keep only PIN code, quantity and delivery days, never
the official's name. Link annotations (catalogue page, buyer attachments) are read with pypdf.
"""
import io, re, subprocess

import pypdf

DEV = re.compile(r"[ऀ-ॿ]+")
BID_RE = re.compile(r"GEM/(20\d\d)/([BR])/(\d+)")

# normalised English label prefix -> field name
FIELDS = [
    ("bidenddatetime", "bid_end"), ("bidopeningdatetime", "bid_opening"), ("bidoffervalidity", "bid_validity"),
    ("bidvalidity", "bid_validity"), ("ministrystatename", "ministry"), ("ministryname", "ministry"),
    ("departmentname", "department"), ("organisationname", "organisation"), ("organizationname", "organisation"),
    ("officename", "office"), ("totalquantity", "total_quantity"), ("contractperiod", "contract_period"), ("itemcategory", "item_category"),
    ("minimumaverageannualturnover", "min_turnover"), ("oemaverageturnover", "oem_turnover"),
    ("yearsofpastexperience", "experience_years"), ("mserelaxation", "mse_relaxation"),
    ("startuprelaxation", "startup_relaxation"), ("documentrequiredfromseller", "documents_required"),
    ("bidtoraenabled", "bid_to_ra"), ("typeofbid", "bid_type"), ("evaluationmethod", "evaluation_method"),
    ("estimatedbidvalue", "estimated_value"), ("emdamount", "emd_amount"), ("pastperformance", "past_performance"),
    ("inspectionrequired", "inspection_required"), ("paymenttimelines", "payment_timelines"),
    ("bidsplitting", "splitting"), ("splitting", "splitting"),
]


def pdf_text(path_or_bytes):
    args = ["pdftotext", "-layout", "-q", "-", "-"]
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else open(path_or_bytes, "rb").read()
    return subprocess.run(args, input=data, capture_output=True, timeout=60).stdout.decode("utf-8", "ignore")


def links(path_or_bytes):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else open(path_or_bytes, "rb").read()
    out = []
    try:
        for pg in pypdf.PdfReader(io.BytesIO(data)).pages:
            for a in pg.get("/Annots") or []:
                u = str(a.get_object().get("/A", {}).get("/URI") or "").strip()
                if u.startswith("http") and u not in out:
                    out.append(u)
    except Exception:
        pass
    return out


def _norm(label):
    label = DEV.sub(" ", label)
    # bilingual labels look like ' / /Bid End Date/Time': keep from the first Latin letter
    m = re.search(r"[A-Za-z].*", label)
    return re.sub(r"[^a-z]", "", (m.group(0) if m else "").lower())


def _blocks(lines):
    """Split the header into blank-line separated blocks of (left label text, right value text)."""
    blocks, cur = [], []
    for ln in lines + [""]:
        if not ln.strip():
            if cur:
                blocks.append(cur)
            cur = []
        else:
            cur.append(ln.rstrip())
    out = []
    for b in blocks:
        # a line with both label and value starts a new field once the current one has a value;
        # label-only lines extend the label, value-only lines extend the value (either side may wrap)
        left, right = [], []
        for ln in b:
            ind = len(ln) - len(ln.lstrip())
            body = ln.strip()
            if ind >= 40:                       # value-only line
                right.append(body)
                continue
            m = re.match(r"(.*?\S)\s{3,}(\S.*)$", body)
            if m:
                if right and left:
                    out.append((" ".join(left), " ".join(right))); left, right = [], []
                left.append(m.group(1)); right.append(m.group(2))
            else:
                left.append(body)
        if left or right:
            out.append((" ".join(left), " ".join(right)))
    return out


def _num(s):
    m = re.search(r"[\d,]+(?:\.\d+)?", s or "")
    return float(m.group(0).replace(",", "")) if m else None


def parse(path_or_bytes, text=None):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else open(path_or_bytes, "rb").read()
    t = text if text is not None else pdf_text(data)
    out = {"ok": False, "template": None, "bid_number": None}
    if not t.strip():
        return out
    m = BID_RE.search(t)
    out["bid_number"] = m.group(0) if m else None
    out["template"] = "bilingual" if DEV.search(t[:3000]) else "english"
    dm = re.search(r"Dated[^0-9\n]{0,30}(\d\d-\d\d-\d{4})", DEV.sub(" ", t))
    out["dated"] = dm.group(1) if dm else None

    # header: from 'Bid Details' to the technical specification / item block
    lines = t.split("\n")
    end = next((i for i, l in enumerate(lines) if re.search(r"Technical Specifications|Consignees", l)), len(lines))
    for label, value in _blocks(lines[:end]):
        key = _norm(label)
        if not key or not value:
            continue
        for pref, field in FIELDS:
            if key.startswith(pref) and field not in out:
                out[field] = re.sub(r"\s+", " ", DEV.sub(" ", value)).strip()
                break
    for f in ("total_quantity", "emd_amount", "estimated_value"):
        if f in out:
            out[f + "_num"] = _num(out[f])

    clean = DEV.sub(" ", t)
    # items: "<category> ( <qty> ) ( Under PAC )" lines, plus Make / Model under them
    items = []
    spec_at = [m.start() for m in re.finditer(r"Technical Specifications", clean)]
    for im in re.finditer(r"^\s*(\S[^\n]{2,200}?)\s*\(\s*([\d,]+)\s*\)\s*(\(\s*Under PAC\s*\))?\s*$", clean, re.M):
        cat = im.group(1).strip()
        if re.search(r"(?i)item category|^(bid|total|quantity)\b|/", cat):
            continue
        # a real item line comes just before its 'Technical Specifications' block, never inside the spec table
        nxt = next((a for a in spec_at if a > im.end()), None)
        if nxt is None or nxt - im.end() > 600:
            continue
        it = {"category": cat, "quantity": int(im.group(2).replace(",", "")), "pac": bool(im.group(3))}
        tail = clean[im.end(): im.end() + 400]
        mk = re.search(r"^\s*Make\s{2,}(\S[^\n]*)$", tail, re.M)
        md = re.search(r"^\s*Model\s{2,}(\S[^\n]*)$", tail, re.M)
        it["make"] = mk.group(1).strip() if mk else None
        it["model"] = md.group(1).strip() if md else None
        items.append(it)
    if not items and out.get("item_category"):   # bilingual template: no per-item line, header carries it
        items = [{"category": re.sub(r"\s*\((?:Q\d|V\d)\)", "", out["item_category"]).strip(), "quantity": int(out.get("total_quantity_num") or 0),
                  "pac": bool(re.search(r"PAC", out["item_category"])), "make": None, "model": None}]
    out["items"] = items
    out["pac"] = bool(re.search(r"PAC Only|Under PAC", clean)) or any(i["pac"] for i in items)
    if items:
        out["make"] = next((i["make"] for i in items if i["make"]), None)
        out["model"] = next((i["model"] for i in items if i["model"]), None)

    # consignees: rows ending '... <qty>  <days>' inside the consignee section; PIN from the row block
    cons = []
    cm = re.search(r"Consignees?.{0,80}?(?:Quantity|Reporting)", clean, re.S)
    if cm:
        sec = clean[cm.end(): cm.end() + 20000]
        stop = re.search(r"Buyer Added|Buyer Specific|Bid Specific|EMD Detail|Required\s{2,}|Splitting|Disclaimer", sec)
        sec = sec[: stop.start()] if stop else sec
        sl = sec.split("\n")
        for i, ln in enumerate(sl):
            q = re.search(r"\S\s{2,}([\d,]+)\s{2,}(\d{1,4})\s*$", ln)
            if not q:
                continue
            near = "\n".join(sl[max(0, i - 3): i + 4])
            p = re.search(r"\b(\d{6})\b", ln) or re.search(r"\b(\d{6})\b", near)
            cons.append({"pin": p.group(1) if p else None, "quantity": int(q.group(1).replace(",", "")), "delivery_days": int(q.group(2))})
    out["consignees"] = cons

    sm = re.search(r"Scope of supply[^:\n]*:\s*([^\n]+(?:\n\s{4,}[^\n]+)?)", clean)
    out["scope"] = re.split(r"\s*This Bid is", re.sub(r"\s+", " ", sm.group(1)))[0].strip() if sm else None
    out["installation"] = bool(out["scope"] and re.search(r"(?i)install|commission", out["scope"]))

    am = re.search(r"Buyer Added Bid Specific|Buyer Specific Additional Terms|Additional Terms and Conditions", clean)
    if am:
        sec = clean[am.start(): am.start() + 25000]
        stop = re.search(r"This Bid is (?:also )?governed by|Disclaimer|---Thank You---", sec)
        out["buyer_terms"] = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", sec[: stop.start()] if stop else sec)).strip()
    else:
        out["buyer_terms"] = None

    sp = re.search(r"Technical Specifications", clean)
    out["spec_text"] = re.sub(r"[ \t]+", " ", clean[sp.end(): sp.end() + 6000]).strip() if sp else None
    out["links"] = links(data)
    out["catalogue_links"] = [u for u in out["links"] if "showCatalogue/" in u]
    out["attachment_links"] = [u for u in out["links"] if re.search(r"slafds|uploaded_documents|documentdownload|BoqDocument|BoqLineItems", u)]
    # some 2021 documents print the bid number only in a header graphic: the crawler knows the id it fetched
    out["ok"] = "total_quantity_num" in out or "contract_period" in out   # services print a contract period, no quantity
    return out
