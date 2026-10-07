# GitHub Profile CLI

A small command-line tool that fetches one or more GitHub user profiles from the
[GitHub REST API](https://docs.github.com/en/rest/users/users), saves each profile
as JSON and writes a summary CSV.

Built for the CodeGirls AI Engineering Bootcamp (Python Refresher and Environment Setup).

## Features

- Accepts **several usernames** in one run (duplicates are skipped)
- Saves each profile to `output/<username>.json`
- Writes `output/summary.csv` with: `login, name, public_repos, followers`
- **Retries** failed requests up to 3 times (timeouts, no internet, 429 and 5xx)
- Does not retry a missing user (404) or a bad token (401)
- **Logs errors to `output/errors.log`** as well as printing a friendly message
- Reads an optional `GITHUB_TOKEN` from `.env` for a higher rate limit
- Exit code is `0` if every user succeeded, `1` if any failed

## Setup

Requires Python 3.9+.

```bash
# 1. Create and activate a virtual environment
# Windows
python -m venv .venv
.venv\Scripts\activate
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) add a GitHub token
# Windows: copy .env.example .env      macOS/Linux: cp .env.example .env
# then open .env and set GITHUB_TOKEN=your_token_here
```

Without a token you get about 60 requests per hour. With one you get about 5,000.
Never commit `.env`.

## Usage

```bash
python main.py <username> [<username> ...] [--output FOLDER]
```

### Example

```bash
python main.py octocat torvalds this-user-does-not-exist-12345
```

Example output:

```
[ok]   octocat: saved to output/octocat.json
[ok]   torvalds: saved to output/torvalds.json
[fail] User 'this-user-does-not-exist-12345' does not exist

Summary CSV: output/summary.csv
Done: 2 succeeded, 1 failed. See output/errors.log for details.
```

`output/summary.csv`:

```csv
login,name,public_repos,followers
octocat,The Octocat,8,<followers>
torvalds,Linus Torvalds,<repos>,<followers>
```

(Numbers change over time; they come live from the API.)

`output/errors.log`:

```
2026-10-07 12:00:01,123 | ERROR | User 'this-user-does-not-exist-12345' does not exist
```

## Run the tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests mock the network, so they run offline.

## Project layout

```
github-profile-cli/
├── .env.example
├── .gitignore
├── README.md
├── main.py
├── requirements.txt
├── requirements-dev.txt
├── test_main.py
└── output/          (created at runtime, git-ignored)
```

## Known limitations

- Fetches profiles one at a time (no concurrency)
- Unauthenticated requests are rate-limited to about 60 per hour
- Retry delay is simple linear backoff (1s, 2s), and does not read the `Retry-After` header
- Only the summary fields go in the CSV; the full profile is in the JSON files
- The summary CSV is overwritten on each run
