"""Shared helpers for redacting sensitive values before logging.

Proxy URLs commonly embed credentials (``http://user:pass@host``); if such a
URL ends up inside an exception message or traceback, logging it verbatim
leaks the credentials. All masking in the codebase funnels through
:func:`mask_proxy_credentials` so the redaction logic lives in exactly one
place.
"""
from __future__ import annotations

import re

# Matches the credential segment of `scheme://user[:pass]@host`. The `@`
# separator is kept so the surrounding URL structure stays intact.
_PROXY_CREDENTIALS_RE = re.compile(r"//[^@]+@")


def mask_proxy_credentials(text: str) -> str:
    """Redact any ``user[:password]@`` segment embedded in *text*.

    Runs unconditionally: when *text* contains no credentials the regex simply
    does not match, so the original text is returned unchanged.
    """
    if not text:
        return text
    return _PROXY_CREDENTIALS_RE.sub("//***:***@", text)
