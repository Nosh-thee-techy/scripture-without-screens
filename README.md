# Scripture Without Screens

Scripture Without Screens brings Bible content to feature phones through USSD,
SMS, and voice. It uses YouVersion Platform for scripture, Gloo AI Studio for
short personalized reflections, and Africa's Talking for telco delivery.

Current flows:

- USSD: dial in, view the menu, and select the Verse of the Day.
- SMS: send `STRESSED`, `GRATEFUL`, or `TIRED` and receive a reflection.
- Voice: hear a keypad menu and press `1` for the Verse of the Day.

## Requirements

- Python 3.10 or newer
- A YouVersion Platform app key with an available Bible license
- Gloo AI Studio credentials
- An Africa's Talking sandbox account and API key
- ngrok for public webhook testing

## Local setup

From the `scripture-without-screens` directory, create and activate a virtual
environment.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy the environment template, then replace its placeholders with real
credentials:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux, use `cp .env.example .env`.

Never commit `.env`. The included `.gitignore` excludes it.

### Credentials

YouVersion:

1. Create an app and app key at the YouVersion Platform developer portal.
2. Accept or request access to the Bible version licenses needed by the app.
3. Set `YOUVERSION_API_KEY` in `.env`.

Gloo AI Studio:

1. Create API credentials in Gloo AI Studio.
2. Set `GLOO_CLIENT_ID` and `GLOO_CLIENT_SECRET` in `.env`.
3. If the hackathon instead gives you a ready-to-use bearer token, place it in
   `GLOO_API_KEY`; it takes precedence over the OAuth2 credentials.

Africa's Talking:

1. Open the Africa's Talking sandbox and generate an API key.
2. Set `AT_USERNAME=sandbox` and set `AT_API_KEY` in `.env`.
3. Use production credentials only after replacing the sandbox username.

Voice calling may require an approved production Voice application and an
Africa's Talking phone number; sandbox availability varies by account. The
voice webhook and its tests work locally without placing a real call.

## Run the API

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Useful local URLs:

- Health check: `http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`
- USSD webhook: `http://127.0.0.1:8000/ussd`
- SMS webhook: `http://127.0.0.1:8000/sms`
- Voice instructions webhook: `http://127.0.0.1:8000/voice`

## Expose webhooks with ngrok

Keep the API running, then start ngrok in a second terminal:

```powershell
ngrok http 8000
```

ngrok prints a temporary HTTPS forwarding URL such as
`https://example.ngrok-free.app`. Keep both processes running while testing.
The URL changes when a free ngrok tunnel restarts, so update Africa's Talking
whenever that happens.

## Configure Africa's Talking sandbox

In the sandbox dashboard:

1. Configure the USSD callback URL as
   `https://example.ngrok-free.app/ussd` using HTTP `POST`.
2. Configure the SMS incoming-messages callback URL as
   `https://example.ngrok-free.app/sms` using HTTP `POST`.
3. If Voice is enabled, configure the phone number's callback URL as
   `https://example.ngrok-free.app/voice` using HTTP `POST`.
4. Launch the Africa's Talking simulator and use the sandbox service code or
   SMS shortcode assigned to your channel.

Dashboard wording can vary by account. The important detail is that incoming
USSD and SMS callbacks point to the HTTPS ngrok URLs above.

### Test the webhooks without the simulator

Start a USSD session:

```powershell
curl.exe -X POST http://127.0.0.1:8000/ussd `
  -d "sessionId=test-session" `
  --data-urlencode "phoneNumber=+254700000001" `
  -d "serviceCode=*384*123#" `
  -d "text="
```

Select the Verse of the Day by repeating the request with `-d "text=1"`.

Send a mood SMS:

```powershell
curl.exe -X POST http://127.0.0.1:8000/sms `
  --data-urlencode "from=+254700000002" `
  -d "to=12345" `
  -d "text=STRESSED"
```

The SMS webhook returns `GOOD` after submitting the outbound reply through
Africa's Talking. It returns `BAD` if outbound submission fails.

Request the opening voice menu:

```powershell
curl.exe -X POST http://127.0.0.1:8000/voice `
  -d "sessionId=test-call" `
  --data-urlencode "callerNumber=+254700000003" `
  --data-urlencode "destinationNumber=+254711000000" `
  -d "isActive=1"
```

Repeat the request with `-d "dtmfDigits=1"` to simulate selecting the Verse of
the Day. The response is Africa's Talking voice action XML.

## Run tests

Tests mock YouVersion, Gloo, and Africa's Talking, so they do not consume API
credits or send messages.

```powershell
python -m pytest -q
```

## API limitation

The current public YouVersion Platform v1 documentation does not expose
reading-plan schedules or day content. `get_reading_plan_day()` therefore
raises a clear `YouVersionUnsupportedError` rather than calling an invented
endpoint. A later implementation can store approved plan passage references
locally and retrieve their text through the documented passage API.
