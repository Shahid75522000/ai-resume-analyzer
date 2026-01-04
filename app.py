from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from flask import session
import os
import json
from groq import Groq
from pypdf import PdfReader
import docx
import razorpay
import threading
import time
import csv

import smtplib
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

ADMIN_EMAIL = "admin@resumematch.ai"
ADMIN_PASSWORD = "admin123"

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import session, redirect, url_for

HTML_WELCOME_EMAIL = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {
      font-family: Arial, sans-serif;
      background-color: #f4f6fb;
      padding: 20px;
    }
    .container {
      max-width: 600px;
      background: #ffffff;
      margin: auto;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid #e5e7eb;
    }
    .header {
      background: linear-gradient(90deg, #4f46e5, #3b82f6);
      padding: 20px;
      text-align: center;
      color: white;
    }
    .header h1 {
      margin: 0;
      font-size: 22px;
    }
    .content {
      padding: 25px;
      color: #111827;
      font-size: 15px;
      line-height: 1.6;
    }
    .cta {
      display: inline-block;
      margin-top: 20px;
      padding: 12px 24px;
      background-color: #4f46e5;
      color: white !important;
      text-decoration: none;
      border-radius: 6px;
      font-weight: bold;
    }
    .footer {
      padding: 15px;
      font-size: 12px;
      color: #6b7280;
      text-align: center;
      border-top: 1px solid #e5e7eb;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>ResumeMatch AI</h1>
      <p>ATS Resume Insights for Data & MIS Professionals</p>
    </div>

    <div class="content">
      <p>Hi 👋</p>

      <p>
        Thanks for subscribing to <strong>ResumeMatch AI</strong>.
        You’ll receive practical ATS resume tips, keyword strategies,
        and interview guidance — especially for <strong>Data, MIS & BI roles</strong>.
      </p>

      <p>
        Start improving your resume right away:
      </p>

      <a href="http://localhost:5000" class="cta">
        Analyze Resume Again
      </a>

      <p style="margin-top: 25px;">
        You’re one step closer to getting shortlisted 🚀
      </p>
    </div>

    <div class="footer">
      © ResumeMatch AI • No spam • Unsubscribe anytime
    </div>
  </div>
</body>
</html>
"""

HTML_DAY2_EMAIL = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial; background:#f4f6fb; padding:20px;">
  <div style="max-width:600px;background:#fff;padding:25px;margin:auto;border-radius:8px;">
    <h2>Why ATS Rejects 70% of Resumes ❌</h2>

    <p>Most resumes fail ATS due to:</p>
    <ul>
      <li>Missing JD keywords</li>
      <li>Over-designed formats</li>
      <li>Generic summaries</li>
    </ul>

    <p>Run your resume through an ATS-style check to see where you stand.</p>

    <a href="http://localhost:5000"
       style="display:inline-block;padding:12px 20px;background:#4f46e5;color:#fff;text-decoration:none;border-radius:6px;">
      Check ATS Score
    </a>

    <p style="margin-top:20px;font-size:12px;color:#6b7280;">
      — ResumeMatch AI
    </p>
  </div>
</body>
</html>
"""

HTML_DAY4_EMAIL = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial; background:#f4f6fb; padding:20px;">
  <div style="max-width:600px;background:#fff;padding:25px;margin:auto;border-radius:8px;">
    <h2>Improve Your ATS Score 🚀</h2>

    <p>
      If your ATS score is below 80%, recruiters may never see your resume.
    </p>

    <p>
      Re-run your resume after adding missing keywords and improvements.
    </p>

    <a href="http://localhost:5000"
       style="display:inline-block;padding:12px 20px;background:#4f46e5;color:#fff;text-decoration:none;border-radius:6px;">
      Analyze Resume Again
    </a>

    <p style="margin-top:20px;font-size:12px;color:#6b7280;">
      Resume Audit PDF coming soon 👀
    </p>
  </div>
</body>
</html>
"""

def schedule_followup_emails(email):
    def run():
        # Day 2 email (48 hours)
        time.sleep(48 * 60 * 60)
        send_email(
            to_email=email,
            subject="Why ATS Rejects 70% of Resumes ❌",
            html_body=HTML_DAY2_EMAIL
        )

        # Day 4 email (96 hours total)
        time.sleep(48 * 60 * 60)
        send_email(
            to_email=email,
            subject="Improve Your ATS Score 🚀",
            html_body=HTML_DAY4_EMAIL
        )

    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

def log_event(event, value=None):
    try:
        file_path = "analytics.csv"
        file_exists = os.path.isfile(file_path)

        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Write header only once
            if not file_exists:
                writer.writerow(["timestamp", "event", "value"])

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                event,
                value
            ])

    except PermissionError:
        # IMPORTANT: do NOT crash the app
        print("⚠️ analytics.csv is open elsewhere (Excel). Skipping log.")
    except Exception as e:
        print("⚠️ Analytics logging failed:", e)

def send_email(to_email, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(os.getenv("EMAIL_HOST"), int(os.getenv("EMAIL_PORT"))) as server:
        server.starttls()
        server.login(
            os.getenv("EMAIL_USER"),
            os.getenv("EMAIL_PASS")
        )
        server.send_message(msg)


# Load .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
razorpay_client = razorpay.Client(
    auth=(
        os.getenv("RAZORPAY_KEY_ID"),
        os.getenv("RAZORPAY_KEY_SECRET")
    )
)


# Debug – check key loaded
print("DEBUG GROQ KEY:", bool(os.getenv("GROQ_API_KEY")))

# Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# ---------- ROUTES ----------

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")






@app.route("/extract_text", methods=["POST"])
def extract_text():
    """
    Extract text from uploaded resume file (PDF or DOCX).
    Returns JSON: { "text": "..." }
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = file.filename.lower()

    try:
        if filename.endswith(".pdf"):
            reader = PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        elif filename.endswith(".docx"):
            doc = docx.Document(file)
            text = "\n".join(para.text for para in doc.paragraphs)
        else:
            return jsonify({"error": "Unsupported file type. Upload PDF or DOCX."}), 400

        return jsonify({"text": text}), 200

    except Exception as e:
        print("Error in /extract_text:", e)
        return jsonify({"error": "Failed to read file"}), 500


# ---------- HELPER: CALL GROQ ----------
import re

def clean_text(text):
    return re.sub(r"[^a-zA-Z0-9 ]", " ", text.lower())

def extract_keywords(text, min_len=3):
    words = clean_text(text).split()
    return set(w for w in words if len(w) >= min_len)

def keyword_match_score(resume, jd):
    resume_words = extract_keywords(resume)
    jd_words = extract_keywords(jd)

    if not jd_words:
        return 0

    matched = resume_words.intersection(jd_words)
    return round((len(matched) / len(jd_words)) * 100)

def skill_match_score(missing_skills):
    if not missing_skills:
        return 100
    total = len(missing_skills) + 5  # baseline
    score = max(0, round((1 - len(missing_skills) / total) * 100))
    return score

def resume_structure_score(resume_text):
    sections = [
        "experience", "education", "skills",
        "project", "summary", "certification"
    ]

    text = resume_text.lower()
    found = sum(1 for s in sections if s in text)
    return round((found / len(sections)) * 100)


def analyze_resume_with_jd(resume_text, jd_text, company_name=None):
    """
    Sends resume and JD to Groq and returns structured analysis.
    """

    system_message = """
You are an Applicant Tracking System (ATS) and expert career coach,
specialised in:
- Data Analyst / BI / MIS roles
- Quality, Jewellery & Gold industry roles (QC, operations, MIS)

You will receive:
- Candidate resume text
- Job Description (JD)
- Optionally: target company name.

Your tasks:
1) Compare resume vs JD (ATS-style).
2) Suggest missing skills & keywords.
3) Generate a tailored resume summary.
4) Generate a customised cover letter.
5) Create 5–7 interview questions AND sample answers.
6) Provide a clear, actionable 4–6 step improvement plan for the resume.
7) Rewrite the entire resume in a clean, ATS-friendly format (1–2 pages text).
8) If company name is provided, give specific advice for that company.

Very important:
- Respond ONLY with a single JSON object.
- Do NOT include any explanations or text outside JSON.
- JSON keys MUST be exactly:

  match_score            -> integer 0–100
  missing_skills         -> array of strings
  suggested_keywords     -> array of strings
  resume_summary         -> string
  cover_letter           -> string
  interview_questions    -> array of strings
  interview_qa           -> array of objects { "question": str, "answer": str }
  improvement_plan       -> array of strings
  improved_resume        -> string
  company_fit_notes      -> string
""".strip()

    # Optional company info
    if company_name:
        company_part = f'\nTARGET_COMPANY:\n"""{company_name}"""\n'
    else:
        company_part = ""

    user_message = f"""
RESUME:
\"\"\"{resume_text}\"\"\"

JOB_DESCRIPTION:
\"\"\"{jd_text}\"\"\"
{company_part}
""".strip()

    raw_text = ""
    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )

        # Raw text from model
        content = chat_completion.choices[0].message.content or ""
        raw_text = content.strip()

        # Robust JSON extraction: take text between first '{' and last '}'
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("No JSON object found in model output")

        json_str = raw_text[start:end + 1]
        data = json.loads(json_str)

    except Exception as e:
        print("Error in analyze_resume_with_jd:", e)
        print("RAW MODEL OUTPUT:")
        try:
            print(raw_text)
        except NameError:
            print("(raw_text not available)")

        # Safe fallback JSON so frontend never gets HTML
        data = {
            "match_score": 0,
            "missing_skills": [],
            "suggested_keywords": [],
            "resume_summary": "Model call failed or returned invalid JSON.",
            "cover_letter": "",
            "interview_questions": [],
            "interview_qa": [],
            "improvement_plan": [],
            "improved_resume": "",
            "company_fit_notes": "",
            "raw_output": raw_text,
            "error": "model_error",
        }

    return data


# ---------- /analyze ENDPOINT ----------
@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()

        if not data or "resume_text" not in data or "jd_text" not in data:
            return jsonify({"error": "resume_text and jd_text are required"}), 400

        resume_text = data["resume_text"]
        jd_text = data["jd_text"]
        company_name = data.get("company_name")

        # CREDIT CHECK (backend enforced)
        if not deduct_credit():
            return jsonify({
                "error": "no_credits",
                "message": "Free limit reached. Buy credits to continue.",
                "remaining_credits": get_credits()
            }), 402

        # AI ANALYSIS
        result = analyze_resume_with_jd(resume_text, jd_text, company_name)

        # --- HYBRID ATS SCORING ---
        kw_score = keyword_match_score(resume_text, jd_text)
        skill_score = skill_match_score(result.get("missing_skills", []))
        structure_score = resume_structure_score(resume_text)
        ai_score = result.get("match_score", 0)

        final_score = round(
            (0.4 * kw_score) +
            (0.3 * skill_score) +
            (0.2 * structure_score) +
            (0.1 * ai_score)
        )

        result["match_score"] = final_score
        result["score_breakdown"] = {
            "keyword_match": kw_score,
            "skill_match": skill_score,
            "resume_structure": structure_score,
            "ai_fit": ai_score
        }

        # EXPOSE REMAINING CREDITS
        result["remaining_credits"] = get_credits()

        status_code = 500 if result.get("error") == "model_error" else 200
        log_event("resume_analyzed")
        return jsonify(result), status_code
    

    except Exception as e:
        print("Error in /analyze route:", e)
        return jsonify({"error": "Internal server error"}), 500

# ---------- BLOG ROUTES ----------

# BLOG HOMEPAGE
@app.route("/blog")
def blog_home():
    # Example list – you may already have a better one
    posts = [
        {"slug": "resume-mistakes", "title": "Top 10 Resume Mistakes That Reduce Shortlisting"},
        {"slug": "ats-friendly-resume", "title": "How to Write an ATS-Friendly Resume"},
        {"slug": "job-description-keywords-analyst-mis-bi", "title": "20 Most Common JD Keywords (Analyst + MIS + BI)"},
        # ...add the rest here
    ]
    return render_template("blog/blog_home.html", posts=posts)


# BLOG POST BY SLUG
@app.route("/blog/<slug>")
def blog_post(slug):
    try:
        with open(f"blog_posts/{slug}.html", "r", encoding="utf-8") as f:
            content = f.read()
        return render_template("blog/blog_post.html", content=content)
    except FileNotFoundError:
        return "<h2>Blog post not found</h2>", 404


# SITEMAP
@app.route("/sitemap.xml")
def sitemap():
    blog_slugs = [
        "ats-friendly-resume",
        "resume-mistakes",
        "resume-summary-examples",
        "top-resume-skills",
        "resume-format-2025",
        "tell-me-about-yourself",
        "ats-rejection-reasons",
        "star-interview-answers",
        "resume-vs-cv",
        "best-resume-templates-2026",
        "switch-mis-to-data-analyst",
        "become-data-engineer-guide",
        "why-resume-not-shortlisted",
        "free-resume-tools-2026",
        "job-description-keywords-analyst-mis-bi",
        # add all others you created
    ]
    return render_template("sitemap.xml", blog_slugs=blog_slugs), 200, {
        "Content-Type": "application/xml"
    }

@app.route("/blog/category/resume-tips")
def blog_category_resume_tips():
    # Only posts that belong to this category
    posts = [
        {
            "slug": "resume-mistakes",
            "title": "Top 10 Resume Mistakes That Reduce Shortlisting"
        },
        {
            "slug": "ats-friendly-resume",
            "title": "How to Write an ATS-Friendly Resume (2026 Guide)"
        },
        {
            "slug": "resume-summary-examples",
            "title": "Best Resume Summary Examples (For All Experience Levels)"
        },
        {
            "slug": "top-resume-skills-2026",
            "title": "Top Skills to Add in Your Resume (2026)"
        },
        {
            "slug": "resume-format-guide",
            "title": "Best Resume Format for Freshers & Experienced"
        },
        {
            "slug": "job-description-keywords-analyst-mis-bi",
            "title": "20 Most Common JD Keywords (Analyst + MIS + BI)"
        },
    ]

    # This template should already exist:
    # templates/blog/category/resume-tips/index.html
    return render_template(
        "blog/category/resume-tips/index.html",
        posts=posts
    )


# ROBOTS
@app.route("/robots.txt")
def robots():
    return app.send_static_file("robots.txt")

@app.route("/download-resume-pdf", methods=["POST"])
def download_resume_pdf():
    try:
        data = request.get_json()
        resume_text = data.get("resume_text")

        if not resume_text:
            return jsonify({"error": "Resume text missing"}), 400

        # CREDIT CHECK (paid users only)
        if not deduct_credit():
            return jsonify({
                "error": "no_credits",
                "message": "No credits left to download PDF."
            }), 402

        # Generate clean PDF for paid users
        pdf_buffer = generate_resume_pdf(
            resume_text,
            watermark=False
        )

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name="ATS_Optimized_Resume.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        print("PDF download error:", e)
        return jsonify({"error": "Failed to generate PDF"}), 500




@app.route("/create-order", methods=["POST"])
def create_order():
    try:
        data = request.get_json()
        plan = data.get("plan", "starter")

        # MVP: only starter plan
        amount_map = {
            "starter": 9900  # ₹99 in paise
        }

        credits_map = {
            "starter": 5
        }

        if plan not in amount_map:
            return jsonify({"error": "Invalid plan"}), 400

        order = razorpay_client.order.create({
            "amount": amount_map[plan],
            "currency": "INR",
            "payment_capture": 1
        })

        # Store credits to be added after payment
        session["pending_credits"] = credits_map[plan]

        return jsonify({
            "order_id": order["id"],
            "amount": amount_map[plan],
            "currency": "INR",
            "key": os.getenv("RAZORPAY_KEY_ID")
        })

    except Exception as e:
        print("Create order error:", e)
        return jsonify({"error": "Order creation failed"}), 500
    
    from flask import session, redirect, url_for

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/admin")

        return "Invalid credentials", 401

    return render_template("admin_login.html")


from collections import defaultdict

def get_daily_resume_counts():
    daily = defaultdict(int)

    if not os.path.exists("analytics.csv"):
        return {}

    with open("analytics.csv", "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 2:
                continue

            timestamp, event = parts[0], parts[1]
            if "resume_analyzed" in event:
                date = timestamp.split(" ")[0]  # YYYY-MM-DD
                daily[date] += 1

    return dict(sorted(daily.items()))


@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    try:
        data = request.get_json()

        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": data["razorpay_order_id"],
            "razorpay_payment_id": data["razorpay_payment_id"],
            "razorpay_signature": data["razorpay_signature"]
        })

        # Add credits
        added = session.get("pending_credits", 0)
        session["credits"] = get_credits() + added
        session.pop("pending_credits", None)

        return jsonify({
            "success": True,
            "credits_added": added,
            "total_credits": get_credits()
        })

    except Exception as e:
        print("Payment verification failed:", e)
        return jsonify({"error": "Payment verification failed"}), 400
    

