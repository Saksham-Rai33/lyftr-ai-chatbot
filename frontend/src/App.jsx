import { useEffect, useRef, useState } from "react";
import { newSessionId, sendChat } from "./api.js";
import Message from "./components/Message.jsx";

const FAILURE_PRESETS = [
  { label: "None", value: "" },
  { label: "key_1 → 429 (failover to key_2)", value: "key_1=429" },
  { label: "key_1 → 500 (failover to key_2)", value: "key_1=500" },
  { label: "All keys → 429 (503 error)", value: "*=429" },
];

export default function App() {
  // A fresh session on every page load (and on "New chat").
  const [sessionId, setSessionId] = useState(newSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulate, setSimulate] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const data = await sendChat({ sessionId, message: text, systemPrompt, simulateFailure: simulate });
      setMessages((m) => [...m, { role: "assistant", content: data.reply, metadata: data.metadata }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", content: err.message }]);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function newChat() {
    setSessionId(newSessionId());
    setMessages([]);
    setInput("");
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Lyftr Chat</h1>
          <p className="muted">
            Session <code data-testid="session-id">{sessionId}</code>
          </p>
        </div>
        <button className="ghost" onClick={newChat} data-testid="new-chat">
          New chat
        </button>
      </header>

      <details className="settings">
        <summary>Session settings</summary>
        <label>
          System prompt <span className="muted">(optional, applies to this session)</span>
          <textarea
            data-testid="system-prompt-input"
            rows={2}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="e.g. You are a pirate. Answer in one sentence."
          />
        </label>
        <label>
          Simulate key failure <span className="muted">(demo of the X-Simulate-Failure header)</span>
          <select data-testid="simulate-failure" value={simulate} onChange={(e) => setSimulate(e.target.value)}>
            {FAILURE_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
      </details>

      <main className="chat" data-testid="chat-log">
        {messages.length === 0 && (
          <div className="empty">
            <p>Ask me anything. I remember this conversation.</p>
            <p className="muted">Each reply shows where it came from, which model answered, latency and token usage.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        {loading && (
          <div className="row assistant">
            <div className="bubble typing" data-testid="typing-indicator">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </main>

      <footer className="composer">
        <textarea
          data-testid="chat-input"
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Type a message and press Enter…"
          maxLength={4000}
          autoFocus
        />
        <button data-testid="send-button" onClick={send} disabled={loading || !input.trim()}>
          {loading ? "Sending…" : "Send"}
        </button>
      </footer>
    </div>
  );
}
