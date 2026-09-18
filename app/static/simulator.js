/**
 * Feature-phone USSD / SMS preview client.
 *
 * USSD mimics Africa's Talking callbacks: cumulative asterisk-delimited `text`,
 * plus sessionId / phoneNumber / serviceCode form fields against POST /ussd.
 * SMS uses POST /demo/sms so the reflection can be previewed without SMS credits.
 */

const SERVICE_CODE = "*384*51567#";
const DEMO_PHONE = "+254711000111";

const idleView = document.getElementById("idleView");
const ussdView = document.getElementById("ussdView");
const smsView = document.getElementById("smsView");
const ussdText = document.getElementById("ussdText");
const ussdInput = document.getElementById("ussdInput");
const smsBubble = document.getElementById("smsBubble");
const dialPreview = document.getElementById("dialPreview");
const idleHint = document.getElementById("idleHint");
const idleSub = document.getElementById("idleSub");
const toast = document.getElementById("toast");
const connStatus = document.getElementById("connStatus");
const clock = document.getElementById("clock");
const coachUssd = document.getElementById("coachUssd");
const coachSms = document.getElementById("coachSms");
const callBtn = document.getElementById("callBtn");

let channel = "ussd";
let sessionId = "";
let cumulativeText = "";
let sessionOpen = false;
let awaitingInput = false;
let dialBuffer = SERVICE_CODE;

/**
 * Refresh the on-screen clock in the feature-phone status bar.
 */
function tickClock() {
  const now = new Date();
  clock.textContent = now.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Show a brief status toast on the phone screen.
 *
 * @param {string} message Text to display.
 */
function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.setTimeout(() => toast.classList.add("hidden"), 1800);
}

/**
 * Create a fresh Africa's Talking-style session identifier.
 *
 * @returns {string} A unique session id for this dial.
 */
function newSessionId() {
  if (window.crypto && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `demo-${Date.now()}`;
}

/**
 * Switch between USSD dialing and SMS mood preview.
 *
 * @param {"ussd"|"sms"} next Channel to show.
 */
function setChannel(next) {
  channel = next;
  document.querySelectorAll(".channel-toggle__btn").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.channel === next);
  });
  coachUssd.classList.toggle("hidden", next !== "ussd");
  coachSms.classList.toggle("hidden", next !== "sms");
  resetToIdle();

  if (next === "ussd") {
    idleHint.textContent = "No smartphone needed";
    dialPreview.textContent = SERVICE_CODE;
    idleSub.textContent = "Press Call to open USSD";
    callBtn.textContent = "Call";
    connStatus.textContent = "USSD mode · ready to dial";
  } else {
    idleHint.textContent = "Text a mood word";
    dialPreview.textContent = "SMS";
    idleSub.textContent = "Tap STRESSED / GRATEFUL / TIRED";
    callBtn.textContent = "SMS";
    connStatus.textContent = "SMS mode · pick a mood";
  }
}

/**
 * Call the live USSD webhook with the current cumulative menu path.
 *
 * @param {string} textValue Cumulative AT-style text ("" on first contact).
 * @returns {Promise<{status: string, message: string}>}
 */
