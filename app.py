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
        /* Clean up main padding */
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        
        /* Status Badges */
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
        
        /* Headers */
        h1, h2, h3 { color: #1f2937; font-weight: 700; }
        
        /* Form styling */
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
    if "Approved" in status_text:
        return f"<div class='badge badge-approved'>✅ {status_text}</div>"
    elif "Rejected" in status_text:
        return f"<div class='badge badge-rejected'>❌ {status_text}</div>"
    else:
        return f"<div class='badge badge-pending'>⏳ {status_text}</div>"

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
        st.write("")
        st.write("")
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

    # ------------------------------------------
    # SIDEBAR DESIGN
    # ------------------------------------------
    st.sidebar.title("🎫 Vahan Tickets")
    st.sidebar.markdown(f"👤 **User:** `{user_email}`")
    st.sidebar.markdown(f"🛡️ **Role:** `{'Admin' if is_admin else 'Standard User'}`")
    st.sidebar.divider()
    
    query_params = st.query_params
    ticket_id = query_params.get("ticket_id")
    
    if not ticket_id:
        page = st.sidebar.radio("Main Menu", ["📝 Create New Ticket", "🗄️ Ticket Dashboard"])
    
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
                current_status = str(target_row_data.get("Document Status", "Pending"))
                doc_link = str(target_row_data.get("Document Status", "")) 
                
                try: history = json.loads(target_row_data.get("History Log", "[]"))
                except: history = []

                # Render Status Badge directly via HTML
                st.markdown(get_status_badge(current_status), unsafe_allow_html=True)
                
                col1, col2 = st.columns([1.5, 1])
                
                with col1:
                    st.markdown("### 📋 Application Details")
                    with st.container(border=True):
                        if "http" in doc_link:
                            st.success(f"📄 **Document Generated Successfully:** [Click here to View Google Doc]({doc_link})")
                        elif "Rejected" not in current_status:
                            st.info("🔄 Google Apps Script is currently generating the document...")
                            
                        # Layout data in a clean grid
                        c1, c2 = st.columns(2)
                        c1.markdown(f"**Applicant Name:**\n{target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')}")
                        c2.markdown(f"**VL Email:**\n{target_row_data.get('VL Mail ID', 'N/A')}")
                        
                        c1.markdown(f"**Requestor:**\n{target_row_data.get('Requestor Mail ID', 'N/A')}")
                        c2.markdown(f"**ZM Email:**\n{target_row_data.get('ZM Mail ID', 'N/A')}")
                        
                        st.divider()
                        
                        c1.markdown(f"**GST Number:**\n{target_row_data.get('GST number (mention N/A if non-GST)', target_row_data.get('GST number (Leave blank if non-GST)', 'N/A'))}")
                        c2.markdown(f"**PAN Details:**\n{target_row_data.get('PAN details', 'N/A')}")
                        
                        st.markdown(f"**Registered Address:**\n{target_row_data.get('Registered Address', 'N/A')}")
                        st.markdown(f"**Address of Ops:**\n{target_row_data.get('Address of operations', 'N/A')}")
                        
                        st.divider()
                        
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**TCs Deploying:**\n{target_row_data.get('Number of TCs VL is deploying', target_row_data.get('No. Of TCs VL is deploying', 'N/A'))}")
                        c2.markdown(f"**Clients:**\n{target_row_data.get('Clients will the VL operate on', 'N/A')}")
                        c3.markdown(f"**Planned FTs:**\n{target_row_data.get('Planned FTs in M1/M2/M3', 'N/A')}")
                        
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
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "✅ Approved", "details": f"Approved by {user_email}."})
                                    
                                    worksheet.update_cell(row_index, 11, "Approved - " + str(doc_link)) 
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    
                                    vl_email = target_row_data.get("VL Mail ID", "")
                                    requestor_email = target_row_data.get("Requestor Mail ID", "")
                                    zm_email = target_row_data.get("ZM Mail ID", "")
                                    vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                    
                                    recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
                                    send_email(recipients, f"Agreement Sent for Signature - {vl_name}", f"<h3>Document Approved</h3><p>The document for <b>{vl_name}</b> has been approved.</p>")
                                    st.success("Approval logged successfully!")
                                    st.rerun()
                                    
                            elif action == "❌ Request Revisions":
                                comments = st.text_area("Reason for rejection / Notes:")
                                if st.button("Return to Sender", type="primary", use_container_width=True):
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "❌ Rejected", "details": f"Rejected by {user_email}. Reason: {comments}"})
                                    
                                    worksheet.update_cell(row_index, 11, "Rejected") 
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    
                                    vl_email = target_row_data.get("VL Mail ID", "")
                                    requestor_email = target_row_data.get("Requestor Mail ID", "")
                                    zm_email = target_row_data.get("ZM Mail ID", "")
                                    vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                    
                                    recipients = ["bansh@vahan.co", "saurabh.dubey@vahan.co", vl_email, requestor_email, zm_email]
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

                    history_log = [{"time": current_time, "title": "📄 Ticket Created", "details": f"Initiated by {user_email}."}]

                    new_row = [
                        current_time, vl_name, registered_address, gst_number, pan_details, 
                        ops_address, tc_count, current_business, vl_age, vl_email, 
                        "Pending Approval", new_ticket_id, tc_count, clients_operated, 
                        planned_fts, user_email, zm_email, json.dumps(history_log)
                    ]
                    
                    try:
                        worksheet.append_row(new_row)
                        app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                        send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", zm_email], f"New Approval: {vl_name}", f"<h3>New Request: {new_ticket_id}</h3><p><a href='{app_url}/?ticket_id={new_ticket_id}'>Review Request</a></p>")
                        st.success(f"🎉 Ticket **{new_ticket_id}** created successfully!")
                        st.balloons()
                    except Exception as err:
                        st.error(f"Database error: {err}")

    # ------------------------------------------
    # VIEW 3: TICKET DASHBOARD (REPOSITORY)
    # ------------------------------------------
    elif page == "🗄️ Ticket Dashboard":
        st.markdown("## 🗄️ Ticket Dashboard")
        
        records = worksheet.get_all_records()
        
        # Deduplicate
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
            
        # Metrics Top Bar
        if user_records:
            total_tickets = len(user_records)
            pending_tickets = len([r for r in user_records if "Pending" in str(r.get("Document Status", ""))])
            approved_tickets = len([r for r in user_records if "Approved" in str(r.get("Document Status", ""))])
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Tickets", total_tickets)
            m2.metric("⏳ Pending Action", pending_tickets)
            m3.metric("✅ Approved", approved_tickets)
            st.divider()

        if not user_records:
            st.info("No tickets found in the system associated with your account.")
        else:
            # Ticket Selector
            ticket_options = [f"{r['Ticket ID']} — {r['VL Name (Mention Owner name if Non-GST/NO GST is available)']}" for r in reversed(user_records)]
            selected_option = st.selectbox("🔍 Search & Select Ticket", ticket_options)
            
            if selected_option:
                selected_id = selected_option.split(" — ")[0]
                record = next(r for r in user_records if r["Ticket ID"] == selected_id)
                status = str(record.get("Document Status", ""))
                is_rejected = "Rejected" in status
                is_owner = (str(record.get("Requestor Mail ID", "")).lower() == user_email.lower()) or (str(record.get("VL Mail ID", "")).lower() == user_email.lower())
                
                # Tab Layout
                tab1, tab2, tab3 = st.tabs(["📝 Details", "🕒 Activity Log", "⚠️ Edit & Resubmit" if is_rejected else "🔒 Modifications Locked"])
                
                with tab1:
                    st.markdown(get_status_badge(status), unsafe_allow_html=True)
                    st.write("")
                    
                    c1, c2 = st.columns(2)
                    for idx, (key, value) in enumerate(record.items()):
                        if key not in ["History Log", "Document Status"]: 
                            if idx % 2 == 0:
                                c1.markdown(f"**{key}:** {value}")
                            else:
                                c2.markdown(f"**{key}:** {value}")
                    
                with tab2:
                    try:
                        history = json.loads(record.get("History Log", "[]"))
                        for event in reversed(history):
                            with st.container(border=True):
                                st.markdown(f"**{event['title']}**")
                                st.caption(f"🗓️ {event['time']} — {event['details']}")
                    except:
                        st.info("No timeline data available.")

                with tab3:
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
                                    
                                    new_row = [
                                        current_time, res_name, res_reg, res_gst, res_pan, 
                                        res_ops, res_tc, res_biz, res_age, res_vl_mail, 
                                        "Pending Approval", selected_id, res_tc, res_cli, 
                                        res_ft, record.get("Requestor Mail ID", user_email), 
                                        res_zm_mail, json.dumps(history_log)
                                    ]
                                    
                                    worksheet.append_row(new_row)
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                                    send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", res_zm_mail], f"Resubmitted: {res_name}", f"<h3>Resubmitted Request: {selected_id}</h3><p><a href='{app_url}/?ticket_id={selected_id}'>Review Request</a></p>")
                                    st.success("Ticket successfully resubmitted!")
                                    st.rerun()
                        else:
                            st.info("🔒 You are viewing someone else's ticket. Only the original requestor can resubmit.")
                    else:
                        st.info("🔒 This ticket is locked because it is Pending Approval or Approved.")
