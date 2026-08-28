import streamlit as st
import gspread
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import uuid
import requests
import json
import base64
import io
from PIL import Image
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
        
        .signature-font {
            font-family: 'Brush Script MT', 'Caveat', 'Pacifico', cursive;
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

def compress_image_to_base64(uploaded_file, max_width=200):
    img = Image.open(uploaded_file)
    img = img.convert("RGBA")
    w_percent = (max_width / float(img.size[0]))
    h_size = int((float(img.size[1]) * float(w_percent)))
    img = img.resize((max_width, h_size), Image.Resampling.LANCZOS)
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

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

def get_preview_link(doc_link):
    doc_link = str(doc_link).strip()
    if "/edit" in doc_link: return doc_link.split("/edit")[0] + "/preview"
    return doc_link

def get_status_and_link(record):
    raw_col_k = str(record.get("Document Status", "")).strip()
    doc_link = raw_col_k if raw_col_k.startswith("http") else ""
        
    status = str(record.get("Approval Status", "")).strip()
    if not status: 
        if raw_col_k.startswith("http"): status = "Pending Approval"
        else: status = raw_col_k
        
    return status, doc_link

def get_status_badge(status_text):
    if "Fully Executed" in status_text or "Executing" in status_text: return f"<div class='badge badge-executed'>📜 Fully Executed</div>"
    elif "Approved" in status_text: return f"<div class='badge badge-approved'>✅ {status_text} (Pending Signatures)</div>"
    elif "Signatures Submitted" in status_text: return f"<div class='badge badge-executed'>⏳ Processing Final Document...</div>"
    elif "Rejected" in status_text: return f"<div class='badge badge-rejected'>❌ {status_text}</div>"
    else: return f"<div class='badge badge-pending'>⏳ {status_text}</div>"

def render_details_table(record):
    vl_name = record.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', record.get('VL Name', '—'))
    business = record.get('Current business', '—')
    vl_email = record.get('VL Mail ID', '—')
    gst = record.get('GST number (mention N/A if non-GST)', record.get('GST number (Leave blank if non-GST)', '—'))
    pan = record.get('PAN details', '—')
    vl_age = record.get('VL Age (If non GST mention owner age)', '—')
    reg_address = record.get('Registered Address', '—')
    ops_address = record.get('Address of operations', '—')
    
    tc_count = record.get('No. of TCs Deploying:', record.get('No. of TCs Deploying', record.get('Number of TCs VL is deploying', record.get('No. Of TCs VL is deploying', '—'))))
    clients = record.get('Clients Operated On:', record.get('Clients Operated On', record.get('Clients will the VL operate on', '—')))
    fts = record.get('Planned FTs (M1/M2/M3):', record.get('Planned FTs (M1/M2/M3)', record.get('Planned FTs in M1/M2/M3', '—')))
    
    req_email = record.get('Requestor Mail ID', record.get('Requestor (Auto-filled):', '—'))
    zm_email = record.get("ZM's Mail ID:", record.get("ZM's Mail ID", record.get("ZM Mail ID", '—')))
    
    html = f"""
    <table style='width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 0.9em;'>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb; width: 35%;'><b>VL Name</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{vl_name}</td></tr>
        <tr><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>Current Business</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{business}</td></tr>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>GST Number</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{gst}</td></tr>
        <tr><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>PAN Details</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{pan}</td></tr>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>VL Age</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{vl_age}</td></tr>
        <tr><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>Registered Address</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{reg_address}</td></tr>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>Address of Operations</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{ops_address}</td></tr>
        <tr><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>No. of TCs Deploying</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{tc_count}</td></tr>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>Clients Operated On</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{clients}</td></tr>
        <tr><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>Planned FTs</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{fts}</td></tr>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>VL Email</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{vl_email}</td></tr>
        <tr><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>ZM Email</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{zm_email}</td></tr>
        <tr style='background-color: #f9fafb;'><td style='padding: 8px; border: 1px solid #e5e7eb;'><b>Requestor Email</b></td><td style='padding: 8px; border: 1px solid #e5e7eb;'>{req_email}</td></tr>
    </table>
    """
    st.markdown(html, unsafe_allow_html=True)

def render_pdf_iframe(url, height=600):
    st.markdown(f'<iframe src="{url}" width="100%" height="{height}px" style="border: none; border-radius: 8px;"></iframe>', unsafe_allow_html=True)

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
    ADMIN_EMAILS = ["nikhil.r@vahan.co", "nikhil.r@vahan.co", "nikhil.r@vahan.co"]
    
    is_admin = user_email.lower() in ADMIN_EMAILS
    is_saurabh = user_email.lower() == "nikhil.r@vahan.co"
    is_internal_staff = user_email.lower().endswith("@vahan.co") or is_admin

    st.sidebar.title("🎫 Vahan Portal")
    st.sidebar.markdown(f"👤 **User:** `{user_email}`")
    st.sidebar.divider()
    
    query_params = st.query_params
    url_ticket_id = query_params.get("ticket_id")
    approval_ticket_id = st.session_state.get('approval_ticket_id')
    
    if is_admin: menu_options = ["📝 Create New Ticket", "✅ Pending Approvals", "✍️ E-Sign Portal", "🗄️ Ticket Dashboard"]
    elif is_internal_staff: menu_options = ["📝 Create New Ticket", "🗄️ Ticket Dashboard"]
    else: menu_options = ["✍️ E-Sign Portal", "🗄️ Ticket Dashboard"]

    if not url_ticket_id:
        page = st.sidebar.radio("Main Menu", menu_options)
        if page != "🗄️ Ticket Dashboard" and 'viewing_ticket' in st.session_state: del st.session_state['viewing_ticket']
        if page != "✅ Pending Approvals" and 'approval_ticket_id' in st.session_state: del st.session_state['approval_ticket_id']
    else: page = "Direct URL View"
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        del st.session_state["user_email"]
        st.rerun()

    # ------------------------------------------
    # DIRECT URL ROUTER & APPROVER VIEW
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

        if not target_row_data: st.error("Ticket ID not found in database.")
        else:
            current_status, doc_link = get_status_and_link(target_row_data)
            vl_email_on_record = str(target_row_data.get("VL Mail ID", "")).lower()
            vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
            THREAD_SUBJECT = f"Vahan Agreement Workflow: {target_ticket_id} - {vl_name}"
            preview_link = get_preview_link(doc_link)

            # ROUTING: E-SIGN PORTAL
            if current_status == "Approved" and (is_saurabh or user_email.lower() == vl_email_on_record):
                st.markdown(f"## ✍️ E-Sign Agreement: `{target_ticket_id}`")
                st.info("📄 Please review the document before signing.")
                with st.expander("🔍 Click to Expand & Review Agreement"):
                    render_pdf_iframe(preview_link, height=600)
                st.divider()

                # --- SAURABH SIGNING ---
                if is_saurabh:
                    st.markdown("#### Apply Authorized Signature & Stamp")
                    with st.container(border=True):
                        c1, c2 = st.columns(2)
                        sig_type = c1.radio("Signature Method:", ["✍️ Type Signature", "🖼️ Upload Image"])
                        saurabh_payload = ""
                        
                        if sig_type == "✍️ Type Signature":
                            saurabh_sig_text = st.text_input("Type Full Name:", placeholder="e.g., Saurabh Dubey")
                            if saurabh_sig_text:
                                st.markdown(f"<div class='signature-font'>{saurabh_sig_text}</div>", unsafe_allow_html=True)
                                saurabh_payload = saurabh_sig_text
                        else:
                            sig_file = st.file_uploader("Upload Signature Image (PNG/JPG):", type=["png", "jpg", "jpeg"])
                            if sig_file: saurabh_payload = compress_image_to_base64(sig_file)

                        st.write("")
                        stamp_file = st.file_uploader("Upload Company Stamp Image (PNG/JPG):", type=["png", "jpg", "jpeg"])
                        stamp_payload = compress_image_to_base64(stamp_file) if stamp_file else ""

                        if st.button("Apply Signatures & Stamp", type="primary", use_container_width=True):
                            if not saurabh_payload: st.error("⚠️ Please provide your signature.")
                            elif not stamp_payload: st.error("⚠️ Please upload the Company Stamp.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                try: history = json.loads(target_row_data.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by Vahan", "details": "Saurabh Dubey signed and stamped."})
                                worksheet.update_cell(row_index, 23, saurabh_payload) 
                                worksheet.update_cell(row_index, 24, stamp_payload) 
                                
                                if bool(target_row_data.get("VL Signature", "").strip()):
                                    worksheet.update_cell(row_index, 19, "Signatures Submitted")
                                    history.append({"time": current_time, "title": "⏳ Processing", "details": "Signatures captured. Modifying document."})

                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Signature applied!")
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
                        
                        sig_type = st.radio("Signature Method:", ["✍️ Type Signature", "🖼️ Upload Image"])
                        vl_payload = ""
                        
                        if sig_type == "✍️ Type Signature":
                            sig_text = st.text_input("Type your Full Name to generate digital signature:")
                            if sig_text:
                                st.markdown(f"<div class='signature-font'>{sig_text}</div>", unsafe_allow_html=True)
                                vl_payload = sig_text
                        else:
                            sig_file = st.file_uploader("Upload Signature Image (PNG/JPG):", type=["png", "jpg", "jpeg"])
                            if sig_file: vl_payload = compress_image_to_base64(sig_file)

                        if st.button("Submit Digital Signature", type="primary", use_container_width=True):
                            if not (sig_name and sig_desig and vl_payload):
                                st.error("⚠️ Please complete all fields to sign.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                try: history = json.loads(target_row_data.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by VL", "details": f"Digitally signed by {sig_name}."})
                                worksheet.update_cell(row_index, 20, vl_payload)
                                worksheet.update_cell(row_index, 21, sig_name)
                                worksheet.update_cell(row_index, 22, sig_desig)
                                
                                if bool(target_row_data.get("Saurabh Signature", "").strip()):
                                    worksheet.update_cell(row_index, 19, "Signatures Submitted")
                                    history.append({"time": current_time, "title": "⏳ Processing", "details": "Signatures captured. Modifying document."})

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
                            st.success(f"🎉 **Agreement Executed!**")
                            with st.expander("🔍 Click to Expand Final PDF"):
                                render_pdf_iframe(preview_link, height=600)
                        elif "http" in doc_link: 
                            with st.expander("🔍 Click to Review Draft"):
                                render_pdf_iframe(preview_link, height=600)
                            
                        st.write("")
                        render_details_table(target_row_data)
                        
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
                                if not doc_link: st.error("Cannot approve yet: Link not ready.")
                                else:
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "✅ Approved", "details": "Approved internally. E-Sign links sent."})
                                    worksheet.update_cell(row_index, 19, "Approved") 
                                    
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app"
                                    sign_link = f"{app_url}/?ticket_id={target_ticket_id}"
                                    
                                    # 1. Threaded Email to Internal Staff
                                    internal_body = f"<p>The agreement has been approved internally.</p><p><a href='{sign_link}'>Click here to Review and E-Sign the Agreement</a></p>"
                                    send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", target_row_data.get("Requestor Mail ID")], THREAD_SUBJECT, internal_body)
                                    
                                    # 2. Custom Email specifically for the VL
                                    vl_email = target_row_data.get("VL Mail ID")
                                    vl_subject = "New signature request from Vahan Technologies"
                                    vl_body = f"""
                                    <div style='font-family: sans-serif; padding: 20px;'>
                                        <p>Vahan Technologies is inviting you to review and sign an Agreement.</p>
                                        <br>
                                        <a href='{sign_link}' style='display: inline-block; padding: 12px 24px; background-color: #000080; color: white; text-decoration: none; font-weight: bold; border-radius: 4px;'>Review and Sign Agreement</a>
                                        <br><br>
                                        <p style='color: #666; font-size: 12px;'>This is an automated message from the Vahan E-Sign Portal.</p>
                                    </div>
                                    """
                                    success, err = send_email([vl_email], vl_subject, vl_body)
                                    
                                    if success:
                                        log_email_to_history(row_index, history, "E-Sign links dispatched to VL.")
                                        st.success("Approved! Links dispatched.")
                                        if url_ticket_id: st.query_params.clear()
                                        else: del st.session_state['approval_ticket_id']
                                        st.rerun()
                                    else:
                                        worksheet.update_cell(row_index, 18, json.dumps(history))
                                        st.error(f"🚨 Email Failed! Error: {err}")
                                    
                            elif action == "❌ Request Revisions":
                                comments = st.text_area("Reason for rejection:")
                                if st.button("Return to Sender", type="primary", use_container_width=True):
                                    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    history.append({"time": current_time, "title": "❌ Rejected", "details": f"Rejected. Reason: {comments}"})
                                    worksheet.update_cell(row_index, 19, "Rejected") 
                                    
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app"
                                    ticket_link = f"{app_url}/?ticket_id={target_ticket_id}"
                                    
                                    # ADDED TICKET LINK TO REJECTION EMAIL
                                    email_body = f"<p>The agreement has been returned for revisions.</p><p><b>Comments:</b> {comments}</p><br><p>👉 <b><a href='{ticket_link}'>Click here to Modify and Resubmit the Request</a></b></p>"
                                    send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", target_row_data.get("VL Mail ID"), target_row_data.get("Requestor Mail ID")], THREAD_SUBJECT, email_body)
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    st.success("Rejection logged.")
                                    if url_ticket_id: st.query_params.clear()
                                    else: del st.session_state['approval_ticket_id']
                                    st.rerun()

    # ------------------------------------------
    # VIEW 1.5: PENDING APPROVALS LIST
    # ------------------------------------------
    elif page == "✅ Pending Approvals":
        st.markdown("## ✅ Pending Approvals")
        records = worksheet.get_all_records()
        pending_tickets = [r for r in records if get_status_and_link(r)[0] == "Pending Approval" and str(r.get("Ticket ID", ""))]
                
        if not pending_tickets: st.success("🎉 You're all caught up! No tickets are pending approval.")
        else:
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

                    new_row = [
                        current_time, vl_name, registered_address, gst_number, pan_details, 
                        ops_address, tc_count, current_business, vl_age, vl_email, 
                        "", new_ticket_id, tc_count, clients_operated, 
                        planned_fts, user_email, zm_email, json.dumps(history_log), 
                        "Pending Approval", "", "", "", "", "" 
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
        st.info("Select an agreement from the dropdown below to review and sign.")
        
        records = worksheet.get_all_records()
        latest_records_map = {str(r.get("Ticket ID", "")): r for r in records if str(r.get("Ticket ID", ""))}
            
        tickets_to_sign = []
        for r in latest_records_map.values():
            status, doc_link = get_status_and_link(r)
            if status == "Approved": 
                if is_saurabh and not r.get("Saurabh Signature", ""):
                    tickets_to_sign.append(r)
                elif user_email.lower() == str(r.get("VL Mail ID", "")).lower() and not r.get("VL Signature", ""):
                    tickets_to_sign.append(r)
                    
        if not tickets_to_sign: pass
        else:
            ticket_options = [f"{r['Ticket ID']} — {r['VL Name (Mention Owner name if Non-GST/NO GST is available)']}" for r in tickets_to_sign]
            selected_option = st.selectbox("Select an agreement to sign:", ticket_options)
            if selected_option:
                selected_id = selected_option.split(" — ")[0]
                st.query_params["ticket_id"] = selected_id
                st.rerun()

    # ------------------------------------------
    # VIEW 4: TICKET DASHBOARD (REPOSITORY)
    # ------------------------------------------
    elif page == "🗄️ Ticket Dashboard":
        st.markdown("## 🗄️ Ticket Dashboard")
        records = worksheet.get_all_records()
        latest_records_map = {str(r.get("Ticket ID", "")): r for r in records if str(r.get("Ticket ID", ""))}
            
        if is_admin: user_records = list(latest_records_map.values())
        else:
            user_records = [r for r in latest_records_map.values() if str(r.get("Requestor Mail ID", "")).lower() == user_email.lower() or str(r.get("VL Mail ID", "")).lower() == user_email.lower()]
            
        if not user_records: st.info("No tickets found in the system associated with your account.")
        else:
            viewing_ticket_id = st.session_state.get('viewing_ticket')
            
            if not viewing_ticket_id:
                st.markdown("### 📋 Your Tickets")
                col1, col2, col3, col4 = st.columns([1.5, 3, 2, 1])
                col1.markdown("**Ticket ID**")
                col2.markdown("**VL Name**")
                col3.markdown("**Status**")
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
                    row_index = records.index(record) + 2
                    status, doc_link = get_status_and_link(record)
                    preview_link = get_preview_link(doc_link)
                    st.markdown(f"### Ticket: `{viewing_ticket_id}`")
                    st.markdown(get_status_badge(status), unsafe_allow_html=True)
                    
                    # --- RESUBMISSION FORM LOGIC ---
                    if status == "Rejected" and str(record.get("Requestor Mail ID", "")).lower() == user_email.lower():
                        st.error("⚠️ This ticket requires revisions. Please update the details below and resubmit.")
                        with st.form(f"resubmit_form_{viewing_ticket_id}"):
                            st.markdown("#### ✏️ Edit Ticket Details")
                            c1, c2 = st.columns(2)
                            new_vl_name = c1.text_input("VL Name:", value=record.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', ''))
                            new_business = c2.text_input("Current business:", value=record.get('Current business', ''))
                            
                            c3, c4 = st.columns(2)
                            new_gst = c3.text_input("GST number:", value=record.get('GST number (mention N/A if non-GST)', ''))
                            new_pan = c4.text_input("PAN details:", value=record.get('PAN details', ''))
                            
                            new_age = c1.text_input("VL Age:", value=record.get('VL Age (If non GST mention owner age)', ''))
                            new_reg_addr = st.text_area("Registered Address:", value=record.get('Registered Address', ''))
                            new_ops_addr = st.text_area("Address of operations:", value=record.get('Address of operations', ''))
                            
                            o1, o2, o3 = st.columns(3)
                            new_tc = o1.text_input("No. of TCs:", value=record.get('No. of TCs Deploying:', record.get('Number of TCs VL is deploying', '')))
                            new_clients = o2.text_input("Clients Operated On:", value=record.get('Clients Operated On:', record.get('Clients will the VL operate on', '')))
                            new_fts = o3.text_input("Planned FTs:", value=record.get('Planned FTs (M1/M2/M3):', record.get('Planned FTs in M1/M2/M3', '')))
                            
                            r1, r2 = st.columns(2)
                            new_vl_email = r1.text_input("VL Mail ID:", value=record.get('VL Mail ID', ''))
                            new_zm_email = r2.text_input("ZM's Mail ID:", value=record.get("ZM's Mail ID:", record.get("ZM Mail ID", '')))
                            
                            if st.form_submit_button("🔄 Save & Resubmit Request", type="primary", use_container_width=True):
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                try: history = json.loads(record.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "🔄 Ticket Resubmitted", "details": f"Requestor updated details. Generating new document."})
                                
                                # Update Sheet Data
                                worksheet.update_cell(row_index, 2, new_vl_name)
                                worksheet.update_cell(row_index, 3, new_reg_addr)
                                worksheet.update_cell(row_index, 4, new_gst)
                                worksheet.update_cell(row_index, 5, new_pan)
                                worksheet.update_cell(row_index, 6, new_ops_addr)
                                worksheet.update_cell(row_index, 7, new_tc)
                                worksheet.update_cell(row_index, 8, new_business)
                                worksheet.update_cell(row_index, 9, new_age)
                                worksheet.update_cell(row_index, 10, new_vl_email)
                                worksheet.update_cell(row_index, 13, new_tc)
                                worksheet.update_cell(row_index, 14, new_clients)
                                worksheet.update_cell(row_index, 15, new_fts)
                                worksheet.update_cell(row_index, 17, new_zm_email)
                                
                                # Set triggers for Apps Script regeneration
                                worksheet.update_cell(row_index, 11, "") # Clear Doc Link to force new gen
                                worksheet.update_cell(row_index, 19, "Pending Approval") 
                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                
                                st.success("✅ Resubmitted successfully! Document regeneration has started.")
                                st.rerun()
                                
                        st.divider()
                    
                    if "Fully Executed" in status or "Executing" in status:
                        st.success("📜 **Agreement Executed!**")
                        with st.expander("🔍 Click to Expand Final PDF", expanded=True):
                            render_pdf_iframe(preview_link, height=800)
                    elif "http" in doc_link:
                        with st.expander("🔍 Click to Review Draft"):
                            render_pdf_iframe(preview_link, height=600)
                        
                    st.write("")
                    tab1, tab2 = st.tabs(["📝 Detailed Information", "🕒 Activity Timeline"])
                    with tab1:
                        st.write("")
                        render_details_table(record)

                    with tab2:
                        try:
                            history = json.loads(record.get("History Log", "[]"))
                            for event in reversed(history):
                                with st.container(border=True):
                                    st.markdown(f"**{event['title']}**")
                                    st.caption(f"🗓️ {event['time']} — {event['details']}")
                        except: st.info("No timeline data available.")