async function postUssd(textValue) {
  const body = new URLSearchParams({
    sessionId,
    phoneNumber: DEMO_PHONE,
    serviceCode: SERVICE_CODE,
    text: textValue,
  });

  const response = await fetch("/ussd", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  const raw = (await response.text()).trim();
  const space = raw.indexOf(" ");
  if (space === -1) {
    return { status: "END", message: raw || "Empty response from server." };
  }
  return {
    status: raw.slice(0, space).toUpperCase(),
    message: raw.slice(space + 1),
  };
}

/**
 * Preview an SMS reflection body without sending via Africa's Talking.
 *
 * @param {string} mood Mood keyword such as STRESSED.
 * @returns {Promise<string>}
 */
async function postDemoSms(mood) {
  const body = new URLSearchParams({
    from: DEMO_PHONE,
    text: mood,
  });
  const response = await fetch("/demo/sms", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return (await response.text()).trim();
}

/**
 * Render a USSD dialog on the phone screen.
 *
 * @param {string} message Menu or result text from the backend.
 * @param {boolean} allowInput Whether CANCEL/SEND should remain available.
 */
function openUssdDialog(message, allowInput) {
  idleView.classList.add("hidden");
  smsView.classList.add("hidden");
  ussdView.classList.remove("hidden");
  ussdView.style.animation = "none";
  void ussdView.offsetWidth;
  ussdView.style.animation = "";

  ussdText.textContent = message;
  ussdInput.value = "";
  awaitingInput = allowInput;
  ussdInput.classList.toggle("hidden", !allowInput);
  document.getElementById("sendBtn").classList.toggle("hidden", !allowInput);
  if (allowInput) {
    ussdInput.focus();
  }
}

/**
 * Show an inbound SMS bubble on the phone screen.
 *
 * @param {string} message Reflection or help text.
 */
function openSmsBubble(message) {
  idleView.classList.add("hidden");
  ussdView.classList.add("hidden");
  smsView.classList.remove("hidden");
  smsBubble.textContent = message;
  smsBubble.style.animation = "none";
  void smsBubble.offsetWidth;
  smsBubble.style.animation = "";
}

/**
 * Close the session and return to the idle dial / SMS screen.
 */
function resetToIdle() {
  sessionOpen = false;
  awaitingInput = false;
  cumulativeText = "";
  sessionId = "";
  dialBuffer = SERVICE_CODE;
  dialPreview.textContent = channel === "ussd" ? SERVICE_CODE : "SMS";
  ussdView.classList.add("hidden");
  smsView.classList.add("hidden");
  idleView.classList.remove("hidden");
  ussdInput.value = "";
}

/**
 * Start a USSD session by dialing the sandbox service code.
 */
async function dialService() {
  if (channel !== "ussd") {
    return;
  }

  sessionId = newSessionId();
  cumulativeText = "";
  sessionOpen = true;
  showToast("Dialing " + SERVICE_CODE);

  try {
    const result = await postUssd("");
    if (result.status === "CON") {
      openUssdDialog(result.message, true);
      connStatus.textContent = "Live session · CON (menu open)";
    } else {
      openUssdDialog(result.message, false);
      connStatus.textContent = "Session ended · END";
      sessionOpen = false;
    }
  } catch (error) {
    connStatus.textContent = "Backend unreachable — is uvicorn running?";
    showToast("Could not reach /ussd");
    resetToIdle();
  }
}

/**
 * Submit the current keypad choice to the continuing USSD session.
 */
async function sendChoice() {
  if (!sessionOpen || !awaitingInput) {
    return;
  }

  const choice = ussdInput.value.trim();
  if (!choice) {
    showToast("Enter a menu number");
    return;
  }

  cumulativeText = cumulativeText ? `${cumulativeText}*${choice}` : choice;

  try {
    const result = await postUssd(cumulativeText);
    if (result.status === "CON") {
      openUssdDialog(result.message, true);
      connStatus.textContent = `Live session · path ${cumulativeText}`;
    } else {
      openUssdDialog(result.message, false);
      connStatus.textContent = "Session ended · END";
      sessionOpen = false;
      awaitingInput = false;
    }
  } catch (error) {
    connStatus.textContent = "Request failed";
    showToast("USSD request failed");
  }
}

/**
 * Request a mood reflection and show it as an SMS on the phone.
 *
 * @param {string} mood Mood keyword.
 */
async function sendMood(mood) {
  showToast("Sending " + mood);
  connStatus.textContent = `SMS · composing ${mood}…`;
  try {
    const body = await postDemoSms(mood);
    openSmsBubble(body);
    connStatus.textContent = `SMS · ${mood} reflection ready`;
  } catch (error) {
    connStatus.textContent = "SMS preview failed";
    showToast("Could not reach /demo/sms");
  }
}

/**
 * Append a dial-pad character to either the idle dial buffer or USSD input.
 *
 * @param {string} key Digit or symbol from the feature-phone keypad.
 */
function pressKey(key) {
  if (channel !== "ussd") {
    return;
  }
  if (sessionOpen && awaitingInput) {
    ussdInput.value += key;
    return;
  }
  if (!sessionOpen) {
    if (dialBuffer === SERVICE_CODE) {
      dialBuffer = key;
    } else {
      dialBuffer += key;
    }
    dialPreview.textContent = dialBuffer;
  }
}

document.getElementById("keypad").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-key]");
  if (!button) {
    return;
  }
  pressKey(button.getAttribute("data-key"));
});

document.getElementById("callBtn").addEventListener("click", () => {
  if (channel === "sms") {
    showToast("Pick a mood on the right");
    return;
  }
  if (sessionOpen) {
    return;
  }
  dialBuffer = SERVICE_CODE;
  dialPreview.textContent = dialBuffer;
  dialService();
});

document.getElementById("clearBtn").addEventListener("click", () => {
  if (sessionOpen && awaitingInput) {
    ussdInput.value = "";
    return;
  }
  resetToIdle();
});

document.getElementById("endBtn").addEventListener("click", () => {
  resetToIdle();
  connStatus.textContent =
    channel === "ussd" ? "Session cleared" : "SMS cleared";
  showToast(channel === "ussd" ? "Call ended" : "Inbox cleared");
});

document.getElementById("cancelBtn").addEventListener("click", () => {
  resetToIdle();
  connStatus.textContent = "USSD cancelled";
});

document.getElementById("sendBtn").addEventListener("click", sendChoice);

ussdInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendChoice();
  }
});

document.querySelectorAll(".channel-toggle__btn").forEach((button) => {
  button.addEventListener("click", () => {
    setChannel(button.dataset.channel);
  });
});

document.querySelectorAll(".mood-btn").forEach((button) => {
  button.addEventListener("click", () => {
    if (channel !== "sms") {
      setChannel("sms");
    }
    sendMood(button.dataset.mood);
  });
});

async function checkHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      throw new Error("bad health");
    }
    connStatus.textContent =
      channel === "ussd"
        ? "Backend online · ready to dial"
        : "Backend online · pick a mood";
  } catch (error) {
    connStatus.textContent = "Backend offline · start uvicorn first";
  }
}

tickClock();
window.setInterval(tickClock, 30_000);
checkHealth();
