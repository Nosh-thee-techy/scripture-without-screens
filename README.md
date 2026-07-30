# Scripture Without Screens

Scripture Without Screens brings Bible content to feature phones through USSD,
SMS, and voice — no smartphone, no app download. YouVersion supplies scripture
text; Featherless (or Gloo) personalizes SMS reflections; Africa's Talking
carries USSD / SMS / voice; ElevenLabs can speak passages on calls.

**Who it's for:** farmers and pastoralists on feature phones. NGOs and churches
are deployment partners, not the primary UI.

## Current flows

- **USSD** (`*384*51567#` in sandbox): Verse of the Day, reading plans
  (continue / choose / restart), change language, change Bible version.
  Preferences persist in Redis by phone number.
- **SMS:** send `STRESSED`, `GRATEFUL`, or `TIRED` → verse + short reflection
  in the subscriber's saved language/version.
- **Voice:** keypad menu uses the same Redis preferences (needs a live AT Voice
  number; sandbox Voice is often unavailable).

Local reading plans (YouVersion has no plan API): **Hope Kenya**, **Daily
Strength**, **Peace for Today** — USFM refs with live YouVersion text.

## Judge demo (90 seconds)

With uvicorn running, open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

1. **USSD tab** → **Call** → dials `*384*51567#` → same menu as a real handset.
2. Press `1` → SEND for Verse of the Day.
3. Dial again → `2` → choose **Daily Strength** or continue Hope Kenya.
4. **SMS tab** → tap **STRESSED** / **GRATEFUL** / **TIRED** → reflection on the
   phone screen (uses `/demo/sms`, no SMS credits).
5. Optional live: dial `*384*51567#` on a real phone pointed at your ngrok URL.

Farmers still use a real handset. Judges see the feature-phone UI.

## Requirements

- Python 3.10 or newer
- Redis (recommended) for persistent preferences
- YouVersion Platform app key + Bible licenses for languages you offer
- Featherless API key **or** Gloo AI Studio credentials (SMS reflections)
- Africa's Talking sandbox account and API key
- Optional: ElevenLabs + `PUBLIC_BASE_URL` (ngrok) for natural voice audio
- ngrok for public webhook testing

## Do you need the API keys?

Yes — for live content. Put them in `.env` (from `.env.example`). Never commit
`.env`.

| Key | Needed for | Without it |
|-----|------------|------------|
| `YOUVERSION_API_KEY` | Verse text, languages, versions | USSD/SMS show “unavailable” |
| `FEATHERLESS_API_KEY` (preferred) or Gloo | Personalized SMS reflections | SMS falls back to the verse alone |
| `AT_API_KEY` + `AT_USERNAME` | Sending SMS; live AT webhooks | SMS webhook returns `BAD`; USSD still testable via curl / demo UI |
| `ELEVENLABS_API_KEY` + `PUBLIC_BASE_URL` | Natural TTS on voice calls | Voice falls back to AT `Say` |
| `REDIS_URL` | Remember language / version / plan across dials | In-memory fallback (lost on restart) |

### How to wire them

1. Copy `.env.example` → `.env`.
2. Fill each value from the portals below.
3. Restart uvicorn so `python-dotenv` reloads.
4. Point Africa's Talking callbacks at your ngrok HTTPS URL.

YouVersion: https://developers.youversion.com — create an app key, then accept
licenses for English, Swahili, Kalenjin, etc.

Featherless: https://featherless.ai — prefer an ungated model such as
`Qwen/Qwen2.5-7B-Instruct` (Meta-Llama is often gated).

Gloo (optional): Studio → API Credentials → Client ID / Secret.

Africa's Talking: https://account.africastalking.com — sandbox API key;
username is always `sandbox` until you go live. Request a **live Voice test
number** if sandbox Voice is not operational — the USSD code is not a voice
number.

ElevenLabs: create an API key and voice id; set `PUBLIC_BASE_URL` to your
current ngrok origin so AT can `Play` the MP3.

Redis:

```powershell
docker run -d --name sws-redis -p 6379:6379 redis:7
```

Then keep `REDIS_URL=redis://localhost:6379/0` in `.env`.

## Local setup

From the `scripture-without-screens` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux: use `python3`, `source .venv/bin/activate`, and `cp .env.example .env`.

## Run the API

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Useful local URLs:

- Demo UI: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Docs: `http://127.0.0.1:8000/docs`
- Webhooks: `/ussd`, `/sms`, `/voice`
- Judge SMS preview: `POST /demo/sms`

## Expose webhooks with ngrok

```powershell
ngrok http 8000
```

Set Africa's Talking callbacks to:

- `https://YOUR-SUBDOMAIN.ngrok-free.dev/ussd`
- `https://YOUR-SUBDOMAIN.ngrok-free.dev/sms`
- `https://YOUR-SUBDOMAIN.ngrok-free.dev/voice` (when Voice number is approved)

Also set `PUBLIC_BASE_URL` to that same origin (no trailing path) and restart
uvicorn after ngrok restarts (free URLs change).

### Quick curl checks

```powershell
curl.exe -X POST http://127.0.0.1:8000/ussd `
  -d "sessionId=test-session" `
  --data-urlencode "phoneNumber=+254700000001" `
  -d "serviceCode=*384*51567#" `
  -d "text="

curl.exe -X POST http://127.0.0.1:8000/demo/sms `
  --data-urlencode "from=+254700000002" `
  -d "text=STRESSED"
```

## Run tests

```powershell
python -m pytest -q
```

## API limitation

YouVersion Platform v1 does not expose reading-plan schedules or audio Bibles.
This project stores local plans of USFM references and fetches each day's text
live from YouVersion. Voice uses ElevenLabs TTS (or AT `Say`) rather than a
YouVersion audio feed. Data Exchange OAuth is not required for USSD farmers —
App Key + licenses are enough.
