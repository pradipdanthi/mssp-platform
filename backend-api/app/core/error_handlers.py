"""
KB-014 fix: sanitize FastAPI/Pydantic 422 validation-error responses so they
never echo back sensitive request input (passwords, tokens, secrets).

Root cause: FastAPI's default RequestValidationError handler includes an
"input" field on each error entry, which is the raw value Pydantic tried to
validate. For a whole-model validator (Pydantic's @model_validator(mode=
"after"), e.g. UserCreateRequest.normalize_and_check_tenant in
app/schemas/users.py), that "input" is the *entire* submitted request body -
including any password/new_password field - not just the one offending
field. Without this fix, a 422 response to e.g. "customer role without
tenant_id" would echo the caller's plaintext password straight back to them.

This handler keeps the standard FastAPI 422 status code and
{"detail": [...]} response shape (with loc/type/msg preserved exactly as
before, since those only ever identify *which* field failed and *why*, not
its value) - it only redacts "input" (and, defensively, "ctx") of each
error entry in two cases:

1. The error's own "loc" points directly at a sensitive field (e.g.
   ["body", "new_password"], a plain field-level error such as a
   too-short password) - "input" is force-redacted regardless of type,
   since it is that field's own plaintext value.
2. "input" is itself a dict/list that contains a sensitive key anywhere
   inside it, at any depth (the whole-model-validator case above) - the
   entire value is replaced with "<redacted>".

Non-sensitive validation errors (e.g. an invalid tenant status enum, or a
bad short_code pattern in KB-013's tenant endpoints) are returned completely
unchanged - this handler is deliberately global (applies to every route in
the app, not just KB-014's), but it never removes a value that isn't
associated with a sensitive key or field.
"""

from typing import Any, List

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

SENSITIVE_KEYS = {
    "password",
    "new_password",
    "password_hash",
    "access_token",
    "token",
    "jwt",
    "secret",
    "jwt_secret",
    # KB-016: appliance registration/heartbeat introduces these field
    # names (see app/schemas/appliance_agent.py). None of them matched
    # any existing entry above by exact string, so a 422 on e.g.
    # activation_token would previously have echoed the caller's raw
    # value back in "input" unredacted.
    "activation_token",
    "appliance_api_key",
    "api_key",
}


def _contains_sensitive_key(value: Any) -> bool:
    """Recursively check a dict/list for any key (case-insensitive) in SENSITIVE_KEYS."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                return True
            if _contains_sensitive_key(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _redact_if_sensitive(value: Any) -> Any:
    """
    Replace value with "<redacted>" if it is a dict/list containing a
    sensitive key anywhere inside it. Scalars (str/int/bool/None) - e.g. a
    single bad enum value like "not_a_real_role" - are left alone here;
    scalar redaction for a sensitive *field* (as opposed to a sensitive key
    inside a dict/list) is handled separately via _loc_is_sensitive below.
    """
    if isinstance(value, (dict, list)) and _contains_sensitive_key(value):
        return "<redacted>"
    return value


def _loc_is_sensitive(loc: Any) -> bool:
    """
    True if a validation error's "loc" (e.g. ["body", "new_password"])
    points directly at a sensitive field. This catches field-level errors
    (e.g. a too-short password failing Field(min_length=...)) where "input"
    is just that one field's own plain scalar value - not a dict/list - so
    _redact_if_sensitive() above would otherwise leave it untouched.
    """
    if isinstance(loc, (list, tuple)) and loc:
        last = loc[-1]
        return isinstance(last, str) and last.lower() in SENSITIVE_KEYS
    return False


def _sanitize_errors(errors: List[Any]) -> List[Any]:
    sanitized: List[Any] = []
    for error in errors:
        if not isinstance(error, dict):
            sanitized.append(error)
            continue

        clean_error = dict(error)

        # "loc" (e.g. ["body", "new_password"]) and "type"/"msg" identify
        # which field failed and why - they never carry the submitted
        # value itself, so they are left untouched to keep the error useful.
        loc_is_sensitive = _loc_is_sensitive(clean_error.get("loc"))

        if "input" in clean_error:
            if loc_is_sensitive:
                clean_error["input"] = "<redacted>"
            else:
                clean_error["input"] = _redact_if_sensitive(clean_error["input"])

        # Defensive: some validators attach extra context to "ctx", which
        # could theoretically carry a copy of the offending value.
        if "ctx" in clean_error:
            if loc_is_sensitive:
                clean_error["ctx"] = "<redacted>"
            else:
                clean_error["ctx"] = _redact_if_sensitive(clean_error["ctx"])

        sanitized.append(clean_error)

    return sanitized


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    sanitized = _sanitize_errors(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(sanitized)},
    )