@app.route("/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email required"}), 400

    with open("leads.txt", "a") as f:
        f.write(email + "\n")
        log_event("email_subscribed", email)

    # Day 0 email
    send_email(
        to_email=email,
        subject="Your Free ATS Resume Tips 🚀",
        html_body=HTML_WELCOME_EMAIL
    )

    # ✅ START AUTOMATION
    schedule_followup_emails(email)

    return jsonify({"message": "Subscribed"})

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin-login")


@app.route("/admin")
def admin_dashboard():
    daily_resumes = get_daily_resume_counts()

    if not session.get("admin_logged_in"):
        return redirect("/admin-login")
    # ---- Read analytics.csv ----
    analytics = []
    if os.path.exists("analytics.csv"):
        with open("analytics.csv", "r", encoding="utf-8") as f:
            analytics = f.readlines()

    # ---- Read leads.txt ----
    leads = []
    if os.path.exists("leads.txt"):
        with open("leads.txt", "r", encoding="utf-8") as f:
            leads = f.readlines()

    return render_template(
        "admin.html",
        analytics=analytics,
        leads=leads,
        total_events=len(analytics),
        total_leads=len(leads),
        daily_resumes=daily_resumes
    )



FREE_CREDITS = int(os.getenv("FREE_CREDITS", 3))

