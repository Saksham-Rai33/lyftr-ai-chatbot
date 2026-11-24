export default function Message({ message }) {
  if (message.role === "user") {
    return (
      <div className="row user">
        <div className="bubble" data-testid="user-message">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="row assistant">
        <div className="bubble error" role="alert" data-testid="error-message">
          ⚠️ {message.content}
        </div>
      </div>
    );
  }

  const m = message.metadata;
  const cached = m.resolution_source === "LLM_CACHE";
  return (
    <div className="row assistant">
      <div className="bubble" data-testid="assistant-message">
        <div className="reply">{message.content}</div>
        <dl className="meta">
          <div>
            <dt>source</dt>
            <dd>
              <span className={`badge ${cached ? "cache" : "live"}`} data-testid="meta-source">
                {m.resolution_source}
              </span>
            </dd>
          </div>
          <div>
            <dt>model</dt>
            <dd data-testid="meta-model">{m.model}</dd>
          </div>
          <div>
            <dt>latency</dt>
            <dd data-testid="meta-latency">{m.latency_ms} ms</dd>
          </div>
          <div>
            <dt>input tokens</dt>
            <dd data-testid="meta-input-tokens">{m.input_tokens}</dd>
          </div>
          <div>
            <dt>output tokens</dt>
            <dd data-testid="meta-output-tokens">{m.output_tokens}</dd>
          </div>
          <div>
            <dt>key</dt>
            <dd data-testid="meta-key">{m.key_id ?? "—"}</dd>
          </div>
          <div>
            <dt>fallbacks</dt>
            <dd data-testid="meta-fallbacks">{m.fallback_attempts}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
