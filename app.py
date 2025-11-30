from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
import json
from groq import Groq
from pypdf import PdfReader
import docx

# Load .env
load_dotenv()

app = Flask(__name__)

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
    """
    Expects JSON:
    {
      "resume_text": "...",
      "jd_text": "...",
      "company_name": "TCS" (optional)
    }
    """
    try:
        data = request.get_json()

        if not data or "resume_text" not in data or "jd_text" not in data:
            return jsonify({"error": "resume_text and jd_text are required"}), 400

        resume_text = data["resume_text"]
        jd_text = data["jd_text"]
        company_name = data.get("company_name")

        result = analyze_resume_with_jd(resume_text, jd_text, company_name)
        status_code = 500 if result.get("error") == "model_error" else 200
        return jsonify(result), status_code

    except Exception as e:
        print("Error in /analyze route:", e)
        return jsonify({"error": "Internal server error"}), 500


# ---------- MAIN ----------

if __name__ == "__main__":
    app.run(debug=True)
