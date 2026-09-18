# Scripture Without Screens

Scripture Without Screens brings Bible content to feature phones through USSD,
SMS, and voice — no smartphone, no app download. YouVersion supplies scripture
text; Featherless (or Gloo) personalizes SMS reflections; Africa's Talking
carries USSD / SMS / voice; ElevenLabs can speak passages on calls.

**Who it's for:** farmers and pastoralists on feature phones. NGOs and churches
are deployment partners, not the primary UI.

## Current flows

- **USSD** (`*384*51567#` in sandbox): first dial welcomes and saves language
  (Redis). Then **Verse of the Day** (citation + explain / pray / full chapter),
  **Read My Bible** (OT/NT → book → chapter → verse via YouVersion), reading
  plans, Kids Corner, Bible version, Change Language / Home.
- **Kids Corner:** age band → pick/continue a local story (Noah, David, Kind
  Stranger) → section-by-section with “Got it / Explain simpler” (AI cascade:
  Featherless Qwen → Featherless Gemma → local Ollama Gemma → plain fallback) →
  age-banded quiz. YouVersion has no kids-plan API, so stories are local with
  optional live scripture refs.
- **SMS:** send `STRESSED`, `GRATEFUL`, or `TIRED` → verse + short reflection.
- **Voice:** same Redis prefs + Kids Corner DTMF (needs a live AT Voice number).

Reading plans use YouVersion-style **topic filters** (Hope, Sadness, Wealth,
Strength, Peace, Anxiety). Platform v1 has no plans API, so catalogs are local;
each day’s verse text is still live from YouVersion in your saved language.

## Try it locally

With uvicorn running, open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

1. **USSD** → **Call** → first time: pick a language.
2. Main menu → `3` Kids Corner → age → story → Got it / Explain simpler → quiz.
3. Nested menus: `8` Change Language, `0` Home.
4. **SMS** → mood buttons preview reflections (`/demo/sms`).
5. Optional live: dial `*384*51567#` on a real phone via ngrok.

The on-screen handset talks to the same `POST /ussd` and SMS preview endpoints
subscribers use in production.

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
| `FEATHERLESS_API_KEY` (preferred) or Gloo | SMS reflections + Kids simplify/translate | Falls back toward verse-only / plain kids text |
| `FEATHERLESS_GEMMA_MODEL` + `OLLAMA_*` | Kids AI cascade steps 2–3 | Skips to next backend / plain fallback |
| `AT_API_KEY` + `AT_USERNAME` | Sending SMS; live AT webhooks | SMS webhook returns `BAD`; USSD still testable via curl / preview UI |
| `ELEVENLABS_API_KEY` + `PUBLIC_BASE_URL` | Natural TTS on voice calls | Voice falls back to AT `Say` |
| `REDIS_URL` | Remember language / version / plan across dials | In-memory fallback (lost on restart) |
| `WHATSAPP_ACCESS_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` | Meta WhatsApp Cloud API (test number OK) | `/whatsapp/*` ignored / send fails |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WABA reference (ops / Meta console) | Status shows unset; send still works with phone id + token |
| `WHATSAPP_VERIFY_TOKEN` | Meta webhook handshake | Verification fails in Meta console |

### How to wire them

1. Copy `.env.example` → `.env`.
2. Fill each value from the portals below.
3. Restart uvicorn so `python-dotenv` reloads.
4. Point Africa's Talking callbacks at your ngrok HTTPS URL.
5. For WhatsApp, point Meta’s callback at the same ngrok host + `/whatsapp/webhook`.

YouVersion: https://developers.youversion.com — create an app key, then accept
licenses for English, Swahili, Kikuyu, Dholuo, Borana, etc.

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

### Meta WhatsApp (test number)

1. [Meta for Developers](https://developers.facebook.com/) → create/select an app → add **WhatsApp**.
2. Open **WhatsApp → API setup**. Copy into `.env`:
   - **Temporary access token** → `WHATSAPP_ACCESS_TOKEN`
   - **Phone number ID** → `WHATSAPP_PHONE_NUMBER_ID`
   - **WhatsApp Business Account ID** → `WHATSAPP_BUSINESS_ACCOUNT_ID`
3. Add your personal phone under **To** (test recipients).
4. **Configuration → Webhook** callback URL:
   `https://YOUR-SUBDOMAIN.ngrok-free.dev/whatsapp/webhook`  
   Verify token: same as `WHATSAPP_VERIFY_TOKEN` (default `sws-whatsapp-verify`).
5. Subscribe to the **messages** field. Restart uvicorn after filling `.env`.
6. Check `GET /whatsapp/status` — `configured` should be `true`.

Chat the test number: first message asks for language (`1`–`5`), then `VOTD` / `MENU` / `HELP`.

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

- Preview UI: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Docs: `http://127.0.0.1:8000/docs`
- Webhooks: `/ussd`, `/sms`, `/voice`, `/whatsapp/webhook`
- WhatsApp status: `GET /whatsapp/status`
- SMS preview (no credits): `POST /demo/sms`

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

YouVersion Platform v1 does not expose reading-plan catalogs, day schedules, or
audio Bibles (`/v1/plans` returns 404). USSD still offers Continue vs Start new
→ topic filter → plan list → about + sample chapter refs → day-by-day reading,
with live YouVersion passage text. Voice uses ElevenLabs TTS (or AT `Say`).
Data Exchange OAuth is not required for USSD farmers — App Key + licenses are
enough.
