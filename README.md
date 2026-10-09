# System Design Daily

A GitHub Actions workflow (`.github/workflows/system_design_daily.yml`) emails **one system design lesson every day at 7:00 AM IST**,
following a **4-month (120-day) plan**. Topics are **not hardcoded**: each day the script tells the model (via OpenRouter)
which day it is, which level that falls in, and every topic already covered, and the model picks the next topic and
writes the lesson. Covered topics are saved in `system_design_progress.json`.

| Days | Level |
|---|---|
| 1–30 | Easy |
| 31–60 | Medium |
| 61–90 | Hard |
| 91–120 | Big Tech architecture breakdowns (Netflix, Amazon, Instagram, Paytm, PhonePe, Flipkart, Swiggy…) |
| 121+ | Mastery & Revision (more breakdowns, mock interviews) |

Every lesson includes a **hands-on lab** with step-by-step commands and complete runnable code (Docker Compose where useful).
Concept lessons cover: why it matters, core idea with a diagram, how it works, trade-offs, a real-world example, the lab,
the interview angle and key takeaways. Company breakdowns cover: the problem they faced, an architecture diagram,
key decisions and rejected alternatives, data and storage, scale and failure handling, how it evolved, a
"build a mini version" lab, and how to answer it in an interview.

**Setup:** add the repository secret `OPENROUTER_API_KEY` (from <https://openrouter.ai/keys>). Also add:

| Name | Value |
|---|---|
| `EMAIL_ADDRESS` | your Gmail address |
| `EMAIL_APP_PASSWORD` | a Gmail app password from <https://myaccount.google.com/apppasswords> (needs 2-Step Verification) |
| `EMAIL_TO` | *(optional)* recipient(s), comma separated; defaults to `EMAIL_ADDRESS` |

 To use a different model, add a repository
**variable** (not secret) `OPENROUTER_MODEL`, e.g. `openai/gpt-5.6-sol`; the default is `anthropic/claude-sonnet-5.5`.

**Test:** Actions → **System Design Daily** → **Run workflow**. Each manual run counts as a day and moves the plan forward.
Locally: `python system_design_bot.py --dry-run` saves `lesson_preview.html` without emailing or saving progress.

**Restart the plan:** delete `system_design_progress.json`.
