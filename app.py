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
    date_pattern = r'\b\d{1,2}/\d{1,2}/\d{4}\b'
    known_mfgs = ["LA RENON", "LIVIDUS", "LUPIN", "RENAUXE", "DA RENON", "BOEHRING", "AKESIS", "Isis Hea", "AVELOR", "KISWAR", "AUREL", "CU CARD", "CU-CARD"]

    # Read the uploaded file lines safely
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    lines = stringio.readlines()

    for line in lines:
        line_raw = line.rstrip('\r\n')
        line_stripped = line_raw.strip()
        
        if "======" in line_stripped:
            start_parsing = True
            continue
            
        if not start_parsing or not line_stripped:
            continue
            
        if '\\' not in line_stripped and '/' not in line_stripped and not any(char.isdigit() for char in line_stripped[:15]):
            current_supplier = line_stripped
            continue
            
        try:
            if '\\' in line_raw:
                slash_pos = line_raw.find('\\')
                before_slash = line_raw[:slash_pos]
                after_slash = line_raw[slash_pos + 1:]
            else:
                continue
                
            before_slash = before_slash.strip()
            if '-' in before_slash:
                item_name, packing = before_slash.rsplit('-', 1)
                item_name = item_name.strip()
                packing = packing.strip()
            else:
                item_name = before_slash
                packing = ""
                
            expiry_match = re.search(date_pattern, after_slash)
            if not expiry_match:
                continue
                
            expiry_date_str = expiry_match.group(0)
            expiry_start_idx = expiry_match.start()
            
            mfg_and_batch_part = after_slash[:expiry_start_idx].strip()
            mfg = ""
            batch = ""
            
            for k_mfg in known_mfgs:
                if mfg_and_batch_part.upper().startswith(k_mfg.upper()):
                    mfg = k_mfg
                    batch = mfg_and_batch_part[len(k_mfg):].strip()
                    break
            
            if not mfg:
                mfg_batch_tokens = re.split(r'\s{2,}', mfg_and_batch_part)
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

            right_part = after_slash[expiry_match.end():].strip()
            right_tokens = right_part.split()
            
            quantity_str = right_tokens[0] if len(right_tokens) > 0 else "0"
            mrp_str = right_tokens[1] if len(right_tokens) > 1 else "0.0"
            
            invoice = ""
            invoice_date_str = ""
            rack_id = ""
            
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
            
            try: expiry_date = pd.to_datetime(expiry_date_str, format='%d/%m/%Y').date()
            except: expiry_date = None
                
            if invoice_date_str:
                try: invoice_date = pd.to_datetime(invoice_date_str, format='%d/%m/%Y').date()
                except: invoice_date = None
            else:
                invoice_date = None
                
            try: quantity = int(quantity_str)
            except: quantity = 0
                
            try: mrp = float(mrp_str)
            except: mrp = 0.0
                
            data_rows.append({
                "Item Name": item_name,
                "Manufacturer": mfg,
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
        columns_order = ["Item Name", "Manufacturer", "Supplier", "Rack ID", "Packing", "Batch", "Expiry Date", "MRP", "Quantity", "Invoice Date", "Invoice Number"]
        df = df[columns_order]
        
        # In-memory output generation
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        processed_data = output.getvalue()
        
        st.success("🎉 File processed successfully!")
        
        # Excel download button
        st.download_button(
            label="📥 DOWNLOAD EXCEL FILE",
            data=processed_data,
            file_name="perfect_medical_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Could not parse any valid rows. Please check the file format.")