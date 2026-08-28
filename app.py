import streamlit as st
import gspread
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
        
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"Vahan Ticketing <{sender_email}>"
        
        if isinstance(to_emails, list):
            to_emails = list(set([email.strip() for email in to_emails if email]))
            msg["To"] = ", ".join(to_emails)
        else:
            msg["To"] = to_emails

        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_emails, msg.as_string())
        return True, "Success"
    except Exception as e:
        return False, str(e)

def log_email_to_history(row_index, current_history, details_text):
    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    current_history.append({"time": current_time, "title": "📧 Email Sent", "details": details_text})
    worksheet.update_cell(row_index, 18, json.dumps(current_history))

def get_pdf_link(doc_link):
    doc_link = str(doc_link).strip()
    if "/edit" in doc_link:
        return doc_link.split("/edit")[0] + "/export?format=pdf"
    return doc_link

def render_field(label, value):
    safe_value = str(value).strip() if str(value).strip() else "—"
    st.markdown(f"<div><div class='field-label'>{label}</div><div class='field-value'>{safe_value}</div></div>", unsafe_allow_html=True)

def get_status_and_link(record):
    raw_col_k = str(record.get("Document Status", "")).strip()
    doc_link = ""
    
    if raw_col_k.startswith("http"): doc_link = get_pdf_link(raw_col_k)
    elif "Approved - http" in raw_col_k: doc_link = get_pdf_link(raw_col_k.replace("Approved - ", ""))
        
    status = str(record.get("Approval Status", "")).strip()
    vl_sig = str(record.get("VL Signature", "")).strip()
    saurabh_sig = str(record.get("Saurabh Signature", "")).strip()
    
    if not status: 
        if raw_col_k.startswith("http"): status = "Pending Approval"
        elif raw_col_k.startswith("Approved - "): status = "Approved"
        else: status = raw_col_k
        
    return status, doc_link

