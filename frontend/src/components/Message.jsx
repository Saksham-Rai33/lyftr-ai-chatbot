import { useState } from "react";

function timeLabel(ts) {
  return ts ? new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }
  // Icon-only on purpose: keeps button text out of the assistant-message container.
  return (
    <button className="icon-btn" onClick={copy} aria-label={done ? "Copied" : "Copy reply"} title={done ? "Copied" : "Copy"}>
      {done ? (
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></svg>
      )}
    </button>
  );
}

const Avatar = ({ kind }) => (
  <div className={`avatar ${kind}`} aria-hidden="true">
    {kind === "bot" ? "AI" : "You"}
  </div>
);

function Chip({ label, children, testid, title }) {
  return (
    <span className="chip" title={title}>
      <span className="chip-k">{label}</span>
      <span className="chip-v" data-testid={testid}>
        {children}
      </span>
    </span>
  );
}

export default function Message({ message }) {
  if (message.role === "user") {
    return (
      <div className="row user">
        <div className="stack">
          <div className="bubble" data-testid="user-message">
            {message.content}
          </div>
          <div className="foot">{timeLabel(message.at)}</div>
        </div>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="row assistant">
        <Avatar kind="bot" />
        <div className="stack">
          <div className="bubble error" role="alert" data-testid="error-message">
            <span className="error-icon" aria-hidden="true">!</span>
            <span>{message.content}</span>
          </div>
        </div>
      </div>
    );
  }

  const m = message.metadata;
  const cached = m.resolution_source === "LLM_CACHE";
  return (
    <div className="row assistant">
      <Avatar kind="bot" />
      <div className="stack">
        <div className="bubble" data-testid="assistant-message">
          <div className="reply">{message.content}</div>
          <div className="meta">
            <span className={`badge ${cached ? "cache" : "live"}`}>
              <i className="dot" />
              <span data-testid="meta-source">{m.resolution_source}</span>
            </span>
            <Chip label="model" testid="meta-model">{m.model}</Chip>
            <Chip label="latency" testid="meta-latency">{m.latency_ms} ms</Chip>
            <Chip label="in" testid="meta-input-tokens" title="Input tokens for this request">{m.input_tokens}</Chip>
            <Chip label="out" testid="meta-output-tokens" title="Output tokens for this request">{m.output_tokens}</Chip>
            <Chip label="key" testid="meta-key" title="Which API key answered">{m.key_id ?? "—"}</Chip>
            <Chip label="fallbacks" testid="meta-fallbacks" title="Keys that failed before this one">{m.fallback_attempts}</Chip>
          </div>
        </div>
        <div className="foot">
          <span>{timeLabel(message.at)}</span>
          <CopyButton text={message.content} />
        </div>
      </div>
    </div>
  );
}
