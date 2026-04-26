# BBC Weather Batch Generator Makefile
# Uses uv for dependency management and script execution

# Default target: bootstrap and prepare
.PHONY: all
all: check-uv
	@echo "Environment ready. Run 'make run' to generate forecasts."

# Check for uv/uvx availability
.PHONY: check-uv
check-uv:
	@which uv > /dev/null 2>&1 || (echo "Error: uv not found. Please install uv: https://docs.astral.sh/uv/" && exit 127)
	@which uvx > /dev/null 2>&1 || (echo "Error: uvx not found. Please install uv: https://docs.astral.sh/uv/" && exit 126)

# Install script to user path for system-wide use
.PHONY: install
install: check-uv
	@echo "Installing bbc-weather-batch to user bin..."
	@mkdir -p ~/.local/bin
	@echo '#!/bin/bash' > ~/.local/bin/bbc-weather-batch
	@echo 'exec uvx --from $(CURDIR) python main.py "$$@"' >> ~/.local/bin/bbc-weather-batch
	@chmod +x ~/.local/bin/bbc-weather-batch
	@echo "Installed to ~/.local/bin/bbc-weather-batch"
	@echo "Add ~/.local/bin to your PATH if not already present."

# Run the batch generator (reads from WEATHER_BATCH_LOCATION env var)
.PHONY: run
run: check-uv
	@if [ -z "$(WEATHER_BATCH_LOCATION)" ]; then \
		echo "Error: WEATHER_BATCH_LOCATION environment variable not set"; \
		echo "Example: WEATHER_BATCH_LOCATION='2644577,2653940' make run"; \
		exit 1; \
	fi
	@echo "Running batch generator for location(s): $(WEATHER_BATCH_LOCATION)"
	uvx --from requirements.txt python main.py

# Run test suite
.PHONY: test
test: check-uv
	@echo "Running test suite..."
	uvx --from requirements.txt python -m unittest discover -s tests -v

# Clean generated outputs and caches
.PHONY: clean
clean:
	@rm -rf output/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned output directory and Python caches."

# Show help
.PHONY: help
help:
	@echo "BBC Weather Batch Generator"
	@echo ""
	@echo "Targets:"
	@echo "  make        - Bootstrap and check environment"
	@echo "  make run    - Generate forecast batches (needs WEATHER_BATCH_LOCATION)"
	@echo "  make test   - Run unit tests"
	@echo "  make install - Install script to ~/.local/bin"
	@echo "  make clean  - Clean output directory and caches"
	@echo "  make help   - Show this help"
	@echo ""
	@echo "Environment variables:"
	@echo "  WEATHER_BATCH_LOCATION  - Comma-separated location IDs (required for run)"
	@echo "  WEATHER_BATCH_OUTPUT    - Output directory (default: output/)"