def get_credits():
    # Initialize credits on first visit
    if "credits" not in session:
        session["credits"] = FREE_CREDITS
    return session["credits"]

def deduct_credit():
   # if DEV_MODE:
      #  return True  # unlimited credits in dev

    credits = get_credits()
    if credits > 0:
        session["credits"] = credits - 1
        return True
    return False

def generate_resume_pdf(resume_text, watermark=False):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_margin = 40
    y = height - 40

    c.setFont("Helvetica", 10)

    for line in resume_text.split("\n"):
        if y < 40:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 40

        c.drawString(x_margin, y, line)
        y -= 14

    # ---- WATERMARK (optional) ----
    if watermark:
        c.saveState()
        c.setFont("Helvetica", 40)
        c.setFillGray(0.85)
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, "ResumeMatch AI – FREE VERSION")
        c.restoreState()

    # ✅ THIS LINE FIXES THE PDF
    c.showPage()

    c.save()
    buffer.seek(0)
    return buffer


def generate_audit_report_pdf(analysis):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x = 40
    y = height - 40

    def draw_line(text, gap=14):
        nonlocal y
        if y < 40:
            c.showPage()
            y = height - 40
        c.drawString(x, y, text)
        y -= gap

    c.setFont("Helvetica-Bold", 14)
    draw_line("Resume Audit Report", 24)

    c.setFont("Helvetica", 10)
    draw_line(f"ATS Match Score: {analysis.get('match_score', 0)}%")
    draw_line("")

    # Score Breakdown
    c.setFont("Helvetica-Bold", 12)
    draw_line("ATS Score Breakdown", 18)
    c.setFont("Helvetica", 10)

    breakdown = analysis.get("score_breakdown", {})
    for k, v in breakdown.items():
        draw_line(f"- {k.replace('_',' ').title()}: {v}%")

    draw_line("")

    # Missing Skills
    c.setFont("Helvetica-Bold", 12)
    draw_line("Missing Skills", 18)
    c.setFont("Helvetica", 10)
    for skill in analysis.get("missing_skills", []):
        draw_line(f"- {skill}")

    draw_line("")

    # Suggested Keywords
    c.setFont("Helvetica-Bold", 12)
    draw_line("Suggested Keywords", 18)
    c.setFont("Helvetica", 10)
    for kw in analysis.get("suggested_keywords", []):
        draw_line(f"- {kw}")

    draw_line("")

    # Improvement Plan
    c.setFont("Helvetica-Bold", 12)
    draw_line("Action Plan to Improve Resume", 18)
    c.setFont("Helvetica", 10)
    for step in analysis.get("improvement_plan", []):
        draw_line(f"- {step}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# ---------- MAIN ----------

if __name__ == "__main__":
    app.run()
