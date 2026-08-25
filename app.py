import streamlit as st
import gspread
import smtplib
from email.mime.text import MIMEText
import datetime
import uuid

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Vahan Document Portal", layout="centered", page_icon="📄")

# ==========================================
# HELPER: GOOGLE SHEETS CONNECTION
# ==========================================
@st.cache_resource
def get_google_sheet():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    # Replace with your actual Google Sheet URL
    sheet_url = "https://docs.google.com/spreadsheets/d/19xDCZHGieGvQ0dYYyarspO-vRUFRFaDUyvyNtLJv9kc/edit"
    return gc.open_by_url(sheet_url).sheet1

# Call the function AFTER it is defined above
try:
    worksheet = get_google_sheet()
except Exception as e:
    st.error(f"Failed to connect to Google Sheets. Exact Error: {e}")
    st.stop()

# ==========================================
# HELPER: EMAIL SENDER
# ==========================================
def send_email(to_emails, subject, body):
    sender_email = "YOUR_SENDER_EMAIL@vahan.co" 
    sender_password = "YOUR_GMAIL_APP_PASSWORD" 
    
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = sender_email
    
    if isinstance(to_emails, list):
        msg["To"] = ", ".join(to_emails)
    else:
        msg["To"] = to_emails

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_emails if isinstance(to_emails, list) else [to_emails], msg.as_string())
        return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False

def trigger_pdffiller_automation(doc_url, vl_name, vl_email):
    st.info("System is triggering pdfFiller automation in the background...")
    return True

# ==========================================
# ROUTING: CHECK FOR APPROVAL TICKET
# ==========================================
query_params = st.query_params
ticket_id = query_params.get("ticket_id")

# ... (The rest of your code from "VIEW 1: BANSH'S APPROVAL PORTAL" stays exactly the same) ...
