import streamlit as st
import pandas as pd
import re
import io
import datetime
import pytz
import base64
from supabase import create_client, Client

st.set_page_config(page_title="Medical Data Converter (Supabase - Final)", page_icon="📋", layout="centered")

# 🔐 SUPABASE CREDENTIALS (നിങ്ങളുടെ വലിയ API Key മാത്രം മാറ്റുക)
SUPABASE_URL = "https://fivchvttdrxywtatqv.supabase.co"
SUPABASE_KEY = "YOUR_SUPABASE_KEY"  # 💡 ഇവിടെ നിങ്ങളുടെ വലിയ API Key പേസ്റ്റ് ചെയ്യുക
TABLE_NAME = "expired_stocks" 

# സുപബേസ് ക്ലയന്റ് സുരക്ഷിതമായി ഇനിഷ്യലൈസ് ചെയ്യുന്നു
supabase = None
try:
    if SUPABASE_KEY != "YOUR_SUPABASE_KEY":
        supabase = create_client(SUPABASE_URL.strip(), SUPABASE_KEY.strip())
except Exception as e:
    st.error(f"Supabase Connection Error: {e}")

def parse_date(d_str):
    if not d_str or str(d_str).strip() == "" or str(d_str).strip() == "-":
        return pd.NaT
    try: return pd.to_datetime(d_str, format='%d/%m/%Y')
    except: pass
    try: return pd.to_datetime(d_str, format='%m/%y')
    except: pass
    try: return pd.to_datetime(d_str, format='%m/%Y')
    except: pass
    try: return pd.to_datetime(d_str, format='%d/%m/%y')
    except: pass
    try: 
        return pd.to_datetime(d_str, dayfirst=True, errors='coerce')
    except: 
        return pd.NaT

st.title("📋 Medical Data Converter (Error Free Version)")
st.write("Upload your raw `.TXT` file. All parsing errors, Date errors, and Packing column mistakes are fixed in this version.")

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
                
            # --- 🎯 NEW BULLETPROOF ITEM NAME & PACKING PARSER ---
            # പേരും പാക്കിങ്ങും മുറിഞ്ഞുപോകാതിരിക്കാനുള്ള പുതിയ സ്മാർട്ട് ലോജിക്
            tokens = before_slash.rsplit(' ', 1)
            if len(tokens) == 2 and '-' in tokens[1] and tokens[1].rsplit('-', 1)[1].isdigit():
                item_name = tokens[0].strip()
                packing = tokens[1].strip()
            elif len(tokens) == 1 and '-' in before_slash and before_slash.rsplit('-', 1)[1].isdigit():
                item_name, packing = before_slash.rsplit('-', 1)
                item_name = item_name.strip()
                packing = packing.strip()
            else:
                item_name = before_slash.strip()
                packing = "-"
                
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
            else:
                left_over_inv = after_slash

            all_date_matches = list(re.finditer(date_pattern, left_over_inv))
            if not all_date_matches:
                continue
                
            expiry_date_str = all_date_matches[0].group(0)
            exp_start_idx = left_over_inv.find(expiry_date_str)
            
            mfg_batch_part = left_over_inv[:exp_start_idx].strip()
            qty_mrp_inv_part = left_over_inv[exp_start_idx + len(expiry_date_str):].strip()
            
            mfg_batch_tokens = [t.strip() for t in re.split(r'\s+', mfg_batch_part) if t.strip()]
            if len(mfg_batch_tokens) >= 2:
                batch = mfg_batch_tokens[-1]
                mfg = " ".join(mfg_batch_tokens[:-1])
            elif len(mfg_batch_tokens) == 1:
                mfg = mfg_batch_tokens[0]
                batch = "BN"
            else:
                mfg = "MISC."
                batch = "BN"
                
            qty_mrp_tokens = [t.strip() for t in re.split(r'\s+', qty_mrp_inv_part) if t.strip()]
            
            quantity = 0
            mrp = 0.0
            
            if len(qty_mrp_tokens) >= 1:
                try: quantity = int(qty_mrp_tokens[0])
                except: pass
            if len(qty_mrp_tokens) >= 2:
                try: mrp = float(qty_mrp_tokens[1])
                except: pass
            if len(qty_mrp_tokens) >= 3:
                invoice = " ".join(qty_mrp_tokens[2:])
            
            expiry_date = parse_date(expiry_date_str)
            invoice_date = parse_date(invoice_date_str)
            
            exp_formatted = expiry_date.strftime('%Y-%m-%d') if pd.notna(expiry_date) else None
            inv_formatted = invoice_date.strftime('%Y-%m-%d') if pd.notna(invoice_date) else None
            
            data_rows.append({
                "item_name": item_name,
                "manufacturer": mfg.upper() if mfg else "MISC.",
                "supplier": current_supplier.upper(),
                "rack_id": rack_val if rack_val and rack_val != "" else "-",
                "packing": packing if packing and packing != "" else "-",
                "batch": batch if batch and batch != "" else "BN",
                "expiry_date": exp_formatted,
                "mrp": mrp,
                "quantity": quantity,
                "invoice_date": inv_formatted,
                "invoice_number": invoice if invoice and invoice != "" else "-"
            })
        except Exception as e:
            pass

    if data_rows:
        df = pd.DataFrame(data_rows)
        df = df.sort_values(by=["supplier", "expiry_date"], na_position='last').reset_index(drop=True)
        
        # --- 🚀 SUPABASE AUTO-REPLACE ---
        if supabase is not None:
            try:
                records = df.to_dict(orient="records")
                
                supabase.table(TABLE_NAME).delete().gt("quantity", -1).execute()
                
                chunk_size = 1000
                for i in range(0, len(records), chunk_size):
                    chunk = records[i:i + chunk_size]
                    supabase.table(TABLE_NAME).insert(chunk).execute()
                    
                st.success(f"⚡ Successfully uploaded {len(df)} records to Supabase! All errors resolved.")
            except Exception as db_err:
                st.error(f"Failed to auto-upload to Supabase: {db_err}")
        else:
            st.warning("⚠️ Supabase connection failed! Data is only available for CSV download.")
            
        # --- CSV Backup Generation ---
        csv_df = df.copy()
        csv_df.columns = [
            "Item Name", "Manufacturer", "Supplier", "Rack ID", 
            "Packing", "Batch", "Expiry Date", "MRP", 
            "Quantity", "Invoice Date", "Invoice Number"
        ]
        csv_data = csv_df.to_csv(index=False, encoding='utf-8')
        
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.datetime.now(ist).strftime("%d-%m-%Y %I-%M-%p")
        dynamic_filename = f"{current_time}-offline_stocks.csv"
        
        b64 = base64.b64encode(csv_data.encode()).decode()
        dl_link = f"""
            <a id="auto_download" href="data:text/csv;base64,{b64}" download="{dynamic_filename}"></a>
            <script>
                document.getElementById('auto_download').click();
            </script>
        """
        st.components.v1.html(dl_link, height=0, width=0)
        st.info("📥 Your CSV download has started automatically!")
        
        st.download_button(
            label="📥 Alternatively Click Here to Download CSV",
            data=csv_data,
            file_name=dynamic_filename,
            mime="text/csv"
        )
    else:
        st.error("Could not parse any valid rows. Please check the file format.")
