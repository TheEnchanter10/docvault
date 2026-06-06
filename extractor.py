import os
import sys
import io
import json
import base64
import sqlite3
import logging
import pandas as pd
from pdf2image import convert_from_path
import ollama

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
POPPLER_PATH = os.environ.get("POPPLER_PATH")


def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "wealth_crm.db")


def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT, client_name TEXT, tfn TEXT,
            taxable_income REAL, tax_payable REAL, total_assets REAL,
            total_liabilities REAL, superannuation REAL, insurance_cover TEXT,
            risk_profile TEXT, dependents TEXT, fund_balance REAL,
            securities_balance REAL, client_code TEXT, email TEXT,
            total_valuation REAL, asset_allocation TEXT, confidence_score REAL,
            source_file TEXT, extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def pdf_to_images(file_path):
    images = convert_from_path(file_path, dpi=200, poppler_path=POPPLER_PATH)
    result = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result.append(base64.b64encode(buf.getvalue()).decode())
    return result


def extract_text_from_file(file_path):
    ext = file_path.lower()
    try:
        if ext.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        elif ext.endswith(".xlsx"):
            df = pd.read_excel(file_path, sheet_name=None)
            parts = [f"--- SHEET: {name} ---\n{sheet.to_string(index=False)}" for name, sheet in df.items()]
            return "\n\n".join(parts)
        elif ext.endswith(".csv"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    except Exception as e:
        raise RuntimeError(f"Text extraction failed: {str(e)}")


def classify_document(text=None, images=None):
    prompt = ('What type of financial document is this? Return ONLY a JSON object with a single key "doc_type" '
              'containing one of these exact values: tax_assessment, broker_statement, portfolio_statement, '
              'bank_statement, super_statement, insurance, unknown.')

    message = {"role": "user", "content": prompt}
    if images:
        message["images"] = images[:2]
    else:
        message["content"] = prompt + f"\n\nDOCUMENT TEXT:\n{text[:4000]}"

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[message],
            format="json",
            options={"temperature": 0.0}
        )
        data = json.loads(response["message"]["content"])
        doc_type = data.get("doc_type", "unknown").lower()
        valid_types = ["tax_assessment", "broker_statement", "portfolio_statement",
                       "bank_statement", "super_statement", "insurance"]
        return doc_type if doc_type in valid_types else "unknown"
    except Exception as e:
        logging.warning(f"Classification failed: {e}. Defaulting to 'unknown'.")
        return "unknown"


def get_extraction_prompt(doc_type):
    rules = ("RULES: 1. Use null for missing numbers, 'N/A' for missing text. "
             "2. Numbers must be pure floats (no symbols). 3. Output valid JSON only.")
    return f"Extract financial data from this {doc_type}. {rules}"


def extract_financial_data(doc_type, text=None, images=None):
    prompt = get_extraction_prompt(doc_type)

    message = {"role": "user", "content": prompt}
    if images:
        message["images"] = images
    else:
        message["content"] = prompt + f"\n\nDOCUMENT TEXT:\n{text}"

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[message],
            format="json",
            options={"temperature": 0.0, "num_ctx": 4096}
        )
        return json.loads(response["message"]["content"])
    except json.JSONDecodeError:
        raise ValueError("LLM did not return valid JSON.")
    except Exception as e:
        raise RuntimeError(f"Ollama extraction failed: {str(e)}")


def save_to_database(data, doc_type, source_file):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO clients (
                doc_type, client_name, tfn, taxable_income, tax_payable,
                total_assets, total_liabilities, superannuation,
                insurance_cover, risk_profile, dependents,
                fund_balance, securities_balance, client_code, email,
                total_valuation, asset_allocation,
                confidence_score, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            doc_type,
            data.get("client_name", "N/A"),
            data.get("tfn", "N/A"),
            data.get("taxable_income"),
            data.get("tax_payable"),
            data.get("total_credits") if doc_type == "bank_statement" else data.get("total_assets"),
            data.get("total_debits") if doc_type == "bank_statement" else data.get("total_liabilities"),
            data.get("superannuation"),
            data.get("insurance_cover", "N/A"),
            data.get("risk_profile", "N/A"),
            data.get("dependents", "N/A"),
            data.get("opening_balance") if doc_type == "bank_statement" else data.get("fund_balance"),
            data.get("overall_gain_loss") if doc_type == "portfolio_statement" else data.get("securities_balance"),
            data.get("account_number", data.get("client_code", "N/A")),
            data.get("email", "N/A"),
            data.get("closing_balance") if doc_type == "bank_statement" else data.get("total_valuation"),
            json.dumps(data.get("transactions")) if doc_type == "bank_statement" and data.get("transactions")
            else (json.dumps(data.get("holdings")) if data.get("holdings") else data.get("asset_allocation", "N/A")),
            data.get("confidence_score", 0.0),
            source_file
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Database insertion failed: {str(e)}")
    finally:
        conn.close()


def process_document(file_path, original_filename=None):
    init_db()
    filename = original_filename or os.path.basename(file_path)

    try:
        logging.info(f"Processing {filename}...")

        if file_path.lower().endswith(".pdf"):
            images = pdf_to_images(file_path)
            doc_type = classify_document(images=images)
            logging.info(f"Classified as: {doc_type}")
            data = extract_financial_data(doc_type, images=images)
        else:
            text = extract_text_from_file(file_path)
            if not text.strip():
                return {"success": False, "error": "Extracted text is empty."}
            doc_type = classify_document(text=text)
            logging.info(f"Classified as: {doc_type}")
            data = extract_financial_data(doc_type, text=text)

        save_to_database(data, doc_type, filename)
        return {"success": True, "doc_type": doc_type, "client_name": data.get("client_name", "Unknown")}

    except Exception as e:
        logging.error(f"Failed to process {filename}: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractor.py <path_to_file>")
        sys.exit(1)
    result = process_document(sys.argv[1])
    print(json.dumps(result, indent=2))
