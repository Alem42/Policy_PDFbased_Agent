import { useEffect, useState } from "react";
import { askQuestion } from "../api";

export default function ChatPage({ 
  documents, 
  user, 
  onNavigate,
  contextSourceIds = [],
  onRemoveSource
 }) {
  const [selected, setSelected] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [responseMode, setResponseMode] = useState("researcher");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setSelected((current) => {
      const stillSelected = current.filter((id) => contextSourceIds.includes(id));
      const newSources = contextSourceIds.filter((id) => !current.includes(id));
      return [...stillSelected, ...newSources];
    });
  }, [contextSourceIds]);

  const sourceDocs = documents.filter((doc) => contextSourceIds.includes(doc.id));

  function toggleDocument(documentId) {
    setSelected((current) =>
      current.includes(documentId)
        ? current.filter((id) => id !== documentId)
        : [...current, documentId],
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const cleanQuestion = question.trim();
    if (!cleanQuestion || !selected.length || busy) return;

    setMessages((current) => [...current, { role: "user", content: cleanQuestion }]);
    setQuestion("");
    setBusy(true);
    setError("");

    try {
      const result = await askQuestion(cleanQuestion, selected, responseMode);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: result.answer,
          truncated: result.truncated,
          evidenceSufficient: result.evidence_sufficient,
          responseMode: result.response_mode || responseMode,
        },
      ]);
    } catch (chatError) {
      setError(chatError.message);
    } finally {
      setBusy(false);
    }
  }

  function handleQuestionKeyDown(event) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  return (
    <section className="page-stack">

      <div className="chat-layout">
        <aside className="content-panel source-panel">
          <p className="eyebrow">Context</p>
          <h2>Sources</h2>
          <div className="checkbox-list">
            {sourceDocs.length === 0 ? (
              <div className="empty-state" style={{ padding: "2rem 1rem", textAlign: "center" }}>
                <p className="muted" style={{ marginBottom: "1rem" }}>
                  No source files in the context right now.
                </p>
                <button className="button ghost" onClick={() => onNavigate("library")}>
                  Find relevant files
                </button>
              </div>
            ) : (
              sourceDocs.map((document) => (
                <div 
                  key={document.id || document.name} 
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}
                >
                  <label style={{ margin: 0, flex: 1, display: "flex", alignItems: "center", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={selected.includes(document.id)}
                      onChange={() => toggleDocument(document.id)}
                      style={{ marginRight: "8px" }}
                    />
                    <span style={{ wordBreak: "break-word" }}>{document.title || document.name}</span>
                  </label>
                  <button
                    className="icon-button"
                    title="Remove from context"
                    style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: "1.2rem", color: "#999", padding: "0 8px" }}
                    onClick={() => onRemoveSource(document.id)}
                  >
                    x
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        <section className="content-panel chat-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Conversation</p>
              <h2>Chat</h2>
            </div>
            <button
              className="button ghost"
              type="button"
              onClick={() => {
                setMessages([]);
                setError("");
              }}
            >
              Clear Chat
            </button>
          </div>

          <div className="messages">
            {messages.length === 0 && (
              <div className="empty-state">Ask a question to start a conversation.</div>
            )}
            {messages.map((message, index) => (
              <div
                className={`message ${message.role}${message.evidenceSufficient === false ? " insufficient" : ""}`}
                key={`${message.role}-${index}`}
              >
                <span>
                  {message.role === "user" ? "You" : "Assistant"}
                  {message.role === "assistant" && message.responseMode && (
                    <small className="message-mode">
                      {message.responseMode === "student" ? "Student mode" : "Policy researcher mode"}
                    </small>
                  )}
                </span>
                <p>{message.content}</p>
                {message.truncated && <small>The combined PDF text was truncated.</small>}
                {message.evidenceSufficient === false && (
                  <small className="muted">Answer withheld because evidence was insufficient.</small>
                )}
              </div>
            ))}
            {busy && <div className="message assistant">Thinking...</div>}
          </div>

          {error && <div className="notice error">{error}</div>}

          <div className="mode-toggle" role="group" aria-label="Response mode">
            <span className="mode-toggle-label">Response mode</span>
            <button
              className={`mode-toggle-button${responseMode === "researcher" ? " active" : ""}`}
              type="button"
              disabled={busy}
              onClick={() => setResponseMode("researcher")}
            >
              Policy Researcher
            </button>
            <button
              className={`mode-toggle-button${responseMode === "student" ? " active" : ""}`}
              type="button"
              disabled={busy}
              onClick={() => setResponseMode("student")}
            >
              Student
            </button>
          </div>

          <form className="chat-form" onSubmit={handleSubmit}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleQuestionKeyDown}
              placeholder={
                selected.length 
                  ? "Ask a question about the selected PDFs..." 
                  : "Please select at least one document first..."
              }
              rows="3"
              disabled={!selected.length}
            />
            <button
              className="button primary"
              disabled={!question.trim() || !selected.length || busy}
              type="submit"
            >
              Send
            </button>
          </form>
        </section>
      </div>
    </section>
  );
}