export const ROUTES = Object.freeze({
  root: "/",
  home: "/home",
  chat: "/chat",
  library: "/library",
  admin: "/admin",
  settings: "/settings",
  auth: "/login",
});

export const VIEW_PATHS = Object.freeze({
  home: ROUTES.home,
  chat: ROUTES.chat,
  library: ROUTES.library,
  admin: ROUTES.admin,
  settings: ROUTES.settings,
  auth: ROUTES.auth,
});

export function getViewFromPath(pathname) {
  return Object.entries(VIEW_PATHS).find(([, path]) => path === pathname)?.[0] || "chat";
}
