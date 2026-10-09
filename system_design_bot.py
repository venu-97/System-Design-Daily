"""Daily system design lesson: emails the next topic from curriculum.py, written up by an LLM.

Topics come from the fixed 120-day list in curriculum.py (Easy, Medium, Hard, then big-tech
architecture breakdowns), one per day, in order. The model (via OpenRouter) writes the full
lesson for that day's topic. If the API key is missing or the call fails (for example, out of
credits), the email still goes out with the topic, what to cover and the hands-on lab.

Usage:
    python system_design_bot.py            # build today's lesson and email it
    python system_design_bot.py --dry-run  # build, save lesson_preview.html, don't email or save progress

Environment variables:
    OPENROUTER_API_KEY  Optional. Without it, emails contain the topic outline only.
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

from curriculum import CURRICULUM, LEVELS

HERE = Path(__file__).parent
PROGRESS_FILE = HERE / "system_design_progress.json"
PREVIEW_FILE = HERE / "lesson_preview.html"
IST = timezone(timedelta(hours=5, minutes=30))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
TOTAL_DAYS = len(CURRICULUM)


def topic_for(day):
    """Return (title, cover, lab, level). After the last day, the list repeats as revision."""
    index = (day - 1) % TOTAL_DAYS
    title, cover, lab = CURRICULUM[index]
    level = next((name for start, end, name in LEVELS if start <= index + 1 <= end), "")
    if day > TOTAL_DAYS:
        level = f"Revision · {level}"
    return title, cover, lab, level


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
and the expected result. It must actually demonstrate the concept. End with one stretch goal.)
## Interview angle
(how this comes up in a system design interview, what a strong answer includes, 2-3 likely follow-up questions)
## Key takeaways
(3-5 bullets)"""

COMPANY_SECTIONS = """## The problem they faced
(scale numbers, business constraints, what broke)
## Architecture overview
(an ASCII diagram in a code block of the main components and data flow)
## Key design decisions
(each decision, the alternatives they rejected, and why; link each to a system design concept)
## Data and storage
(databases, data models, partitioning, caching)
## Handling scale and failure
(traffic peaks, outages, consistency choices)
## What changed over time
(how the architecture evolved and what they learned)
## Hands-on lab: build a mini version
(a real, runnable 60-120 minute exercise: step-by-step commands and complete code (Python, Go or
Java, plus Docker Compose), what to observe, and a stretch goal)
## If you were asked to design this in an interview
(how to structure the answer and 2-3 likely follow-up questions)
## Key takeaways
(3-5 bullets)"""


def build_prompt(day):
    title, cover, lab, level = topic_for(day)
    is_company = "Big Tech" in level
    sections = COMPANY_SECTIONS if is_company else CONCEPT_SECTIONS
    accuracy = ("Only state facts the company has published (engineering blogs, talks, papers); "
                "if you are inferring something, say so.\n\n") if is_company else ""
    return f"""You are a staff engineer mentoring a senior software developer who is getting an overall grip on system design in 4 months, one lesson per day, with real hands-on practice. They want to pass senior/staff interviews and design real systems at work.

Today is day {day}. Level: {level}.
Today's topic: {title}
Cover: {cover}
Hands-on lab idea (improve on it if useful): {lab}

{accuracy}Write today's lesson in Markdown, about 1500-2200 words including code, with these sections:
{sections}

Start directly with the first section heading. Do not repeat the topic title."""


def generate_lesson(day):
    """Return (lesson_markdown, model), or (None, reason) if the AI lesson isn't available."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None, "OPENROUTER_API_KEY is not set"
    model = os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(day)}],
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
            if resp.status_code in (401, 402, 403):
                # Bad key or out of credits: retrying won't help.
                msg = f"OpenRouter refused the request (HTTP {resp.status_code}): {resp.text[:300]}"
                print(msg)
                return None, msg
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            choice = resp.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise RuntimeError("lesson was cut off at max_tokens")
            text = (choice["message"]["content"] or "").strip()
            if len(text) < 1000:
                raise RuntimeError("lesson was too short")
            return text, model
        except Exception as exc:  # network errors, API errors, malformed responses
            last_error = exc
            print(f"Attempt {attempt} failed: {exc}")
            time.sleep(10 * attempt)
    return None, f"could not generate lesson: {last_error}"


def outline_lesson(day, reason):
    """Lesson used when the AI write-up isn't available: the curriculum entry itself."""
    _, cover, lab, _ = topic_for(day)
    return (f"## What to cover today\n{cover}\n\n"
            f"## Hands-on lab\n{lab}\n\n"
            f"## How to study it\n"
            f"1. Read about each point above (official docs, engineering blogs, *Designing Data-Intensive "
            f"Applications*, *System Design Interview* by Alex Xu).\n"
            f"2. Draw the architecture yourself before looking at any diagram.\n"
            f"3. Do the lab and write down what surprised you.\n"
            f"4. Explain the topic out loud in 5 minutes as if in an interview.\n\n"
            f"> The full AI-written lesson wasn't available today ({reason[:200]}).")


# ---------- rendering ----------

def render(day, title, level, lesson_md, footer):
    today = datetime.now(IST).strftime("%A, %d %B %Y")
    progress_pct = min(100, round(day / TOTAL_DAYS * 100))
    day_label = f"Day {day} of {TOTAL_DAYS}" if day <= TOTAL_DAYS else f"Day {day}"
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
<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#3b6fd8;font-weight:600;">System Design Daily · {html.escape(day_label)} · {html.escape(level)}</div>
<h1 style="margin:6px 0 4px;font-size:24px;">{html.escape(title)}</h1>
<div style="color:#656d76;font-size:14px;margin-bottom:12px;">{today}</div>
<div style="background:#d0d7de;border-radius:4px;height:8px;margin-bottom:22px;"><div style="background:#3b6fd8;border-radius:4px;height:8px;width:{progress_pct}%;"></div></div>
<div style="background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:8px 20px 14px;">
{body}
</div>
<p style="font-size:12px;color:#8c959f;margin-top:24px;">{html.escape(footer)} Sent by your System Design Daily bot.</p>
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
    title, _, _, level = topic_for(day)
    print(f"Day {day} ({level}): {title}")

    lesson_md, info = generate_lesson(day)
    if lesson_md:
        footer = f"Lesson written by {info} via OpenRouter."
    else:
        print(f"Sending topic outline only: {info}")
        lesson_md, footer = outline_lesson(day, info), "Topic outline from curriculum.py."

    body = render(day, title, level, lesson_md, footer)
    subject = f"System Design Day {day}: {title}"

    if args.dry_run:
        PREVIEW_FILE.write_text(body, encoding="utf-8")
        print(f"Dry run: saved {PREVIEW_FILE.name}")
        return
    send_email(body, subject)
    save_progress(progress, day, title)


if __name__ == "__main__":
    main()
