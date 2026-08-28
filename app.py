import streamlit as st
import gspread
import smtplib
from email.mime.text import MIMEText
import datetime
import uuid
import requests
from streamlit_oauth import OAuth2Component

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Vahan Document Portal", layout="wide", page_icon="📄")

# ==========================================
# HELPER: GOOGLE SHEETS CONNECTION
# ==========================================
@st.cache_resource(ttl=60)
def get_google_sheet():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
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
    sender_email = st.secrets["emails"]["sender_email"]
    sender_password = st.secrets["emails"]["sender_password"]
    
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = sender_email
    
    # Clean up the email list (remove duplicates and empty strings)
    if isinstance(to_emails, list):
        to_emails = list(set([email.strip() for email in to_emails if email]))
        msg["To"] = ", ".join(to_emails)
    else:
        msg["To"] = to_emails

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_emails, msg.as_string())
        return True
    except Exception as e:
        return False

def trigger_pdffiller_automation(doc_url, vl_name, vl_email):
    st.info("System is triggering pdfFiller automation in the background...")
    return True

# ==========================================
# OAUTH 2.0 LOGIN SYSTEM
# ==========================================
client_id = st.secrets["google_oauth"]["client_id"]
client_secret = st.secrets["google_oauth"]["client_secret"]
redirect_uri = st.secrets["google_oauth"]["redirect_uri"]

oauth2 = OAuth2Component(
    client_id,
    client_secret,
    "https://accounts.google.com/o/oauth2/auth",
    "https://oauth2.googleapis.com/token",
    "https://oauth2.googleapis.com/token",
    "https://oauth2.googleapis.com/revoke"
)

if "user_email" not in st.session_state:
    st.title("🔒 Vahan Document Portal")
    st.write("Please sign in with your Vahan Google account to access the portal.")
    
    result = oauth2.authorize_button(
        name="Sign in with Google",
        icon="https://www.google.com/favicon.ico",
        redirect_uri=redirect_uri,
        scope="openid email profile",
        key="google_login",
        use_container_width=True
    )
    
    if result and "token" in result:
        token = result["token"]["access_token"]
        user_info = requests.get(f"https://www.googleapis.com/oauth2/v1/userinfo?access_token={token}").json()
        st.session_state["user_email"] = user_info["email"]
        st.rerun()

