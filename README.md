# System Design Daily

A GitHub Actions workflow (`.github/workflows/system_design_daily.yml`) emails **one system design lesson every day at 7:00 AM IST**,
following a **4-month (120-day) curriculum** listed in [`curriculum.py`](curriculum.py), one topic per day in order:

| Days | Level | Examples |
|---|---|---|
| 1–30 | Easy | How the web works, caching, load balancing, indexing, queues, URL shortener |
| 31–60 | Medium | Sharding, consistent hashing, Kafka, CAP, CQRS, chat and news feed designs, BookMyShow |
| 61–90 | Hard | Raft, sagas, vector clocks, CRDTs, Spanner, payment system, matching engine |
| 91–120 | Big Tech Architecture | Netflix, PhonePe, Amazon, Paytm, Instagram, Flipkart, Uber, Swiggy, Hotstar, UPI… |
| 121+ | Revision | The list starts again from day 1 |

Each topic has what to cover and a **hands-on lab**. With an OpenCode Zen key, the model writes a full lesson for the day's
topic (explanation, diagram, trade-offs, real-world example, step-by-step lab with complete code, interview angle).
If the main model fails (for example, out of credit), a free model is tried. If that fails too, the email still goes out with the topic outline and lab.

Progress is saved in `system_design_progress.json`. To change topics, edit `curriculum.py`.

**Setup:** add these repository secrets (**Settings → Secrets and variables → Actions**):

| Name | Value |
|---|---|
| `OPENCODE_API_KEY` | your OpenCode Zen API key from <https://opencode.ai/zen> (needed for full lessons) |
| `EMAIL_ADDRESS` | your Gmail address |
| `EMAIL_APP_PASSWORD` | a Gmail app password from <https://myaccount.google.com/apppasswords> (needs 2-Step Verification) |
| `EMAIL_TO` | *(optional)* recipient(s), comma separated; defaults to `EMAIL_ADDRESS` |

**Models** (optional repository **variables**, not secrets; IDs from <https://opencode.ai/docs/zen/>):

| Variable | Default | Notes |
|---|---|---|
| `OPENCODE_MODEL` | `claude-haiku-5-5` | about $0.003 per lesson (~$0.40 for all 120). For richer lessons try `claude-sonnet-5-5` (~$8 total). |
| `OPENCODE_FALLBACK_MODEL` | `nemotron-3-ultra-free` | free model used when the main one fails |

**Test:** Actions → **System Design Daily** → **Run workflow**. Each manual run counts as a day and moves the plan forward.
Locally: `python system_design_bot.py --dry-run` saves `lesson_preview.html` without emailing or saving progress.

**Restart the plan:** delete `system_design_progress.json`.
