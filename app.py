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
# PAGE CONFIGURATION & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="Vahan App Portal", layout="wide", page_icon="🎫")

def apply_custom_css():
    st.markdown("""
        <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        .badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            display: inline-block;
            margin-bottom: 10px;
        }
        .badge-pending { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .badge-approved { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .badge-rejected { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .field-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 2px; }
        .field-value { font-size: 1.05rem; color: #111827; font-weight: 500; margin-bottom: 16px; word-wrap: break-word; }
        h1, h2, h3 { color: #1f2937; font-weight: 700; }
        .stTextInput>div>div>input { border-radius: 6px; }
        .stTextArea>div>div>textarea { border-radius: 6px; }
        </style>
    """, unsafe_allow_html=True)

apply_custom_css()

# ==========================================
# HELPER FUNCTIONS
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

def trigger_pdffiller_automation(doc_url, vl_name, vl_email, zm_email):
    st.info("⚙️ Initiating pdfFiller signature sequence...")
    # Ready for your Zapier/Make Webhook or API connection!
    return True

def send_email(to_emails, subject, body):
    sender_email = st.secrets["emails"]["sender_email"]
    sender_password = st.secrets["emails"]["sender_password"]
    
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = f"Vahan Ticketing <{sender_email}>"
    
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

def get_status_badge(status_text):
    if "Approved" in status_text: return f"<div class='badge badge-approved'>✅ {status_text}</div>"
    elif "Rejected" in status_text: return f"<div class='badge badge-rejected'>❌ {status_text}</div>"
    else: return f"<div class='badge badge-pending'>⏳ {status_text}</div>"

def render_field(label, value):
    safe_value = str(value).strip() if str(value).strip() else "—"
    st.markdown(f"<div><div class='field-label'>{label}</div><div class='field-value'>{safe_value}</div></div>", unsafe_allow_html=True)

