.PHONY: help build lint test bootstrap ci-package backup

help:
	@echo 'bootstrap - local pinned tools; build - HTML/PDF; lint - sources; test - regressions; ci-package - verified Pages artifact'

bootstrap:
	python3 tools/bootstrap.py

build:
	python3 build.py

lint:
	python3 -B verify.py --sources

test: build
	python3 -B verify.py
	python3 -B -m unittest -v test_verification test_build test_publish test_ci test_snapshot

ci-package:
	python3 tools/site_ci.py package

backup:
	python3 tools/backup.py
