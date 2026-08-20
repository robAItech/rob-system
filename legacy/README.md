# legacy/

Arhivirani testni/demo moduli, ločeni od produkcijskega `actions/`, da ne
onesnažujejo grafa, spomina in deploymenta. To **niso** produkcijski izdelki —
so ostanki testiranja, demo-a in eval izzivov.

Trenutno vsebuje samo še zadnji izvedeni modul:

| Modul | Izvor |
|---|---|
| `test` | Gmail testna naloga (zadnja izvedena agenda) |

Prejšnji moduli (`demo_bug`, `master_test`, `testna`, `count_words`,
`divide_safe`, `fizzbuzz`) so bili izbrisani med čiščenjem starih artefaktov.

Runtime moduli so izključeni iz AST grafa (`graphify_bridge`) in iz spominske
konsolidacije (`memory_consolidation`).
