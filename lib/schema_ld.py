"""Deterministic schema.org JSON-LD generator for SEO / GEO / AIO.

Pure-python, stdlib-only. NO network, NO LLM, NO external API. Given already-
generated article markdown plus an optional grounding bundle, this module parses
what it can and emits copy-paste-ready schema.org JSON-LD.

Guiding principle: never fabricate. A schema property is only emitted when a value
is clearly derivable from the inputs. Missing / None inputs never raise — the
functions return sensible empties instead.

Public API
----------
- parse_faq(publish_md) -> list[(question, answer)]
- parse_howto_steps(publish_md) -> list[(step_name, step_text)]
- article_schema(...) -> dict
- faqpage_schema(pairs) -> dict | None
- howto_schema(...) -> dict | None
- breadcrumb_schema(...) -> dict
- localbusiness_schema(grounding_bundle, ...) -> dict | None
- build_all(publish_md, ...) -> {"blocks", "combined_json", "script_html"}
"""
from __future__ import annotations

import datetime
import json
import re

SCHEMA_CONTEXT = "https://schema.org"

# article_type -> Article @type
_ARTICLE_TYPE_MAP = {
    "blog article": "BlogPosting",
    "thought leadership": "BlogPosting",
    "listicle": "BlogPosting",
    "comparison article": "BlogPosting",
    "news article": "NewsArticle",
    "press release": "NewsArticle",
    "how-to guide": "Article",
    "landing page": "WebPage",
    "pillar page": "WebPage",
    "web page": "WebPage",
}


# --------------------------------------------------------------------------- #
# Markdown cleaning helpers
# --------------------------------------------------------------------------- #
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_UNDERSCORE_BOLD_RE = re.compile(r"__([^_]+)__")
_CODE_RE = re.compile(r"`([^`]*)`")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def _strip_inline(text: str) -> str:
    """Strip markdown inline formatting to clean prose. Never raises."""
    if not text:
        return ""
    s = str(text)
    s = _IMG_RE.sub(r"\1", s)            # images -> alt text
    s = _LINK_RE.sub(r"\1", s)           # links -> link text
    s = _BOLD_RE.sub(r"\1", s)           # **bold**
    s = _UNDERSCORE_BOLD_RE.sub(r"\1", s)  # __bold__
    s = _ITALIC_RE.sub(r"\1", s)         # *italic*
    s = _CODE_RE.sub(r"\1", s)           # `code`
    # leftover stray markers
    s = s.replace("**", "").replace("`", "")
    # strip leading list markers / blockquote markers on a single fragment
    s = re.sub(r"^\s*[-*+]\s+", "", s)
    s = re.sub(r"^\s*>\s?", "", s)
    return s.strip()


