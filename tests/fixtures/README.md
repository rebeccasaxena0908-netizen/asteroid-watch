# Test fixtures

`feed_sample.json` is a real NeoWs feed response from 2026-10-12, trimmed to 2 days × 2 asteroids
(one hazardous, one not) with `element_count` set to match. The API key in its `links` was redacted
before saving.

`feed_twins.json` is real feed data for 2026-10-17: the same asteroid listed under two neo_ids
(3430309 "(2008 TC4)" and 2614134 "614134 (2008 TC4)") plus one unrelated asteroid.

`lookup_sample.json` is a real NeoWs Lookup response (close_approach_data trimmed to 2), redacted.

`cad_sample.json` is a real JPL CAD response for 465824 (2010 FR), 2026-09-10 to 2026-09-13 (no key).
