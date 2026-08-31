# ADR-0004: Access token in memory, refresh token in an httpOnly cookie

**Status**: accepted (Phase 6)

**Context**: The cabinet SPA needs session persistence without exposing
long-lived credentials to XSS.

**Decision**: SimpleJWT access tokens live only in JS memory; the refresh
token is an httpOnly, path-scoped (`/api/web/v1/auth`) SameSite=Lax cookie.
Refresh rotates and blacklists the previous token; page reloads recover the
session with one silent refresh; 401s trigger a single shared refresh-retry.

**Consequences**: XSS cannot exfiltrate the refresh token; the anonymous
first visit logs one expected 401 on the refresh probe (allow-listed in E2E);
logout blacklists server-side.
