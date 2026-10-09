"""Daily system design lesson: asks an LLM (via OpenRouter) for the next concept and emails it.

Nothing is hardcoded: each day the model is told which day of the 4-month (120-day) plan it is,
which level that day falls in, and every topic already covered, and it picks the next topic
itself. Days 1-30 Easy, 31-60 Medium, 61-90 Hard, 91-120 big-company architecture breakdowns
(Netflix, Amazon, Instagram, Paytm, PhonePe...). Every lesson includes a hands-on lab.

Usage:
    python system_design_bot.py            # generate today's lesson and email it
    python system_design_bot.py --dry-run  # generate, save lesson_preview.html, don't email or save progress

Environment variables:
    OPENROUTER_API_KEY  OpenRouter API key (required)
    OPENROUTER_MODEL    Optional, defaults to anthropic/claude-sonnet-5.5
    EMAIL_ADDRESS       Gmail address that sends the lesson (required unless --dry-run)
    EMAIL_APP_PASSWORD  Gmail app password (required unless --dry-run)
    EMAIL_TO            Recipient(s), comma separated (optional, defaults to EMAIL_ADDRESS)
"""

import argparse
import html
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import markdown
import requests

HERE = Path(__file__).parent
PROGRESS_FILE = HERE / "system_design_progress.json"
PREVIEW_FILE = HERE / "lesson_preview.html"
IST = timezone(timedelta(hours=5, minutes=30))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
TOTAL_DAYS = 120  # 4 months

# The plan's levels. These describe difficulty and format only; there is no topic list.
# Each day the model picks the concept itself, based on the level and what's been covered.
STAGES = [
    (1, 30, "Easy", "concept",
     "Beginner-to-intermediate system design. Pick the fundamental concepts a system designer must "
     "know cold before anything else, ordered so each builds on the previous ones. Explain from "
     "first principles at the depth a senior engineer expects. Labs are small and run on a laptop."),
    (31, 60, "Medium", "concept",
     "Intermediate system design. Concepts that come up in most real designs and interviews, where "
     "the challenge is choosing between options and understanding their trade-offs under load. "
     "Labs combine two or three components (for example with Docker Compose) and measure behaviour."),
    (61, 90, "Hard", "concept",
     "Advanced distributed systems and large-scale design. Concepts behind correctness, consistency, "
     "failure handling and global scale, plus complete end-to-end designs of the kind asked in "
     "senior/staff interviews. Labs simulate failures, concurrency and scale, not just happy paths."),
    (91, 120, "Big Tech Architecture Breakdowns", "company",
     "Each day, break down how one real company built one part of its system, using what that "
     "company has published (engineering blogs, conference talks, papers). Cover both global "
     "companies (for example Netflix, Amazon, Instagram, Uber, WhatsApp, Google, Discord) and Indian "
     "ones (for example Paytm, PhonePe, Flipkart, Swiggy, Zomato, Razorpay, Hotstar, UPI/NPCI). "
     "Alternate between global and Indian companies, choose a different company or a different "
     "part of a company each day, and connect every decision to concepts from earlier stages."),
]
AFTER_PLAN = ("Mastery & Revision", "company",
              "The 4-month plan is complete. Alternate between more company architecture breakdowns "
              "and mock interview problems that combine several earlier concepts. Stay at expert level.")


def stage_for(day):
    for start, end, name, kind, guide in STAGES:
        if start <= day <= end:
            return name, kind, guide
    return AFTER_PLAN


# ---------- progress ----------

def load_progress():
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_progress(progress, day, topic):
    progress.append({"day": day, "date": datetime.now(IST).strftime("%Y-%m-%d"), "topic": topic})
    PROGRESS_FILE.write_text(json.dumps(progress, indent=1), encoding="utf-8")


# ---------- lesson generation ----------

