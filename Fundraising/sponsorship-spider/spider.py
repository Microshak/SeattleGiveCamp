#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys

from analyzer import Analyzer
from crawler import Crawler
from writer import CSVWriter


def load_completed(output_dir: str) -> set[str]:
    path = os.path.join(output_dir, "completed_sites.json")
    if os.path.isfile(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_completed(output_dir: str, completed: set[str]):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "completed_sites.json")
    with open(path, "w") as f:
        json.dump(sorted(completed), f, indent=2)


def run_single(start_url, args, writer):
    llm_analyzer = None
    if args.keep_llm:
        from llm import LLMAnalyzer
        llm_analyzer = LLMAnalyzer(base_url=args.lmstudio_url, model=args.model)

    analyzer = Analyzer(llm_analyzer=llm_analyzer)
    crawler = Crawler(
        start_url=start_url,
        max_pages=args.max_pages,
        delay=args.delay,
        same_domain_only=True,
        verbose=args.verbose,
    )

    if args.verbose:
        print(f"\n{'='*60}\nCrawling: {start_url}\n{'='*60}")

    crawler.run(
        analyze_fn=analyzer.analyze_page,
        write_email_fn=writer.write_email,
        write_form_fn=writer.write_form,
        write_all_emails_fn=writer.write_emails_batch,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Crawl websites and extract sponsorship contact info."
    )
    parser.add_argument("start_url", nargs="?", help="URL to begin crawling from")
    parser.add_argument("--input-csv", help="CSV file with company URLs to crawl (columns: company,url)")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages to crawl per site (default: 10)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1.0)")
    parser.add_argument("--output-dir", default="./output", help="Directory for CSV output (default: ./output)")
    parser.add_argument("--append", action="store_true", help="Append to existing CSVs instead of overwriting")
    parser.add_argument("--verbose", action="store_true", help="Print status of each page as it's processed")
    parser.add_argument("--keep-llm", action="store_true", help="Use LLM (LM Studio) as fallback for form detection")
    parser.add_argument("--model", default="phi-4", help="LM Studio model name (default: phi-4)")
    parser.add_argument(
        "--lmstudio-url", default="http://localhost:1234/v1",
        help="LM Studio API base URL (default: http://localhost:1234/v1)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-crawl all sites even if previously completed (only with --input-csv)",
    )
    args = parser.parse_args()

    if not args.start_url and not args.input_csv:
        parser.error("either start_url or --input-csv is required")

    if args.input_csv:
        with open(args.input_csv, newline="") as f:
            reader = csv.DictReader(f)
            urls = []
            for row in reader:
                url = row.get("url", "").strip()
                if url:
                    urls.append(url)

        if not urls:
            sys.exit("No URLs found in input CSV")

        completed = set() if args.force else load_completed(args.output_dir)
        pending = [u for u in urls if u not in completed]
        skipped = len(urls) - len(pending)

        if skipped:
            print(f"{skipped} site(s) already completed, skipping (use --force to re-crawl)")

        if not pending:
            print("All sites already completed!")
            return

        for i, url in enumerate(pending):
            run_single(
                url,
                args,
                CSVWriter(output_dir=args.output_dir, append=(args.append or i > 0 or len(completed) > 0)),
            )
            completed.add(url)
            save_completed(args.output_dir, completed)
    else:
        run_single(
            args.start_url,
            args,
            CSVWriter(output_dir=args.output_dir, append=args.append),
        )


if __name__ == "__main__":
    main()