# ==========================================
# MAIN APPLICATION (USER IS LOGGED IN)
# ==========================================
else:
    user_email = st.session_state["user_email"]
    
    ADMIN_EMAILS = ["bansh@vahan.co", "saurabh.dubey@vahan.co", "nikhil.r@vahan.co"]
    is_admin = user_email.lower() in ADMIN_EMAILS

    st.sidebar.write(f"Logged in as: **{user_email}**")
    if st.sidebar.button("Logout"):
        del st.session_state["user_email"]
        st.rerun()
    st.sidebar.divider()

    query_params = st.query_params
    ticket_id = query_params.get("ticket_id")

    # ------------------------------------------
    # VIEW 1: BANSH'S APPROVAL PORTAL
    # ------------------------------------------
    if ticket_id:
        if not is_admin:
            st.error("Access Denied: You do not have admin permissions to approve this document.")
        else:
            st.title("📋 Document Approval Request")
            st.info(f"Reviewing Request ID: **{ticket_id}**")

            records = worksheet.get_all_records()
            target_row_data = None
            row_index = 2 
            
            for record in records:
                if str(record.get("Ticket ID", "")) == str(ticket_id):
                    target_row_data = record
                    break
                row_index += 1

            if not target_row_data:
                st.error("Ticket ID not found.")
            else:
                vl_name = target_row_data.get("VL Name (Mention Owner name if Non-GST/NO GST is available)", "Unknown")
                vl_email = target_row_data.get("VL Mail ID", "")
                requestor_email = target_row_data.get("Requestor Mail ID", "")
                zm_email = target_row_data.get("ZM Mail ID", "")
                current_status = target_row_data.get("Document Status", "Pending")
                doc_link = target_row_data.get("Document Status", "") 

                # Fallback handler in case you change the GSheet header to match the new text
                gst_display_val = target_row_data.get("GST number (mention N/A if non-GST)", target_row_data.get("GST number (Leave blank if non-GST)", "N/A"))

                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("Applicant Details")
                    if "http" in str(doc_link):
                        st.write(f"**Generated Document:** [📄 View Google Doc]({doc_link})")
                    else:
                        st.warning("Document is still generating. Please wait a moment and refresh.")
                        
                    with st.expander("🔍 View Full Application Details", expanded=True):
                        st.write(f"**Name:** {vl_name}")
                        st.write(f"**VL Email:** {vl_email}")
                        st.write(f"**Requestor Email:** {requestor_email}")
                        st.write(f"**ZM Email:** {zm_email}")
                        st.write(f"**GST Number:** {gst_display_val}")
                        st.write(f"**PAN Details:** {target_row_data.get('PAN details', 'N/A')}")
                        st.write(f"**Registered Address:** {target_row_data.get('Registered Address', 'N/A')}")
                        st.write(f"**Address of Operations:** {target_row_data.get('Address of operations', 'N/A')}")
                        st.write(f"**Current Business:** {target_row_data.get('Current business', 'N/A')}")
                        st.write(f"**VL Age:** {target_row_data.get('VL Age (If non GST mention owner age)', 'N/A')}")
                        st.divider()
                        st.write(f"**No. of TCs VL is deploying:** {target_row_data.get('Number of TCs VL is deploying', target_row_data.get('No. Of TCs VL is deploying', 'N/A'))}")
                        st.write(f"**Clients VL will operate on:** {target_row_data.get('Clients will the VL operate on', 'N/A')}")
                        st.write(f"**Planned FTs in M1/M2/M3:** {target_row_data.get('Planned FTs in M1/M2/M3', 'N/A')}")

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
                                
                                recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
                                
                                email_body = f"""
                                <h3>Document Approved & Sent for Signature</h3>
                                <p>The document for <b>{vl_name}</b> has been approved.</p>
                                <p>It has been sent for signature via pdfFiller to Saurabh Dubey and {vl_name}.</p>
                                """
                                send_email(recipients, f"Agreement Sent for Signature - {vl_name}", email_body)
                                st.success("Document approved and emails sent to all parties!")
                                st.balloons()
                                
                        elif action == "Send Back to Requester":
                            comments = st.text_area("Rejection Comments / Notes:")
                            if st.button("Submit Rejection"):
                                worksheet.update_cell(row_index, 11, "Rejected: " + comments) 
                                
                                recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
                                
                                email_body = f"<h3>Document Requires Revision</h3><p>Comments: {comments}</p><p>Please review and resubmit.</p>"
                                send_email(recipients, f"Action Required - {vl_name}", email_body)
                                st.success("Rejection feedback logged and sent to all parties.")

    # ------------------------------------------
    # VIEW 2 & 3: STANDARD PORTAL
    # ------------------------------------------
    else:
        page = st.sidebar.radio("Navigation", ["Submit New Request", "Ticket Repository"])

        if page == "Submit New Request":
            st.title("📄 Vahan Agreement Generation Form")
            st.write("Please fill in the details below to generate your official agreement.")

            with st.form("user_request_form"):
                st.subheader("Business Details")
                vl_name = st.text_input("VL Name (Mention Owner name if Non-GST): *")
                registered_address = st.text_area("Registered Address: *")
                gst_number = st.text_input("GST number (mention N/A if non-GST): *")
                pan_details = st.text_input("PAN details: *")
                ops_address = st.text_area("Address of operations: *")
                tc_count = st.text_input("Number of TCs VL is deploying: *")
                clients_operated = st.text_input("Clients will the VL operate on: *")
                planned_fts = st.text_input("Planned FTs in M1/M2/M3: *")
                current_business = st.text_input("Current business: *")
                vl_age = st.text_input("VL Age (If non GST mention owner age): *")
                
                st.subheader("Contact Information")
                vl_email = st.text_input("VL Mail ID: *")
                zm_email = st.text_input("ZM's Mail ID: *")
                st.text_input("Requestor's Mail ID (Auto-filled)", value=user_email, disabled=True)
                
                submitted = st.form_submit_button("Submit Request")

                if submitted:
                    # Require absolutely all fields to be populated
                    if not (vl_name and registered_address and gst_number and pan_details and ops_address and tc_count and clients_operated and planned_fts and current_business and vl_age and vl_email and zm_email):
                        st.error("Please complete all required fields (*).")
                    else:
                        new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                        current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                        new_row = [
                            current_time,          # 1: Timestamp
                            vl_name,               # 2: VL Name
                            registered_address,    # 3: Registered Address
                            gst_number,            # 4: GST number
                            pan_details,           # 5: PAN details
                            ops_address,           # 6: Address of operations
                            tc_count,              # 7: TC Count
                            current_business,      # 8: Current business
                            vl_age,                # 9: VL Age
                            vl_email,              # 10: VL Mail ID
                            "Pending Approval",    # 11: Document Status
                            new_ticket_id,         # 12: Ticket ID
                            tc_count,              # 13: Number of TCs 
                            clients_operated,      # 14: Clients
                            planned_fts,           # 15: Planned FTs
                            user_email,            # 16: Requestor Mail ID
                            zm_email               # 17: ZM Mail ID
                        ]
                        
                        try:
                            worksheet.append_row(new_row)
                            app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                            approval_link = f"{app_url}/?ticket_id={new_ticket_id}"
                            
                            email_body = f"""
                            <div style="font-family: Arial, sans-serif; color: #333;">
                                <h3>New Agreement Approval Request</h3>
                                <p>A new document request has been submitted by <b>{user_email}</b>. Please review the details below:</p>
                                
                                <table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%; max-width: 600px; margin-bottom: 20px;">
                                    <tr style="background-color: #f2f2f2;">
                                        <th style="text-align: left; width: 40%;">Field</th>
                                        <th style="text-align: left;">Details</th>
                                    </tr>
                                    <tr><td><b>Applicant Name</b></td><td>{vl_name}</td></tr>
                                    <tr><td><b>VL Email Address</b></td><td>{vl_email}</td></tr>
                                    <tr><td><b>Requestor Email</b></td><td>{user_email}</td></tr>
                                    <tr><td><b>ZM Email</b></td><td>{zm_email}</td></tr>
                                    <tr><td><b>GST Number</b></td><td>{gst_number}</td></tr>
                                    <tr><td><b>PAN Details</b></td><td>{pan_details}</td></tr>
                                    <tr><td><b>Registered Address</b></td><td>{registered_address}</td></tr>
                                    <tr><td><b>Address of Operations</b></td><td>{ops_address}</td></tr>
                                    <tr><td><b>Current Business</b></td><td>{current_business}</td></tr>
                                    <tr><td><b>VL Age</b></td><td>{vl_age}</td></tr>
                                    <tr><td><b>No. of TCs Deploying</b></td><td>{tc_count}</td></tr>
                                    <tr><td><b>Clients Operated On</b></td><td>{clients_operated}</td></tr>
                                    <tr><td><b>Planned FTs (M1/M2/M3)</b></td><td>{planned_fts}</td></tr>
                                </table>
                                
                                <p><i>Admin Note: Click below to approve or reject this request.</i></p>
                                <a href="{approval_link}" style="display: inline-block; padding: 12px 24px; background-color: #0056b3; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">Review and Approve Request</a>
                            </div>
                            """
                            
                            initial_recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", zm_email]
                            send_email(initial_recipients, f"New Approval Needed: {vl_name}", email_body)
                            
                            st.success(f"Form submitted successfully! Your Ticket ID is {new_ticket_id}.")
                            st.balloons()
                        except Exception as err:
                            st.error(f"Error saving to Google Sheets: {err}")

        elif page == "Ticket Repository":
            st.title("🗄️ Ticket Repository")
            records = worksheet.get_all_records()
            
            if is_admin:
                st.success("Admin Dashboard Active. Showing all system tickets.")
                st.dataframe(records)
            else:
                user_records = [
                    r for r in records 
                    if str(r.get("Requestor Mail ID", "")).lower() == user_email.lower()
                    or str(r.get("VL Mail ID", "")).lower() == user_email.lower()
                ]
                
                if len(user_records) == 0:
                    st.warning("You have not submitted any tickets yet.")
                else:
                    st.success(f"Showing your tickets:")
                    st.dataframe(user_records)
