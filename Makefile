# Local release automation for korvoice.
#
# No .github/workflows/publish.yml yet: korvoice depends on GigaAM via a
# git+https direct reference (see pyproject.toml), which PyPI rejects in
# uploaded package metadata — so there's no PyPI project to trigger a
# trusted-publish release against yet. `release` here only tags and pushes;
# revisit once the GigaAM dependency story allows a real PyPI publish.
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

# Prefers, in order: a `pipx install -e .` editable install's own venv, then
# a local .venv/, then a bare `python3` on $PATH (CI, or anyone who ran
# `pip install -e '.[dev]'` into their own active environment instead).
PIPX_VENV := $(HOME)/.local/share/pipx/venvs/korvoice/bin/python
PYTHON    ?= $(shell if [ -x $(PIPX_VENV) ]; then printf '%s' '$(PIPX_VENV)'; \
                      elif [ -x .venv/bin/python ]; then printf '%s' '.venv/bin/python'; \
                      else printf '%s' 'python3'; fi)
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
TAG     := v$(VERSION)
MSG     ?= Release $(TAG)

.PHONY: help install test lint check release version

help:
	@printf '%s\n' 'Targets: install test lint check release version'

install:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

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
