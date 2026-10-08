#!/bin/bash
# Builds the Amelia Island / Fernandina Beach dashboard using this project's
# own private Python environment. Used for a local preview; the live site is
# rebuilt in the cloud by .github/workflows/build.yml.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python amelia_dashboard.py
