# Opportunity-record → workflow field mapping

Every field of a `geo-content-opportunity-engine` opportunity is used. This is how.

## Directly fills a generation parameter
| Opportunity field | Used as | Notes |
|---|---|---|
| `core_topic` | article topic | the page's subject |
| `keywords[0]` | primary keyword | placed in H1, intro, one H2, conclusion, meta |
| `keywords[1:]` | secondary keywords | woven naturally, no stuffing |
| `entities` (from `memory_graph_nodes`) | entities to include | entity-rich headings + coverage |
| `intent` | search intent | drives content depth + CTA type |
| `prompts[:3]` | the optional topic Q&A | first-person AI-search questions answered by the user |
| `industry` | industry context | |
| `pillar_topic` | content pillar | also feeds semantic keywords |

## Steers strategy (Step 3), not copied verbatim
| Field | How it changes the plan |
|---|---|
| `content_gap_type` | **Structural** → create/restructure page + schema; **Thematic** → broaden topical coverage; **Critical** → fix a high-stakes accuracy/authority gap. |
| `recommendation` | default output format (Blog / Web Page / How-To / Listicle / social). User can override. |
| `geo_signals.factual_density` | low → pack in more verifiable specifics from Odin. |
| `geo_signals.semantic_structure` | low → add FAQ/HowTo/table blocks + recommend schema. |
| `geo_signals.retrieval_chunk_quality` | low → make each section self-contained for RAG retrieval. |
| `geo_signals.entity_coverage` | low → cover more named entities the graph knows. |
| `geo_signals.citation_worthiness` | target for the Information-Gain plan. |
| `business_objective` | shapes the CTA and the value framing (e.g. drive direct bookings). |
| `customer_journey` | tone + funnel positioning (awareness vs consideration vs booking). |

## Grounding & provenance
| Field | Use |
|---|---|
| `memory_graph_nodes.entities` / `.relations` | the real Odin subgraph to feature; expand via `odin query` for facts. |
| `evidence_sources` | provenance to cite in Grounding Notes; verify before asserting. |
| `confidence` | low confidence → lean harder on live verification; surface "data to collect". |

## Semantic keywords (derived, never fabricated)
Built from `entities` + `pillar_topic` + secondary `keywords` — related phrases grounded in real
entities. Never attach invented search volume.

## Metadata JSON passed to generation
The full opportunity object **plus** a compact Odin business-metadata block (brand, industry,
primary location, available schema types) — so the model can populate meta title/description,
schema, categories, tags, and internal-link suggestions from real structured data.
