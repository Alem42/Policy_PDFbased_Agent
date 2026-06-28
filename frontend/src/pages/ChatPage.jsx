import { useEffect, useState } from "react";
import { askQuestion } from "../api";

export default function ChatPage({ documents, user, onNavigate }) {
  const [selected, setSelected] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setSelected((current) => {
      const available = new Set(documents.map((document) => document.id));
      const retained = current.filter((id) => available.has(id));
      return retained.length ? retained : documents.map((document) => document.id);
    });
  }, [documents]);

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
      const result = await askQuestion(cleanQuestion, selected);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: result.answer,
          truncated: result.truncated,
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
            {documents.length === 0 && <p className="muted">No documents available.</p>}
            {documents.map((document) => (
              <label key={document.id || document.name}>
                <input
                  type="checkbox"
                  checked={selected.includes(document.id)}
                  onChange={() => toggleDocument(document.id)}
                />
                <span>{document.title || document.name}</span>
              </label>
            ))}
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
              <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role === "user" ? "You" : "Assistant"}</span>
                <p>{message.content}</p>
                {message.truncated && <small>The combined PDF text was truncated.</small>}
              </div>
            ))}
            {busy && <div className="message assistant">Thinking...</div>}
          </div>

          {error && <div className="notice error">{error}</div>}

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