CONCEPT_SECTIONS = """## Why it matters
## Core idea
(clear explanation; include an ASCII diagram in a code block)
## How it works in practice
(mechanics, key numbers, variants)
## Trade-offs and pitfalls
(a table is welcome)
## Real-world example
(a specific company or open-source system and what they actually do)
## Hands-on lab
(a real, runnable exercise taking 45-90 minutes: prerequisites, step-by-step commands, complete
code (Python, Go or Java, plus Docker/Docker Compose where useful), what to observe or measure,
and the expected result. It must actually demonstrate the concept, e.g. break something and watch
the system react. End with one stretch goal.)
## Interview angle
(how this comes up in a system design interview, what a strong answer includes, 2-3 likely follow-up questions)
## Key takeaways
(3-5 bullets)"""

COMPANY_SECTIONS = """## The problem they faced
(scale numbers, business constraints, what broke)
## Architecture overview
(an ASCII diagram in a code block of the main components and data flow)
## Key design decisions
(each decision, the alternatives they rejected, and why; link each to an earlier concept)
## Data and storage
(databases, data models, partitioning, caching)
## Handling scale and failure
(traffic peaks, outages, consistency choices)
## What changed over time
(how the architecture evolved and what they learned)
## Hands-on lab: build a mini version
(a real, runnable 60-120 minute exercise that rebuilds the most interesting piece at small scale:
step-by-step commands and complete code (Python, Go or Java, plus Docker Compose), what to
observe, and a stretch goal)
## If you were asked to design this in an interview
(how to structure the answer and 2-3 likely follow-up questions)
## Key takeaways
(3-5 bullets)"""


def build_prompt(day, progress):
    stage, kind, guide = stage_for(day)
    covered = "\n".join(f"- Day {p['day']}: {p['topic']}" for p in progress) or "(none yet, this is day 1)"
    if kind == "company":
        task = ("Choose today's company and the specific part of its architecture to break down. "
                "Only state facts the company has published; if you are inferring something, say so. "
                "Use a topic title like \"<Company>: <what is being broken down>\".")
        sections = COMPANY_SECTIONS
    else:
        task = ("Choose the single best next concept for today. It must fit the current level, follow "
                "logically from what has been covered, and be slightly harder than recent days. Do not "
                "jump ahead to a later level.")
        sections = CONCEPT_SECTIONS
    return f"""You are a staff engineer mentoring a senior software developer who wants an overall grip on system design in 4 months ({TOTAL_DAYS} days), one lesson per day: strong enough to pass senior/staff interviews and design real systems at work, with real hands-on experience, not just theory.

The plan: days 1-30 Easy, 31-60 Medium, 61-90 Hard, 91-120 breakdowns of real big-company architectures.
Today is day {day} of {TOTAL_DAYS}. Current level: {stage}.
Level guidance: {guide}

Topics already covered (do not repeat them; you may build on them):
{covered}

{task}

Then write today's lesson in Markdown, about 1500-2200 words including code, with these sections:
{sections}

Write the first line exactly as:
TOPIC: <short topic title>
then a blank line, then the Markdown lesson. Do not add anything before the TOPIC line."""


def generate_lesson(day, progress):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY must be set.")
    model = os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(day, progress)}],
        "max_tokens": 10000,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "Daily System Design",
    }

    last_error = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=300)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            text = resp.json()["choices"][0]["message"]["content"] or ""
            match = re.search(r"^\s*\**TOPIC:\**\s*(.+)$", text, re.MULTILINE)
            if not match:
                raise RuntimeError("response had no TOPIC line")
            topic = match.group(1).strip().strip("*").strip()
            body = text[match.end():].strip()
            if len(body) < 500:
                raise RuntimeError("lesson was too short")
            return topic, body, model
        except Exception as exc:  # network errors, API errors, malformed responses
            last_error = exc
            print(f"Attempt {attempt} failed: {exc}")
            time.sleep(10 * attempt)
    sys.exit(f"Could not generate lesson: {last_error}")


