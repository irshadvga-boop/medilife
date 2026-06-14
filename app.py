import streamlit as st
import pandas as pd
import re
import io
import datetime
import pytz
import base64
from supabase import create_client, Client

st.set_page_config(page_title="Medical Data Converter (Supabase - Final)", page_icon="📋", layout="centered")

# 🔐 SUPABASE CREDENTIALS (ഇവിടെ നിങ്ങളുടെ ശരിയായ വിവരങ്ങൾ നൽകുക)
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_KEY"
TABLE_NAME = "expired_stocks" 

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Supabase Connection Error: {e}")

def parse_date(d_str):
    if not d_str or d_str.strip() == "" or d_str.strip() == "-":
        return None
    try: return pd.to_datetime(d_str, format='%d/%m/%Y')
    except: pass
    try: return pd.to_datetime(d_str, format='%m/%y')
    except: pass
    try: return pd.to_datetime(d_str, format='%m/%Y')
    except: pass
    try: return pd.to_datetime(d_str, format='%d/%m/%y')
    except: pass
    try: 
        dt = pd.to_datetime(d_str, dayfirst=True, errors='coerce')
        return None if pd.isna(dt) else dt
    except: return None

st.title("📋 Medical Data Converter (Strict DB Columns)")
st.write("Upload your raw `.TXT` file. This version strictly uses lowercase and underscores for database columns.")

uploaded_file = st.file_uploader("Choose a TXT file", type=["txt", "TXT"])

if uploaded_file is not None:
    data_rows = []
    current_supplier = "UNKNOWN SUPPLIER"  
    start_parsing = False
    
    # Strict date pattern
    date_pattern = r'\b(?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[012])/\d{2,4}\b'
    
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8", errors="ignore"))
    raw_lines = stringio.readlines()
    cleaned_lines = [line.rstrip('\r\n') for line in raw_lines if line.strip()]

    # --- Dual-Merge Logic ---
    merged_lines = []
    i = 0
    while i < len(cleaned_lines):
        line = cleaned_lines[i]
        if '\\' not in line and "======" not in line and "----" not in line and "EXPIRED" not in line.upper() and "DATE" not in line.upper():
            if i + 1 < len(cleaned_lines) and '\\' in cleaned_lines[i+1] and "Item Name" not in cleaned_lines[i+1]:
                line = line.strip() + " " + cleaned_lines[i+1].strip()
                i += 1  
        if '\\' in line and not list(re.finditer(date_pattern, line)) and "Item Name" not in line:
            if i + 1 < len(cleaned_lines):
                line = line.strip() + " " + cleaned_lines[i+1].strip()
                i += 1  
        merged_lines.append(line)
        i += 1

    for line_raw in merged_lines:
        line_stripped = line_raw.strip()
        if "======" in line_stripped:
            start_parsing = True
            continue
        if not start_parsing and "----" in line_stripped:
            start_parsing = True
            continue
        if not start_parsing or not line_stripped:
            continue
        if '\\' not in line_stripped and '/' not in line_stripped and '-' not in line_stripped and not any(char.isdigit() for char in line_stripped[:12]):
            if "EXPIRED ITEMS" not in line_stripped.upper() and "ITEM NAME" not in line_stripped.upper() and "DATE :" not in line_stripped.upper():
                current_supplier = line_stripped
                continue
            
        try:
            if '\\' in line_raw:
                slash_pos = line_raw.find('\\')
                before_slash = line_raw[:slash_pos].strip()
                after_slash = line_raw[slash_pos + 1:].strip()
                if "Item Name" in before_slash or "Manf" in after_slash:
                    continue
            else:
                continue
                
            # Column Mapping Rules for Item Name & Packing
            match_item = re.search(r'^(.*?-\d)', before_slash)
            if match_item:
                item_name = match_item.group(1).strip()
                packing = before_slash[len(item_name):].strip()
            elif '-' in before_slash:
                item_name, packing = before_slash.rsplit('-', 1)
                item_name = item_name.strip()
                packing = packing.strip()
            else:
                item_name = before_slash
                packing = ""
                
            # BULLETPROOF ROW PARSER:
            inv_split = [p.strip() for p in after_slash.split(" - ")]
            rack_val = "-"
            invoice_date_str = ""
            invoice = "-"
            
            if len(inv_split) >= 3:
                rack_val = inv_split[-1]
                invoice_date_str = inv_split[-2]
                left_over_inv = inv_split[0]
            elif len(inv_split) == 2:
                invoice_date_str = inv_split[-1]
                left_over_inv = inv_split[0]
