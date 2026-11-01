# Local release automation for korvoice.
#
# Pushing the version tag created by `release` triggers
# .github/workflows/publish.yml, which tests, builds and publishes to PyPI
# through trusted publishing. Configure the `pypi` GitHub environment and
# matching PyPI trusted publisher before the first release.
#
# No typecheck target — see pyproject.toml's
# [project.optional-dependencies] comment.
#
# Usage:
#   make check                          # lint + test
#   make release                        # check, then tag vX.Y.Z (clean tree only) and push
#   make version                        # print the tag this would create

# `uv run --extra dev` creates/updates an isolated project environment with
# pytest, pytest-qt and ruff. Do not use korvoice's pipx runtime venv for
# release checks: it intentionally contains runtime dependencies only.
# Without uv, use the active/local virtualenv (after `make install`).
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then printf '%s' '.venv/bin/python'; \
                   else printf '%s' 'python3'; fi)
RUNNER := $(shell if command -v uv >/dev/null 2>&1; then \
                     printf '%s' 'uv run --extra dev'; \
                   else printf '%s' '$(PYTHON) -m'; fi)
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
TAG     := v$(VERSION)

.PHONY: help install test lint check release version

help:
	@printf '%s\n' 'Targets: install test lint check release version'

install:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	QT_QPA_PLATFORM=offscreen $(RUNNER) pytest -q

lint:
	$(RUNNER) ruff check .

check: lint test

version:
	@echo $(TAG)

# Tags the version currently in pyproject.toml and pushes it. Requires a
# clean working tree (commit the version bump and changelog first) and
# refuses to touch a tag that already exists: release tags are immutable.
# To retry a failed publish, use "Re-run jobs" in GitHub Actions; for a fix,
# bump the patch version.
release: check
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "release: working tree is not clean; commit or stash your changes first" >&2; \
		exit 1; \
	fi
	@if git rev-parse -q --verify "refs/tags/$(TAG)" >/dev/null \
		|| git ls-remote --exit-code --tags origin "refs/tags/$(TAG)" >/dev/null 2>&1; then \
		echo "release: tag $(TAG) already exists; bump the version instead" >&2; \
		exit 1; \
	fi
	@echo "release: tagging $(TAG) at $$(git rev-parse --short HEAD)"
	git push origin HEAD
	git tag -a "$(TAG)" -m "Release $(TAG)"
	git push origin "$(TAG)"
