"""
Resume Analyzer — Flask Application
All routes wired together.
"""

import os
import uuid
import logging
import json
from flask import (
    Flask, request, render_template, redirect, url_for,
    session, jsonify, send_file, send_from_directory, flash
)
from config import Config
from modules.parser   import safe_save, extract_text
from modules.ai_engine import analyze_resume, generate_interview_questions
from modules.scorer   import keyword_match_score, run_ats_checks, compute_final_score
from modules.report   import generate_pdf_report

# ──────────────────────────────────────────────
#  App Setup
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
app.config["UPLOAD_FOLDER"]      = Config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


# ──────────────────────────────────────────────
#  Route 1 — Upload Form  (GET /)
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────
#  Route 2 — Analyze  (POST /analyze)
# ──────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():
    # ── 1. Grab inputs ──────────────────────────
    files = request.files.getlist("resume")
    jd    = request.form.get("job_description", "").strip()

    if not files or not files[0] or not jd:
        flash("Please upload at least one resume AND paste a job description.", "error")
        return redirect(url_for("index"))

    batch_results = []

    for file in files:
        if not file:
            continue
            
        # ── 2. Save & parse ─────────────────────────
        try:
            filepath, _ = safe_save(file)
            resume_text = extract_text(filepath)
        except ValueError as e:
            logger.error("File processing error for %s: %s", file.filename, e)
            continue

        # ── 3. AI Analysis ──────────────────────────
        try:
            analysis = analyze_resume(resume_text, jd)
        except RuntimeError as e:
            logger.error("Groq API error for %s: %s", file.filename, e)
            continue

        # ── 4. Scoring ──────────────────────────────
        kw_score, kw_matched, kw_total = keyword_match_score(resume_text, jd)
        ats_checks = run_ats_checks(resume_text)
        scoring    = compute_final_score(analysis["ai_match_score"], kw_score, ats_checks=ats_checks)

        batch_results.append({
            "filename": file.filename,
            "analysis": analysis,
            "scoring": scoring,
            "ats_checks": ats_checks,
            "kw_matched": kw_matched,
            "kw_total": kw_total
        })

    if not batch_results:
        flash("Failed to analyze any of the uploaded resumes.", "error")
        return redirect(url_for("index"))

    # Sort results by score (descending)
    batch_results.sort(key=lambda x: x["scoring"]["final_score"], reverse=True)

    # ── 5. Persist to session ───────────────────
    session["batch_results"] = batch_results
    # For backward compatibility with results route if needed, 
    # but we'll update results to handle the list
    session["analysis"]   = batch_results[0]["analysis"]
    session["scoring"]    = batch_results[0]["scoring"]
    session["ats_checks"] = batch_results[0]["ats_checks"]
    session["kw_matched"] = batch_results[0]["kw_matched"]
    session["kw_total"]   = batch_results[0]["kw_total"]

    return redirect(url_for("results"))


# ──────────────────────────────────────────────
#  Route 3 — Results Dashboard  (GET /results)
# ──────────────────────────────────────────────

@app.route("/results")
def results():
    batch_results = session.get("batch_results")
    
    if not batch_results:
        flash("No analysis found. Please upload a resume first.", "error")
        return redirect(url_for("index"))

    # If user wants a specific resume detail
    resume_index = request.args.get("idx", type=int)
    if resume_index is not None and 0 <= resume_index < len(batch_results):
        current = batch_results[resume_index]
    else:
        current = batch_results[0]
        resume_index = 0

    # SYNC SESSION: Update the active resume data so that Report, Interview, 
    # Voice, and Optimize features work for the *currently viewed* resume.
    session["analysis"]   = current["analysis"]
    session["scoring"]    = current["scoring"]
    session["ats_checks"] = current["ats_checks"]
    session["kw_matched"] = current["kw_matched"]
    session["kw_total"]   = current["kw_total"]

    return render_template(
        "results.html",
        batch_results=batch_results,
        current_idx=resume_index,
        analysis=current["analysis"],
        scoring=current["scoring"],
        ats_checks=current["ats_checks"],
        kw_matched=current["kw_matched"],
        kw_total=current["kw_total"],
    )


@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory("/tmp", filename)

# ──────────────────────────────────────────────
#  Route — Resume Builder (GET /builder)
# ──────────────────────────────────────────────

@app.route("/builder")
def builder():
    return render_template("builder.html")

@app.route("/builder/download", methods=["POST"])
def builder_download():
    data = request.json
    from modules.builder_report import generate_resume_pdf
    pdf_bytes = generate_resume_pdf(data)
    
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{data.get('fullName', 'Resume')}.pdf"
    )

