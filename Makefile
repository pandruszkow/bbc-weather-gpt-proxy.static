# BBC Weather Batch Generator Makefile
# Uses uv to run with requirements.txt in an ephemeral environment.
# CI does not use this file (it uses pip); `python main.py` works too.

UV_RUN := uv run --no-project --with-requirements $(CURDIR)/requirements.txt

# Default target: check that uv is available
.PHONY: all
all: check-uv
	@echo "Environment ready. Run 'make run' to generate forecasts."

.PHONY: check-uv
check-uv:
	@command -v uv > /dev/null 2>&1 || { echo "Error: uv not found. Install it: https://docs.astral.sh/uv/"; exit 127; }

# Install a wrapper script to ~/.local/bin (runs from this checkout)
.PHONY: install
install: check-uv
	@mkdir -p ~/.local/bin
	@printf '#!/bin/sh\nexec %s python %s "$$@"\n' '$(UV_RUN)' '$(CURDIR)/main.py' > ~/.local/bin/bbc-weather-batch
	@chmod +x ~/.local/bin/bbc-weather-batch
	@echo "Installed to ~/.local/bin/bbc-weather-batch"
	@echo "Add ~/.local/bin to your PATH if not already present."

# Generate forecasts. Locations: WEATHER_BATCH_LOCATION if set, otherwise
# every entry in SUPPORTED_LOCATIONS.md.
.PHONY: run
run: check-uv
	$(UV_RUN) python main.py

# Run test suite
.PHONY: test
test: check-uv
	$(UV_RUN) python -m unittest discover -s tests -v

# Clean generated outputs and caches
.PHONY: clean
clean:
	@rm -rf output/ _output/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned output directories and Python caches."

.PHONY: help
help:
	@echo "BBC Weather Batch Generator"
	@echo ""
	@echo "Targets:"
	@echo "  make         - Check that uv is installed"
	@echo "  make run     - Generate forecast batches"
	@echo "  make test    - Run unit tests"
	@echo "  make install - Install wrapper script to ~/.local/bin"
	@echo "  make clean   - Remove output/, _output/ and caches"
	@echo "  make help    - Show this help"
	@echo ""
	@echo "Environment variables:"
	@echo "  WEATHER_BATCH_LOCATION  - Location IDs (default: all of SUPPORTED_LOCATIONS.md)"
	@echo "  WEATHER_BATCH_OUTPUT    - Output directory (default: output/)"
