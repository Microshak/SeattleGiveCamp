"""
Google Sheets integration for the email monitor.

Provides functions to remove rows from the Nonprofits worksheet
when a sponsorship email is received, keeping the sheet deduplicated.
"""

import logging

import gspread
from gspread.exceptions import APIError, WorksheetNotFound

logger = logging.getLogger(__name__)


def delete_nonprofit_row_by_email(
    sheet_url: str,
    sheet_name: str,
    service_account_file: str,
    email: str,
) -> bool:
    """
    Connect to the Google Sheet, find the row in *sheet_name* whose
    "Email" column matches *email*, and delete that row.

    Returns True if a row was found and deleted, False otherwise.
    """
    if not sheet_url or not email:
        logger.warning("Missing sheet_url or email; skipping sheet deletion.")
        return False

    email_lower = email.strip().lower()

    try:
        gc = gspread.service_account(filename=service_account_file)
        sh = gc.open_by_url(sheet_url)
        ws = sh.worksheet(sheet_name)
    except FileNotFoundError:
        logger.error("Service account file not found: %s", service_account_file)
        return False
    except WorksheetNotFound:
        logger.error("Worksheet '%s' not found in spreadsheet.", sheet_name)
        return False
    except APIError as exc:
        logger.error("Google Sheets API error: %s", exc)
        return False

    try:
        all_values = ws.get_all_values()
    except APIError as exc:
        logger.error("Failed to read worksheet '%s': %s", sheet_name, exc)
        return False

    if len(all_values) < 2:
        logger.info("Worksheet '%s' has no data rows.", sheet_name)
        return False

    header = all_values[0]
    try:
        email_col_idx = header.index("Email")
    except ValueError:
        logger.error("No 'Email' column found in worksheet '%s'.", sheet_name)
        return False

    # Find the row (1-based in gspread, row 1 = header)
    for i, row in enumerate(all_values[1:], start=2):
        cell_email = row[email_col_idx].strip().lower() if len(row) > email_col_idx else ""
        if cell_email == email_lower:
            logger.info(
                "Found match at row %d in '%s': %s — deleting row.",
                i, sheet_name, email,
            )
            ws.delete_rows(i)
            return True

    logger.info("Email '%s' not found in '%s' worksheet.", email, sheet_name)
    return False
