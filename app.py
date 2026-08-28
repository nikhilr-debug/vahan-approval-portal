import streamlit as st
import gspread
import smtplib
from email.mime.text import MIMEText
import datetime
import uuid
import requests
import json
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

# ==========================================
# OAUTH 2.0 LOGIN SYSTEM
# ==========================================
client_id = st.secrets["google_oauth"]["client_id"]
client_secret = st.secrets["google_oauth"]["client_secret"]
redirect_uri = st.secrets["google_oauth"]["redirect_uri"]

oauth2 = OAuth2Component(
    client_id, client_secret,
    "https://accounts.google.com/o/oauth2/auth",
    "https://oauth2.googleapis.com/token",
    "https://oauth2.googleapis.com/token",
    "https://oauth2.googleapis.com/revoke"
)

if "user_email" not in st.session_state:
    st.title("🔒 Vahan Document Portal")
    st.write("Please sign in with your Vahan Google account to access the portal.")
    
    result = oauth2.authorize_button(
        name="Sign in with Google", icon="https://www.google.com/favicon.ico",
        redirect_uri=redirect_uri, scope="openid email profile", key="google_login", use_container_width=True
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
            row_index = -1
            
            # Loop through ALL records and keep the LAST one matching the Ticket ID
            # This ensures we are always looking at the most recent resubmission
            current_idx = 2
            for record in records:
                if str(record.get("Ticket ID", "")) == str(ticket_id):
                    target_row_data = record
                    row_index = current_idx
                current_idx += 1

            if not target_row_data:
                st.error("Ticket ID not found.")
            else:
                vl_name = target_row_data.get("VL Name (Mention Owner name if Non-GST/NO GST is available)", "Unknown")
                vl_email = target_row_data.get("VL Mail ID", "")
                requestor_email = target_row_data.get("Requestor Mail ID", "")
                zm_email = target_row_data.get("ZM Mail ID", "")
                current_status = target_row_data.get("Document Status", "Pending")
                doc_link = target_row_data.get("Document Status", "") 
                gst_display_val = target_row_data.get("GST number (mention N/A if non-GST)", target_row_data.get("GST number (Leave blank if non-GST)", "N/A"))
                
                try:
                    history = json.loads(target_row_data.get("History Log", "[]"))
                except:
                    history = []

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
                        st.write(f"**No. of TCs Deploying:** {target_row_data.get('Number of TCs VL is deploying', target_row_data.get('No. Of TCs VL is deploying', 'N/A'))}")
                        st.write(f"**Clients:** {target_row_data.get('Clients will the VL operate on', 'N/A')}")
                        st.write(f"**Planned FTs:** {target_row_data.get('Planned FTs in M1/M2/M3', 'N/A')}")

                with col2:
                    st.subheader("Action Required")
                    if "http" not in str(doc_link) and "Error" not in str(doc_link):
                         st.info("Waiting for Google Apps Script to finish generating the document...")
                    elif "Approved" in current_status:
                        st.success("This document has already been approved.")
                    elif "Rejected" in current_status:
                        st.error("This document was rejected and is awaiting resubmission from the user.")
                    else:
                        action = st.radio("Choose Action:", ["Approve", "Send Back to Requester"])
                        if action == "Approve":
                            if st.button("Confirm Approval", type="primary"):
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                history.append({"time": current_time, "title": "✅ Approved", "details": f"Approved by {user_email}. Sent for signature."})
                                
                                worksheet.update_cell(row_index, 11, "Approved - " + str(doc_link)) 
                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                
                                recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
                                email_body = f"<h3>Document Approved & Sent for Signature</h3><p>The document for <b>{vl_name}</b> has been approved.</p>"
                                send_email(recipients, f"Agreement Sent for Signature - {vl_name}", email_body)
                                st.success("Document approved and emails sent to all parties!")
                                st.balloons()
                                
                        elif action == "Send Back to Requester":
                            comments = st.text_area("Rejection Comments / Notes:")
                            if st.button("Submit Rejection"):
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                history.append({"time": current_time, "title": "❌ Rejected", "details": f"Rejected by {user_email}. Reason: {comments}"})
                                
                                worksheet.update_cell(row_index, 11, "Rejected") 
                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                
                                recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
                                email_body = f"<h3>Document Requires Revision</h3><p><b>Comments:</b> {comments}</p><p>Please log in to the portal to edit and resubmit your ticket.</p>"
                                send_email(recipients, f"Action Required - {vl_name}", email_body)
                                st.success("Rejection feedback logged.")

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
                    if not (vl_name and registered_address and gst_number and pan_details and ops_address and tc_count and clients_operated and planned_fts and current_business and vl_age and vl_email and zm_email):
                        st.error("Please complete all required fields (*).")
                    else:
                        new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                        current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                        history_log = [{"time": current_time, "title": "📄 Ticket Submitted", "details": f"Initial request created by {user_email}."}]

                        new_row = [
                            current_time, vl_name, registered_address, gst_number, pan_details, 
                            ops_address, tc_count, current_business, vl_age, vl_email, 
                            "Pending Approval", new_ticket_id, tc_count, clients_operated, 
                            planned_fts, user_email, zm_email, json.dumps(history_log)
                        ]
                        
                        try:
                            worksheet.append_row(new_row)
                            app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                            approval_link = f"{app_url}/?ticket_id={new_ticket_id}"
                            
                            email_body = f"<h3>New Agreement Request</h3><p>Applicant: <b>{vl_name}</b>.</p><p><a href='{approval_link}'>Review and Approve Request</a></p>"
                            send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", zm_email], f"New Approval Needed: {vl_name}", email_body)
                            
                            st.success(f"Form submitted successfully! Your Ticket ID is {new_ticket_id}.")
                            st.balloons()
                        except Exception as err:
                            st.error(f"Error saving to Google Sheets: {err}")

        # ------------------------------------------
        # REVAMPED TICKET REPOSITORY
        # ------------------------------------------
        elif page == "Ticket Repository":
            st.title("🗄️ Ticket Repository")
            records = worksheet.get_all_records()
            
            # Deduplicate records by Ticket ID to only show the most recent submission of each ticket
            latest_records_map = {}
            for r in records:
                tid = str(r.get("Ticket ID", ""))
                if tid:
                    latest_records_map[tid] = r
            
            if is_admin:
                user_records = list(latest_records_map.values())
            else:
                user_records = [
                    r for r in latest_records_map.values() 
                    if str(r.get("Requestor Mail ID", "")).lower() == user_email.lower() 
                    or str(r.get("VL Mail ID", "")).lower() == user_email.lower()
                ]
                
            if len(user_records) == 0:
                st.warning("No tickets found.")
            else:
                ticket_options = [f"{r['Ticket ID']} - {r['VL Name (Mention Owner name if Non-GST/NO GST is available)']} ({r['Document Status'][:15]}...)" for r in reversed(user_records)]
                
                selected_option = st.selectbox("Select a ticket to view details:", ticket_options)
                
                if selected_option:
                    selected_id = selected_option.split(" - ")[0]
                    record = next(r for r in user_records if r["Ticket ID"] == selected_id)
                    
                    status = str(record.get("Document Status", ""))
                    is_rejected = "Rejected" in status
                    
                    tab1, tab2, tab3 = st.tabs(["📝 Details", "🕒 Timeline & History", "⚠️ Edit & Resubmit" if is_rejected else "🔒 Modifications Locked"])
                    
                    with tab1:
                        st.subheader("Ticket Details")
                        for key, value in record.items():
                            if key not in ["History Log", "Document Status"]: 
                                st.write(f"**{key}:** {value}")
                        st.write(f"**Current Status:** {status}")
                        
                    with tab2:
                        st.subheader("Audit Log & Timeline")
                        try:
                            history = json.loads(record.get("History Log", "[]"))
                            for event in reversed(history):
                                st.markdown(f"**{event['time']}** — {event['title']}")
                                st.caption(event['details'])
                                st.divider()
                        except:
                            st.info("No timeline data available for this ticket.")

                    with tab3:
                        if is_rejected and not is_admin:
                            st.warning("This ticket requires revisions. Please update the fields below and resubmit.")
                            st.info("Submitting these updates will retain your old rejected record for historical logging and create a fresh submission automatically.")
                            
                            with st.form("resubmit_form"):
                                res_name = st.text_input("VL Name *", value=record.get("VL Name (Mention Owner name if Non-GST/NO GST is available)", ""))
                                res_reg = st.text_area("Registered Address *", value=record.get("Registered Address", ""))
                                res_gst = st.text_input("GST number *", value=record.get("GST number (mention N/A if non-GST)", record.get("GST number (Leave blank if non-GST)", "")))
                                res_pan = st.text_input("PAN details *", value=record.get("PAN details", ""))
                                res_ops = st.text_area("Address of operations *", value=record.get("Address of operations", ""))
                                res_tc = st.text_input("Number of TCs *", value=record.get("Number of TCs VL is deploying", record.get("No. Of TCs VL is deploying", "")))
                                res_cli = st.text_input("Clients *", value=record.get("Clients will the VL operate on", ""))
                                res_ft = st.text_input("Planned FTs *", value=record.get("Planned FTs in M1/M2/M3", ""))
                                res_biz = st.text_input("Current business *", value=record.get("Current business", ""))
                                res_age = st.text_input("VL Age *", value=record.get("VL Age (If non GST mention owner age)", ""))
                                res_vl_mail = st.text_input("VL Mail ID *", value=record.get("VL Mail ID", ""))
                                res_zm_mail = st.text_input("ZM Mail ID *", value=record.get("ZM Mail ID", ""))
                                
                                if st.form_submit_button("Update and Resubmit Ticket"):
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    
                                    try:
                                        history_log = json.loads(record.get("History Log", "[]"))
                                    except:
                                        history_log = []
                                        
                                    history_log.append({"time": current_time, "title": "🔄 Resubmitted", "details": f"Ticket fields updated and resubmitted by {user_email}."})
                                    
                                    # Create a brand new row instead of overwriting the old one!
                                    new_row = [
                                        current_time, res_name, res_reg, res_gst, res_pan, 
                                        res_ops, res_tc, res_biz, res_age, res_vl_mail, 
                                        "Pending Approval", selected_id, res_tc, res_cli, 
                                        res_ft, record.get("Requestor Mail ID", user_email), 
                                        res_zm_mail, json.dumps(history_log)
                                    ]
                                    
                                    worksheet.append_row(new_row)
                                    
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                                    approval_link = f"{app_url}/?ticket_id={selected_id}"
                                    email_body = f"<h3>Agreement Resubmitted</h3><p>The ticket for <b>{res_name}</b> has been corrected and resubmitted.</p><p><a href='{approval_link}'>Review the updated Request</a></p>"
                                    send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", res_zm_mail], f"Resubmitted Approval Needed: {res_name}", email_body)
                                    
                                    st.success("Ticket successfully resubmitted! A new record has been created.")
                                    st.rerun()
                                    
                        elif is_admin:
                            st.info("You are in Admin mode. Admins cannot edit tickets—only the original requestor can resubmit a rejected ticket.")
                        else:
                            st.info("This ticket is locked because it is currently Pending Approval or already Approved.")
