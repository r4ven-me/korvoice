# Local release automation for korvoice.
#
# Pushing the version tag created by `release` triggers
# .github/workflows/publish.yml, which tests, builds and publishes to PyPI
# through trusted publishing. Configure the `pypi` GitHub environment and
# matching PyPI trusted publisher before the first release.
#
# No typecheck target: per this author's convention, strict mypy is for
# server/backend projects, optional for a small GUI utility like this one —
# see pyproject.toml's [project.optional-dependencies] comment. kortalk,
# the reference project korvoice is patterned after, skips it the same way.
#
# Usage:
#   make check                          # lint + test
#   make release                        # check, commit if dirty, tag vX.Y.Z, push
#   make release MSG="Fix hotkeys"      # custom commit message (used only if there
#                                        # are uncommitted changes to commit)
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
MSG     ?= Release $(TAG)

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

# Tags the version currently in pyproject.toml and pushes it. Refuses to
# re-tag a version that was already released — bump pyproject.toml first.
release: check
	@if [ -n "$$(git status --porcelain)" ]; then \
		git add -A; \
		git commit -m "$(MSG)"; \
	fi
	@if git rev-parse "$(TAG)" >/dev/null 2>&1; then \
		echo "release: tag $(TAG) already exists -- bump the version in pyproject.toml first" >&2; \
		exit 1; \
	fi
	git push origin HEAD
	git tag -a "$(TAG)" -m "Release $(TAG)"
	git push origin "$(TAG)"
