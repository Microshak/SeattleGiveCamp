"""
Google Sheets integration — reads target companies from Forms tab,
checks Tracking tab for dedup, and writes completion rows.
"""

import logging
from dataclasses import dataclass

import gspread
from gspread.exceptions import APIError, WorksheetNotFound

from config import GoogleSheetConfig

logger = logging.getLogger(__name__)


@dataclass
class TargetCompany:
    """A single target company read from the Forms tab."""
    name: str
    url: str
    notes: str
    row_index: int  # 1-based row in the sheet (for reference)


class GoogleSheetsClient:
    """Manages reading/writing the Forms and Tracking tabs."""

    def __init__(self, config: GoogleSheetConfig):
        self.config = config
        self._gc = None
        self._sh = None
        self._forms_ws = None
        self._tracking_ws = None

    def connect(self) -> bool:
        """Authenticate and open the spreadsheet. Returns True on success."""
        try:
            self._gc = gspread.service_account(filename=self.config.service_account_file)
            self._sh = self._gc.open_by_url(self.config.url)
            self._forms_ws = self._sh.worksheet(self.config.forms_tab)
            self._tracking_ws = self._sh.worksheet(self.config.tracking_tab)
            logger.info("Connected to Google Sheet: %s", self.config.url)
            return True
        except FileNotFoundError:
            logger.error("Service account file not found: %s", self.config.service_account_file)
            return False
        except WorksheetNotFound as e:
            logger.error("Worksheet not found: %s", e)
            return False
        except APIError as e:
            logger.error("Google Sheets API error: %s", e)
            return False

    def get_targets(self) -> list[TargetCompany]:
        """Read all target companies from the Forms tab (skipping header row)."""
        if not self._forms_ws:
            if not self.connect():
                return []

        try:
            all_values = self._forms_ws.get_all_values()
        except APIError as e:
            logger.error("Failed to read Forms tab: %s", e)
            return []

        if len(all_values) < 2:
            logger.warning("Forms tab has no data rows (only header or empty).")
            return []

        targets = []
        for i, row in enumerate(all_values[1:], start=2):  # row 2 = first data row
            name = self._safe_cell(row, self.config.forms_company_col)
            url = self._safe_cell(row, self.config.forms_url_col)
            notes = self._safe_cell(row, self.config.forms_notes_col)

            if not url:
                continue  # skip rows without a URL

            targets.append(TargetCompany(
                name=name or f"Unknown (row {i})",
                url=url,
                notes=notes,
                row_index=i,
            ))

        logger.info("Read %d target companies from Forms tab.", len(targets))
        return targets

    def get_tracked_urls(self) -> set[str]:
        """Return the set of URLs already in the Tracking tab (for dedup)."""
        if not self._tracking_ws:
            if not self.connect():
                return set()

        try:
            all_values = self._tracking_ws.get_all_values()
        except APIError as e:
            logger.error("Failed to read Tracking tab: %s", e)
            return set()

        urls = set()
        col = self.config.tracking_url_col
        for row in all_values[1:]:  # skip header
            url = self._safe_cell(row, col)
            if url:
                urls.add(url.strip())
        return urls

    def is_already_submitted(self, url: str) -> bool:
        """Check if a URL has already been submitted."""
        tracked = self.get_tracked_urls()
        return url.strip() in tracked

    def record_submission(self, company_name: str, company_url: str) -> bool:
        """Append a row to the Tracking tab: [company_name, agent_name, company_url]."""
        if not self._tracking_ws:
            if not self.connect():
                return False

        try:
            self._tracking_ws.append_row([
                company_name,
                self.config.agent_name,
                company_url,
            ])
            logger.info("Recorded submission: %s (%s)", company_name, company_url)
            return True
        except APIError as e:
            logger.error("Failed to record submission for %s: %s", company_name, e)
            return False

    @staticmethod
    def _safe_cell(row: list, col_index: int) -> str:
        """Safely get a cell value, returning empty string if out of bounds."""
        if col_index < len(row):
            return row[col_index].strip()
        return ""
