import { Link } from "react-router-dom";

const links = [
  { to: "/documents", label: "Documents" },
  { to: "/ask", label: "Ask AI" },
  { to: "/compare", label: "Compare Cases" },
  { to: "/summaries", label: "Learning Summary" },
  { to: "/saved-answers", label: "Saved Answers" },
  { to: "/admin", label: "Admin" },
  { to: "/admin/login", label: "Admin Login" },
  { to: "/admin/documents", label: "Admin Documents" },
  { to: "/admin/upload", label: "Admin Upload" },
  { to: "/admin/processing", label: "Processing Status" },
  { to: "/admin/trusted-sources", label: "Trusted Sources" },
  { to: "/admin/crawl-jobs", label: "Crawl Jobs" }
];

export function SimpleNav() {
  return (
    <nav>
      {links.map((link) => (
        <Link key={link.to} to={link.to}>
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
