# zgradi__s8 — Markdown Report Builder

Poročilo modula **zgradi__s8**: arhitektura, uporaba in navodila za zagon.
Modul generira Markdown poročila s strogim Pydantic V2 validiranjem, čisto
async logiko in FastAPI vmesnikom z direktnim JSONResponse 4xx/5xx handlingom.

## Arhitektura

| Plast | Datoteka | Odgovornost |
| --- | --- | --- |
| Sheme | `schemas.py` | Pydantic V2 modeli s strogimi validatorji (`extra="forbid"`, stripanje presledkov, zavrnitev praznih vrednosti). |
| Jedrna logika | `zgradi__s8.py` | Čista async domena: `render_markdown()`, `generate_report()`, `build_default_report()`; brez spletnih odvisnosti. |
| API | `main.py` | FastAPI router (`/api/v1/reports`, `/api/v1/health`) in `app` z direktnim `JSONResponse` za 4xx (422) in 5xx (500). |
| Paket | `__init__.py` | Javni izvoz simbolov modula. |

Tok podatkov:

1. Odjemalec pošlje `POST /api/v1/reports` z JSON vhodom.
2. Pydantic V2 s strogimi validatorji preveri shemo `ReportRequest` (prazna polja in dodatni ključi padejo s 422).
3. Async `generate_report()` sestavi Markdown niz in vrne `ReportResponse`.
4. API vrne `JSONResponse` 200 z `filename` in `markdown`; neveljaven vhod → 422, nepričakovana napaka → 500.

## Uporaba

### Python API