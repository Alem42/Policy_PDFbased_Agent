export const ROUTES = Object.freeze({
  root: "/",
  home: "/home",
  chat: "/chat",
  history: "/history",
  library: "/library",
  admin: "/admin",
  manage: "/manage",
  settings: "/settings",
  auth: "/login",
});

export const VIEW_PATHS = Object.freeze({
  home: ROUTES.home,
  chat: ROUTES.chat,
  history: ROUTES.history,
  library: ROUTES.library,
  admin: ROUTES.admin,
  manage: ROUTES.manage,
  settings: ROUTES.settings,
  auth: ROUTES.auth,
});

// Each saved conversation gets its own URL (like ChatGPT's /c/<id>), so it can
// be bookmarked, reloaded, or returned to with the browser's back button.
export function chatSessionPath(sessionId) {
  return sessionId ? `${ROUTES.chat}/${sessionId}` : ROUTES.chat;
}

export function getViewFromPath(pathname) {
  if (pathname === ROUTES.chat || pathname.startsWith(`${ROUTES.chat}/`)) return "chat";
  return Object.entries(VIEW_PATHS).find(([, path]) => path === pathname)?.[0] || "chat";
}
