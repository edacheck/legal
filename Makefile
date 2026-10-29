.PHONY: help build lint test check handoff bootstrap ci-package backup

help:
	@echo 'bootstrap - local pinned tools; build - HTML/PDF; lint - sources; test/check - regressions; handoff - approved public JSON'

bootstrap:
	python3 tools/bootstrap.py

build:
	python3 build.py

lint:
	python3 -B verify.py --sources

test: build
	python3 -B verify.py
	python3 -B -m unittest -v test_verification test_build test_publish test_ci test_snapshot test_release_handoff

check: lint test

handoff:
	test -n "$(HANDOFF_OUTPUT)" || (echo 'Set HANDOFF_OUTPUT to a JSON path outside the repository' >&2; exit 2)
	python3 -B tools/release_handoff.py --output "$(HANDOFF_OUTPUT)"

ci-package:
	python3 tools/site_ci.py package

backup:
	python3 tools/backup.py
