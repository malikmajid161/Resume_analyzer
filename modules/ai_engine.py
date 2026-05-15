"""
Module 3 — AI Logic (Groq API Integration)
Uses the groq SDK. Client is lazy-initialized.
"""

import json
import time
import logging
import os
from config import Config

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=Config.GROQ_API_KEY)
    return _client


SYSTEM_PROMPT = (
    "You are an expert ATS analyst and career coach. "
    "Return ONLY a valid JSON object — no markdown fences, no explanations."
)

ANALYSIS_PROMPT_TEMPLATE = """Analyze this resume against the job description. Return ONLY this JSON:

{{
  "ai_match_score": <integer 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "found_skills": ["<skill>"],
  "missing_skills": ["<skill>"],
  "strengths": ["<point>"],
  "weaknesses": ["<point>"],
  "ats_flags": ["<flag>"]
}}

--- RESUME ---
{resume_text}

--- JOB DESCRIPTION ---
{job_description}
"""

INTERVIEW_PROMPT_TEMPLATE = """You are a world-class interviewer from a top-tier tech company (FAANG-level). 
Generate a comprehensive set of 50 to 60 interview questions and detailed expert answers. 

PRIORITY FOCUS (Area of Interest): {interest}
ADDITIONAL FOCUS (Gaps): {missing_skills}

Structure the questions across these areas:
1. TECHNICAL DEEP-DIVE: Intensive questions on the priority and gap areas.
2. SCENARIO-BASED (Behavioral): Situational questions (leadership, conflict, results).
3. STRATEGIC & CULTURE: General high-level industry prep.

Return ONLY this JSON object:
{{
  "questions": [
    {{
      "category": "Technical | Behavioral | Strategic",
      "question": "The specific interview question...",
      "answer": "A detailed, expert-level sample answer or strategy."
    }}
  ]
}}

Return 50 to 60 high-quality questions. Ensure they are DIFFERENT from standard common ones. Return ONLY JSON.
"""


def _call_groq(prompt: str) -> str:
    client = _get_client()
    last_error = None
    for attempt in range(1, Config.MAX_RETRY + 1):
        try:
            response = client.chat.completions.create(
                model=Config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=8000, 
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            logger.warning("Groq attempt %d/%d failed: %s", attempt, Config.MAX_RETRY, e)
            if attempt < Config.MAX_RETRY:
                time.sleep(Config.RETRY_DELAY_SEC)

    raise RuntimeError(f"Groq API failed after {Config.MAX_RETRY} attempts: {last_error}")


def _parse_json(text: str) -> any:
    try:
        # Clean potential markdown fences
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        logger.error("JSON parsing failed: %s\nText: %s", e, text[:200])
        return {}


def _truncate(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[...truncated...]"
    return text


def analyze_resume(resume_text: str, job_description: str) -> dict:
    half = Config.MAX_INPUT_CHARS // 2
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        resume_text=_truncate(resume_text, half),
        job_description=_truncate(job_description, half),
    )
    raw    = _call_groq(prompt)
    result = _parse_json(raw)

    defaults = {
        "ai_match_score": 0, "summary": "Analysis unavailable.",
        "found_skills": [], "missing_skills": [],
        "strengths": [], "weaknesses": [], "ats_flags": [],
    }
    for key, default in defaults.items():
        result.setdefault(key, default)
    return result


def generate_interview_questions(missing_skills: list, interest: str = "General") -> list:
    prompt = INTERVIEW_PROMPT_TEMPLATE.format(
        missing_skills=", ".join(missing_skills) if missing_skills else "Industry standards",
        interest=interest
    )
    raw    = _call_groq(prompt)
    result = _parse_json(raw)
    
    if isinstance(result, dict) and "questions" in result:
        return result["questions"]
    return result if isinstance(result, list) else []


OPTIMIZE_PROMPT_TEMPLATE = """Based on the analysis, provide specific, professional suggestions to improve this resume for this job. Return ONLY this JSON:
{{
  "professional_summary": "<rewritten professional summary incorporating target keywords>",
  "targeted_improvements": [
    {{"section": "<e.g. Experience, Skills>", "suggestion": "<detailed professional advice>"}}
  ],
  "keyword_injection": ["<list of 5-7 high-impact keywords to add>"]
}}

--- ANALYSIS SUMMARY ---
{summary}

--- MISSING SKILLS ---
{missing_skills}
"""

def generate_resume_optimizations(summary: str, missing_skills: list) -> dict:
    prompt = OPTIMIZE_PROMPT_TEMPLATE.format(
        summary=summary,
        missing_skills=", ".join(missing_skills)
    )
    raw    = _call_groq(prompt)
    result = _parse_json(raw)
    return result if isinstance(result, dict) else {}
