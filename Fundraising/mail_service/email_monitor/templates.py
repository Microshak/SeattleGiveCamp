"""
HTML email templates for common response types.

Each method returns an HTML string suitable for use as the body of an
HTML email sent over Gmail SMTP.
"""

from email_monitor.config import settings


class ResponseTemplates:
    """Collection of static email template methods."""

    @staticmethod
    def volunteer_dropout_confirmation(name: str) -> str:
        """Confirm that a volunteer has been removed from the roster."""
        safe = _escape(name or "Valued Volunteer")
        return f"""<html>
<body style="font-family: Arial, sans-serif; color: #333;">
<p>Hi {safe},</p>
<p>We have processed your request and <strong>removed you</strong> from the Seattle GiveCamp volunteer roster.</p>
<p>We're sorry to see you go! If you change your mind or have any questions, feel free to reach out to us at any time.</p>
<p>Thank you for your interest in supporting Seattle GiveCamp.</p>
{ResponseTemplates.standard_footer()}
</body>
</html>"""

    @staticmethod
    def volunteer_not_found(email: str) -> str:
        """Notify that the sender's email was not found on the volunteer list."""
        safe = _escape(email)
        return f"""<html>
<body style="font-family: Arial, sans-serif; color: #333;">
<p>Hi there,</p>
<p>We searched our volunteer roster for <strong>{safe}</strong> but could not find a matching entry.</p>
<p>If you believe this is an error, please reply to this email with your full name and the email address you used to register, and we'll look into it manually.</p>
{ResponseTemplates.standard_footer()}
</body>
</html>"""

    @staticmethod
    def sponsor_501c3_footer() -> str:
        """Standard 501(c)(3) documentation links appended to sponsor replies."""
        return """<p style="font-size: 0.9em; color: #555;">
<strong>Seattle GiveCamp</strong> is a tax-exempt 501(c)(3) nonprofit organization (EIN: 47-2723225).
Donations are tax-deductible to the fullest extent of the law.
<a href="https://seattlegivecamp.org/nonprofit-status">View our 501(c)(3) determination letter</a>.
</p>"""

    @staticmethod
    def standard_footer() -> str:
        """Standard email footer for all sent messages."""
        return f"""<p style="font-size: 0.85em; color: #888; border-top: 1px solid #ddd; padding-top: 8px; margin-top: 16px;">
Seattle GiveCamp &bull; <a href="https://seattlegivecamp.org">seattlegivecamp.org</a><br>
If you'd like to stop receiving these emails, reply with "UNSUBSCRIBE".
</p>"""


def _escape(text: str) -> str:
    """Minimal HTML escaping for user-supplied strings."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
