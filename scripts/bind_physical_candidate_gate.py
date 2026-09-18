#!/usr/bin/env python3
"""Compatibility wrapper for the shared physical-candidate operator CLI."""
from kaliphonestudio.physical_candidate_operator import bind_physical_candidate_main


if __name__ == "__main__":
    raise SystemExit(bind_physical_candidate_main())