def _collapse_ws(text: str) -> str:
    """Collapse all runs of whitespace / newlines into single spaces."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _clean_block(text: str) -> str:
    """Strip inline markdown from a multi-line block and collapse whitespace."""
    if not text:
        return ""
    lines = [_strip_inline(ln) for ln in str(text).splitlines()]
    return _collapse_ws(" ".join(ln for ln in lines if ln))


def _iter_headings(md: str):
    """Yield (index, level, heading_text_stripped) for each markdown heading line."""
    if not md:
        return
    for i, line in enumerate(md.splitlines()):
        m = _HEADING_RE.match(line)
        if m:
            yield i, len(m.group(1)), _strip_inline(m.group(2))


# --------------------------------------------------------------------------- #
# FAQ parsing
# --------------------------------------------------------------------------- #
def parse_faq(publish_md: str) -> list:
    """Parse a FAQ section into [(question, answer_plaintext), ...].

    Looks for a `## Frequently Asked Questions` heading, then collects each
    following `### <question>` block (question text typically ends in '?') with
    its answer paragraphs, up to the next heading. Returns [] if no FAQ section.
    """
    if not publish_md:
        return []
    lines = publish_md.splitlines()

    # locate the FAQ H2 (any level 2 heading whose text mentions "frequently
    # asked questions" or is exactly "faq" / "faqs").
    faq_start = None
    faq_level = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        htext = _strip_inline(m.group(2)).lower()
        if "frequently asked question" in htext or htext in ("faq", "faqs"):
            faq_start = i
            faq_level = level
            break
    if faq_start is None:
        return []

    pairs = []
    i = faq_start + 1
    n = len(lines)
    while i < n:
        m = _HEADING_RE.match(lines[i])
        if m:
            level = len(m.group(1))
            # a heading at or above the FAQ section level ends the section
            if level <= faq_level:
                break
            # a question heading (deeper than the FAQ heading)
            question = _strip_inline(m.group(2))
            # collect answer lines until the next heading
            j = i + 1
            ans_lines = []
            while j < n and not _HEADING_RE.match(lines[j]):
                ans_lines.append(lines[j])
                j += 1
            answer = _clean_block("\n".join(ans_lines))
            if question:
                pairs.append((question, answer))
            i = j
            continue
        i += 1
    return pairs


# --------------------------------------------------------------------------- #
# HowTo parsing
# --------------------------------------------------------------------------- #
_STEP_HEADING_RE = re.compile(r"^step\s+\d+\s*[:.)-]?\s*(.*)$", re.IGNORECASE)
_STEP_PREFIX_RE = re.compile(r"^step\s+\d+\s*[:.)-]\s*(.*)$", re.IGNORECASE)


def parse_howto_steps(publish_md: str) -> list:
    """Parse How-To steps into [(step_name, step_text), ...].

    Steps come from either: headings under a section whose heading text is
    "Steps" (case-insensitive), OR any heading whose text matches `Step \\d+`.
    Step name = text after `Step N:` if present, else the heading text.
    Returns [] if no steps found.
    """
    if not publish_md:
        return []
    lines = publish_md.splitlines()
    n = len(lines)

    # Find a "Steps" section: collect the level so we know where it ends.
    steps_start = None
    steps_level = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        if _strip_inline(m.group(2)).strip().lower() == "steps":
            steps_start = i
            steps_level = len(m.group(1))
            break

    def _extract_step(heading_text: str):
        """Return step_name from a heading, or None if it isn't a step heading."""
        pm = _STEP_HEADING_RE.match(heading_text.strip())
        if pm:
            name = pm.group(1).strip()
            return name if name else heading_text.strip()
        return None

    results = []

    if steps_start is not None:
        # parse sub-headings within the Steps section
        i = steps_start + 1
        while i < n:
            m = _HEADING_RE.match(lines[i])
            if m:
                level = len(m.group(1))
                if level <= steps_level:
                    break  # section ended
                heading_text = _strip_inline(m.group(2))
                # collect body until next heading
                j = i + 1
                body = []
                while j < n and not _HEADING_RE.match(lines[j]):
                    body.append(lines[j])
                    j += 1
                step_name = _extract_step(heading_text)
                if step_name is None:
                    step_name = heading_text
                text = _clean_block("\n".join(body))
                if step_name:
                    results.append((step_name, text))
                i = j
                continue
            i += 1
        if results:
            return results

    # Fallback: no Steps section (or it was empty) — scan for `Step N` headings
    # anywhere in the document.
    i = 0
    while i < n:
        m = _HEADING_RE.match(lines[i])
        if m:
            heading_text = _strip_inline(m.group(2))
            step_name = _extract_step(heading_text)
            if step_name is not None:
                j = i + 1
                body = []
                while j < n and not _HEADING_RE.match(lines[j]):
                    body.append(lines[j])
                    j += 1
                text = _clean_block("\n".join(body))
                results.append((step_name, text))
                i = j
                continue
        i += 1
    return results


