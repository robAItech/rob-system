"""chief — Chief of Staff paket (faza 1: prvi teden).

Namerno izven `core/`: nov podsistem, ki v prvem tednu še NI povezan v
daemon/orchestrator (jedro zaklenjeno). Izvaja se ročno ali kasneje kot
samostojna zanka. Vsebina:
  - model.yaml      — model lastnika (seed; ureja Robert)
  - chief_of_staff  — determinističen dnevni krog + učenje iz popravkov
  - __main__        — CLI vstop (python -m chief ...)
"""
from chief.chief_of_staff import (
    load_model,
    audit_activity,
    build_digest,
    write_digest,
    propose_next,
    guard,
    append_correction,
    MODEL_FILE,
    DIGEST_DIR,
    AUDIT_FILE,
)

__all__ = [
    "load_model", "audit_activity", "build_digest", "write_digest",
    "propose_next", "guard", "append_correction",
    "MODEL_FILE", "DIGEST_DIR", "AUDIT_FILE",
]
