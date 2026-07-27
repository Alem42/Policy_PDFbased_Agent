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

export function getViewFromPath(pathname) {
  return Object.entries(VIEW_PATHS).find(([, path]) => path === pathname)?.[0] || "chat";
}
