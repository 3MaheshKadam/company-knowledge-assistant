# Contributing

## Workflow

1. Branch from `main`: `git switch -c feature/<short-description>` (never commit to `main` directly).
2. Make focused commits using [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `build:`, `chore:`.
3. Run the checks locally:
   ```bash
   pip install -e ".[dev]"
   ruff check src tests eval
   pytest --cov --cov-fail-under=85
   python -m eval.run_eval
   bandit -q -r src -ll
   ```
4. Push the branch and open a pull request into `main`. CI (lint, tests, eval gate, container smoke test, security scans) must be green.
5. Squash-merge after review.

Optional: `pip install pre-commit && pre-commit install` runs ruff, bandit and gitleaks on every commit.

## Guidelines

- New behaviour needs tests. Changes to retrieval or generation should include before/after numbers from `python -m eval.run_eval`.
- Never commit secrets, real company documents, or `.env`.
- Keep the offline backends working: CI has no GPU, no model downloads and no API keys.
