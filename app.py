import streamlit as st
import pandas as pd
import re
import io
import datetime
import pytz

st.set_page_config(page_title="Medical Data Converter (CSV)", page_icon="📋", layout="centered")

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

st.title("📋 Medical Data Converter to CSV")
st.write("Upload your raw `.TXT` file below to convert it into a formatted CSV sheet.")

uploaded_file = st.file_uploader("Choose a TXT file", type=["txt", "TXT"])

if uploaded_file is not None:
    data_rows = []
    current_supplier = "UNKNOWN SUPPLIER"  
    start_parsing = False
    
    # Strict date pattern from your original logic
    date_pattern = r'\b(?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[012])/\d{2,4}\b|\b(?:0?[1-9]|1[012])/\d{2,4}\b|(?:(?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[012])/\d{2,4}|(?:0?[1-9]|1[012])/\d{2,4})(?=\s)'
    
    # List of known manufacturers
    known_mfgs = [
        "MICRO GEN", "DR. REDDY", "DR.REDDY", "BOEHRING", "CHETHANA", "LA RENON", "GLENMARK", "BLUECROS", 
        "MACLEODS", "SYSTOPIC", "BLUECOSS", "DA RENON", "RELIANCE", "ISIS HEA", "CU-CARD", 
        "CU CARD", "ALEMBIC", "CURATIO", "AKESISS", "LEEFORD", "MANKIND", "LIVIDUS", "PANACEA", 
        "WALLACE", "RENAUXE", "ARISTO", "ZEYYER", "AVELOR", "REDDYS", "KISWAR", "AKESIS", 
        "BIOCON", "SANOFI", "ABBOTT", "GERMAN", "LUPIN", "ALKEM", "EYSYS", "MISC.", "PIRCA", 
        "INTAS", "AUREL", "CIPLA", "MICRO", "LLOYD", "ZYDUS", "ELITE", "IPCA", "ICON", "H&H", 
        "SUN", "ZEY", "USV"
    ]

    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
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
                
            # 🔄 Column Mapping Rules for Item Name & Packing
            # Hyphen-നു ശേഷം വരുന്ന ഒരൊറ്റ ഡിജിറ്റ് വരെയുള്ള ഭാഗം മാത്രം Item Name ആക്കുന്നു.
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
                
            all_date_matches = list(re.finditer(date_pattern, after_slash))
            if not all_date_matches:
                continue
                
            expiry_date_str = all_date_matches[0].group(0)  
            
            expiry_idx = after_slash.find(expiry_date_str)
            left_part = after_slash[:expiry_idx].strip()   
            right_part = after_slash[expiry_idx + len(expiry_date_str):].strip() 
            
            # --- Manufacturer & Batch Extraction ---
            mfg = ""
            batch = ""
            
            for k_mfg in known_mfgs:
                if left_part.upper().startswith(k_mfg.upper()):
                    mfg = k_mfg
                    batch = left_part[len(k_mfg):].strip()
                    break
            
            if not mfg:
                mfg_batch_tokens = re.split(r'\s{2,}', left_part)
                if len(mfg_batch_tokens) >= 2:
                    mfg = mfg_batch_tokens[0].strip()
                    batch = mfg_batch_tokens[1].strip()
                else:
                    combined = mfg_batch_tokens[0]
                    words = combined.split()
                    
                    if len(words) > 1 and any(char.isdigit() for char in words[-1]):
                        mfg = " ".join(words[:-1]).strip()
                        batch = words[-1].strip()
                    else:
                        match = re.match(r'^([a-zA-Z\s\-\.\*]+?)([0-9].*)$', combined)
                        if match:
                            mfg = match.group(1).strip()
                            batch = match.group(2).strip()
                        else:
                            mfg = combined
                            batch = ""

            right_tokens = right_part.split()
            quantity_str = right_tokens[0] if len(right_tokens) > 0 else "0"
            mrp_str = right_tokens[1] if len(right_tokens) > 1 else "0.0"
            
            invoice = ""
            invoice_date_str = ""
            rack_id = ""
            
            if len(right_tokens) > 2:
                invoice_section = " ".join(right_tokens[2:])
                
                inv_date_matches = list(re.finditer(date_pattern, invoice_section))
                if inv_date_matches:
                    invoice_date_str = inv_date_matches[0].group(0)
                    idx = invoice_section.find(invoice_date_str)
                    
                    invoice_part = invoice_section[:idx].strip()
                    rack_part = invoice_section[idx + len(invoice_date_str):].strip()
                    
                    invoice = invoice_part.strip('- ').strip()
                    rack_id = rack_part.strip('- ').strip()
                else:
                    inv_parts = [p.strip() for p in invoice_section.split('-') if p.strip()]
                    if len(inv_parts) >= 2:
                        invoice = inv_parts[0]
                        rack_id = inv_parts[1]
                        if invoice == '*':
                            invoice = ""
                    elif len(inv_parts) == 1:
                        val = inv_parts[0]
                        if any(char.isdigit() for char in val) and len(val) <= 3:
                            rack_id = val
                        else:
                            invoice = val if val != '*' else ""
            
            # Format dates nicely for CSV sorting later (YYYY-MM-DD)
            expiry_date = parse_date(expiry_date_str)
            invoice_date = parse_date(invoice_date_str) if invoice_date_str else pd.NaT
            
            try: quantity = int(quantity_str)
            except: quantity = 0
                
            try: mrp = float(mrp_str)
            except: mrp = 0.0
                
            data_rows.append({
                "Item Name": item_name,
                "Manufacturer": mfg.upper() if mfg else "MISC.",
                "Supplier": current_supplier.upper(),
                "Rack": rack_id if rack_id else "-",
                "Packing": packing if packing else "-",
                "Batch": batch if batch else "BN",
                "Expiry Date": expiry_date,
                "MRP": mrp,
                "Quantity": quantity,
                "Invoice Date": invoice_date,
                "Invoice Number": invoice if invoice else "-"
            })
            
        except Exception as e:
            pass

    if data_rows:
        df = pd.DataFrame(data_rows)
        
        # Column order exactly as requested
        columns_order = [
            "Item Name", 
            "Manufacturer", 
            "Supplier", 
            "Rack", 
            "Packing", 
            "Batch", 
            "Expiry Date", 
            "MRP", 
            "Quantity", 
            "Invoice Date", 
            "Invoice Number"
        ]
        df = df[columns_order]
        
        # Later sort ചെയ്യാൻ എളുപ്പത്തിന് സപ്ലയർ, എക്സ്പെയറി ഡേറ്റ് അനുസരിച്ച് സോർട്ട് ചെയ്യുന്നു
        df = df.sort_values(by=["Supplier", "Expiry Date"]).reset_index(drop=True)
        
        # Date കോളങ്ങൾ വ്യക്തമായ YYYY-MM-DD ഫോർമാറ്റിലേക്ക് മാറ്റുന്നു
        df['Expiry Date'] = df['Expiry Date'].dt.strftime('%Y-%m-%d')
        df['Invoice Date'] = df['Invoice Date'].dt.strftime('%Y-%m-%d').fillna('')
        
        # 📄 Convert DataFrame to CSV String
        csv_data = df.to_csv(index=False, encoding='utf-8')
        
        st.success(f"🎉 File processed successfully! Total {len(df)} items found.")
        
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.datetime.now(ist).strftime("%d-%m-%Y %I-%M-%p")
        dynamic_filename = f"{current_time}-offline_stocks.csv"
        
        # Streamlit CSV Download Button
        st.download_button(
            label="📥 DOWNLOAD CSV FILE",
            data=csv_data,
            file_name=dynamic_filename,
            mime="text/csv"
        )
    else:
        st.error("Could not parse any valid rows. Please check the file format.")
