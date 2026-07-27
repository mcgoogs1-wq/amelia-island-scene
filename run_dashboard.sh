#!/bin/bash
# Builds the Amelia Island / Fernandina Beach dashboard using this project's
# own private Python environment. Safe to run by hand or from a scheduler.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python amelia_dashboard.py
