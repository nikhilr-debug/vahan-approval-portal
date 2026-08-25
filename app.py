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
    # Authenticate using Streamlit Secrets
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    # Replace with your actual Google Sheet URL
    sheet_url = "https://docs.google.com/spreadsheets/d/19xDCZHGieGvQ0dYYyarspO-vRUFRFaDUyvyNtLJv9kc/edit"
    return gc.open_by_url(sheet_url).sheet1

try:
    worksheet = get_google_sheet()
except Exception as e:
    st.error("Failed to connect to Google Sheets. Check your secrets and sheet permissions.")
    st.stop()

# ==========================================
# HELPER: EMAIL SENDER
# ==========================================
def send_email(to_emails, subject, body):
    # Configure your sender email and App Password here
    sender_email = "YOUR_SENDER_EMAIL@vahan.co" 
    sender_password = "YOUR_GMAIL_APP_PASSWORD" 
    
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = sender_email
    
    # Handle single string or list of emails
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

# ==========================================
# HELPER: PLAYWRIGHT (MOCK / PLACEHOLDER)
# ==========================================
# Note: Running actual Playwright inside Streamlit Community Cloud requires custom Docker setup.
# In a standard Streamlit Cloud deployment, you can trigger an external webhook here, 
# or host this app on Render.com to run the Playwright python code directly.
def trigger_pdffiller_automation(doc_url, vl_name, vl_email):
    st.info("System is triggering pdfFiller automation in the background...")
    # Your playwright script logic goes here (from the previous code provided)
    return True

# ==========================================
# ROUTING: CHECK FOR APPROVAL TICKET
# ==========================================
# Use Streamlit's query params to see if Bansh clicked a link (e.g., ?ticket_id=TK-1234)
query_params = st.query_params
ticket_id = query_params.get("ticket_id")

# ==========================================
# VIEW 1: BANSH'S APPROVAL PORTAL
# ==========================================
if ticket_id:
    st.title("📋 Document Approval Request")
    st.info(f"Reviewing Request ID: **{ticket_id}**")

    # Fetch all records to find the specific ticket
    records = worksheet.get_all_records()
    
    # Find the row matching the ticket ID
    target_row_data = None
    row_index = 2 # Starts at 2 because row 1 is headers
    
    for record in records:
        if str(record.get("Ticket ID", "")) == str(ticket_id):
            target_row_data = record
            break
        row_index += 1

    if not target_row_data:
        st.error("Ticket ID not found. It may have been deleted or doesn't exist.")
    else:
        vl_name = target_row_data.get("VL Name", "Unknown")
        vl_email = target_row_data.get("VL Mail ID", "Unknown")
        current_status = target_row_data.get("Status", "Pending")
        doc_link = target_row_data.get("Document Link", "Not Generated Yet") # Assuming Column K is named "Document Link"

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Applicant Details")
            st.write(f"**Name:** {vl_name}")
            st.write(f"**Email:** {vl_email}")
            st.write(f"**Current Status:** {current_status}")
            if "http" in str(doc_link):
                st.write(f"[📄 View Generated Google Doc]({doc_link})")
            else:
                st.warning("Document is still generating. Please wait a moment and refresh.")

        with col2:
            st.subheader("Action Required")
            if current_status == "Approved":
                st.success("This document has already been approved.")
            else:
                action = st.radio("Choose Action:", ["Approve", "Send Back to Requester"])

                if action == "Approve":
                    if st.button("Confirm Approval", type="primary"):
                        # 1. Update Sheet Status
                        worksheet.update_cell(row_index, 11, "Approved") # Assuming Status is Column K (11)
                        
                        # 2. Trigger Playwright automation for pdfFiller
                        trigger_pdffiller_automation(doc_link, vl_name, vl_email)
                        
                        # 3. Send Emails
                        recipients = [vl_email, "bansh@vahan.co", "saurabh.dubey@vahan.co"]
                        email_body = f"""
                        <h3>Document Approved & Sent for Signature</h3>
                        <p>The document for <b>{vl_name}</b> has been approved by Bansh.</p>
                        <p>It has been sent for signature via pdfFiller to Saurabh Dubey and {vl_name}.</p>
                        """
                        send_email(recipients, f"Agreement Sent for Signature - {vl_name}", email_body)
                        
                        st.success("Document approved! pdfFiller process initiated and emails sent.")
                        st.balloons()

                elif action == "Send Back to Requester":
                    comments = st.text_area("Rejection Comments / Notes:")
                    extra_emails = st.text_input("Additional Emails (Comma separated):", placeholder="zm@vahan.co, cl@vahan.co")
                    st.warning("⚠️ **Note:** Add ZM/CL mail id as well, else mail/message will only be sent to the user mail and name.")

                    if st.button("Submit Rejection"):
                        if not comments:
                            st.error("Please add comments explaining why the document is sent back.")
                        else:
                            # 1. Update Sheet Status and Comments
                            worksheet.update_cell(row_index, 11, "Rejected") # Status col
                            worksheet.update_cell(row_index, 12, comments)   # Assuming Column L (12) is Comments
                            
                            # 2. Parse emails
                            all_recipients = [vl_email, "bansh@vahan.co", "saurabh.dubey@vahan.co"]
                            if extra_emails:
                                all_recipients.extend([e.strip() for e in extra_emails.split(",") if e.strip()])

                            # 3. Send Email
                            email_body = f"""
                            <h3>Document Requires Revision</h3>
                            <p><b>Approver Comments:</b> {comments}</p>
                            <p>Please review the trailing messages on the portal and re-submit.</p>
                            """
                            send_email(all_recipients, f"Action Required: Agreement Returned - {vl_name}", email_body)
                            st.success("Rejection feedback logged and emails dispatched.")

