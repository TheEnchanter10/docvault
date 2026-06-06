import os
import json
import tempfile
import sqlite3
import pandas as pd
import streamlit as st

from extractor import process_document, get_db_path

st.set_page_config(page_title="DOCVAULT | WealthLink AI", layout="wide")

st.title("DOCVAULT | Client Intelligence")

# --- 2. UPLOAD & PROCESS (Concurrency Fixed) ---
uploaded_file = st.file_uploader("Upload a Client Document (PDF, TXT, XLSX, CSV)", type=["pdf", "txt", "xlsx", "csv"])

if uploaded_file is not None:
    st.info(f"📄 '{uploaded_file.name}' ready.")

    if st.button("🚀 Process with AI"):
        # Use tempfile to prevent file overwrite crashes when multiple users upload
        ext = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        with st.spinner("Processing document via Ollama pipeline..."):
            # DIRECT CALL to backend module instead of subprocess
            result = process_document(tmp_path, original_filename=uploaded_file.name)
        
        # Clean up the temp file immediately
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        # Handle API response
        if result.get("success"):
            st.success(f"Extraction complete for {result.get('client_name')} ({result.get('doc_type')})")
            st.rerun()
        else:
            st.error(f"Extraction failed: {result.get('error')}")

st.markdown("---")

# --- 3. DATA DISPLAY ---
db_path = get_db_path()
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT * FROM clients ORDER BY id DESC", conn)
        
        if not df.empty:
            st.subheader("Extracted Client Records")
            
            # Formatting for display table
            display_df = df.drop(columns=["id"], errors="ignore")
            display_df.insert(0, "No.", range(1, 1 + len(display_df)))

            def highlight_confidence(row):
                conf = row.get("confidence_score", 1.0)
                if pd.notna(conf) and float(conf) < 0.6:
                    return ["background-color: #3a1c1c"] * len(row)
                return [""] * len(row)

            st.dataframe(
                display_df.style.apply(highlight_confidence, axis=1),
                use_container_width=True,
                hide_index=True,
            )

            # --- RECORD DETAIL VIEW ---
            st.subheader("Record Detail")
            record_ids = df["id"].tolist()
            selected = st.selectbox(
                "Select record", 
                record_ids, 
                format_func=lambda x: f"#{x} — {df[df['id']==x]['client_name'].values[0]}"
            )
            
            if selected:
                row = df[df["id"] == selected].iloc[0]
                doc_type = row["doc_type"] if pd.notna(row.get("doc_type")) else "unknown"
                col1, col2 = st.columns(2)

                # Shared Metrics
                with col1:
                    st.metric("Client Name", row.get("client_name", "N/A"))
                    st.metric("Total Assets / Balance", f"${row['total_assets']:,.2f}" if pd.notna(row.get("total_assets")) else "N/A")
                with col2:
                    st.metric("Document Type", doc_type.upper())
                    st.metric("Confidence Score", f"{row.get('confidence_score', 0):.0%}")

                # Context-Specific Views
                asset_alloc = row.get("asset_allocation")
                if pd.notna(asset_alloc) and asset_alloc != "N/A":
                    try:
                        parsed_json = json.loads(asset_alloc)
                        if isinstance(parsed_json, list):
                            st.subheader("Structured Line Items (Holdings/Transactions)")
                            st.dataframe(pd.DataFrame(parsed_json), use_container_width=True, hide_index=True)
                        else:
                            st.write("**Summary:**", asset_alloc)
                    except:
                        st.write("**Raw Data:**", asset_alloc)
        else:
            st.info("No records yet. Upload a document to begin.")
            
    except Exception as e:
        st.error(f"Database error: {str(e)}")
    finally:
        conn.close()
else:
    st.info("No database found. Upload a document to begin.")

# --- 4. ADMIN ---
st.markdown("---")
with st.expander("🛠️ Admin Controls"):
    if st.button("🗑️ Reset Database", type="primary"):
        if os.path.exists(db_path):
            os.remove(db_path)
            st.success("Database cleared.")
            st.rerun()