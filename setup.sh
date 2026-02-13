#!/bin/bash
# Install Playwright Chromium browser (needed for carousel image downloads)
playwright install chromium 2>/dev/null || python -m playwright install chromium 2>/dev/null || true