# --------------------------------------------------------------------------- #
# Schema builders
# --------------------------------------------------------------------------- #
def article_schema(
    *,
    article_type,
    headline,
    description,
    author,
    publisher_name,
    publisher_url=None,
    url=None,
    language="English",
    date_published=None,
    date_modified=None,
    image=None,
) -> dict:
    """Build an Article-family JSON-LD dict.

    `author` is a dict {"name","title","url"} (any key may be missing) or None.
    Only fields with real values are emitted.
    """
    at = _ARTICLE_TYPE_MAP.get((article_type or "").strip().lower(), "Article")
    obj = {"@context": SCHEMA_CONTEXT, "@type": at}

    headline = _collapse_ws(_strip_inline(headline or ""))
    if headline:
        obj["headline"] = headline

    description = _collapse_ws(_strip_inline(description or ""))
    if description:
        obj["description"] = description

    if url:
        obj["url"] = url
        obj["mainEntityOfPage"] = {"@type": "WebPage", "@id": url}

    if image:
        obj["image"] = image

    if language:
        obj["inLanguage"] = language

    if date_published:
        obj["datePublished"] = date_published
    if date_modified:
        obj["dateModified"] = date_modified

    # author
    if isinstance(author, dict):
        a_name = _collapse_ws(str(author.get("name") or ""))
        if a_name:
            a = {"@type": "Person", "name": a_name}
            a_title = _collapse_ws(str(author.get("title") or ""))
            if a_title:
                a["jobTitle"] = a_title
            a_url = author.get("url")
            if a_url:
                a["url"] = a_url
            obj["author"] = a

    # publisher
    pub_name = _collapse_ws(str(publisher_name or ""))
    if pub_name:
        publisher = {"@type": "Organization", "name": pub_name}
        if publisher_url:
            publisher["url"] = publisher_url
        obj["publisher"] = publisher

    return obj


def faqpage_schema(pairs) -> dict:
    """Build a FAQPage JSON-LD dict from [(q, a), ...]. None if pairs empty."""
    if not pairs:
        return None
    main = []
    for q, a in pairs:
        q_clean = _collapse_ws(_strip_inline(q or ""))
        a_clean = _collapse_ws(_strip_inline(a or ""))
        if not q_clean:
            continue
        main.append({
            "@type": "Question",
            "name": q_clean,
            "acceptedAnswer": {"@type": "Answer", "text": a_clean},
        })
    if not main:
        return None
    return {
        "@context": SCHEMA_CONTEXT,
        "@type": "FAQPage",
        "mainEntity": main,
    }


def howto_schema(*, name, steps, description=None) -> dict:
    """Build a HowTo JSON-LD dict. None if steps empty."""
    if not steps:
        return None
    step_objs = []
    for idx, (sname, stext) in enumerate(steps, start=1):
        sname_clean = _collapse_ws(_strip_inline(sname or "")) or "Step {}".format(idx)
        stext_clean = _collapse_ws(_strip_inline(stext or ""))
        step = {
            "@type": "HowToStep",
            "position": idx,
            "name": sname_clean,
            "text": stext_clean or sname_clean,
        }
        step_objs.append(step)
    if not step_objs:
        return None
    obj = {
        "@context": SCHEMA_CONTEXT,
        "@type": "HowTo",
        "name": _collapse_ws(_strip_inline(name or "")) or "How-To",
        "step": step_objs,
    }
    desc = _collapse_ws(_strip_inline(description or ""))
    if desc:
        obj["description"] = desc
    return obj


def breadcrumb_schema(*, brand_name, article_type, headline, base_url=None) -> dict:
    """Build a BreadcrumbList: Home > <article_type section> > <headline>.

    If base_url is provided, items carry `item` URLs; otherwise name+position only.
    """
    crumbs = []
    home_name = _collapse_ws(str(brand_name or "")) or "Home"
    crumbs.append(home_name)

    section = _collapse_ws(str(article_type or "")).strip()
    if section:
        crumbs.append(section)

    head = _collapse_ws(_strip_inline(headline or ""))
    if head:
        crumbs.append(head)

    def _slug(text):
        s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
        return s

    item_list = []
    base = (base_url or "").rstrip("/") if base_url else None
    accumulated = base
    for i, crumb in enumerate(crumbs, start=1):
        entry = {
            "@type": "ListItem",
            "position": i,
            "name": crumb,
        }
        if base:
            if i == 1:
                url_i = base + "/"
            else:
                accumulated = (accumulated or base) + "/" + _slug(crumb)
                url_i = accumulated
            entry["item"] = url_i
        item_list.append(entry)

    return {
        "@context": SCHEMA_CONTEXT,
        "@type": "BreadcrumbList",
        "itemListElement": item_list,
    }


