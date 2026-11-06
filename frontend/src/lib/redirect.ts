const fallback = '/dashboard'
const authPages = /^\/(?:login|register)\/?$/i
// Placeholder origin used only to let the URL parser resolve the path.
const origin = 'http://riichi.invalid'

type PathLike = { pathname?: unknown; search?: unknown; hash?: unknown }

/**
 * Turn the `from` value a route guard stored in navigation state into a same-site
 * path, keeping its search and hash. Other origins, protocol-relative or backslash
 * tricks and the auth pages themselves fall back to the dashboard, so the login
 * page can never become an open redirect.
 */
export function safeReturnPath(from: unknown): string {
  let path: string
  if (typeof from === 'string') path = from
  else if (from && typeof from === 'object' && typeof (from as PathLike).pathname === 'string') {
    const { pathname, search, hash } = from as PathLike
    path = `${pathname}${typeof search === 'string' ? search : ''}${typeof hash === 'string' ? hash : ''}`
  } else return fallback
  // Browsers treat "\" like "/" and drop tabs/newlines, so "/\evil" or "/\t/evil"
  // would become "//evil". Reject them before any parsing.
  if (!path.startsWith('/') || path.startsWith('//') || /[\\\u0000-\u001f\u007f]/.test(path))
    return fallback
  let url: URL
  try {
    url = new URL(path, origin)
  } catch {
    return fallback
  }
  if (url.origin !== origin || authPages.test(url.pathname)) return fallback
  return `${url.pathname}${url.search}${url.hash}`
}
