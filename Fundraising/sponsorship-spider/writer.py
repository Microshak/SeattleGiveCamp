import csv
import os
from datetime import datetime, timezone


class CSVWriter:
    def __init__(self, output_dir: str, append: bool = False):
        self.output_dir = output_dir
        self.append = append
        os.makedirs(output_dir, exist_ok=True)

        self.email_file = os.path.join(output_dir, "emails_found.csv")
        self.form_file = os.path.join(output_dir, "forms_found.csv")

        self.email_fields = ["page_url", "email", "type", "timestamp"]
        self.form_fields = ["page_url", "form_description", "timestamp"]

        self.email_fh, self.email_writer = self._make_writer(
            self.email_file, self.email_fields
        )
        self.form_fh, self.form_writer = self._make_writer(
            self.form_file, self.form_fields
        )

    def _make_writer(self, filepath: str, fields: list):
        exists = os.path.isfile(filepath) and self.append
        mode = "a" if exists else "w"
        fh = open(filepath, mode, newline="")
        writer = csv.DictWriter(fh, fieldnames=fields)
        if not exists:
            writer.writeheader()
            fh.flush()
        return fh, writer

    def write_email(self, page_url: str, email: str, email_type: str = "general"):
        self.email_writer.writerow({
            "page_url": page_url,
            "email": email,
            "type": email_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.email_fh.flush()

    def write_emails_batch(self, page_url: str, emails: list[dict]):
        for e in emails:
            self.write_email(page_url, e["email"], e.get("type", "general"))

    def write_form(self, page_url: str, form_description: str):
        self.form_writer.writerow({
            "page_url": page_url,
            "form_description": form_description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.form_fh.flush()
