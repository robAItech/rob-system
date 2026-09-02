"""Omogoči `python -m chief ...` iz korena projekta."""
from chief.chief_of_staff import main

if __name__ == "__main__":
    raise SystemExit(main())