def get_status_and_link(record):
    """
    Intelligently extracts the Google Doc link from Col 11 and Status from Col 19.
    Includes fallbacks so old tickets before Col 19 was added don't break.
    """
    raw_col_k = str(record.get("Document Status", "")).strip()
    doc_link = ""
    
    if raw_col_k.startswith("http"):
        doc_link = raw_col_k
    elif "Approved - http" in raw_col_k: # Legacy support
        doc_link = raw_col_k.replace("Approved - ", "").strip()
        
    status = str(record.get("Approval Status", "")).strip()
    
    if not status: # Fallback for older rows
        if raw_col_k.startswith("http"):
            status = "Pending Approval"
        elif raw_col_k.startswith("Approved - "):
            status = "Approved"
        else:
            status = raw_col_k
            
    return status, doc_link

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
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("\n\n")
        st.title("🔒 Vahan Secure Portal")
        st.markdown("Welcome to the unified Vahan Ticketing & Agreement portal. Please authenticate using your corporate Google workspace credentials.")
        
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
# MAIN APPLICATION
# ==========================================
else:
    user_email = st.session_state["user_email"]
    ADMIN_EMAILS = ["bansh@vahan.co", "saurabh.dubey@vahan.co", "nikhil.r@vahan.co"]
    is_admin = user_email.lower() in ADMIN_EMAILS

    st.sidebar.title("🎫 Vahan Tickets")
    st.sidebar.markdown(f"👤 **User:** `{user_email}`\n🛡️ **Role:** `{'Admin' if is_admin else 'Standard User'}`")
    st.sidebar.divider()
    
    query_params = st.query_params
    ticket_id = query_params.get("ticket_id")
    
    if not ticket_id:
        page = st.sidebar.radio("Main Menu", ["📝 Create New Ticket", "🗄️ Ticket Dashboard"])
        if page != "🗄️ Ticket Dashboard" and 'viewing_ticket' in st.session_state:
            del st.session_state['viewing_ticket']
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        del st.session_state["user_email"]
        st.rerun()

    # ------------------------------------------
    # VIEW 1: APPROVER VIEW (URL CONTAINS TICKET)
    # ------------------------------------------
    if ticket_id:
        if not is_admin:
            st.error("🔒 Access Denied: You do not have admin permissions to approve this document.")
        else:
            st.markdown(f"## 🎫 Ticket Review: `{ticket_id}`")
            st.divider()

            records = worksheet.get_all_records()
            target_row_data, row_index = None, -1
            current_idx = 2
            
            for record in records:
                if str(record.get("Ticket ID", "")) == str(ticket_id):
                    target_row_data = record
                    row_index = current_idx
                current_idx += 1

            if not target_row_data:
                st.error("Ticket ID not found in the database.")
            else:
                current_status, doc_link = get_status_and_link(target_row_data)
                
                try: history = json.loads(target_row_data.get("History Log", "[]"))
                except: history = []

                st.markdown(get_status_badge(current_status), unsafe_allow_html=True)
                
                col1, col2 = st.columns([1.5, 1])
                
                with col1:
                    st.markdown("### 📋 Application Details")
                    with st.container(border=True):
                        if "http" in doc_link:
                            st.success(f"📄 **Document Generated Successfully:** [Click here to View Google Doc]({doc_link})")
                        elif "Rejected" not in current_status:
                            st.info("🔄 Waiting for Google Apps Script to generate the document link...")
                            
                        c1, c2 = st.columns(2)
                        with c1:
                            render_field("Applicant Name", target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)'))
                            render_field("Requestor Email", target_row_data.get('Requestor Mail ID'))
                        with c2:
                            render_field("VL Email", target_row_data.get('VL Mail ID'))
                            render_field("ZM Email", target_row_data.get('ZM Mail ID'))
                        
                        st.divider()
                        c1, c2 = st.columns(2)
                        with c1: render_field("GST Number", target_row_data.get('GST number (mention N/A if non-GST)', target_row_data.get('GST number (Leave blank if non-GST)')))
                        with c2: render_field("PAN Details", target_row_data.get('PAN details'))
                        render_field("Registered Address", target_row_data.get('Registered Address'))
                        render_field("Address of Operations", target_row_data.get('Address of operations'))
                        
                        st.divider()
                        c1, c2, c3 = st.columns(3)
                        with c1: render_field("TCs Deploying", target_row_data.get('Number of TCs VL is deploying', target_row_data.get('No. Of TCs VL is deploying')))
                        with c2: render_field("Clients", target_row_data.get('Clients will the VL operate on'))
                        with c3: render_field("Planned FTs", target_row_data.get('Planned FTs in M1/M2/M3'))
                        
                with col2:
                    st.markdown("### ⚡ Action Panel")
                    with st.container(border=True):
                        if "Approved" in current_status:
                            st.success("🎉 This document is already approved.")
                        elif "Rejected" in current_status:
                            st.error("⚠️ Awaiting user resubmission.")
                        else:
                            st.write("Please review the application before deciding.")
                            action = st.radio("Decision:", ["✅ Approve", "❌ Request Revisions"], label_visibility="collapsed")
                            st.divider()
                            
                            if action == "✅ Approve":
                                if st.button("Submit Approval", type="primary", use_container_width=True):
                                    if not doc_link:
                                        st.error("Cannot approve yet: Google Doc link has not been generated by the Apps Script.")
                                    else:
                                        current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                        history.append({"time": current_time, "title": "✅ Approved", "details": f"Approved by {user_email}. Sent for signature."})
                                        
                                        # Update Column 19 to Approved, leave Column 11 completely untouched!
                                        worksheet.update_cell(row_index, 19, "Approved") 
                                        worksheet.update_cell(row_index, 18, json.dumps(history))
                                        
                                        vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                        vl_email = target_row_data.get("VL Mail ID", "")
                                        requestor_email = target_row_data.get("Requestor Mail ID", "")
                                        zm_email = target_row_data.get("ZM Mail ID", "")
                                        
                                        trigger_pdffiller_automation(doc_link, vl_name, vl_email, zm_email)
                                        
                                        recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
                                        send_email(recipients, f"Agreement Sent for Signature - {vl_name}", f"<h3>Document Approved</h3><p>The document for <b>{vl_name}</b> has been approved and sent for e-signatures.</p>")
                                        st.success("Approval logged and signature sequence initiated!")
                                        st.rerun()
                                    
                            elif action == "❌ Request Revisions":
                                comments = st.text_area("Reason for rejection / Notes:")
                                if st.button("Return to Sender", type="primary", use_container_width=True):
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "❌ Rejected", "details": f"Rejected by {user_email}. Reason: {comments}"})
                                    
                                    # Update Column 19 to Rejected
                                    worksheet.update_cell(row_index, 19, "Rejected") 
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    
                                    vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                    recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", target_row_data.get("VL Mail ID"), target_row_data.get("Requestor Mail ID"), target_row_data.get("ZM Mail ID")]
                                    send_email(recipients, f"Action Required - {vl_name}", f"<h3>Revision Required</h3><p><b>Comments:</b> {comments}</p>")
                                    st.success("Rejection logged.")
                                    st.rerun()

    # ------------------------------------------
    # VIEW 2: SUBMIT NEW REQUEST (CLEAN FORM)
    # ------------------------------------------
    elif page == "📝 Create New Ticket":
        st.markdown("## 📝 Create New Ticket")
        st.markdown("Fill out the structured form below to initiate a new agreement process. All fields are mandatory.")
        
        with st.form("user_request_form"):
            st.markdown("#### 🏢 Business Details")
            c1, c2 = st.columns(2)
            vl_name = c1.text_input("VL Name (Mention Owner name if Non-GST): *")
            current_business = c2.text_input("Current business: *")
            
            c3, c4 = st.columns(2)
            gst_number = c3.text_input("GST number (mention N/A if non-GST): *")
            pan_details = c4.text_input("PAN details: *")
            
            vl_age = c1.text_input("VL Age (If non GST mention owner age): *")
            
            registered_address = st.text_area("Registered Address: *")
            ops_address = st.text_area("Address of operations: *")
            
            st.divider()
            st.markdown("#### ⚙️ Operations")
            o1, o2, o3 = st.columns(3)
            tc_count = o1.text_input("No. of TCs Deploying: *")
            clients_operated = o2.text_input("Clients Operated On: *")
            planned_fts = o3.text_input("Planned FTs (M1/M2/M3): *")
            
            st.divider()
            st.markdown("#### 📬 Contact & Routing")
            r1, r2, r3 = st.columns(3)
            vl_email = r1.text_input("VL Mail ID: *")
            zm_email = r2.text_input("ZM's Mail ID: *")
            r3.text_input("Requestor (Auto-filled): *", value=user_email, disabled=True)
            
            st.write("")
            submitted = st.form_submit_button("🚀 Submit Ticket", use_container_width=True)

            if submitted:
                if not (vl_name and registered_address and gst_number and pan_details and ops_address and tc_count and clients_operated and planned_fts and current_business and vl_age and vl_email and zm_email):
                    st.error("⚠️ Please complete all required fields before submitting.")
                else:
                    new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                    history_log = [{"time": current_time, "title": "📄 Ticket Created", "details": f"Initiated by {user_email}. Apps script generating document..."}]

                    # Appending all 19 columns
                    new_row = [
                        current_time, vl_name, registered_address, gst_number, pan_details, 
                        ops_address, tc_count, current_business, vl_age, vl_email, 
                        "Pending Approval", # Col 11: Apps Script reads this
                        new_ticket_id, tc_count, clients_operated, 
                        planned_fts, user_email, zm_email, json.dumps(history_log), 
                        "Pending Approval" # Col 19: Streamlit reads this for approval status
                    ]
                    
                    try:
                        worksheet.append_row(new_row)
                        app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                        send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", zm_email], f"New Approval: {vl_name}", f"<h3>New Request: {new_ticket_id}</h3><p><a href='{app_url}/?ticket_id={new_ticket_id}'>Review Request</a></p>")
                        st.success(f"🎉 Ticket **{new_ticket_id}** created successfully! The Google Doc is generating in the background.")
                        st.balloons()
                    except Exception as err:
                        st.error(f"Database error: {err}")

    # ------------------------------------------
    # VIEW 3: TICKET DASHBOARD (REPOSITORY)
    # ------------------------------------------
    elif page == "🗄️ Ticket Dashboard":
        st.markdown("## 🗄️ Ticket Dashboard")
        
        records = worksheet.get_all_records()
        
        latest_records_map = {}
        for r in records:
            tid = str(r.get("Ticket ID", ""))
            if tid: latest_records_map[tid] = r
            
        if is_admin:
            user_records = list(latest_records_map.values())
        else:
            user_records = [
                r for r in latest_records_map.values() 
                if str(r.get("Requestor Mail ID", "")).lower() == user_email.lower() 
                or str(r.get("VL Mail ID", "")).lower() == user_email.lower()
            ]
            
        if not user_records:
            st.info("No tickets found in the system associated with your account.")
        else:
            viewing_ticket_id = st.session_state.get('viewing_ticket')
            
            if not viewing_ticket_id:
                pending_tickets = 0
                approved_tickets = 0
                for r in user_records:
                    status_str, _ = get_status_and_link(r)
                    if "Pending" in status_str: pending_tickets += 1
                    elif "Approved" in status_str: approved_tickets += 1
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Tickets", len(user_records))
                m2.metric("⏳ Pending Action", pending_tickets)
                m3.metric("✅ Approved", approved_tickets)
                st.write("")
                
                st.markdown("### 📋 Your Tickets")
                col1, col2, col3, col4 = st.columns([1.5, 3, 2, 1])
                col1.markdown("**Ticket ID**")
                col2.markdown("**VL Name**")
                col3.markdown("**Status**")
                col4.markdown("**Action**")
                st.divider()

                for r in reversed(user_records):
                    c1, c2, c3, c4 = st.columns([1.5, 3, 2, 1])
                    c1.write(f"**{r['Ticket ID']}**")
                    c2.write(r['VL Name (Mention Owner name if Non-GST/NO GST is available)'])
                    
                    status_text, _ = get_status_and_link(r)
                    c3.markdown(get_status_badge(status_text), unsafe_allow_html=True)
                    
                    if c4.button("🔍 View", key=f"view_{r['Ticket ID']}", use_container_width=True):
                        st.session_state['viewing_ticket'] = r['Ticket ID']
                        st.rerun()
                        
            else:
                if st.button("⬅️ Back to Ticket List"):
                    del st.session_state['viewing_ticket']
                    st.rerun()
                
                st.write("")
                record = next((r for r in user_records if r["Ticket ID"] == viewing_ticket_id), None)
                
                if not record:
                    st.error("Ticket not found.")
                else:
                    status, doc_link = get_status_and_link(record)
                    
                    is_rejected = "Rejected" in status
                    is_owner = (str(record.get("Requestor Mail ID", "")).lower() == user_email.lower()) or (str(record.get("VL Mail ID", "")).lower() == user_email.lower())
                    
                    st.markdown(f"### Ticket: `{viewing_ticket_id}`")
                    st.markdown(get_status_badge(status), unsafe_allow_html=True)
                    if "http" in doc_link:
                        st.markdown(f"[📄 View Generated Document]({doc_link})")
                    st.write("")
                    
                    tab1, tab2, tab3 = st.tabs(["📝 Detailed Information", "🕒 Activity Timeline", "⚠️ Edit & Resubmit" if is_rejected else "🔒 Modifications Locked"])
                    
                    with tab1:
                        st.write("")
                        c1, c2 = st.columns(2)
                        with c1:
                            render_field("VL Name", record.get("VL Name (Mention Owner name if Non-GST/NO GST is available)"))
                            render_field("Current Business", record.get("Current business"))
                            render_field("VL Email", record.get("VL Mail ID"))
                            render_field("GST Number", record.get("GST number (mention N/A if non-GST)", record.get("GST number (Leave blank if non-GST)")))
                            render_field("Registered Address", record.get("Registered Address"))
                            render_field("Clients", record.get("Clients will the VL operate on"))
                        with c2:
                            render_field("Requestor Email", record.get("Requestor Mail ID"))
                            render_field("ZM Email", record.get("ZM Mail ID"))
                            render_field("VL Age", record.get("VL Age (If non GST mention owner age)"))
                            render_field("PAN Details", record.get("PAN details"))
                            render_field("Address of Operations", record.get("Address of operations"))
                            o1, o2 = st.columns(2)
                            with o1: render_field("No. of TCs", record.get("Number of TCs VL is deploying", record.get("No. Of TCs VL is deploying")))
                            with o2: render_field("Planned FTs", record.get("Planned FTs in M1/M2/M3"))
                        
                    with tab2:
                        st.write("")
                        try:
                            history = json.loads(record.get("History Log", "[]"))
                            for event in reversed(history):
                                with st.container(border=True):
                                    st.markdown(f"**{event['title']}**")
                                    st.caption(f"🗓️ {event['time']} — {event['details']}")
                        except:
                            st.info("No timeline data available.")

                    with tab3:
                        st.write("")
                        if is_rejected:
                            if is_owner:
                                st.warning("⚠️ This ticket requires revisions. Submitting updates will generate a fresh revision history.")
                                with st.form("resubmit_form"):
                                    c1, c2 = st.columns(2)
                                    res_name = c1.text_input("VL Name *", value=record.get("VL Name (Mention Owner name if Non-GST/NO GST is available)", ""))
                                    res_biz = c2.text_input("Current business *", value=record.get("Current business", ""))
                                    res_gst = c1.text_input("GST number *", value=record.get("GST number (mention N/A if non-GST)", record.get("GST number (Leave blank if non-GST)", "")))
                                    res_pan = c2.text_input("PAN details *", value=record.get("PAN details", ""))
                                    res_age = c1.text_input("VL Age *", value=record.get("VL Age (If non GST mention owner age)", ""))
                                    res_reg = st.text_area("Registered Address *", value=record.get("Registered Address", ""))
                                    res_ops = st.text_area("Address of operations *", value=record.get("Address of operations", ""))
                                    o1, o2, o3 = st.columns(3)
                                    res_tc = o1.text_input("Number of TCs *", value=record.get("Number of TCs VL is deploying", record.get("No. Of TCs VL is deploying", "")))
                                    res_cli = o2.text_input("Clients *", value=record.get("Clients will the VL operate on", ""))
                                    res_ft = o3.text_input("Planned FTs *", value=record.get("Planned FTs in M1/M2/M3", ""))
                                    r1, r2 = st.columns(2)
                                    res_vl_mail = r1.text_input("VL Mail ID *", value=record.get("VL Mail ID", ""))
                                    res_zm_mail = r2.text_input("ZM Mail ID *", value=record.get("ZM Mail ID", ""))
                                    
                                    if st.form_submit_button("🔄 Update and Resubmit", use_container_width=True):
                                        current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                        try: history_log = json.loads(record.get("History Log", "[]"))
                                        except: history_log = []
                                        history_log.append({"time": current_time, "title": "🔄 Resubmitted", "details": f"Ticket fields updated by {user_email}."})
                                        
                                        # Resubmitting all 19 columns
                                        new_row = [
                                            current_time, res_name, res_reg, res_gst, res_pan, 
                                            res_ops, res_tc, res_biz, res_age, res_vl_mail, 
                                            "Pending Approval", viewing_ticket_id, res_tc, res_cli, 
                                            res_ft, record.get("Requestor Mail ID", user_email), 
                                            res_zm_mail, json.dumps(history_log), "Pending Approval"
                                        ]
                                        
                                        worksheet.append_row(new_row)
                                        app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                                        send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", res_zm_mail], f"Resubmitted: {res_name}", f"<h3>Resubmitted Request: {viewing_ticket_id}</h3><p><a href='{app_url}/?ticket_id={viewing_ticket_id}'>Review Request</a></p>")
                                        st.success("Ticket successfully resubmitted!")
                                        del st.session_state['viewing_ticket']
                                        st.rerun()
                            else:
                                st.info("🔒 You are viewing someone else's ticket. Only the original requestor can resubmit.")
                        else:
                            st.info("🔒 This ticket is locked because it is Pending Approval or Approved.")
