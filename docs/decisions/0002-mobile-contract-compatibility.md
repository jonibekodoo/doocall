# ADR-0002: Mobile API stays byte-compatible with the shipped app

**Status**: accepted (Phase 3)

**Context**: The Android app (`uz.hakimbek.doocall`) is already written
against `docs/backend-api-docs.md`: POST-only, api_key in the JSON body,
local-time strings, exact §4/§5.4 response shapes.

**Decision**: implement the contract exactly (field names, envelopes, error
taxonomy §9) and add capabilities only additively (Bearer auth accepted
alongside body keys; 402 SUBSCRIPTION_INACTIVE documented as an extension).
Contract tests replay the literal example payloads from the doc; breaking
changes require a parallel `/api/call/v2/`.

**Consequences**: devices in the field never break; some non-RESTful choices
(POST-for-read, body auth) are kept deliberately and confined to `apps.api`.
