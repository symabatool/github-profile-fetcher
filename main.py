"""GitHub profile CLI.

Usage:
    python main.py octocat
    python main.py octocat torvalds gvanrossum
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://api.github.com/users/{username}"
TIMEOUT = 10  # seconds; always set a timeout
MAX_ATTEMPTS = 3  # total tries per user before giving up
RETRY_DELAY = 1.0  # seconds; multiplied by the attempt number
OUTPUT_DIR = Path("output")
LOG_FILE = OUTPUT_DIR / "errors.log"
CSV_FIELDS = ["login", "name", "public_repos", "followers"]

logger = logging.getLogger("github_profile_cli")


class UserNotFoundError(Exception):
    """The GitHub user does not exist (404). Retrying will not help."""


class FetchError(Exception):
    """The profile could not be fetched after all attempts."""


def setup_logging(log_file=LOG_FILE):
    """Send errors to a log file (the console shows friendly messages)."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)


def build_headers():
    """Read the optional GITHUB_TOKEN from .env and build request headers."""
    load_dotenv()
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_profile(username, headers=None, attempts=MAX_ATTEMPTS, delay=RETRY_DELAY):
    """Fetch one profile, retrying temporary failures up to `attempts` times.

    Retried: timeouts, connection errors (no internet), 429 and 5xx.
    Not retried: 404 (no such user) and other 4xx such as 401 (bad token).
    """
    url = API_URL.format(username=username)
    last_error = "unknown error"

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=headers or {}, timeout=TIMEOUT)

            if response.status_code == 404:
                raise UserNotFoundError(f"User '{username}' does not exist")

            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
            else:
                response.raise_for_status()  # other 4xx -> HTTPError
                return response.json()

        except UserNotFoundError:
            raise
        except requests.Timeout:
            last_error = "request timed out"
        except requests.ConnectionError:
            last_error = "no internet connection"
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            if code == 401:
                raise FetchError("HTTP 401: bad or missing GITHUB_TOKEN") from e
            if code == 403:
                raise FetchError("HTTP 403: rate limit or forbidden") from e
            raise FetchError(f"HTTP error {code}") from e
        except ValueError as e:  # response was not valid JSON
            raise FetchError(f"Invalid JSON in response: {e}") from e

        logger.warning(
            "Attempt %d/%d for '%s' failed: %s", attempt, attempts, username, last_error
        )
        if attempt < attempts:
            time.sleep(delay * attempt)

    raise FetchError(f"Gave up on '{username}' after {attempts} attempts ({last_error})")


def save_profile(profile, username, output_dir=OUTPUT_DIR):
    """Save the raw profile to output/<username>.json."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{username}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    return path


def summary_row(profile):
    """Pick the four summary fields; .get() handles missing/null values."""
    return {
        "login": profile.get("login", ""),
        "name": profile.get("name") or "",
        "public_repos": profile.get("public_repos", 0),
        "followers": profile.get("followers", 0),
    }


def write_summary_csv(rows, path):
    """Write one CSV row per successfully fetched user."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def unique_usernames(usernames):
    """Drop duplicates (case-insensitive) while keeping the original order."""
    seen, result = set(), []
    for name in usernames:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(name.strip())
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch GitHub profiles, save them as JSON and write a summary CSV."
    )
    parser.add_argument("usernames", nargs="+", help="one or more GitHub usernames")
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR),
        help="output folder (default: output)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output_dir = Path(args.output)
    setup_logging(output_dir / "errors.log")
    headers = build_headers()

    rows, failures = [], 0

    for username in unique_usernames(args.usernames):
        try:
            profile = fetch_profile(username, headers=headers)
            path = save_profile(profile, username, output_dir)
            rows.append(summary_row(profile))
            print(f"[ok]   {username}: saved to {path}")
        except UserNotFoundError as e:
            failures += 1
            logger.error("%s", e)
            print(f"[fail] {e}")
        except FetchError as e:
            failures += 1
            logger.error("%s: %s", username, e)
            print(f"[fail] {username}: {e}")
        except OSError as e:
            failures += 1
            logger.error("%s: could not write files: %s", username, e)
            print(f"[fail] {username}: could not write files ({e})")

    if rows:
        csv_path = write_summary_csv(rows, output_dir / "summary.csv")
        print(f"\nSummary CSV: {csv_path}")

    print(f"Done: {len(rows)} succeeded, {failures} failed. See {output_dir / 'errors.log'} for details.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