# ==========================================
# VIEW 2: USER FORM (FRONT-FACING)
# ==========================================
else:
    st.title("📄 Vahan Agreement Generation Form")
    st.write("Please fill in the details below to generate your official agreement.")

    with st.form("user_request_form"):
        vl_name = st.text_input("VL Name (Owner Name if Non-GST): *")
        registered_address = st.text_area("Registered Address: *")
        gst_number = st.text_input("GST Number (Enter 'N/A' if Non-GST): *")
        vl_age = st.text_input("VL Age (Required if Non-GST):")
        vl_email = st.text_input("VL Mail ID: *")
        
        submitted = st.form_submit_button("Submit Request")

        if submitted:
            if not vl_name or not registered_address or not gst_number or not vl_email:
                st.error("Please complete all required fields (*).")
            else:
                try:
                    # Generate a unique Ticket ID (e.g., TK-A1B2)
                    new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Structure the row data based on your Google Sheet columns.
                    # IMPORTANT: Adjust this list so the data falls exactly into the right columns!
                    # For this example: 
                    # Col A: Ticket ID, Col B: Timestamp, Col C: VL Name, Col D: Address, Col E: GST, Col F-H: Blank, Col I: Age, Col J: Email, Col K: Status
                    new_row = [
                        new_ticket_id,       # A
                        current_time,        # B
                        vl_name,             # C
                        registered_address,  # D
                        gst_number,          # E
                        "", "", "",          # F, G, H
                        vl_age,              # I
                        vl_email,            # J
                        "Pending"            # K
                    ]
                    
                    worksheet.append_row(new_row)
                    
                    # Send Approval Email to Bansh
                    # (In production, replace with your live app URL)
                    app_url = "https://your-app-name.streamlit.app"
                    approval_link = f"{app_url}/?ticket_id={new_ticket_id}"
                    email_body = f"""
                    <h3>New Agreement Approval Request</h3>
                    <p><b>Applicant:</b> {vl_name} ({vl_email})</p>
                    <p><a href="{approval_link}">Click here to Review and Approve/Reject</a></p>
                    """
                    send_email("bansh@vahan.co", f"New Approval Needed: {vl_name}", email_body)
                    
                    st.success(f"Form submitted successfully! Your Ticket ID is {new_ticket_id}. Document generation initiated.")
                    st.balloons()
                except Exception as err:
                    st.error(f"Error saving to Google Sheets: {err}")
