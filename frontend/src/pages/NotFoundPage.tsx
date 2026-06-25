import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main>
      <h1>这是 Not Found 页面</h1>
      <p>
        <Link to="/documents">Back to Documents</Link>
      </p>
    </main>
  );
}
