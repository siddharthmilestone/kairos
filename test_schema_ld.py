"""Plain-assert tests for lib/schema_ld.py. Run: .venv/bin/python test_schema_ld.py"""
import json

from lib import schema_ld as S


# --------------------------------------------------------------------------- #
# FAQ parsing
# --------------------------------------------------------------------------- #
FAQ_MD = """# Best Time to Visit Napa Valley

Some intro text about Napa.

## Frequently Asked Questions

### What is the best month to visit Napa?

The **best** months are typically [August](https://x.com) through October,
when the harvest is in full swing.

### Is Napa expensive to visit?

Yes, it can be. Expect `premium` prices for tastings and lodging.

## Conclusion

Wrap up text.
"""


def test_parse_faq():
    pairs = S.parse_faq(FAQ_MD)
    assert len(pairs) == 2, pairs
    q1, a1 = pairs[0]
    assert q1 == "What is the best month to visit Napa?", q1
    # markdown stripped, whitespace collapsed, no link syntax / bold markers
    assert "**" not in a1 and "[" not in a1, a1
    assert a1 == "The best months are typically August through October, " \
                 "when the harvest is in full swing.", a1
    q2, a2 = pairs[1]
    assert q2 == "Is Napa expensive to visit?", q2
    assert "`" not in a2 and "premium" in a2, a2
    # empty / None never raise
    assert S.parse_faq("") == []
    assert S.parse_faq(None) == []
    assert S.parse_faq("# Title\n\nNo faq here.") == []


# --------------------------------------------------------------------------- #
# HowTo parsing
# --------------------------------------------------------------------------- #
HOWTO_MD = """# How to Brew Pour-Over Coffee

Intro paragraph.

## Steps

### Step 1: Heat the water

Bring water to about 200F. Use **filtered** water for best flavor.

### Step 2: Grind the beans

Grind to a medium-coarse consistency.

### Step 3: Bloom and pour

Pour slowly in circles.

## Notes

Extra info that is not a step.
"""


def test_parse_howto():
    steps = S.parse_howto_steps(HOWTO_MD)
    assert len(steps) == 3, steps
    assert steps[0][0] == "Heat the water", steps[0]
    assert "**" not in steps[0][1] and "filtered" in steps[0][1], steps[0]
    assert steps[1][0] == "Grind the beans", steps[1]
    assert steps[2][0] == "Bloom and pour", steps[2]
    # no steps
    assert S.parse_howto_steps("# Title\n\nNothing here.") == []
    assert S.parse_howto_steps(None) == []


# --------------------------------------------------------------------------- #
# build_all: Blog Article (Article + Breadcrumb, no HowTo)
# --------------------------------------------------------------------------- #
def test_build_all_blog():
    out = S.build_all(
        FAQ_MD,
        article_type="Blog Article",
        brand_name="Napa Getaways",
        topic="Best time to visit Napa",
        description="A guide to Napa's seasons.",
        author={"name": "Jane Doe", "title": "Travel Editor", "url": None},
        url="https://example.com/napa-guide",
        today="2026-08-25",
    )
    types = [b["type"] for b in out["blocks"]]
    assert "Article" in types, types
    assert "FAQPage" in types, types
    assert "BreadcrumbList" in types, types
    assert "HowTo" not in types, types
    # deterministic order: Article first, Breadcrumb last
    assert types[0] == "Article", types
    assert types[-1] == "BreadcrumbList", types

    art = out["blocks"][0]["json"]
    assert art["@type"] == "BlogPosting", art
    assert art["@context"] == "https://schema.org"
    assert art["headline"] == "Best Time to Visit Napa Valley", art  # from H1
    assert art["datePublished"] == "2026-08-25"
    assert art["dateModified"] == "2026-08-25"
    assert art["author"]["name"] == "Jane Doe"
    assert art["author"]["jobTitle"] == "Travel Editor"
    assert "url" not in art["author"]  # None url omitted
    assert art["publisher"]["name"] == "Napa Getaways"

    # breadcrumb has positions and, with url, item links
    crumb = out["blocks"][-1]["json"]
    assert crumb["@type"] == "BreadcrumbList"
    positions = [e["position"] for e in crumb["itemListElement"]]
    assert positions == list(range(1, len(positions) + 1)), positions
    assert all("item" in e for e in crumb["itemListElement"]), crumb

    # combined_json mirrors blocks
    assert out["combined_json"] == [b["json"] for b in out["blocks"]]


