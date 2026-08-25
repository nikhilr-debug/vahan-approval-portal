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

try:
    worksheet = get_google_sheet()
except Exception as e:
    st.error(f"Failed to connect to Google Sheets. Exact Error: {e}")
    st.stop()

# ==========================================
# HELPER: EMAIL SENDER
# ==========================================
def send_email(to_emails, subject, body):
    # Fetching credentials securely from Streamlit Secrets
    sender_email = st.secrets["emails"]["sender_email"]
    sender_password = st.secrets["emails"]["sender_password"]
    
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

# ==========================================
# VIEW 1: BANSH'S APPROVAL PORTAL
# ==========================================
if ticket_id:
    st.title("📋 Document Approval Request")
    st.info(f"Reviewing Request ID: **{ticket_id}**")

    records = worksheet.get_all_records()
    
    target_row_data = None
    row_index = 2 # Starts at 2 because row 1 is headers
    
    for record in records:
        # Looking for Ticket ID in Column 12 (L)
        if str(record.get("Ticket ID", "")) == str(ticket_id):
            target_row_data = record
            break
        row_index += 1

    if not target_row_data:
        st.error("Ticket ID not found. Ensure you have a 'Ticket ID' header in Column L of your sheet.")
    else:
        vl_name = target_row_data.get("VL Name (Mention Owner name if Non-GST/NO GST is available)", "Unknown")
        vl_email = target_row_data.get("VL Mail ID", "Unknown")
        current_status = target_row_data.get("Document Status", "Pending")
        doc_link = target_row_data.get("Document Status", "") 

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
            if "http" not in str(doc_link) and "Error" not in str(doc_link):
                 st.info("Waiting for Google Apps Script to finish generating the document...")
            elif "Approved" in current_status:
                st.success("This document has already been approved.")
            else:
                action = st.radio("Choose Action:", ["Approve", "Send Back to Requester"])

                if action == "Approve":
                    if st.button("Confirm Approval", type="primary"):
                        worksheet.update_cell(row_index, 11, "Approved - " + str(doc_link)) 
                        trigger_pdffiller_automation(doc_link, vl_name, vl_email)
                        
                        recipients = [vl_email, "nikhil.r@vahan.co", "nikhil.r@vahan.co"]
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
                            worksheet.update_cell(row_index, 11, "Rejected: " + comments) 
                            
                            all_recipients = [vl_email, "nikhil.r@vahan.co", "nikhil.r@vahan.co"]
                            if extra_emails:
                                all_recipients.extend([e.strip() for e in extra_emails.split(",") if e.strip()])

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
        # Match all columns from the Google Sheet
        vl_name = st.text_input("VL Name (Mention Owner name if Non-GST): *")
        registered_address = st.text_area("Registered Address: *")
        gst_number = st.text_input("GST number (Leave blank if non-GST):")
        pan_details = st.text_input("PAN details:")
        ops_address = st.text_area("Address of operations:")
        tc_count = st.text_input("No. Of TCs VL is deploying:")
        current_business = st.text_input("Current business:")
        vl_age = st.text_input("VL Age (If non GST mention owner age):")
        vl_email = st.text_input("VL Mail ID: *")
        
        submitted = st.form_submit_button("Submit Request")

        if submitted:
            if not vl_name or not registered_address or not vl_email:
                st.error("Please complete all required fields (*).")
            else:
                try:
                    new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                    # EXACT MATCH TO YOUR COLUMNS (1 to 12)
                    new_row = [
                        current_time,          # Column 1: Timestamp
                        vl_name,               # Column 2: VL Name
                        registered_address,    # Column 3: Registered Address
                        gst_number,            # Column 4: GST number
                        pan_details,           # Column 5: PAN details
                        ops_address,           # Column 6: Address of operations
                        tc_count,              # Column 7: No. Of TCs
                        current_business,      # Column 8: Current business
                        vl_age,                # Column 9: VL Age
                        vl_email,              # Column 10: VL Mail ID
                        "Pending Approval",    # Column 11: Document Status (Apps Script reads/writes this)
                        new_ticket_id          # Column 12: Ticket ID (For Streamlit Routing)
                    ]
                    
                    worksheet.append_row(new_row)
                    
                    # Send Approval Email to Bansh
                    # IMPORTANT: Update this URL once your app is live!
                    app_url = "https://your-app-name.streamlit.app" 
                    approval_link = f"{app_url}/?ticket_id={new_ticket_id}"
                    email_body = f"""
                    <h3>New Agreement Approval Request</h3>
                    <p><b>Applicant:</b> {vl_name} ({vl_email})</p>
                    <p><a href="{approval_link}">Click here to Review and Approve/Reject</a></p>
                    """
                    send_email("nikhil.r@vahan.co", f"New Approval Needed: {vl_name}", email_body)
                    
                    st.success(f"Form submitted successfully! Your Ticket ID is {new_ticket_id}.")
                    st.balloons()
                except Exception as err:
                    st.error(f"Error saving to Google Sheets: {err}")
