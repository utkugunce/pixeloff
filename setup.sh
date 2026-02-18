#!/bin/bash
# Install Playwright Chromium browser (needed for carousel image downloads)
echo "Invoking Playwright installation..."
playwright install chromium 2>/dev/null || python -m playwright install chromium 2>/dev/null || echo "Playwright install failed (or already installed)"
