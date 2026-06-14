"""
Email sender.

Sends the markdown report by email over SMTP using only the standard library
(smtplib + email). If email settings are missing, it prints a warning and skips
sending instead of crashing.

The report is sent both as a plain-text part (the raw markdown) and a very
light HTML part, so it is readable in any mail client.
"""

from __future__ import annotations

import html
import re
import smtplib
from email.message import EmailMessage

import config
from radar.utils.logging import get_logger

logger = get_logger(__name__)

# Page styling kept inline so it renders the same in every mail client.
_HTML_STYLE = """
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       line-height: 1.5; color: #1a1a1a; max-width: 760px; margin: 0 auto; padding: 16px; }
h1 { font-size: 22px; border-bottom: 2px solid #2d6cdf; padding-bottom: 6px; }
h2 { font-size: 17px; margin-top: 28px; color: #2d6cdf; }
ul { padding-left: 20px; } li { margin: 4px 0; }
a { color: #2d6cdf; text-decoration: none; } a:hover { text-decoration: underline; }
em { color: #666; } hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
"""


def _inline_md(text: str) -> str:
    """Apply inline markdown (links, bold, italic) to already-escaped text."""
    # [label](url) -> <a href="url">label</a>
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # **bold** and _italic_
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)
    return text


def _markdown_to_html(markdown_text: str) -> str:
    """
    Convert our report markdown into clean HTML with real headings and
    clickable links.

    This is a small, purpose-built converter (no extra dependencies) that
    handles exactly the markdown our report generator emits: h1/h2 headings,
    bullet lists, horizontal rules, blank-line paragraphs, and inline
    links/bold/italic.
    """
    out: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        # Escape HTML-special chars first, then re-apply markdown as real tags.
        safe = _inline_md(html.escape(line, quote=False))

        if not line.strip():
            close_list()
            continue
        if line.startswith("## "):
            close_list()
            out.append(f"<h2>{_inline_md(html.escape(line[3:], quote=False))}</h2>")
        elif line.startswith("# "):
            close_list()
            out.append(f"<h1>{_inline_md(html.escape(line[2:], quote=False))}</h1>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_md(html.escape(line[2:], quote=False))}</li>")
        elif line.strip() == "---":
            close_list()
            out.append("<hr>")
        else:
            close_list()
            out.append(f"<p>{safe}</p>")

    close_list()
    body = "\n".join(out)
    return f"<html><head><style>{_HTML_STYLE}</style></head><body>{body}</body></html>"


def send_report(report_markdown: str, report_date: str) -> bool:
    """
    Send the report by email. Returns True on success, False otherwise.

    Never raises — failures are logged and reported via the return value.
    """
    if not config.email_is_configured():
        logger.warning(
            "Email settings are incomplete — skipping send. "
            "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, "
            "EMAIL_TO in your .env to enable email."
        )
        return False

    subject = f"EU Job Market Radar — {report_date}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    # Force quoted-printable + utf-8 so non-ASCII characters (em dashes,
    # emoji, the non-breaking spaces that often appear in scraped news
    # titles) survive even if the SMTP server does not advertise 8BITMIME
    # and the message gets re-encoded as 7-bit on the wire.
    msg.set_content(report_markdown, subtype="plain", charset="utf-8", cte="quoted-printable")
    msg.add_alternative(
        _markdown_to_html(report_markdown),
        subtype="html",
        charset="utf-8",
        cte="quoted-printable",
    )

    try:
        logger.info(
            "Connecting to SMTP %s:%s as %s",
            config.SMTP_HOST,
            config.SMTP_PORT,
            config.SMTP_USER,
        )
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()  # upgrade to a secure connection
            server.ehlo()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Report emailed to %s", config.EMAIL_TO)
        return True
    except Exception as exc:
        # Log the full traceback so SMTP/encoding issues are diagnosable
        # from the GitHub Actions logs, not just the one-line message.
        logger.exception("Failed to send email: %s", exc)
        return False
