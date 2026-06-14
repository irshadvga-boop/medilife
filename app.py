import streamlit as st
import pandas as pd
import re
import io
import datetime
import pytz
import base64
from supabase import create_client, Client

st.set_page_config(page_title="Medical Data Converter (Supabase - Stable)", page_icon="📋", layout="centered")

# 🔐 SUPABASE CREDENTIALS (ഇവിടെ നിങ്ങളുടെ വിവരങ്ങൾ മാറ്റുക)
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_KEY"
TABLE_NAME = "expired_stocks" 

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Supabase Connection Error: {e}")

def parse_date(d_str):
    try: return pd.to_datetime(d_str, format='%d/%m/%Y')
    except: pass
    try: return pd.to_datetime(d_str, format='%m/%y')
    except: pass
    try: return pd.to_datetime(d_str, format='%m/%Y')
    except: pass
    try: return pd.to_datetime(d_str, format='%d/%m/%y')
    except: pass
    try: return pd.to_datetime(d_str, dayfirst=True)
    except: return pd.NaT

st.title("📋 Medical Data Converter (Stable Engine)")
st.write("Upload your raw `.TXT` file. This version uses a robust dual-direction parser to avoid syntax errors.")

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
                
            # 🎯 BULLETPROOF ROW PARSER:
            # വലതുവശത്തുനിന്നും ഹൈഫനുകൾ വെച്ച് Invoice Details വേർതിരിക്കുന്നു
            inv_split = [p.strip() for p in after_slash.split(" - ")]
            rack_id = "-"
            invoice_date_str = ""
            invoice = "-"
            
            if len(inv_split) >= 3:
                rack_id = inv_split[-1]
                invoice_date_str = inv_split[-2]
                # ആദ്യത്തെ പാർട്ടിൽ നിന്നും ബാക്കി ഇൻവോയ്സ് നമ്പർ കണ്ടുപിടിക്കണം
                left_over_inv = inv_split[0]
            elif len(inv_split) == 2:
                invoice_date_str = inv_split[-1]
                left_over_inv = inv_split[0]
            else:
                left_over_inv = after_slash

            # അടിയന്തിരമായി Expiry Date കണ്ടുപിടിക്കുന്നു (ഇതാണ് നമ്മുടെ സെൻ്റർ പോയിന്റ്)
            all_date_matches = list(re.finditer(date_pattern, left_over_inv))
            if not all_date_matches:
                continue
                
            expiry_date_str = all_date_matches[0].group(0)
            exp_start_idx = left_over_inv.find(expiry_date_str)
            
            # എക്സ്പെയറിക്ക് മുൻപിലുള്ള ഭാഗം (Manufacturer & Batch)
            mfg_batch_part = left_over_inv[:exp_start_idx].strip()
            # എക്സ്പെയറിക്ക് ശേഷമുള്ള ഭാഗം (Qty, MRP & Invoice Number)
            qty_mrp_inv_part = left_over_inv[exp_start_idx + len(expiry_date_str):].strip()
            
            # 1. Manufacturer & Batch വേർതിരിക്കൽ
            mfg_batch_tokens = [t.strip() for t in re.split(r'\s+', mfg_batch_part) if t.strip()]
            if len(mfg_batch_tokens) >= 2:
                # അവസാനത്തെ ടോക്കൺ എപ്പോഴും ബാച്ച് നമ്പർ ആയിരിക്കും
                batch = mfg_batch_tokens[-1]
                mfg = " ".join(mfg_batch_tokens[:-1])
            elif len(mfg_batch_tokens) == 1:
                mfg = mfg_batch_tokens[0]
                batch = "BN"
            else:
                mfg = "MISC."
                batch = "BN"
                
            # 2. Qty, MRP & Invoice Number വേർതിരിക്കൽ (നിങ്ങൾ പറഞ്ഞ എറർ ഒഴിവാക്കാൻ ഇവിടെയാണ് മാറ്റം വരുത്തിയത്)
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
                # ബാക്കി വരുന്ന എല്ലാ ടോക്കണും ഇൻവോയ്സ് നമ്പറിലേക്ക് ലയിപ്പിക്കുന്നു
                invoice = " ".join(qty_mrp_tokens[2:])
            
            # ഡേറ്റ് ഒബ്ജക്റ്റുകൾ ജനറേറ്റ് ചെയ്യുന്നു
            expiry_date = parse_date(expiry_date_str)
            invoice_date = parse_date(invoice_date_str) if invoice_date_str else pd.NaT
            
            data_rows.append({
                "item_name": item_name,
                "manufacturer": mfg.upper() if mfg else "MISC.",
                "supplier": current_supplier.upper(),
                "rack": rack_id if rack_id else "-",
                "packing": packing if packing else "-",
                "batch": batch if batch else "BN",
                "expiry_date": expiry_date,
                "mrp": mrp,
                "quantity": quantity,
                "invoice_date": invoice_date,
                "invoice_number": invoice if invoice else "-"
            })
        except Exception as e:
            pass

    if data_rows:
        df = pd.DataFrame(data_rows)
        df = df.sort_values(by=["supplier", "expiry_date"]).reset_index(drop=True)
        
        # തീയതികൾ സ്ട്രിംഗ് ഫോർമാറ്റിലേക്ക് മാറ്റുന്നു
        df['expiry_date'] = df['expiry_date'].dt.strftime('%Y-%m-%d')
        df['invoice_date'] = df['invoice_date'].dt.strftime('%Y-%m-%d').fillna('')
        
        # --- 🚀 SUPABASE AUTO-REPLACE (STABLE VERSION) ---
        try:
            records = df.to_dict(orient="records")
            
            # പഴയ ഷീറ്റ് ഡാറ്റ മുഴുവൻ ക്ലിയർ ചെയ്യുന്നു
            supabase.table(TABLE_NAME).delete().gt("quantity", -1).execute()
            
            # പുതിയ ക്ലീൻ ഡാറ്റ പുഷ് ചെയ്യുന്നു
            chunk_size = 1000
            for i in range(0, len(records), chunk_size):
                supabase.table(TABLE_NAME).insert(records[i:i+chunk_size]).execute()
                
            st.success("⚡ Supabase database successfully synced without any syntax/numeric errors!")
        except Exception as db_err:
            st.error(f"Failed to auto-upload to Supabase: {db_err}")
            
        # --- CSV Generation for Backup Download ---
        csv_df = df.copy()
        csv_df.columns = [
            "Item Name", "Manufacturer", "Supplier", "Rack", 
            "Packing", "Batch", "Expiry Date", "MRP", 
            "Quantity", "Invoice Date", "Invoice Number"
        ]
        csv_data = csv_df.to_csv(index=False, encoding='utf-8')
        
        # ഫയൽ ഓട്ടോ ഡൗൺലോഡ് ട്രിഗർ ചെയ്യുന്നു
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
