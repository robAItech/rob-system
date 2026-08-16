# repos/ — Integrirani paketi Rob AI Studio

Ta mapa vsebuje **lastne, lahke Python pakete**, ki jih Core mostovi in
preizkusni niz pričakujejo kot uvozljive module. Vsak podmapek je veljaven
Python paket s `pyproject.toml` (flat/src layout) in javnim SDK API-jem.

Namen ni kloniranje tujih repozitorijev, temveč zagotoviti koherentno,
določljivo izvorno kodo brez zunanjih mrežnih odvisnosti. Polnopravna,
produkcijska logika posameznega mosta živi v `core/*_bridge.py`; tu so
standardni, uvozljivi vmesniki.

| Podmapek | Modul (uvoz) | Vloga |
|---|---|---|
| `gbrain` | `gbrain` | Kontekstni spomin (ključ-vrednost, black-list) |
| `loopx` | `loopx` | Verifikacijska / samo-zdravilna zanka |
| `gstack` | `gstack` | Arhitekturni manifest (dekompozicija direktive) |
| `gbrain-evals` | `gbrain_evals` | Vrednotenje (accuracy, EvalResult) |
| `hermes-agent` | `hermes_agent` | Ogrodje (scaffold) modulov |
| `graphify` | `graphify` | AST / graf odvisnosti |