# ---------- rendering ----------

def render(day, topic, lesson_md, model):
    stage = stage_for(day)[0]
    today = datetime.now(IST).strftime("%A, %d %B %Y")
    progress_pct = min(100, round(day / TOTAL_DAYS * 100))
    day_label = f"Day {day} of {TOTAL_DAYS}" if day <= TOTAL_DAYS else f"Day {day} (bonus)"
    body = markdown.markdown(lesson_md, extensions=["fenced_code", "tables"])

    # Gmail ignores <style> blocks in many cases, so add inline styles.
    styles = {
        "<h2>": '<h2 style="font-size:18px;color:#1f2328;border-bottom:1px solid #d0d7de;padding-bottom:4px;margin:26px 0 10px;">',
        "<h3>": '<h3 style="font-size:16px;margin:18px 0 8px;">',
        "<p>": '<p style="font-size:15px;line-height:1.6;margin:0 0 12px;">',
        "<li>": '<li style="font-size:15px;line-height:1.6;margin-bottom:4px;">',
        "<pre>": '<pre style="background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:12px;overflow-x:auto;font-size:13px;line-height:1.4;">',
        "<code>": '<code style="font-family:Consolas,Menlo,monospace;background:#f6f8fa;padding:1px 4px;border-radius:4px;">',
        "<table>": '<table style="border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 14px;">',
        "<th>": '<th style="border:1px solid #d0d7de;background:#f6f8fa;padding:6px 8px;text-align:left;">',
        "<td>": '<td style="border:1px solid #d0d7de;padding:6px 8px;vertical-align:top;">',
        "<blockquote>": '<blockquote style="border-left:4px solid #d0d7de;margin:0 0 12px;padding:4px 12px;color:#57606a;">',
    }
    for tag, styled in styles.items():
        body = body.replace(tag, styled)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>System Design Daily</title></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2328;">
<div style="max-width:700px;margin:0 auto;padding:24px 16px;">
<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#3b6fd8;font-weight:600;">System Design Daily · {html.escape(day_label)} · {html.escape(stage)}</div>
<h1 style="margin:6px 0 4px;font-size:24px;">{html.escape(topic)}</h1>
<div style="color:#656d76;font-size:14px;margin-bottom:12px;">{today}</div>
<div style="background:#d0d7de;border-radius:4px;height:8px;margin-bottom:22px;"><div style="background:#3b6fd8;border-radius:4px;height:8px;width:{progress_pct}%;"></div></div>
<div style="background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:8px 20px 14px;">
{body}
</div>
<p style="font-size:12px;color:#8c959f;margin-top:24px;">Generated by {html.escape(model)} via OpenRouter. Sent by your System Design Daily bot.</p>
</div></body></html>"""


# ---------- email ----------

def send_email(html_body, subject):
    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    if not sender or not password:
        sys.exit("EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be set (or use --dry-run).")
    recipients = [r.strip() for r in (os.environ.get("EMAIL_TO") or sender).split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText("Your email client doesn't support HTML. Open the lesson in a browser.", "plain"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password.replace(" ", ""))
        smtp.sendmail(sender, recipients, msg.as_string())
    print(f"Email sent to {', '.join(recipients)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="save lesson_preview.html instead of emailing")
    args = parser.parse_args()

    progress = load_progress()
    day = len(progress) + 1
    print(f"Generating lesson for day {day} ({stage_for(day)[0]})")
    topic, lesson_md, model = generate_lesson(day, progress)
    print(f"Topic: {topic}")

    body = render(day, topic, lesson_md, model)
    subject = f"System Design Day {day}: {topic}"

    if args.dry_run:
        PREVIEW_FILE.write_text(body, encoding="utf-8")
        print(f"Dry run: saved {PREVIEW_FILE.name}")
        return
    send_email(body, subject)
    save_progress(progress, day, topic)


if __name__ == "__main__":
    main()
