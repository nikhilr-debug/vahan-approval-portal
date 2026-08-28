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
        .badge { padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600; display: inline-block; margin-bottom: 10px; }
        .badge-pending { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .badge-approved { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .badge-rejected { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .badge-executed { background-color: #cce5ff; color: #004085; border: 1px solid #b8daff; }
        .field-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 2px; }
        .field-value { font-size: 1.05rem; color: #111827; font-weight: 500; margin-bottom: 16px; word-wrap: break-word; }
        h1, h2, h3 { color: #1f2937; font-weight: 700; }
        .stTextInput>div>div>input { border-radius: 6px; }
        .stTextArea>div>div>textarea { border-radius: 6px; }
        
        .signature-font {
            font-family: 'Brush Script MT', 'Bradley Hand', cursive;
            font-size: 42px; color: #000080; padding: 10px;
            border-bottom: 2px solid #ccc; display: inline-block;
            min-width: 300px; background-color: #f9f9f9;
        }
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
    try:
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

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_emails, msg.as_string())
        return True, "Success"
    except Exception as e:
        return False, str(e)  # We will now print this exact error!

def get_pdf_link(doc_link):
    if "/edit" in doc_link:
        return doc_link.split("/edit")[0] + "/export?format=pdf"
    return doc_link

def render_field(label, value):
    safe_value = str(value).strip() if str(value).strip() else "—"
    st.markdown(f"<div><div class='field-label'>{label}</div><div class='field-value'>{safe_value}</div></div>", unsafe_allow_html=True)

def get_status_and_link(record):
    raw_col_k = str(record.get("Document Status", "")).strip()
    doc_link = ""
    
    if raw_col_k.startswith("http"): doc_link = raw_col_k
    elif "Approved - http" in raw_col_k: doc_link = raw_col_k.replace("Approved - ", "").strip()
        
    status = str(record.get("Approval Status", "")).strip()
    vl_sig = str(record.get("VL Signature", "")).strip()
    saurabh_sig = str(record.get("Saurabh Signature", "")).strip()
    
    if not status: 
        if raw_col_k.startswith("http"): status = "Pending Approval"
        elif raw_col_k.startswith("Approved - "): status = "Approved"
        else: status = raw_col_k
            
    if status == "Approved" and vl_sig and saurabh_sig:
        status = "Fully Executed"
        
    return status, doc_link

def get_status_badge(status_text):
    if "Fully Executed" in status_text: return f"<div class='badge badge-executed'>📜 {status_text}</div>"
    elif "Approved" in status_text: return f"<div class='badge badge-approved'>✅ {status_text} (Pending Signatures)</div>"
    elif "Rejected" in status_text: return f"<div class='badge badge-rejected'>❌ {status_text}</div>"
    else: return f"<div class='badge badge-pending'>⏳ {status_text}</div>"

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
    ADMIN_EMAILS = ["nikhil.r@vahan.co", "nikhil.r@vahan.co", "nikhil.r@vahan.co"]
    is_admin = user_email.lower() in ADMIN_EMAILS
    is_saurabh = user_email.lower() == "nikhil.r@vahan.co"

    st.sidebar.title("🎫 Vahan Tickets")
    st.sidebar.markdown(f"👤 **User:** `{user_email}`\n🛡️ **Role:** `{'Admin' if is_admin else 'Standard User'}`")
    st.sidebar.divider()
    
    query_params = st.query_params
    ticket_id = query_params.get("ticket_id")
    
    if not ticket_id:
        page = st.sidebar.radio("Main Menu", ["📝 Create New Ticket", "🗄️ Ticket Dashboard", "✍️ E-Sign Portal"])
        if page != "🗄️ Ticket Dashboard" and 'viewing_ticket' in st.session_state:
            del st.session_state['viewing_ticket']
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        del st.session_state["user_email"]
        st.rerun()

    # ------------------------------------------
    # VIEW 1: APPROVER VIEW (BANSH)
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
                        if current_status == "Fully Executed":
                            st.success(f"🎉 **Agreement Fully Executed:** [📥 Download Final PDF]({get_pdf_link(doc_link)})")
                        elif "http" in doc_link: 
                            st.success(f"📄 **Document Generated (Draft):** [View Google Doc]({doc_link})")
                        elif "Rejected" not in current_status: 
                            st.info("🔄 Generating document link...")
                            
                        c1, c2 = st.columns(2)
                        with c1:
                            render_field("Applicant Name", target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)'))
                            render_field("Requestor Email", target_row_data.get('Requestor Mail ID'))
                        with c2:
                            render_field("VL Email", target_row_data.get('VL Mail ID'))
                            render_field("ZM Email", target_row_data.get('ZM Mail ID'))
                        
                with col2:
                    st.markdown("### ⚡ Action Panel")
                    with st.container(border=True):
                        if "Approved" in current_status or "Executed" in current_status:
                            st.success("🎉 Document is already approved.")
                        elif "Rejected" in current_status:
                            st.error("⚠️ Awaiting user resubmission.")
                        else:
                            action = st.radio("Decision:", ["✅ Approve", "❌ Request Revisions"], label_visibility="collapsed")
                            if action == "✅ Approve" and st.button("Submit Approval", type="primary", use_container_width=True):
                                if not doc_link:
                                    st.error("Cannot approve yet: Google Doc link not ready.")
                                else:
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "✅ Approved", "details": f"Approved by {user_email}. Moved to E-Sign."})
                                    
                                    worksheet.update_cell(row_index, 19, "Approved") 
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    
                                    vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                    vl_email = target_row_data.get("VL Mail ID", "")
                                    
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app"
                                    email_body = f"<h3>Document Approved & Ready for Signature</h3><p>The document for <b>{vl_name}</b> has been approved.</p><p>Please log in to the <a href='{app_url}'>Vahan Portal</a> and go to the <b>E-Sign Portal</b> tab to digitally sign the agreement.</p>"
                                    
                                    success, err_msg = send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", vl_email], f"Signature Required - {vl_name}", email_body)
                                    if success:
                                        st.success("Approved! Directed to E-Sign Portal.")
                                        st.rerun()
                                    else:
                                        st.error(f"🚨 Email Failed! Error: {err_msg}")
                                    
                            elif action == "❌ Request Revisions":
                                comments = st.text_area("Reason for rejection:")
                                if st.button("Return to Sender", type="primary", use_container_width=True):
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "❌ Rejected", "details": f"Rejected by {user_email}. Reason: {comments}"})
                                    worksheet.update_cell(row_index, 19, "Rejected") 
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    
                                    vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                    success, err_msg = send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", target_row_data.get("VL Mail ID"), target_row_data.get("Requestor Mail ID")], f"Action Required - {vl_name}", f"<h3>Revision Required</h3><p><b>Comments:</b> {comments}</p>")
                                    
                                    if success:
                                        st.success("Rejection logged.")
                                        st.rerun()
                                    else:
                                        st.error(f"🚨 Email Failed! Error: {err_msg}")

    # ------------------------------------------
    # VIEW 2: SUBMIT NEW REQUEST
    # ------------------------------------------
    elif page == "📝 Create New Ticket":
        st.markdown("## 📝 Create New Ticket")
        with st.form("user_request_form"):
            c1, c2 = st.columns(2)
            vl_name = c1.text_input("VL Name (Mention Owner name if Non-GST): *")
            current_business = c2.text_input("Current business: *")
            
            c3, c4 = st.columns(2)
            gst_number = c3.text_input("GST number (mention N/A if non-GST): *")
            pan_details = c4.text_input("PAN details: *")
            
            vl_age = c1.text_input("VL Age (If non GST mention owner age): *")
            registered_address = st.text_area("Registered Address: *")
            ops_address = st.text_area("Address of operations: *")
            
            o1, o2, o3 = st.columns(3)
            tc_count = o1.text_input("No. of TCs Deploying: *")
            clients_operated = o2.text_input("Clients Operated On: *")
            planned_fts = o3.text_input("Planned FTs (M1/M2/M3): *")
            
            r1, r2, r3 = st.columns(3)
            vl_email = r1.text_input("VL Mail ID: *")
            zm_email = r2.text_input("ZM's Mail ID: *")
            r3.text_input("Requestor (Auto-filled): *", value=user_email, disabled=True)
            
            if st.form_submit_button("🚀 Submit Ticket", use_container_width=True):
                if not (vl_name and registered_address and gst_number and pan_details and ops_address and tc_count and clients_operated and planned_fts and current_business and vl_age and vl_email and zm_email):
                    st.error("⚠️ Please complete all required fields.")
                else:
                    new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    history_log = [{"time": current_time, "title": "📄 Ticket Created", "details": f"Initiated by {user_email}."}]

                    new_row = [
                        current_time, vl_name, registered_address, gst_number, pan_details, 
                        ops_address, tc_count, current_business, vl_age, vl_email, 
                        "Pending Approval", new_ticket_id, tc_count, clients_operated, 
                        planned_fts, user_email, zm_email, json.dumps(history_log), 
                        "Pending Approval", "", "" 
                    ]
                    
                    try:
                        # USING INSERT_ROW AT INDEX 2 - Guaranteed NO overwriting!
                        worksheet.insert_row(new_row, index=2)
                        
                        app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                        success, err_msg = send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", zm_email], f"New Approval: {vl_name}", f"<h3>New Request: {new_ticket_id}</h3><p><a href='{app_url}/?ticket_id={new_ticket_id}'>Review Request</a></p>")
                        
                        if success:
                            st.success(f"🎉 Ticket **{new_ticket_id}** created successfully! Check your email.")
                            st.balloons()
                        else:
                            st.error(f"🚨 TICKETING SUCCESSFUL, BUT EMAIL FAILED! \n\n**Google Error details:** {err_msg}")
                    except Exception as err:
                        st.error(f"Database error: {err}")

    # ------------------------------------------
    # VIEW 3: E-SIGN PORTAL
    # ------------------------------------------
    elif page == "✍️ E-Sign Portal":
        st.markdown("## ✍️ E-Sign Portal")
        
        records = worksheet.get_all_records()
        
        latest_records_map = {}
        for r in records:
            tid = str(r.get("Ticket ID", ""))
            if tid: latest_records_map[tid] = r
            
        tickets_to_sign = []
        for r in latest_records_map.values():
            status, doc_link = get_status_and_link(r)
            if status == "Approved": 
                if is_saurabh and not r.get("Saurabh Signature", ""):
                    tickets_to_sign.append(r)
                elif user_email.lower() == str(r.get("VL Mail ID", "")).lower() and not r.get("VL Signature", ""):
                    tickets_to_sign.append(r)
                    
        if not tickets_to_sign:
            st.success("🎉 You have no documents pending your signature at this time.")
        else:
            ticket_options = [f"{r['Ticket ID']} — {r['VL Name (Mention Owner name if Non-GST/NO GST is available)']}" for r in tickets_to_sign]
            selected_option = st.selectbox("Select an agreement to sign:", ticket_options)
            
            if selected_option:
                selected_id = selected_option.split(" — ")[0]
                record = next(r for r in tickets_to_sign if r["Ticket ID"] == selected_id)
                row_index = records.index(record) + 2
                _, doc_link = get_status_and_link(record)
                vl_name = record.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                
                st.markdown(f"### Agreement: {selected_id}")
                st.info(f"📄 Please review the finalized agreement here before signing: [View Document]({doc_link})")
                st.divider()
                
                if is_saurabh:
                    st.markdown("#### Apply Authorized Signature & Company Stamp")
                    with st.container(border=True):
                        sig_name = st.text_input("Type your full name to generate digital signature:")
                        if sig_name:
                            st.write("Signature Preview:")
                            st.markdown(f"<div class='signature-font'>{sig_name}</div>", unsafe_allow_html=True)
                            
                        stamp_file = st.file_uploader("Upload Company Stamp Image (PNG/JPG)", type=["png", "jpg", "jpeg"])
                        agree = st.checkbox("I, Saurabh Dubey, hereby digitally sign and apply the company stamp to this agreement.")
                        
                        if st.button("Apply Stamp & Sign", type="primary", use_container_width=True):
                            if not sig_name or not stamp_file or not agree:
                                st.error("⚠️ Please type your name, upload the stamp, and check the consent box.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                sig_log = f"Signed by {sig_name} on {current_time} (Stamp Applied)"
                                
                                try: history = json.loads(record.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by Vahan", "details": "Saurabh Dubey applied signature and stamp."})
                                
                                worksheet.update_cell(row_index, 21, sig_log) 
                                
                                vl_already_signed = bool(record.get("VL Signature", "").strip())
                                if vl_already_signed:
                                    pdf_link = get_pdf_link(doc_link)
                                    history.append({"time": current_time, "title": "📜 Fully Executed", "details": "All parties have signed. Final PDF distributed."})
                                    email_body = f"<h3>Agreement Fully Executed</h3><p>The agreement for <b>{vl_name}</b> has been signed by all parties.</p><p><a href='{pdf_link}'>📥 Download Final Signed PDF</a></p>"
                                    send_email([record.get("VL Mail ID"), record.get("Requestor Mail ID"), "nikhil.r@vahan.co"], f"Fully Executed Agreement - {vl_name}", email_body)
                                    
                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Signature successfully applied!")
                                st.balloons()
                                st.rerun()
                                
                else:
                    st.markdown("#### Digital Signature Consent")
                    with st.container(border=True):
                        agree = st.checkbox(f"I, acting on behalf of {vl_name}, have read the agreement and hereby digitally sign it.")
                        if st.button("Submit Digital Signature", type="primary", use_container_width=True):
                            if not agree:
                                st.error("⚠️ You must check the consent box to sign.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                sig_log = f"Signed by {user_email} on {current_time}"
                                
                                try: history = json.loads(record.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by VL", "details": f"Digitally signed by {user_email}."})
                                
                                worksheet.update_cell(row_index, 20, sig_log) 
                                
                                saurabh_already_signed = bool(record.get("Saurabh Signature", "").strip())
                                if saurabh_already_signed:
                                    pdf_link = get_pdf_link(doc_link)
                                    history.append({"time": current_time, "title": "📜 Fully Executed", "details": "All parties have signed. Final PDF distributed."})
                                    email_body = f"<h3>Agreement Fully Executed</h3><p>The agreement for <b>{vl_name}</b> has been signed by all parties.</p><p><a href='{pdf_link}'>📥 Download Final Signed PDF</a></p>"
                                    send_email([record.get("VL Mail ID"), record.get("Requestor Mail ID"), "nikhil.r@vahan.co"], f"Fully Executed Agreement - {vl_name}", email_body)

                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Document digitally signed!")
                                st.balloons()
                                st.rerun()

    # ------------------------------------------
    # VIEW 4: TICKET DASHBOARD (REPOSITORY)
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
                
                if record:
                    status, doc_link = get_status_and_link(record)
                    st.markdown(f"### Ticket: `{viewing_ticket_id}`")
                    st.markdown(get_status_badge(status), unsafe_allow_html=True)
                    
                    if status == "Fully Executed":
                        st.success(f"📜 **Fully Executed Agreement:**\n\n[📥 Click to Download Final PDF]({get_pdf_link(doc_link)})")
                    elif "http" in doc_link:
                        st.info(f"📄 **Draft Document:**\n\n[View Google Doc]({doc_link})")
                        
                    st.write("")
                    tab1, tab2, tab3 = st.tabs(["📝 Detailed Information", "🕒 Activity Timeline", "✍️ Signatures"])
                    
                    with tab1:
                        st.write("")
                        c1, c2 = st.columns(2)
                        with c1:
                            render_field("VL Name", record.get("VL Name (Mention Owner name if Non-GST/NO GST is available)"))
                            render_field("Current Business", record.get("Current business"))
                            render_field("VL Email", record.get("VL Mail ID"))
                            render_field("GST Number", record.get("GST number (mention N/A if non-GST)", record.get("GST number (Leave blank if non-GST)")))
                        with c2:
                            render_field("Requestor Email", record.get("Requestor Mail ID"))
                            render_field("ZM Email", record.get("ZM Mail ID"))
                            render_field("VL Age", record.get("VL Age (If non GST mention owner age)"))
                            render_field("PAN Details", record.get("PAN details"))
                        
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
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("#### VL Signature")
                            vl_sig = record.get("VL Signature", "")
                            if vl_sig: st.success(f"✅ {vl_sig}")
                            else: st.warning("⏳ Pending Signature")
                            
                        with c2:
                            st.markdown("#### Vahan Signature")
                            vahan_sig = record.get("Saurabh Signature", "")
                            if vahan_sig: st.success(f"✅ {vahan_sig}")
                            else: st.warning("⏳ Pending Signature")
