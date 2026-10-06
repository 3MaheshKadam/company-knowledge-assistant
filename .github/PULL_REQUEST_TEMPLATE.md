## What & why
<!-- What does this change and why is it needed? Link issues with "Closes #123". -->

## How it was tested
- [ ] `ruff check src tests eval`
- [ ] `pytest --cov` (coverage gate 85%)
- [ ] `python -m eval.run_eval` (no retrieval-quality regression)
- [ ] `scripts/smoke_test.sh` against the container (if API/Docker changed)

## Checklist
- [ ] No secrets, keys or proprietary documents committed
- [ ] Docs / README / CHANGELOG updated where behaviour changed
- [ ] Security impact considered (auth, input validation, new dependencies)