# --------------------------------------------------------------------------- #
# build_all: How-To Guide (includes HowTo)
# --------------------------------------------------------------------------- #
def test_build_all_howto():
    out = S.build_all(
        HOWTO_MD,
        article_type="How-To Guide",
        brand_name="Coffee Co",
        topic="How to brew pour-over coffee",
        today="2026-08-25",
    )
    types = [b["type"] for b in out["blocks"]]
    assert "HowTo" in types, types
    assert "Article" in types, types
    assert "BreadcrumbList" in types, types
    # order: Article, (FAQ), HowTo, (LocalBusiness), Breadcrumb
    assert types.index("Article") < types.index("HowTo") < types.index("BreadcrumbList")

    ht = next(b["json"] for b in out["blocks"] if b["type"] == "HowTo")
    assert ht["@type"] == "HowTo"
    assert len(ht["step"]) == 3, ht
    assert ht["step"][0]["@type"] == "HowToStep"
    assert ht["step"][0]["position"] == 1
    assert ht["step"][0]["name"] == "Heat the water"


# --------------------------------------------------------------------------- #
# localbusiness_schema
# --------------------------------------------------------------------------- #
def test_localbusiness_with_facts():
    bundle = {
        "company": [
            {
                "id": "1",
                "name": "Seaside Resort & Spa",
                "type": "hotel",
                "facts": {
                    "street": "100 Ocean Ave",
                    "city": "Santa Cruz",
                    "state": "CA",
                    "postal_code": "95060",
                    "country": "US",
                    "telephone": "+1-831-555-0100",
                    "latitude": 36.97,
                    "longitude": -122.03,
                    "rating": 4.6,
                    "review_count": 812,
                },
            }
        ],
        "_fact_ledger": [],
    }
    lb = S.localbusiness_schema(bundle, brand_name="Seaside Resort & Spa",
                                url="https://seaside.example")
    assert lb is not None
    assert lb["@type"] == "LodgingBusiness", lb  # hotel-ish
    assert lb["address"]["@type"] == "PostalAddress"
    assert lb["address"]["streetAddress"] == "100 Ocean Ave"
    assert lb["address"]["addressLocality"] == "Santa Cruz"
    assert lb["telephone"] == "+1-831-555-0100"
    assert lb["geo"]["latitude"] == 36.97
    assert lb["aggregateRating"]["reviewCount"] == 812
    assert lb["url"] == "https://seaside.example"


def test_localbusiness_no_address():
    # entity with a name but no location facts -> LocalBusiness with NO address
    bundle = {
        "company": [
            {"id": "1", "name": "Acme Widgets", "type": "company", "facts": {}}
        ],
    }
    lb = S.localbusiness_schema(bundle, brand_name="Acme Widgets")
    assert lb is not None
    assert lb["@type"] == "LocalBusiness", lb
    assert "address" not in lb, lb  # no fabrication
    assert "geo" not in lb
    assert "aggregateRating" not in lb


def test_localbusiness_empty():
    assert S.localbusiness_schema({}, brand_name="") is None
    assert S.localbusiness_schema(None, brand_name="") is None
    assert S.localbusiness_schema({"_source": "llm"}, brand_name="") is None


def test_localbusiness_public_profile():
    bundle = {
        "_source": "llm",
        "_public_profile": {
            "name": "Downtown Bistro",
            "url": "https://bistro.example",
            "profile_name": "downtown-bistro",
        },
    }
    lb = S.localbusiness_schema(bundle, brand_name="Downtown Bistro")
    assert lb is not None
    assert lb["name"] == "Downtown Bistro"
    assert lb["url"] == "https://bistro.example"


# --------------------------------------------------------------------------- #
# script_html: valid JSON in each <script>
# --------------------------------------------------------------------------- #
def test_script_html_valid_json():
    out = S.build_all(
        FAQ_MD,
        article_type="Blog Article",
        brand_name="Napa Getaways",
        topic="Napa",
        url="https://example.com/napa",
        today="2026-08-25",
    )
    html = out["script_html"]
    assert 'application/ld+json' in html
    # extract each script body and json.loads it
    import re
    bodies = re.findall(
        r'<script type="application/ld\+json">\n(.*?)\n</script>',
        html, re.DOTALL,
    )
    assert len(bodies) == len(out["blocks"]), (len(bodies), len(out["blocks"]))
    for body in bodies:
        parsed = json.loads(body)  # must not raise
        assert parsed["@context"] == "https://schema.org"
        assert "@type" in parsed


# --------------------------------------------------------------------------- #
# robustness: empty / None inputs never raise
# --------------------------------------------------------------------------- #
def test_empty_inputs():
    out = S.build_all("", article_type="", brand_name="", topic="")
    assert isinstance(out["blocks"], list)
    assert isinstance(out["combined_json"], list)
    assert isinstance(out["script_html"], str)
    # breadcrumb is always attempted
    assert any(b["type"] == "BreadcrumbList" for b in out["blocks"])
    # faqpage_schema / howto_schema guards
    assert S.faqpage_schema([]) is None
    assert S.howto_schema(name="x", steps=[]) is None


if __name__ == "__main__":
    test_parse_faq()
    test_parse_howto()
    test_build_all_blog()
    test_build_all_howto()
    test_localbusiness_with_facts()
    test_localbusiness_no_address()
    test_localbusiness_empty()
    test_localbusiness_public_profile()
    test_script_html_valid_json()
    test_empty_inputs()
    print("OK")
