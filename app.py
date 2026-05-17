import streamlit as st
import pandas as pd
import re
import io

st.set_page_config(page_title="Medical Data Converter", page_icon="📋", layout="centered")

st.title("📋 Medical Data Converter")
st.write("Upload your raw `.TXT` file below to convert it into a formatted Excel sheet.")

# File Uploader component
uploaded_file = st.file_uploader("Choose a TXT file", type=["txt", "TXT"])

if uploaded_file is not None:
    data_rows = []
    current_supplier = ""
    start_parsing = False
    
    # തീയതികൾ കണ്ടെത്താനുള്ള റീജക്സ് (Format: DD/MM/YYYY)
    date_pattern = r'\b\d{1,2}/\d{1,2}/\d{4}\b'
    
    # കോമൺ ആയി ഒട്ടിനിൽക്കുന്ന പ്രധാന കമ്പനികളുടെ ലിസ്റ്റ്
    known_mfgs = ["LA RENON", "LIVIDUS", "LUPIN", "RENAUXE", "DA RENON", "BOEHRING", "AKESIS", "Isis Hea", "AVELOR", "KISWAR", "AUREL", "CU CARD", "CU-CARD"]

    # Read the uploaded file lines safely
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    lines = stringio.readlines()

    for line in lines:
        line_raw = line.rstrip('\r\n')
        line_stripped = line_raw.strip()
        
        # 1. റിപ്പോർട്ട് ഹെഡ്ഡറുകൾ ഒഴിവാക്കുന്നു
        if "======" in line_stripped:
            start_parsing = True
            continue
            
        if not start_parsing or not line_stripped:
            continue
            
        # 2. സപ്ലയർ പേര് കണ്ടെത്തുന്നു
        if '\\' not in line_stripped and '/' not in line_stripped and not any(char.isdigit() for char in line_stripped[:15]):
            current_supplier = line_stripped
            continue
            
        try:
            # 3. ബാക്ക് സ്ലാഷ് (\) വെച്ച് ഐറ്റം നെയിമും ബാക്കി ഭാഗവും തിരിക്കുന്നു
            if '\\' in line_raw:
                slash_pos = line_raw.find('\\')
                before_slash = line_raw[:slash_pos].strip()
                after_slash = line_raw[slash_pos + 1:].strip()
            else:
                continue
                
            # --- Item Name & Packing Extraction ---
            if '-' in before_slash:
                item_name, packing = before_slash.rsplit('-', 1)
                item_name = item_name.strip()
                packing = packing.strip()
            else:
                item_name = before_slash
                packing = ""
                
            # --- EXPIRY DATE അടിസ്ഥാനമാക്കിയുള്ള ലോജിക് ---
            all_dates = re.findall(date_pattern, after_slash)
            if not all_dates:
                continue
                
            expiry_date_str = all_dates[0]  # ആദ്യത്തെ തീയതി എപ്പോഴും Expiry Date ആണ്
            
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
                    match = re.match(r'^([a-zA-Z\s\-\.]+)(.*)$', combined)
                    if match:
                        mfg = match.group(1).strip()
                        batch = match.group(2).strip()
                    else:
                        mfg = combined
                        batch = ""

            # --- Quantity & MRP Extraction ---
            right_tokens = right_part.split()
            quantity_str = right_tokens[0] if len(right_tokens) > 0 else "0"
            mrp_str = right_tokens[1] if len(right_tokens) > 1 else "0.0"
            
            invoice = ""
            invoice_date_str = ""
            rack_id = ""
            
            # MRP കഴിഞ്ഞുള്ള ഭാഗം ഇൻവോയ്സ് സെക്ഷൻ ആയി എടുക്കുന്നു
            if len(right_tokens) > 2:
                invoice_section = " ".join(right_tokens[2:])
                inv_parts = [p.strip() for p in invoice_section.split('-') if p.strip()]
                
                inv_date_matches = re.findall(date_pattern, invoice_section)
                if inv_date_matches:
                    invoice_date_str = inv_date_matches[0]
                    
                    if invoice_date_str in inv_parts:
                        inv_date_idx = inv_parts.index(invoice_date_str)
                        invoice = " ".join(inv_parts[:inv_date_idx])
                        if inv_date_idx + 1 < len(inv_parts):
                            rack_id = inv_parts[inv_date_idx + 1]
                    else:
                        idx = invoice_section.find(invoice_date_str)
                        invoice = invoice_section[:idx].replace('-', '').strip()
                        rack_id = invoice_section[idx + len(invoice_date_str):].replace('-', '').strip()
                else:
                    invoice = " ".join(inv_parts)
            
            # --- 📅 എക്സലിന് അനുയോജ്യമായ യഥാർത്ഥ Datetime ഒബ്ജക്റ്റുകളാക്കുന്നു ---
            try:
                expiry_date = pd.to_datetime(expiry_date_str, format='%d/%m/%Y')
            except:
                expiry_date = pd.NaT
                
            if invoice_date_str:
                try:
                    invoice_date = pd.to_datetime(invoice_date_str, format='%d/%m/%Y')
                except:
                    invoice_date = pd.NaT
            else:
                invoice_date = pd.NaT
                
            try: quantity = int(quantity_str)
            except: quantity = 0
                
            try: mrp = float(mrp_str)
            except: mrp = 0.0
                
            data_rows.append({
                "Item Name": item_name,
                "Manufacturer": mfg.upper(),
                "Supplier": current_supplier if current_supplier else "ALFA AGENCIES",
                "Rack ID": rack_id,
                "Packing": packing,
                "Batch": batch,
                "Expiry Date": expiry_date,
                "MRP": mrp,
                "Quantity": quantity,
                "Invoice Date": invoice_date,
                "Invoice Number": invoice
            })
            
        except Exception as e:
            pass

    if data_rows:
        df = pd.DataFrame(data_rows)
        
        columns_order = [
            "Item Name", 
            "Manufacturer", 
            "Supplier", 
            "Rack ID", 
            "Packing", 
            "Batch", 
            "Expiry Date", 
            "MRP", 
            "Quantity", 
            "Invoice Date", 
            "Invoice Number"
        ]
        df = df[columns_order]
        
        # Excel system memory-il വെച്ച് തയാറാക്കുന്നു
        output = io.BytesIO()
        # തീയതികൾ എക്സലിൽ 'YYYY-MM-DD' ഫോർമാറ്റിൽ കാണിക്കാൻ ഇൻസ്ട്രക്ഷൻ നൽകുന്നു
        with pd.ExcelWriter(output, engine='openpyxl', datetime_format='YYYY-MM-DD') as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
            
            # 📐 കോളങ്ങളുടെ വീതി ഓട്ടോമാറ്റിക് ആയി വലുതാക്കി ഫിക്സ് ചെയ്യുന്ന ലോജിക്
            worksheet = writer.sheets["Sheet1"]
            for col in worksheet.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    if cell.value is not None:
                        # തീയതികൾ വരുമ്പോൾ അവയുടെ സ്ട്രിങ് നീളം കൃത്യമായി അളക്കുന്നു
                        if isinstance(cell.value, pd.Timestamp) or hasattr(cell.value, 'strftime'):
                            cell_len = 12
                        else:
                            cell_len = len(str(cell.value))
                        max_len = max(max_len, cell_len)
                worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)
                
        processed_data = output.getvalue()
        
        st.success("🎉 File processed successfully!")
        
        st.download_button(
            label="📥 DOWNLOAD EXCEL FILE",
            data=processed_data,
            file_name="perfect_medical_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Could not parse any valid rows. Please check the file format.")