// Backend base URL is baked in at build time (VITE_API_URL).
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export function newSessionId() {
  return "s-" + crypto.randomUUID().slice(0, 8);
}

// Turn any failure into a short human-readable string; the UI never shows a blank screen.
function readableError(status, detail) {
  if (status === 503) return "All AI providers are currently unavailable. Please try again in a moment.";
  if (status === 422) {
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0];
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "input";
      return `Invalid request (${field}): ${first.msg}`;
    }
    return "Invalid request. Please check your message and try again.";
  }
  if (typeof detail === "string" && detail) return detail;
  return `Something went wrong (HTTP ${status}). Please try again.`;
}

export async function sendChat({ sessionId, message, systemPrompt, simulateFailure }) {
  const headers = { "Content-Type": "application/json" };
  if (simulateFailure) headers["X-Simulate-Failure"] = simulateFailure;
  const body = { session_id: sessionId, message };
  if (systemPrompt && systemPrompt.trim()) body.system_prompt = systemPrompt.trim();

  let res;
  try {
    res = await fetch(`${API_URL}/chat`, { method: "POST", headers, body: JSON.stringify(body) });
  } catch {
    throw new Error("Cannot reach the server. Check your connection and try again.");
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) throw new Error(readableError(res.status, data?.detail));
  return data;
}
