import streamlit as st
import openai
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import date
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
def check_password():
    password = st.text_input("Enter password:", type="password")
    if password == "Aa654?654?":
        return True
    else:
        if password:
            st.error("Wrong password!")
        return False

if not check_password():
    st.stop()
# ---------- googlesearch compatibility ----------
try:
    from googlesearch import search as google_search
except ImportError:
    try:
        from googlesearch import search as google_search
    except ImportError:
        google_search = None

# ---------- utils ----------
PERSISTENT_FILE = "counter_state.txt"

def load_counter():
    today = str(date.today())
    if os.path.exists(PERSISTENT_FILE):
        with open(PERSISTENT_FILE, "r") as f:
            data = f.read().strip().split(",")
        if len(data) == 2 and data[0] == today:
            return int(data[1])
    return 0

def save_counter(count):
    with open(PERSISTENT_FILE, "w") as f:
        f.write(f"{date.today()},{count}")

def extract_emails_from_url(url, headers, timeout=5):
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(resp.text, "html.parser")
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = set(re.findall(pattern, soup.text))
        if not emails:
            contact_keywords = ["kontakt", "impressum", "karriere", "bewerbung", "jobs"]
            for a in soup.find_all("a", href=True):
                href_lower = a["href"].lower()
                if any(k in href_lower for k in contact_keywords):
                    if a["href"].startswith("http"):
                        contact_url = a["href"]
                    else:
                        base = "/".join(url.split("/")[:3])
                        contact_url = base + "/" + a["href"].lstrip("/")
                    resp2 = requests.get(contact_url, headers=headers, timeout=timeout)
                    emails.update(re.findall(pattern, resp2.text))
                    if emails:
                        break
        valid = [e for e in emails if not e.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".css"))]
        return valid[0] if valid else None
    except Exception:
        return None

def generate_cover_letter(client, cv_text, job_title):
    prompt = (
        f"Write a professional German cover letter (Anschreiben) for an Ausbildung "
        f"position as '{job_title}'. CV details: {cv_text}. Use formal, professional German only."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as e:
        st.error(f"OpenAI error: {e}")
        return None

def send_email(sender, password, to_email, subject, body, attachment_file):
    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        payload = MIMEBase("application", "octet-stream")
        payload.set_payload(attachment_file.getvalue())
        encoders.encode_base64(payload)
        payload.add_header("Content-Disposition", f"attachment; filename={attachment_file.name}")
        msg.attach(payload)
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        st.error("Gmail rejected login. Use an App Password (not your regular password).")
        return False
    except smtplib.SMTPRecipientsRefused:
        st.error(f"Recipient {to_email} was refused.")
        return False
    except Exception as e:
        st.error(f"Email error: {e}")
        return False

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Ausbildung Auto-Applier v5", layout="centered")
st.title("Ausbildung Auto-Applier v5")

# ── initialise persistent counter ──
if "daily_counter" not in st.session_state:
    st.session_state.daily_counter = load_counter()

# ── sidebar ──
st.sidebar.header("Configuration")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password")
email_sender = st.sidebar.text_input("Your Gmail address")
email_password = st.sidebar.text_input("Gmail App Password", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("Daily Tracker")
st.sidebar.metric("Emails sent today", f"{st.session_state.daily_counter} / 30")

reset_col, clear_col = st.sidebar.columns(2)
with reset_col:
    if st.button("Reset counter (new day)"):
        st.session_state.daily_counter = 0
        save_counter(0)
        st.rerun()
with clear_col:
    if st.button("Clear .txt state"):
        if os.path.exists(PERSISTENT_FILE):
            os.remove(PERSISTENT_FILE)
        st.rerun()

# ── main inputs ──
cv_file = st.file_uploader("Upload your CV (PDF or TXT)", type=["pdf", "txt"])
profession = st.text_input("Ausbildung name (e.g. Fachinformatiker, Pflegefachkraft)")
city = st.text_input("City (empty = all Germany)")
max_results = st.slider("Max companies to search (1-30)", 1, 30, 10)

# ── run ──
if st.button("Start search"):
    errors = []
    if not openai_api_key:
        errors.append("OpenAI API Key is missing")
    if not email_sender or not email_password:
        errors.append("Gmail credentials are missing")
    if not cv_file or not profession:
        errors.append("CV file and profession are required")
    if google_search is None:
        errors.append("googlesearch library not installed — run: pip install googlesearch-python")

    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    if st.session_state.daily_counter >= 30:
        st.error("Daily limit (30) reached. Reset the counter or wait until tomorrow.")
        st.stop()
# هنا السيستم كيقرا النص من الـ CV بذكاء (PDF أو TXT)
        cv_text = ""
        if cv_file.name.lower().endswith('.pdf'):
            import pypdf
            reader = pypdf.PdfReader(cv_file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    cv_text += page_text + "\n"
        else:
            cv_text = cv_file.read().decode('utf-8')
    client = OpenAI(api_key=openai_api_key)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # Build search query
    query_parts = [f'Ausbildung {profession} "Ausbildungsplatz" site:.de']
    if city:
        query_parts.insert(0, city)
    query = " ".join(query_parts)

    st.info(f"Searching Google for: `{query}`")
    try:
        links = list(google_search(query, num_results=max_results))
    except TypeError:
        # fallback for 'google' (pip install google) API
        try:
            links = list(google_search(query, stop=max_results))
        except Exception as e2:
            st.error(f"Google search failed: {e2}")
            st.stop()
    except Exception as e:
        st.error(f"Google search error: {e}")
        st.stop()

    if not links:
        st.warning("No results found. Try a broader query.")
        st.stop()

    total_sent = 0
    processed_urls = 0

    for idx, link in enumerate(links):
        if st.session_state.daily_counter >= 30:
            st.warning("Daily limit reached — stopping.")
            break

        st.markdown(f"### #{idx + 1}: {link}")
        processed_urls += 1

        email = extract_emails_from_url(link, headers)
        if not email:
            st.write("No email found, skipping.")
            st.markdown("---")
            time.sleep(1)
            continue

        st.success(f"Found: `{email}`")

        with st.spinner("Generating cover letter with AI…"):
            cover_letter = generate_cover_letter(client, cv_file.read().decode("utf-8"), profession)
            if cover_letter is None:
                st.error("Skipping — AI generation failed.")
                st.markdown("---")
                continue

        with st.expander("Preview Anschreiben"):
            st.text_area("Cover letter", cover_letter, height=200, key=f"cl_{idx}")

        col1, col2 = st.columns([1, 3])
        send_clicked = col1.button(f"Send to {email}", key=f"btn_{idx}")
        col2.write("")  # spacer

        if send_clicked:
            if st.session_state.daily_counter >= 30:
                st.error("Limit reached.")
                continue

            subject = f"Bewerbung um einen Ausbildungsplatz als {profession}"
            ok = send_email(email_sender, email_password, email, subject, cover_letter, cv_file)
            if ok:
                st.session_state.daily_counter += 1
                save_counter(st.session_state.daily_counter)
                total_sent += 1
                st.success(f"Sent! Total today: {st.session_state.daily_counter}/30")
            else:
                st.error("Failed to send.")

        time.sleep(1.5)  # polite delay
        st.markdown("---")

    st.info(f"Done. Processed {processed_urls} URLs, sent {total_sent} new emails.")