def get_status_badge(status_text):
    if "Fully Executed" in status_text or "Executing" in status_text: return f"<div class='badge badge-executed'>📜 Fully Executed</div>"
    elif "Approved" in status_text: return f"<div class='badge badge-approved'>✅ {status_text} (Pending Signatures)</div>"
    elif "Signatures Submitted" in status_text: return f"<div class='badge badge-executed'>⏳ Processing Final Document...</div>"
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
        st.title("🔒 Vahan Agreement Portal")
        st.markdown("Welcome to the Vahan Document Portal. Please authenticate using your Google account.")
        
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
    is_saurabh = user_email.lower() == "saurabh.dubey@vahan.co"
    is_internal_staff = user_email.lower().endswith("@vahan.co") or is_admin

    st.sidebar.title("🎫 Vahan Portal")
    st.sidebar.markdown(f"👤 **User:** `{user_email}`")
    if is_admin:
        st.sidebar.markdown("🛡️ **Role:** `Admin`")
    elif is_internal_staff:
        st.sidebar.markdown("💼 **Role:** `Vahan Team`")
    else:
        st.sidebar.markdown("🤝 **Role:** `External Vendor / VL`")
        
    st.sidebar.divider()
    
    query_params = st.query_params
    url_ticket_id = query_params.get("ticket_id")
    approval_ticket_id = st.session_state.get('approval_ticket_id')
    
    # STRICT ROLE-BASED NAVIGATION
    if is_admin:
        menu_options = ["📝 Create New Ticket", "✅ Pending Approvals", "✍️ E-Sign Portal", "🗄️ Ticket Dashboard"]
    elif is_internal_staff:
        menu_options = ["📝 Create New Ticket", "🗄️ Ticket Dashboard"]
    else:
        menu_options = ["✍️ E-Sign Portal", "🗄️ Ticket Dashboard"]

    if not url_ticket_id:
        page = st.sidebar.radio("Main Menu", menu_options)
        if page != "🗄️ Ticket Dashboard" and 'viewing_ticket' in st.session_state:
            del st.session_state['viewing_ticket']
        if page != "✅ Pending Approvals" and 'approval_ticket_id' in st.session_state:
            del st.session_state['approval_ticket_id']
    else:
        page = "Direct URL View"
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        del st.session_state["user_email"]
        st.rerun()

    # ------------------------------------------
    # VIEW 1: DIRECT URL ROUTER / APPROVER VIEW
    # ------------------------------------------
    if url_ticket_id or (page == "✅ Pending Approvals" and approval_ticket_id):
        target_ticket_id = url_ticket_id or approval_ticket_id
        
        records = worksheet.get_all_records()
        target_row_data, row_index = None, -1
        current_idx = 2
        
        for record in records:
            if str(record.get("Ticket ID", "")) == str(target_ticket_id):
                target_row_data = record
                row_index = current_idx
            current_idx += 1

        if not target_row_data:
            st.error("Ticket ID not found in database.")
        else:
            current_status, pdf_link = get_status_and_link(target_row_data)
            vl_email_on_record = str(target_row_data.get("VL Mail ID", "")).lower()
            vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
            
            # CONSISTENT THREADING SUBJECT LINE
            THREAD_SUBJECT = f"Vahan Agreement Workflow: {target_ticket_id} - {vl_name}"

            # ROUTING LOGIC: IF IT IS APPROVED, ROUTE SIGNERS DIRECTLY TO E-SIGN PORTAL
            if current_status == "Approved" and (is_saurabh or user_email.lower() == vl_email_on_record):
                st.markdown(f"## ✍️ E-Sign Agreement: `{target_ticket_id}`")
                st.info(f"📄 Review document draft before signing: [📄 Review Document Draft]({pdf_link})")
                st.divider()

                # --- SAURABH SIGNING ---
                if is_saurabh:
                    st.markdown("#### Apply Authorized Signature")
                    with st.container(border=True):
                        saurabh_sig_text = st.text_input("Type your Full Name to generate digital signature:", placeholder="e.g., Saurabh Dubey")
                        
                        if saurabh_sig_text:
                            st.write("Signature Preview:")
                            st.markdown(f"<div class='signature-font'>{saurabh_sig_text}</div>", unsafe_allow_html=True)
                            
                        if st.button("Apply Digital Signature", type="primary", use_container_width=True):
                            if not saurabh_sig_text:
                                st.error("⚠️ Please type your signature name.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                
                                try: history = json.loads(target_row_data.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by Vahan", "details": "Saurabh Dubey signed the agreement."})
                                
                                worksheet.update_cell(row_index, 23, saurabh_sig_text)
                                
                                vl_already_signed = bool(target_row_data.get("VL Signature", "").strip())
                                if vl_already_signed:
                                    # Trigger Apps Script Phase 2
                                    worksheet.update_cell(row_index, 19, "Signatures Submitted")
                                    history.append({"time": current_time, "title": "⏳ Processing Signatures", "details": "All signatures captured. Google Apps Script is generating final document."})

                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Signature successfully applied!")
                                st.balloons()
                                st.query_params.clear()
                                st.rerun()

                # --- VL SIGNING ---
                elif user_email.lower() == vl_email_on_record:
                    st.markdown("#### Authorized Signatory Details")
                    with st.container(border=True):
                        c1, c2 = st.columns(2)
                        sig_name = c1.text_input("Signatory's Full Name:", placeholder="e.g., John Doe")
                        sig_desig = c2.text_input("Signatory's Designation:", placeholder="e.g., Proprietor")
                        
                        sig_text = st.text_input("Type your Full Name to generate digital signature:")
                        
                        if sig_text:
                            st.write("Signature Preview:")
                            st.markdown(f"<div class='signature-font'>{sig_text}</div>", unsafe_allow_html=True)

                        if st.button("Submit Digital Signature", type="primary", use_container_width=True):
                            if not (sig_name and sig_desig and sig_text):
                                st.error("⚠️ Please complete all fields to sign.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                
                                try: history = json.loads(target_row_data.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by VL", "details": f"Digitally signed by {sig_name} ({sig_desig})."})
                                
                                worksheet.update_cell(row_index, 20, sig_text)
                                worksheet.update_cell(row_index, 21, sig_name)
                                worksheet.update_cell(row_index, 22, sig_desig)
                                
                                saurabh_already_signed = bool(target_row_data.get("Saurabh Signature", "").strip())
                                if saurabh_already_signed:
                                    # Trigger Apps Script Phase 2
                                    worksheet.update_cell(row_index, 19, "Signatures Submitted")
                                    history.append({"time": current_time, "title": "⏳ Processing Signatures", "details": "All signatures captured. Google Apps Script is generating final document."})

                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Document digitally signed!")
                                st.balloons()
                                st.query_params.clear()
                                st.rerun()

            # ADMIN REVIEW VIEW
            elif is_admin:
                if approval_ticket_id:
                    if st.button("⬅️ Back to Pending List"):
                        del st.session_state['approval_ticket_id']
                        st.rerun()
                elif url_ticket_id:
                    if st.button("🏠 Go to Main Dashboard"):
                        st.query_params.clear()
                        st.rerun()
                        
                st.markdown(f"## 🎫 Ticket Review: `{target_ticket_id}`")
                st.divider()
                st.markdown(get_status_badge(current_status), unsafe_allow_html=True)
                
                try: history = json.loads(target_row_data.get("History Log", "[]"))
                except: history = []

                col1, col2 = st.columns([1.5, 1])
                with col1:
                    st.markdown("### 📋 Application Details")
                    with st.container(border=True):
                        if "Fully Executed" in current_status or "Executing" in current_status:
                            st.success(f"🎉 **Agreement Executed!** (Check your email for the final PDF)")
                        elif "http" in pdf_link: 
                            st.success(f"📄 **Draft PDF Preview:** [📄 Review PDF Document]({pdf_link})")
                        elif "Rejected" not in current_status: 
                            st.info("🔄 Generating PDF preview link...")
                            
                        c1_inner, c2_inner = st.columns(2)
                        with c1_inner:
                            render_field("Applicant Name", vl_name)
                            render_field("Current Business", target_row_data.get("Current business"))
                            render_field("VL Email", target_row_data.get('VL Mail ID'))
                            render_field("GST Number", target_row_data.get('GST number (mention N/A if non-GST)', target_row_data.get('GST number (Leave blank if non-GST)')))
                            render_field("Registered Address", target_row_data.get('Registered Address'))
                            render_field("Clients", target_row_data.get('Clients will the VL operate on'))
                        with c2_inner:
                            render_field("Requestor Email", target_row_data.get('Requestor Mail ID'))
                            render_field("ZM Email", target_row_data.get('ZM Mail ID'))
                            render_field("VL Age", target_row_data.get('VL Age (If non GST mention owner age)'))
                            render_field("PAN Details", target_row_data.get('PAN details'))
                            render_field("Address of Operations", target_row_data.get('Address of operations'))
                            
                            o1, o2 = st.columns(2)
                            with o1: render_field("No. of TCs", target_row_data.get('Number of TCs VL is deploying', target_row_data.get('No. Of TCs VL is deploying')))
                            with o2: render_field("Planned FTs", target_row_data.get('Planned FTs in M1/M2/M3'))
                        
                with col2:
                    st.markdown("### ⚡ Action Panel")
                    with st.container(border=True):
                        if "Approved" in current_status or "Executed" in current_status or "Submitted" in current_status:
                            st.success("🎉 Document has been approved.")
                        elif "Rejected" in current_status:
                            st.error("⚠️ Awaiting user resubmission.")
                        else:
                            action = st.radio("Decision:", ["✅ Approve", "❌ Request Revisions"], label_visibility="collapsed")
                            if action == "✅ Approve" and st.button("Submit Approval", type="primary", use_container_width=True):
                                if not pdf_link:
                                    st.error("Cannot approve yet: PDF preview link not ready.")
                                else:
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "✅ Approved", "details": f"Approved by {user_email}. Sent for signature."})
                                    
                                    worksheet.update_cell(row_index, 19, "Approved") 
                                    
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app"
                                    sign_link = f"{app_url}/?ticket_id={target_ticket_id}"
                                    email_body = f"<p>The agreement has been approved internally.</p><p><a href='{sign_link}'>Click here to Review and E-Sign the Agreement</a></p>"
                                    
                                    success, err_msg = send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", target_row_data.get("VL Mail ID")], THREAD_SUBJECT, email_body)
                                    if success:
                                        log_email_to_history(row_index, history, "E-Sign links dispatched.")
                                        st.success("Approved! E-Sign links dispatched.")
                                        if url_ticket_id: st.query_params.clear()
                                        else: del st.session_state['approval_ticket_id']
                                        st.rerun()
                                    else:
                                        worksheet.update_cell(row_index, 18, json.dumps(history))
                                        st.error(f"🚨 Email Failed! Error: {err_msg}")
                                    
                            elif action == "❌ Request Revisions":
                                comments = st.text_area("Reason for rejection:")
                                if st.button("Return to Sender", type="primary", use_container_width=True):
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "❌ Rejected", "details": f"Rejected by {user_email}. Reason: {comments}"})
                                    worksheet.update_cell(row_index, 19, "Rejected") 
                                    
                                    email_body = f"<p>The agreement has been returned for revisions.</p><p><b>Comments:</b> {comments}</p>"
                                    success, err_msg = send_email(["bansh@vahan.co", "saurabh.dubey@vahan.co", target_row_data.get("VL Mail ID"), target_row_data.get("Requestor Mail ID")], THREAD_SUBJECT, email_body)
                                    
                                    if success:
                                        log_email_to_history(row_index, history, "Rejection notice sent to Requestor.")
                                        st.success("Rejection logged.")
                                        if url_ticket_id: st.query_params.clear()
                                        else: del st.session_state['approval_ticket_id']
                                        st.rerun()
                                    else:
                                        worksheet.update_cell(row_index, 18, json.dumps(history))
                                        st.error(f"🚨 Email Failed! Error: {err_msg}")
            else:
                st.warning("You do not have active signature or approval permissions for this specific ticket.")

    # ------------------------------------------
    # VIEW 1.5: PENDING APPROVALS LIST
    # ------------------------------------------
    elif page == "✅ Pending Approvals":
        st.markdown("## ✅ Pending Approvals")
        st.write("Review and process newly submitted tickets waiting for your approval.")
        
        records = worksheet.get_all_records()
        latest_records_map = {}
        for r in records:
            tid = str(r.get("Ticket ID", ""))
            if tid: latest_records_map[tid] = r
            
        pending_tickets = []
        for r in latest_records_map.values():
            status, _ = get_status_and_link(r)
            if status == "Pending Approval":
                pending_tickets.append(r)
                
        if not pending_tickets:
            st.success("🎉 You're all caught up! No tickets are pending approval.")
        else:
            st.markdown("### ⏳ Action Required")
            col1, col2, col3 = st.columns([1.5, 3, 1])
            col1.markdown("**Ticket ID**")
            col2.markdown("**VL Name**")
            col3.markdown("**Action**")
            st.divider()

            for r in reversed(pending_tickets):
                c1, c2, c3 = st.columns([1.5, 3, 1])
                c1.write(f"**{r['Ticket ID']}**")
                c2.write(r['VL Name (Mention Owner name if Non-GST/NO GST is available)'])
                if c3.button("🔍 Review", key=f"approve_btn_{r['Ticket ID']}", use_container_width=True):
                    st.session_state['approval_ticket_id'] = r['Ticket ID']
                    st.rerun()

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
            vl_email = r1.text_input("VL Mail ID (External Google/Gmail allowed): *")
            zm_email = r2.text_input("ZM's Mail ID: *")
            r3.text_input("Requestor (Auto-filled): *", value=user_email, disabled=True)
            
            if st.form_submit_button("🚀 Submit Ticket", use_container_width=True):
                if not (vl_name and registered_address and gst_number and pan_details and ops_address and tc_count and clients_operated and planned_fts and current_business and vl_age and vl_email and zm_email):
                    st.error("⚠️ Please complete all required fields.")
                else:
                    new_ticket_id = "TK-" + str(uuid.uuid4()).split('-')[0].upper()
                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    history_log = [{"time": current_time, "title": "📄 Ticket Created", "details": f"Initiated by {user_email}. Awaiting document generation."}]

                    # Added Empty Strings for the 4 Signature Columns so Array Matches Sheet Structure
                    new_row = [
                        current_time, vl_name, registered_address, gst_number, pan_details, 
                        ops_address, tc_count, current_business, vl_age, vl_email, 
                        "", # Apps script writes doc link here
                        new_ticket_id, tc_count, clients_operated, 
                        planned_fts, user_email, zm_email, json.dumps(history_log), 
                        "Pending Approval", "", "", "", "" 
                    ]
                    
                    try:
                        worksheet.insert_row(new_row, index=2)
                        st.success(f"🎉 Ticket **{new_ticket_id}** saved. Document Generation has started. Approvers will be emailed shortly!")
                        st.balloons()
                    except Exception as err:
                        st.error(f"Database error: {err}")

    # ------------------------------------------
    # VIEW 3: E-SIGN PORTAL (MANUAL NAVIGATION)
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
                _, pdf_link = get_status_and_link(record)
                vl_name = record.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                
                st.markdown(f"### Agreement: {selected_id}")
                st.info(f"📄 Review document draft before signing: [📄 Review Document Draft]({pdf_link})")
                st.divider()
                
                # --- SAURABH SIGNING ---
                if is_saurabh:
                    st.markdown("#### Apply Authorized Signature")
                    with st.container(border=True):
                        saurabh_sig_text = st.text_input("Type your Full Name to generate digital signature:", placeholder="e.g., Saurabh Dubey")
                        
                        if saurabh_sig_text:
                            st.write("Signature Preview:")
                            st.markdown(f"<div class='signature-font'>{saurabh_sig_text}</div>", unsafe_allow_html=True)

                        if st.button("Apply Digital Signature", type="primary", use_container_width=True):
                            if not saurabh_sig_text:
                                st.error("⚠️ Please type your signature name.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                
                                try: history = json.loads(record.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by Vahan", "details": "Saurabh Dubey signed the agreement."})
                                
                                worksheet.update_cell(row_index, 23, saurabh_sig_text) 
                                
                                vl_already_signed = bool(record.get("VL Signature", "").strip())
                                if vl_already_signed:
                                    worksheet.update_cell(row_index, 19, "Signatures Submitted")
                                    history.append({"time": current_time, "title": "⏳ Processing Signatures", "details": "All signatures captured. Google Apps Script is generating final document."})
                                        
                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Signature successfully applied!")
                                st.balloons()
                                st.rerun()
                                
                # --- VL SIGNING ---
                else:
                    st.markdown("#### Authorized Signatory Details")
                    with st.container(border=True):
                        c1, c2 = st.columns(2)
                        sig_name = c1.text_input("Signatory's Full Name:", placeholder="e.g., John Doe")
                        sig_desig = c2.text_input("Signatory's Designation:", placeholder="e.g., Proprietor")
                        
                        sig_text = st.text_input("Type your Full Name to generate digital signature:")
                        
                        if sig_text:
                            st.write("Signature Preview:")
                            st.markdown(f"<div class='signature-font'>{sig_text}</div>", unsafe_allow_html=True)

                        if st.button("Submit Digital Signature", type="primary", use_container_width=True):
                            if not (sig_name and sig_desig and sig_text):
                                st.error("⚠️ Please complete all fields to sign.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                
                                try: history = json.loads(record.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by VL", "details": f"Digitally signed by {sig_name} ({sig_desig})."})
                                
                                worksheet.update_cell(row_index, 20, sig_text) 
                                worksheet.update_cell(row_index, 21, sig_name) 
                                worksheet.update_cell(row_index, 22, sig_desig) 
                                
                                saurabh_already_signed = bool(record.get("Saurabh Signature", "").strip())
                                if saurabh_already_signed:
                                    worksheet.update_cell(row_index, 19, "Signatures Submitted")
                                    history.append({"time": current_time, "title": "⏳ Processing Signatures", "details": "All signatures captured. Google Apps Script is generating final document."})

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
                    status, pdf_link = get_status_and_link(record)
                    st.markdown(f"### Ticket: `{viewing_ticket_id}`")
                    st.markdown(get_status_badge(status), unsafe_allow_html=True)
                    
                    if "Fully Executed" in status or "Executing" in status:
                        st.success("📜 **Agreement Executed!** Check your email for the final PDF.")
                    elif "http" in pdf_link:
                        st.info(f"📄 **Draft PDF Preview:** [📄 Review PDF Document]({pdf_link})")
                        
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
                            if vl_sig: 
                                st.success(f"✅ {vl_sig}")
                                st.caption(f"**Name:** {record.get('VL Signatory Name', '')}")
                                st.caption(f"**Role:** {record.get('VL Signatory Designation', '')}")
                            else: st.warning("⏳ Pending Signature")
                            
                        with c2:
                            st.markdown("#### Vahan Signature")
                            vahan_sig = record.get("Saurabh Signature", "")
                            if vahan_sig: st.success(f"✅ {vahan_sig}")
                            else: st.warning("⏳ Pending Signature")
