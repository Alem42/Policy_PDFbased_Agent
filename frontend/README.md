# Frontend Skeleton

React + TypeScript + Vite skeleton for the policy research application.

This is intentionally minimal: each page only shows the page name and the Jira stories suggested for that page.

## Start

```bash
npm install
npm run dev
```

By default, API calls use `VITE_API_BASE_URL=/api/v1`. Vite also proxies `/api` to `http://localhost:8000` for local backend development.

## Module Map

- `features/documents`: document library and document detail pages.
- `features/chat`: AI question page.
- `features/learning`: learning summary and case comparison pages.
- `features/admin`: admin login, upload, documents, processing pages.
- `features/crawler`: trusted sources and crawl jobs pages.
- `features/savedAnswers`: saved answers page.
