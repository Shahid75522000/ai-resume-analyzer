from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
import json
from groq import Groq  # 👈 Groq instead of OpenAI

from pypdf import PdfReader        # 👈 add this
import docx    

# Load environment variables
load_dotenv()
print("DEBUG GROQ KEY:", os.getenv("GROQ_API_KEY"))

app = Flask(__name__)

# Initialize Groq client
client = Groq(api_key=os.getenv('key'))


# ---------- Helper: call Groq ----------
def analyze_resume_with_jd(resume_text: str, jd_text: str) -> dict:
    """
    Sends resume and JD to Groq (Llama 3) and gets structured analysis back.
    We ask it to return STRICT JSON.
    """

    system_message = """
You are an Applicant Tracking System (ATS) and expert career coach.
specialised in:
- Data Analyst / BI / MIS roles
Compare the candidate resume with the Job Description.

You MUST respond ONLY with valid JSON.
NO explanations, NO markdown, NO extra text.

JSON format:
{
  "match_score": 0-100,
  "missing_skills": ["skill1", "skill2", ...],
  "suggested_keywords": ["keyword1", "keyword2", ...],
  "resume_summary": "3-4 line optimized professional summary",
  "cover_letter": "short customized cover letter for this JD",
  "interview_questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]
}
""".strip()

    user_message = f"""
RESUME:
\"\"\"{resume_text}\"\"\"

JOB_DESCRIPTION:
\"\"\"{jd_text}\"\"\"
""".strip()

    chat_completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # fast, good quality on Groq :contentReference[oaicite:3]{index=3}
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )

    raw_text = chat_completion.choices[0].message.content.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # fallback if model returns non-perfect JSON
        data = {
            "match_score": 0,
            "missing_skills": [],
            "suggested_keywords": [],
            "resume_summary": "Unable to parse structured output.",
            "cover_letter": "",
            "interview_questions": [],
            "raw_output": raw_text,
        }

    return data

@app.route("/extract_text", methods=["POST"])
def extract_text():
    """
    Extracts text from uploaded resume file (PDF or DOCX).
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
                text += page.extract_text() + "\n"
        elif filename.endswith(".docx"):
            doc = docx.Document(file)
            text = "\n".join([para.text for para in doc.paragraphs])
        else:
            return jsonify({"error": "Unsupported file type. Upload PDF or DOCX."}), 400

        return jsonify({"text": text}), 200

    except Exception as e:
        print("Error extracting text:", e)
        return jsonify({"error": "Failed to read file"}), 500

# ---------- API endpoint ----------
@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Expects JSON:
    {
      "resume_text": "...",
      "jd_text": "..."
    }
    """
    data = request.get_json()

    if not data or "resume_text" not in data or "jd_text" not in data:
        return jsonify({"error": "resume_text and jd_text are required"}), 400

    resume_text = data["resume_text"]
    jd_text = data["jd_text"]

    result = analyze_resume_with_jd(resume_text, jd_text)
    return jsonify(result), 200


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")



if __name__ == "__main__":
    app.run(debug=True)