# ──────────────────────────────────────────────
#  Route 4 — Interview Questions  (GET /interview)
# ──────────────────────────────────────────────

@app.route("/interview")
def interview():
    analysis = session.get("analysis")
    if not analysis:
        flash("Please analyze a resume first.", "error")
        return redirect(url_for("index"))

    # Get interest from query param, default to 'General'
    interest = request.args.get("interest", "General Prep")
    missing_skills = analysis.get("missing_skills", [])

    try:
        from modules.ai_engine import generate_interview_questions
        questions = generate_interview_questions(missing_skills, interest=interest)
    except Exception as e:
        logger.error("Interview generation failed: %s", e)
        flash("Could not generate interview questions. Please try again.", "error")
        return redirect(url_for("results"))

    return render_template("interview.html", questions=questions, current_interest=interest)


# ──────────────────────────────────────────────
#  Route 5 — Resume Optimization  (GET /optimize)
# ──────────────────────────────────────────────

@app.route("/optimize")
def optimize():
    analysis = session.get("analysis")
    if not analysis:
        flash("Please analyze a resume first.", "error")
        return redirect(url_for("index"))

    summary = analysis.get("summary", "")
    missing = analysis.get("missing_skills", [])

    try:
        from modules.ai_engine import generate_resume_optimizations
        tips = generate_resume_optimizations(summary, missing)
    except Exception as e:
        logger.error("Optimization failed: %s", e)
        flash("Could not generate optimization tips.", "error")
        return redirect(url_for("results"))

    return render_template("optimize.html", tips=tips)


# ──────────────────────────────────────────────
#  Route 6 — Voice Feedback  (GET /voice)
# ──────────────────────────────────────────────

@app.route("/voice")
def voice():
    analysis = session.get("analysis")
    scoring  = session.get("scoring")

    if not analysis:
        return jsonify({"error": "No analysis in session."}), 400

    score   = scoring["final_score"]
    grade   = scoring["grade"]
    summary = analysis.get("summary", "")
    found   = ", ".join(analysis.get("found_skills",   [])[:5]) or "none"
    missing = ", ".join(analysis.get("missing_skills", [])[:5]) or "none"

    speech_text = (
        f"Analysis complete. Your match score is {score} percent, a {grade} match. "
        f"{summary} "
        f"Focus on highlighting {found}, and consider developing {missing}. "
        f"Check the Optimizer for more tips. Good luck!"
    )

    try:
        from gtts import gTTS
        import time
        import glob
        
        audio_dir  = "/tmp"
        # os.makedirs(audio_dir, exist_ok=True)
        
        # Cleanup old files (older than 10 mins) to save space
        current_time = time.time()
        for f in glob.glob(os.path.join(audio_dir, "feedback_*.mp3")):
            if os.path.getmtime(f) < current_time - 600:
                try: os.remove(f)
                except: pass

        audio_file = f"feedback_{int(current_time)}.mp3"
        audio_path = os.path.join(audio_dir, audio_file)

        tts = gTTS(text=speech_text, lang="en", slow=False)
        tts.save(audio_path)
        
        if os.path.exists(audio_path):
            return jsonify({"audio_url": url_for("serve_audio", filename=audio_file)})
        else:
            raise Exception("File was not saved.")

    except Exception as e:
        logger.error("gTTS error: %s", e)
        return jsonify({"error": "Voice generation failed. Please ensure you have an active internet connection and try again."}), 500


# ──────────────────────────────────────────────
#  Route 6 — PDF Report Download  (GET /report)
# ──────────────────────────────────────────────

@app.route("/report")
def report():
    analysis   = session.get("analysis")
    scoring    = session.get("scoring")
    ats_checks = session.get("ats_checks")

    if not analysis:
        flash("No analysis found. Please upload a resume first.", "error")
        return redirect(url_for("index"))

    try:
        import io
        pdf_bytes = generate_pdf_report(analysis, scoring, ats_checks)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="resume_analysis_report.pdf",
        )
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        flash("Could not generate the PDF report.", "error")
        return redirect(url_for("results"))


# ──────────────────────────────────────────────
#  Error Handlers
# ──────────────────────────────────────────────

@app.errorhandler(413)
def file_too_large(e):
    flash(f"File too large. Maximum size is {Config.MAX_FILE_SIZE_MB} MB.", "error")
    return redirect(url_for("index"))

@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error")
    return render_template("index.html"), 500


# ──────────────────────────────────────────────
#  Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
