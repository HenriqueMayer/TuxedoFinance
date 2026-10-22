# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Keep OAuth callbacks and credential material out of local diagnostics."""
import logging
import re
import traceback


def redact(message):
    text = str(message)
    # Callback queries contain one-use authorization codes even before views
    # validate them; development-server request lines need the same protection.
    text = re.sub(r'(/assistant/connections/callback/)\?[^\s"<>]*', r'\1?[redacted]', text)
    text = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+', 'Bearer [redacted]', text)
    return re.sub(
        r'''(?ix)((?:access_token|refresh_token|id_token|id_token_hint|login_hint|code_verifier|code_challenge|nonce|state)\s*["']?\s*[:=]\s*["']?)([^&\s"'<>]+)''',
        r'\1[redacted]', text,
    )


class OAuthRedactionFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True