# --------------------------------------------------------------------------- #
# LocalBusiness / LodgingBusiness
# --------------------------------------------------------------------------- #
_HOTEL_HINTS = (
    "hotel", "resort", "inn", "lodge", "motel", "suites", "lodging",
    "hospitality", "guesthouse", "guest house", "bed and breakfast", "b&b",
    "villa", "residence",
)


def _looks_like_hotel(name, entity_type, facts) -> bool:
    hay = " ".join(
        str(x or "").lower()
        for x in (name, entity_type, (facts or {}).get("category"),
                  (facts or {}).get("business_type"))
    )
    return any(h in hay for h in _HOTEL_HINTS)


def _first(facts, *keys):
    """Return the first present, non-empty value among keys in facts."""
    if not isinstance(facts, dict):
        return None
    for k in keys:
        if k in facts and facts[k] not in (None, "", []):
            return facts[k]
    return None


def _pick_identity_entity(grounding_bundle):
    """Find the best entity to describe as a local business.

    Returns (name, entity_type, facts_dict) or None.
    Handles both Odin bundles and public {"_public_profile": ...} bundles.
    """
    if not isinstance(grounding_bundle, dict):
        return None

    # public profile bundle
    prof = grounding_bundle.get("_public_profile")
    if isinstance(prof, dict):
        name = prof.get("name") or prof.get("profile_name")
        if name:
            facts = {}
            if prof.get("url"):
                facts["url"] = prof["url"]
            return (str(name), None, facts)

    # Odin bundle: entity_type -> [entities]. Prefer an entity whose facts carry
    # location/contact detail; else the first named entity.
    best = None
    for key, val in grounding_bundle.items():
        if isinstance(key, str) and key.startswith("_"):
            continue
        if not isinstance(val, list):
            continue
        for ent in val:
            if not isinstance(ent, dict):
                continue
            name = ent.get("name")
            if not name:
                continue
            facts = ent.get("facts") if isinstance(ent.get("facts"), dict) else {}
            etype = ent.get("type") or key
            has_detail = any(
                _first(facts, k) for k in (
                    "address", "street", "city", "telephone", "phone",
                    "latitude", "lat", "url",
                )
            )
            candidate = (str(name), etype, facts)
            if has_detail:
                return candidate
            if best is None:
                best = candidate
    return best


def localbusiness_schema(grounding_bundle, *, brand_name, url=None) -> dict:
    """Build a LocalBusiness (or LodgingBusiness for hotels) JSON-LD dict.

    Only emits properties clearly present in the bundle facts. Returns None if
    there is no usable identity at all.
    """
    identity = _pick_identity_entity(grounding_bundle)

    # fall back to brand_name if the bundle had nothing but we at least have a
    # brand — but only if we can produce something meaningful (a name).
    if identity is None:
        if brand_name:
            name, etype, facts = str(brand_name), None, {}
        else:
            return None
    else:
        name, etype, facts = identity
        # prefer explicit brand_name for the visible name if provided
        if brand_name:
            name = str(brand_name)

    if not name:
        return None

    facts = facts if isinstance(facts, dict) else {}
    is_hotel = _looks_like_hotel(name, etype, facts)
    at = "LodgingBusiness" if is_hotel else "LocalBusiness"

    obj = {"@context": SCHEMA_CONTEXT, "@type": at, "name": _collapse_ws(name)}

    # url
    biz_url = url or _first(facts, "url")
    if biz_url:
        obj["url"] = biz_url

    # telephone
    tel = _first(facts, "telephone", "phone")
    if tel:
        obj["telephone"] = str(tel)

    # email
    email = _first(facts, "email")
    if email:
        obj["email"] = str(email)

    # price range
    pr = _first(facts, "price_range", "priceRange")
    if pr:
        obj["priceRange"] = str(pr)

    # address (PostalAddress) — only if at least one component present
    street = _first(facts, "street", "street_address", "streetAddress", "address")
    city = _first(facts, "city", "locality", "addressLocality")
    region = _first(facts, "state", "region", "addressRegion")
    postal = _first(facts, "postal_code", "zip", "postalCode", "zipcode")
    country = _first(facts, "country", "addressCountry")
    addr = {}
    if street:
        addr["streetAddress"] = str(street)
    if city:
        addr["addressLocality"] = str(city)
    if region:
        addr["addressRegion"] = str(region)
    if postal:
        addr["postalCode"] = str(postal)
    if country:
        addr["addressCountry"] = str(country)
    if addr:
        addr["@type"] = "PostalAddress"
        obj["address"] = addr

    # geo (GeoCoordinates) — only if both lat and lng present
    lat = _first(facts, "latitude", "lat")
    lng = _first(facts, "longitude", "lng", "lon")
    if lat not in (None, "") and lng not in (None, ""):
        obj["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": lat,
            "longitude": lng,
        }

    # aggregate rating — only if both rating and review count present
    rating = _first(facts, "rating", "aggregateRating", "average_rating")
    review_count = _first(facts, "review_count", "reviewCount", "review_count_total")
    if rating not in (None, "") and review_count not in (None, ""):
        obj["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": rating,
            "reviewCount": review_count,
        }

    return obj


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _extract_h1(publish_md):
    """Return the first level-1 heading text, cleaned, or ''."""
    for _i, level, text in _iter_headings(publish_md):
        if level == 1:
            return _collapse_ws(text)
    return ""


