# Installation

## Prerequisites

- Python 3.10–3.12
- [Poetry](https://python-poetry.org/) package manager

## Install from Source

```bash
git clone https://github.com/your-org/XBrainLab.git
cd XBrainLab
poetry install
```

## Optional: LLM Support

To enable the local LLM backend (transformers, bitsandbytes):

```bash
poetry install --with llm
```

## Optional: Documentation

To build the documentation locally:

```bash
poetry install --with docs
poetry run mkdocs serve
```

Then open [http://localhost:8000](http://localhost:8000).

## Verify Installation

```bash
poetry run python -c "from XBrainLab import Study; print('OK')"
```
