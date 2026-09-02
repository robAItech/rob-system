"""nis2_compliance — NIS2 skladnostna tovarna (ZInfV-1, done-for-you).

Regulatorno jedro za slovenske SME (50+/10M€+), nove zavezance ZInfV-1
(prenos NIS2) z rokom 19. 12. 2026:

- child #1: pravila engine (rules JSON → checklist → evidence-tip, tier-ji)
- child #2: per-firm store (C4 izolacija) + obseg determinacija + klient intake
- child #3: varnostne politike (predloge) + ISO 27005 ocena tveganj + API
- child #7: ZInfV-1 pravni realignment — structured legal_ref na dejanske
  člene (20/21/22/23/24/25/29/30), scope z bilančno vsoto (43M/10M) +
  pravilna Priloga logika, 21(1) 8-dokumentna politika, samoocena + izjavi
  (25. člen), samoregistracija (8. člen), obvestilo uporabnikom (29(6)).

Deterministično; LLM se uporablja SAMO za opis tveganja (draft za človeško
potrditev), nikoli za pravila/politike.
"""
