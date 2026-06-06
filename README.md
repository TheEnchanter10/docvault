# DOCVAULT | 

A document intelligence tool for wealth managers. Upload client financial documents and have structured data automatically extracted and stored in a local SQLite database — exportable to Excel, without sending anything to external servers.

## Why local?

Financial documents contain sensitive data — tax file numbers, income figures, asset balances. Every cloud-based AI solution sends that data to third-party servers. This tool runs the LLM entirely on your own machine via [Ollama](https://ollama.com), so client data never leaves your environment.

## What it handles

| Document Type | Extracted Fields |
|---|---|
| Tax Assessment | TFN, taxable income, tax payable |
| Bank Statement | Opening/closing balance, credits, debits, transactions |
| Portfolio Statement | Holdings, valuations, gain/loss |
| Broker Statement | Securities balance, client code |
| Super Statement | Fund balance |
| Insurance | Cover details, risk profile |

## Architecture

Two files:

- **`app.py`** — Streamlit frontend. Handles file upload, calls the backend, and renders extracted records.
- **`extractor.py`** — Processing pipeline. Converts documents to text or images, classifies the document type via LLM, extracts structured JSON, and saves to SQLite.

PDFs are converted to images (via Poppler) and passed directly to Gemma 4's vision capability — no OCR step. Non-PDF files (CSV, XLSX, TXT) are read as text.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- [Poppler](https://github.com/oschwartz10612/poppler-windows) installed (PDF support)

## Hardware & Model Selection

The model runs locally via Ollama. Choose based on your machine:

| Hardware | Recommended Model | Notes |
|---|---|---|
| 8GB RAM, no GPU | `gemma2:2b` or `phi3:mini` | Lightweight, slower extraction |
| 16GB RAM, no GPU | `gemma4:e4b` *(default)* | Good balance of speed and accuracy |
| 16GB+ with dedicated GPU | `llama3.1:8b` or `mistral:7b` | Faster, more accurate |

To switch models, set the environment variable before running:
```bash
# Windows
set OLLAMA_MODEL=llama3.1:8b

# Mac/Linux
export OLLAMA_MODEL=llama3.1:8b
```

## Setup

```bash
git clone https://github.com/TheEnchanter10/docvault.git
cd docvault

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

ollama pull gemma4:e4b
```

## Run

```bash
streamlit run app.py
```

To test the extraction pipeline directly without the UI:

```bash
python extractor.py path/to/document.pdf
```

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `OLLAMA_MODEL` | Ollama model to use | `gemma4:e4b` |
| `POPPLER_PATH` | Path to Poppler binaries | system PATH |
