import streamlit as st
import gspread
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import datetime
import uuid
import requests
import json
import io
from streamlit_oauth import OAuth2Component

# PDF Processing & Drawing
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

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

def send_email(to_emails, subject, body, pdf_attachment_bytes=None, pdf_filename="Agreement.pdf"):
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
        
        if pdf_attachment_bytes:
            part = MIMEApplication(pdf_attachment_bytes, Name=pdf_filename)
            part['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_emails, msg.as_string())
        return True, "Success"
    except Exception as e:
        return False, str(e)

def get_pdf_link(doc_link):
    doc_link = str(doc_link).strip()
    if "/edit" in doc_link:
        return doc_link.split("/edit")[0] + "/export?format=pdf"
    return doc_link

def create_stamped_pdf(pdf_bytes, vl_sig_text="", saurabh_sig_name="", stamp_bytes=None):
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        num_pages = len(reader.pages)
        
        vl_loc = None      # (page_index, x, y)
        saurabh_loc = None # (page_index, x, y)
        
        for page_idx, page in enumerate(reader.pages):
            def visitor_text(text, cm, tm, font_dict, font_size):
                nonlocal vl_loc, saurabh_loc
                if "[VL Signature]" in text or "[VL" in text:
                    if not vl_loc:
                        vl_loc = (page_idx, tm[4], tm[5])
                        
                if "[Saurabh Dubey" in text or "[Saurabh" in text:
                    if not saurabh_loc:
                        saurabh_loc = (page_idx, tm[4], tm[5])
                        
            page.extract_text(visitor_text=visitor_text)

        # Fallback to last page bottom if placeholders aren't detected
        if not vl_loc:
            vl_loc = (num_pages - 1, 50, 95)
        if not saurabh_loc:
            saurabh_loc = (num_pages - 1, 340, 95)

        pages_to_overlay = {}
        if vl_sig_text and vl_loc:
            p_idx, x, y = vl_loc
            pages_to_overlay.setdefault(p_idx, []).append(('vl', x, y))
        if saurabh_sig_name and saurabh_loc:
            p_idx, x, y = saurabh_loc
            pages_to_overlay.setdefault(p_idx, []).append(('saurabh', x, y))

        for page_idx in range(num_pages):
            page = reader.pages[page_idx]
            if page_idx in pages_to_overlay:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=(width, height))
                
                items = pages_to_overlay[page_idx]
                for item_type, x, y in items:
                    can.setFillColorRGB(1, 1, 1)
                    can.rect(x - 5, y - 5, 230, 50, fill=1, stroke=0)
                    
                    if item_type == 'vl':
                        can.setFont("Helvetica-Bold", 9)
                        can.setFillColorRGB(0.1, 0.1, 0.3)
                        can.drawString(x, y + 25, "DIGITALLY SIGNED BY VL")
                        can.setFont("Helvetica", 8)
                        can.setFillColorRGB(0.2, 0.2, 0.2)
                        can.drawString(x, y + 10, str(vl_sig_text)[:55])
                        can.setStrokeColorRGB(0.2, 0.4, 0.8)
                        can.line(x, y + 5, x + 200, y + 5)
                        
                    elif item_type == 'saurabh':
                        can.setFont("Times-BoldItalic", 15)
                        can.setFillColorRGB(0.0, 0.0, 0.5)
                        can.drawString(x, y + 25, f"Saurabh Dubey ({saurabh_sig_name})")
                        can.setFont("Helvetica-Bold", 8)
                        can.setFillColorRGB(0.2, 0.2, 0.2)
                        can.drawString(x, y + 10, "Authorized Signatory - Vahan")
                        can.setStrokeColorRGB(0.2, 0.4, 0.8)
                        can.line(x, y + 5, x + 200, y + 5)
                        
                        if stamp_bytes:
                            try:
                                img = ImageReader(io.BytesIO(stamp_bytes))
                                can.drawImage(img, x + 120, y - 15, width=75, height=50, mask='auto')
                            except Exception:
                                pass

                can.save()
                packet.seek(0)
                overlay_pdf = PdfReader(packet)
                page.merge_page(overlay_pdf.pages[0])
                
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception as e:
        st.error(f"Error placing signatures at placeholders: {e}")
        return pdf_bytes

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
            
    if (status == "Approved" or status == "Fully Executed") and vl_sig and saurabh_sig:
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
        # Requesters create and track tickets (E-Sign removed for non-signers)
        menu_options = ["📝 Create New Ticket", "🗄️ Ticket Dashboard"]
    else:
        # External VLs ONLY see E-Sign Portal & Dashboard
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

            # ROUTING LOGIC BASED ON STATUS & USER ROLE
            if current_status == "Approved" and (is_saurabh or user_email.lower() == vl_email_on_record):
                # Redirect directly to E-Sign View for this specific ticket!
                st.markdown(f"## ✍️ E-Sign Agreement: `{target_ticket_id}`")
                st.info(f"📄 Review document PDF before signing: [📄 Review PDF Document]({pdf_link})")
                st.divider()

                # --- SAURABH SIGNING ---
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
                                
                                try: history = json.loads(target_row_data.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by Vahan", "details": "Saurabh Dubey applied signature and stamp."})
                                
                                worksheet.update_cell(row_index, 21, sig_log)
                                
                                vl_already_signed = bool(target_row_data.get("VL Signature", "").strip())
                                if vl_already_signed:
                                    worksheet.update_cell(row_index, 19, "Fully Executed")
                                    history.append({"time": current_time, "title": "📜 Fully Executed", "details": "All parties signed. PDF stamped."})
                                    
                                    pdf_res = requests.get(pdf_link, allow_redirects=True)
                                    if pdf_res.status_code == 200:
                                        stamp_bytes = stamp_file.getvalue()
                                        final_pdf_bytes = create_stamped_pdf(pdf_res.content, target_row_data.get("VL Signature", ""), sig_name, stamp_bytes)
                                        email_body = f"<h3>Agreement Fully Executed</h3><p>The agreement for <b>{target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)')}</b> has been signed and stamped. Attached is the final PDF.</p>"
                                        send_email([target_row_data.get("VL Mail ID"), target_row_data.get("Requestor Mail ID"), "nikhil.r@vahan.co"], f"Fully Executed Agreement - {target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)')}", email_body, pdf_attachment_bytes=final_pdf_bytes, pdf_filename=f"Executed_{target_ticket_id}.pdf")
                                    else:
                                        st.warning(f"Signature saved, but could not retrieve PDF (HTTP {pdf_res.status_code}). Ensure Google Doc sharing is set to 'Anyone with link can view'.")

                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Signature & Stamp successfully applied!")
                                st.balloons()
                                st.query_params.clear()
                                st.rerun()

                # --- VL SIGNING ---
                elif user_email.lower() == vl_email_on_record:
                    st.markdown("#### Digital Signature Consent")
                    with st.container(border=True):
                        agree = st.checkbox(f"I, acting on behalf of {target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)')}, have read the agreement and hereby digitally sign it.")
                        if st.button("Submit Digital Signature", type="primary", use_container_width=True):
                            if not agree:
                                st.error("⚠️ You must check the consent box to sign.")
                            else:
                                current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                sig_log = f"Signed by {user_email} on {current_time}"
                                
                                try: history = json.loads(target_row_data.get("History Log", "[]"))
                                except: history = []
                                history.append({"time": current_time, "title": "✍️ Signed by VL", "details": f"Digitally signed by {user_email}."})
                                
                                worksheet.update_cell(row_index, 20, sig_log)
                                
                                saurabh_already_signed = bool(target_row_data.get("Saurabh Signature", "").strip())
                                if saurabh_already_signed:
                                    worksheet.update_cell(row_index, 19, "Fully Executed")
                                    history.append({"time": current_time, "title": "📜 Fully Executed", "details": "All parties signed. PDF stamped."})
                                    
                                    pdf_res = requests.get(pdf_link, allow_redirects=True)
                                    if pdf_res.status_code == 200:
                                        final_pdf_bytes = create_stamped_pdf(pdf_res.content, sig_log, "Saurabh Dubey", None)
                                        email_body = f"<h3>Agreement Fully Executed</h3><p>The agreement for <b>{target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)')}</b> has been signed by all parties. Attached is the final PDF.</p>"
                                        send_email([target_row_data.get("VL Mail ID"), target_row_data.get("Requestor Mail ID"), "nikhil.r@vahan.co"], f"Fully Executed Agreement - {target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)')}", email_body, pdf_attachment_bytes=final_pdf_bytes, pdf_filename=f"Executed_{target_ticket_id}.pdf")
                                    else:
                                        st.warning(f"Signature saved, but could not retrieve PDF (HTTP {pdf_res.status_code}). Ensure Google Doc sharing is set to 'Anyone with link can view'.")

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
                        if current_status == "Fully Executed":
                            st.success(f"🎉 **Agreement Fully Executed:** [📄 Review Signed PDF]({pdf_link})")
                        elif "http" in pdf_link: 
                            st.success(f"📄 **Draft PDF Preview:** [📄 Review PDF Document]({pdf_link})")
                        elif "Rejected" not in current_status: 
                            st.info("🔄 Generating PDF preview link...")
                            
                        c1_inner, c2_inner = st.columns(2)
                        with c1_inner:
                            render_field("Applicant Name", target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)'))
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
                        if "Approved" in current_status or "Executed" in current_status:
                            st.success("🎉 Document is already approved.")
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
                                    worksheet.update_cell(row_index, 18, json.dumps(history))
                                    
                                    vl_name = target_row_data.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                                    vl_email = target_row_data.get("VL Mail ID", "")
                                    
                                    app_url = "https://vahan-agreement-approval-flow-app.streamlit.app"
                                    # EXACT URL WITH TICKET_ID PARAMETER FOR DIRECT REDIRECT
                                    sign_link = f"{app_url}/?ticket_id={target_ticket_id}"
                                    email_body = f"<h3>Document Approved & Ready for Signature</h3><p>The document for <b>{vl_name}</b> has been approved.</p><p><a href='{sign_link}'>Click here to Review and Sign Agreement ({target_ticket_id})</a></p>"
                                    
                                    success, err_msg = send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", vl_email], f"Signature Required - {vl_name}", email_body)
                                    if success:
                                        st.success("Approved! E-Sign links dispatched.")
                                        if url_ticket_id: st.query_params.clear()
                                        else: del st.session_state['approval_ticket_id']
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
                                        if url_ticket_id: st.query_params.clear()
                                        else: del st.session_state['approval_ticket_id']
                                        st.rerun()
                                    else:
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
                    history_log = [{"time": current_time, "title": "📄 Ticket Created", "details": f"Initiated by {user_email}."}]

                    new_row = [
                        current_time, vl_name, registered_address, gst_number, pan_details, 
                        ops_address, tc_count, current_business, vl_age, vl_email, 
                        "", # Col 11: Apps script writes doc link here
                        new_ticket_id, tc_count, clients_operated, 
                        planned_fts, user_email, zm_email, json.dumps(history_log), 
                        "Pending Approval", "", "" 
                    ]
                    
                    try:
                        worksheet.insert_row(new_row, index=2)
                        app_url = "https://vahan-agreement-approval-flow-app.streamlit.app" 
                        approval_link = f"{app_url}/?ticket_id={new_ticket_id}"
                        success, err_msg = send_email(["nikhil.r@vahan.co", "nikhil.r@vahan.co", zm_email], f"New Approval: {vl_name}", f"<h3>New Request: {new_ticket_id}</h3><p><a href='{approval_link}'>Review Request</a></p>")
                        
                        if success:
                            st.success(f"🎉 Ticket **{new_ticket_id}** created successfully!")
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
                _, pdf_link = get_status_and_link(record)
                vl_name = record.get('VL Name (Mention Owner name if Non-GST/NO GST is available)', 'N/A')
                
                st.markdown(f"### Agreement: {selected_id}")
                st.info(f"📄 Review document PDF before signing: [📄 Review PDF Document]({pdf_link})")
                st.divider()
                
                # --- SAURABH SIGNING ---
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
                                    worksheet.update_cell(row_index, 19, "Fully Executed")
                                    history.append({"time": current_time, "title": "📜 Fully Executed", "details": "All parties signed. PDF stamped at placeholders."})
                                    
                                    pdf_res = requests.get(pdf_link, allow_redirects=True)
                                    if pdf_res.status_code == 200:
                                        stamp_bytes = stamp_file.getvalue()
                                        final_pdf_bytes = create_stamped_pdf(pdf_res.content, record.get("VL Signature", ""), sig_name, stamp_bytes)
                                        email_body = f"<h3>Agreement Fully Executed</h3><p>The agreement for <b>{vl_name}</b> has been signed and stamped. Attached is the final executed PDF.</p>"
                                        send_email([record.get("VL Mail ID"), record.get("Requestor Mail ID"), "nikhil.r@vahan.co"], f"Fully Executed Agreement - {vl_name}", email_body, pdf_attachment_bytes=final_pdf_bytes, pdf_filename=f"Executed_{selected_id}.pdf")
                                    else:
                                        st.warning(f"Signature saved, but could not retrieve PDF (HTTP {pdf_res.status_code}). Ensure Google Doc sharing is set to 'Anyone with link can view'.")
                                    
                                worksheet.update_cell(row_index, 18, json.dumps(history))
                                st.success("✅ Signature & Stamp successfully applied!")
                                st.balloons()
                                st.rerun()
                                
                # --- VL SIGNING ---
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
                                    worksheet.update_cell(row_index, 19, "Fully Executed")
                                    history.append({"time": current_time, "title": "📜 Fully Executed", "details": "All parties signed. PDF stamped at placeholders."})
                                    
                                    pdf_res = requests.get(pdf_link, allow_redirects=True)
                                    if pdf_res.status_code == 200:
                                        final_pdf_bytes = create_stamped_pdf(pdf_res.content, sig_log, "Saurabh Dubey", None)
                                        email_body = f"<h3>Agreement Fully Executed</h3><p>The agreement for <b>{vl_name}</b> has been signed by all parties. Attached is the final executed PDF.</p>"
                                        send_email([record.get("VL Mail ID"), record.get("Requestor Mail ID"), "nikhil.r@vahan.co"], f"Fully Executed Agreement - {vl_name}", email_body, pdf_attachment_bytes=final_pdf_bytes, pdf_filename=f"Executed_{selected_id}.pdf")
                                    else:
                                        st.warning(f"Signature saved, but could not retrieve PDF (HTTP {pdf_res.status_code}). Ensure Google Doc sharing is set to 'Anyone with link can view'.")

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
            # Filter strictly to requests where user is Requestor or VL
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
                    
                    if status == "Fully Executed":
                        st.success("📜 **Agreement Fully Executed & Digitally Stamped**")
                        if "http" in pdf_link:
                            pdf_res = requests.get(pdf_link, allow_redirects=True)
                            if pdf_res.status_code == 200:
                                stamped_bytes = create_stamped_pdf(pdf_res.content, record.get("VL Signature", ""), "Saurabh Dubey", None)
                                st.download_button(
                                    label="📥 Download Executed PDF with Signatures & Stamp",
                                    data=stamped_bytes,
                                    file_name=f"Executed_{viewing_ticket_id}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
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
                            if vl_sig: st.success(f"✅ {vl_sig}")
                            else: st.warning("⏳ Pending Signature")
                            
                        with c2:
                            st.markdown("#### Vahan Signature")
                            vahan_sig = record.get("Saurabh Signature", "")
                            if vahan_sig: st.success(f"✅ {vahan_sig}")
                            else: st.warning("⏳ Pending Signature")
