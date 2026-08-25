import streamlit as st
import gspread

# 1. Page Configuration
st.set_page_config(page_title="Vahan Document Request Portal", layout="centered")

st.title("📄 Vahan Agreement Generation Form")
st.write("Please fill in the details below to generate your official agreement.")

# 2. Connect to Google Sheets via Streamlit Secrets
@st.cache_resource
def get_google_sheet():
    # Authenticate using the secrets configured in Streamlit Cloud
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    
    # PASTE YOUR FULL GOOGLE SHEET URL HERE
    sheet_url = "https://docs.google.com/spreadsheets/d/19xDCZHGieGvQ0dYYyarspO-vRUFRFaDUyvyNtLJv9kc/edit"
    return gc.open_by_url(sheet_url).sheet1

try:
    worksheet = get_google_sheet()
except Exception as e:
    st.error("Failed to connect to Google Sheets. Check your secrets and sheet permissions.")
    st.stop()

# 3. User Input Form
with st.form("user_request_form"):
    vl_name = st.text_input("VL Name (Owner Name if Non-GST): *")
    registered_address = st.text_area("Registered Address: *")
    gst_number = st.text_input("GST Number (Enter 'N/A' or 'NA' if Non-GST): *")
    vl_age = st.text_input("VL Age (Required if Non-GST):")
    vl_email = st.text_input("VL Mail ID: *")
    
    submitted = st.form_submit_button("Submit Request")

    if submitted:
        # Validation checks
        if not vl_name or not registered_address or not gst_number or not vl_email:
            st.error("Please complete all required fields (*).")
        else:
            try:
                # Append row matching your Google Sheet column layout
                # Adjust column order if needed to match your sheet headers
                new_row = [
                    "",                  # Timestamp / Column A
                    vl_name,             # Column B: VL Name
                    registered_address,  # Column C: Registered Address
                    gst_number,          # Column D: GST Number
                    "", "", "", "",      # Columns E, F, G, H
                    vl_age,              # Column I: VL Age
                    vl_email,            # Column J: VL Mail ID
                    "Pending"            # Column K: Status
                ]
                
                worksheet.append_row(new_row)
                st.success("Form submitted successfully! Your document is being generated.")
                st.balloons()
            except Exception as err:
                st.error(f"Error saving to Google Sheets: {err}")