def build_all(
    publish_md,
    *,
    article_type,
    brand_name,
    topic,
    headline="",
    description="",
    author=None,
    publisher_url=None,
    grounding_bundle=None,
    url=None,
    language="English",
    today=None,
) -> dict:
    """Assemble every derivable JSON-LD block for a finished article.

    Returns {"blocks": [...], "combined_json": [...], "script_html": "..."}.
    Deterministic block order: Article, FAQPage, HowTo, LocalBusiness, Breadcrumb.
    Never raises on empty / None inputs.
    """
    publish_md = publish_md or ""
    article_type = article_type or ""
    brand_name = brand_name or ""
    topic = topic or ""

    date_iso = today or datetime.date.today().isoformat()

    # resolve headline: explicit -> H1 in markdown -> topic
    resolved_headline = _collapse_ws(_strip_inline(headline or ""))
    if not resolved_headline:
        resolved_headline = _extract_h1(publish_md)
    if not resolved_headline:
        resolved_headline = _collapse_ws(str(topic))

    publisher_name = brand_name or ""

    blocks = []

    # ---- Article (always, if we have any headline) ----
    if resolved_headline:
        art = article_schema(
            article_type=article_type,
            headline=resolved_headline,
            description=description,
            author=author,
            publisher_name=publisher_name,
            publisher_url=publisher_url,
            url=url,
            language=language,
            date_published=date_iso,
            date_modified=date_iso,
        )
        blocks.append({"type": "Article", "json": art})

    # ---- FAQPage ----
    faq_pairs = parse_faq(publish_md)
    faq = faqpage_schema(faq_pairs)
    if faq:
        blocks.append({"type": "FAQPage", "json": faq})

    # ---- HowTo (only for How-To Guide with parsed steps) ----
    if (article_type or "").strip().lower() == "how-to guide":
        steps = parse_howto_steps(publish_md)
        ht = howto_schema(name=resolved_headline or topic, steps=steps,
                          description=description or None)
        if ht:
            blocks.append({"type": "HowTo", "json": ht})

    # ---- LocalBusiness / LodgingBusiness ----
    lb = localbusiness_schema(grounding_bundle, brand_name=brand_name, url=url)
    if lb:
        blocks.append({"type": lb.get("@type", "LocalBusiness"), "json": lb})

    # ---- BreadcrumbList (always) ----
    crumb = breadcrumb_schema(
        brand_name=brand_name,
        article_type=article_type,
        headline=resolved_headline,
        base_url=url,
    )
    blocks.append({"type": "BreadcrumbList", "json": crumb})

    combined_json = [b["json"] for b in blocks]

    # script html: each block as its own pretty-printed <script> tag
    scripts = []
    for b in blocks:
        payload = json.dumps(b["json"], indent=2, ensure_ascii=False)
        scripts.append(
            '<script type="application/ld+json">\n{}\n</script>'.format(payload)
        )
    script_html = "\n".join(scripts) + ("\n" if scripts else "")

    return {
        "blocks": blocks,
        "combined_json": combined_json,
        "script_html": script_html,
    }
