import { useCallback, useEffect, useRef, useState } from "react";
import { checkHealth, newSessionId, sendChat } from "./api.js";
import Message from "./components/Message.jsx";

const FAILURE_PRESETS = [
  { label: "Off", value: "" },
  { label: "key_1 fails with 429 → falls back to key_2", value: "key_1=429" },
  { label: "key_1 fails with 500 → falls back to key_2", value: "key_1=500" },
  { label: "All keys fail with 429 → 503 error", value: "*=429" },
];

const SUGGESTIONS = [
  "Explain how a cache speeds up an API in two sentences.",
  "Give me three tips for writing clean Python.",
  "What is the capital of Australia?",
  "Write a haiku about debugging.",
];

const STATUS_TEXT = {
  checking: "Connecting…",
  waking: "Waking server…",
  online: "Online",
  offline: "Offline",
};

function useTheme() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  // A fresh session on every page load (and on "New chat").
  const [sessionId, setSessionId] = useState(newSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulate, setSimulate] = useState("");
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const [status, setStatus] = useState("checking");
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Backend status badge. A free-tier host may need a while to wake up.
  useEffect(() => {
    const ctrl = new AbortController();
    const waking = setTimeout(() => setStatus((s) => (s === "checking" ? "waking" : s)), 3000);
    checkHealth(ctrl.signal).then((h) => {
      clearTimeout(waking);
      if (!ctrl.signal.aborted) setStatus(h ? "online" : "offline");
    });
    return () => {
      clearTimeout(waking);
      ctrl.abort();
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  // Auto-grow the textarea up to a cap.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [input]);

  // Tell the user when a request is taking long (cold start on free hosting).
  useEffect(() => {
    if (!loading) return setSlow(false);
    const t = setTimeout(() => setSlow(true), 6000);
    return () => clearTimeout(t);
  }, [loading]);

  const send = useCallback(
    async (override) => {
      const text = (typeof override === "string" ? override : input).trim();
      if (!text || loading) return;
      setInput("");
      setMessages((m) => [...m, { role: "user", content: text, at: Date.now() }]);
      setLoading(true);
      try {
        const data = await sendChat({ sessionId, message: text, systemPrompt, simulateFailure: simulate });
        setStatus("online");
        setMessages((m) => [...m, { role: "assistant", content: data.reply, metadata: data.metadata, at: Date.now() }]);
      } catch (err) {
        setMessages((m) => [...m, { role: "error", content: err.message, at: Date.now() }]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [input, loading, sessionId, systemPrompt, simulate]
  );

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  }

  function newChat() {
    setSessionId(newSessionId());
    setMessages([]);
    setInput("");
    inputRef.current?.focus();
  }

  const nearLimit = input.length > 3500;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12Z" />
            </svg>
          </div>
          <div>
            <h1>Lyftr Chat</h1>
            <p className="muted">
              Session <code data-testid="session-id">{sessionId}</code>
            </p>
          </div>
        </div>
        <div className="actions">
          <span className={`status ${status}`} data-testid="backend-status" title="Backend status">
            <i className="dot" />
            {STATUS_TEXT[status]}
          </span>
          <button className="icon-btn lg" onClick={toggleTheme} aria-label="Toggle dark mode" title="Toggle theme">
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" /></svg>
            )}
          </button>
          <button className="ghost" onClick={newChat} data-testid="new-chat">
            + New chat
          </button>
        </div>
      </header>

      <details className="settings">
        <summary>
          <span>Session settings</span>
          <span className="muted">
            {systemPrompt.trim() ? "custom system prompt" : "default prompt"}
            {simulate ? " · failure demo on" : ""}
          </span>
        </summary>
        <div className="settings-body">
          <label>
            <span className="label">System prompt</span>
            <span className="hint">Optional. Applies to this whole session.</span>
            <textarea
              data-testid="system-prompt-input"
              rows={2}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="e.g. You are a pirate. Answer in one sentence."
            />
          </label>
          <label>
            <span className="label">
              Simulate key failure <span className="tag">demo</span>
            </span>
            <span className="hint">Sends the X-Simulate-Failure header so you can watch failover on demand.</span>
            <select data-testid="simulate-failure" value={simulate} onChange={(e) => setSimulate(e.target.value)}>
              {FAILURE_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>

      <main className="chat" data-testid="chat-log">
        {messages.length === 0 && (
          <div className="empty">
            <div className="empty-logo" aria-hidden="true">✦</div>
            <h2>How can I help?</h2>
            <p className="muted">
              I remember this conversation. Every reply shows its source, model, latency and token usage.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => send(s)} disabled={loading}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        {loading && (
          <div className="row assistant">
            <div className="avatar bot" aria-hidden="true">AI</div>
            <div className="stack">
              <div className="bubble typing" data-testid="typing-indicator">
                <span />
                <span />
                <span />
              </div>
              {slow && <div className="foot slow">Still working… the free server may be waking up.</div>}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </main>

      <footer className="composer-wrap">
        <div className="composer">
          <textarea
            ref={inputRef}
            data-testid="chat-input"
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message Lyftr Chat…"
            maxLength={4000}
            autoFocus
          />
          <button data-testid="send-button" onClick={() => send()} disabled={loading || !input.trim()} aria-label="Send">
            {loading ? (
              "Sending…"
            ) : (
              <>
                Send
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </>
            )}
          </button>
        </div>
        <div className="composer-foot muted">
          <span>Enter to send · Shift+Enter for a new line</span>
          {nearLimit && <span className="warn">{input.length}/4000</span>}
        </div>
      </footer>
    </div>
  );
}
