# legacy/

Arhivirani testni/demo moduli (refaktorizacija C). To **niso** produkcijski
izdelki — so ostanki testiranja, demo-a in eval izzivov, ločeni od
produkcijskega `actions/`, da ne onesnažujejo grafa, spomina in deploymenta.

| Modul | Izvor |
|---|---|
| `demo_bug` | učni primer Zanke 1 (namerna napaka → konsolidacija) |
| `master_test` | testni modul |
| `test`, `testna` | Gmail testne naloge |
| `count_words`, `divide_safe`, `fizzbuzz` | P5 eval izzivi |

Ti moduli so izključeni iz AST grafa (`graphify_bridge`) in iz spominske
konsolidacije (`memory_consolidation`).
