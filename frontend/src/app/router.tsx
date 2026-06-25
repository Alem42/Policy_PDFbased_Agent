import { createBrowserRouter, Navigate } from "react-router-dom";
import { AdminDashboardPage } from "../features/admin/AdminDashboardPage";
import { AdminDocumentsPage } from "../features/admin/AdminDocumentsPage";
import { AdminLoginPage } from "../features/admin/AdminLoginPage";
import { AdminUploadPage } from "../features/admin/AdminUploadPage";
import { ProcessingStatusPage } from "../features/admin/ProcessingStatusPage";
import { ChatPage } from "../features/chat/ChatPage";
import { CrawlJobsPage } from "../features/crawler/CrawlJobsPage";
import { TrustedSourcesPage } from "../features/crawler/TrustedSourcesPage";
import { CompareCasesPage } from "../features/learning/CompareCasesPage";
import { LearningSummaryPage } from "../features/learning/LearningSummaryPage";
import { DocumentDetailPage } from "../features/documents/DocumentDetailPage";
import { DocumentLibraryPage } from "../features/documents/DocumentLibraryPage";
import { SavedAnswersPage } from "../features/savedAnswers/SavedAnswersPage";
import { NotFoundPage } from "../pages/NotFoundPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/documents" replace /> },
  { path: "/documents", element: <DocumentLibraryPage /> },
  { path: "/documents/:documentId", element: <DocumentDetailPage /> },
  { path: "/ask", element: <ChatPage /> },
  { path: "/compare", element: <CompareCasesPage /> },
  { path: "/summaries", element: <LearningSummaryPage /> },
  { path: "/saved-answers", element: <SavedAnswersPage /> },
  { path: "/admin/login", element: <AdminLoginPage /> },
  { path: "/admin", element: <AdminDashboardPage /> },
  { path: "/admin/documents", element: <AdminDocumentsPage /> },
  { path: "/admin/upload", element: <AdminUploadPage /> },
  { path: "/admin/processing", element: <ProcessingStatusPage /> },
  { path: "/admin/trusted-sources", element: <TrustedSourcesPage /> },
  { path: "/admin/crawl-jobs", element: <CrawlJobsPage /> },
  { path: "*", element: <NotFoundPage /> }
]);
