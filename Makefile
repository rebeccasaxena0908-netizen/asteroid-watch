PYTHON  := .venv/bin/python
CLI     := .venv/bin/asteroid-watch
HTDOCS  := /Applications/XAMPP/xamppfiles/htdocs
SITE    := $(HTDOCS)/asteroid-watch
AGENT   := com.asteroidwatch.pipeline
AGENT_PLIST := $(HOME)/Library/LaunchAgents/$(AGENT).plist

.PHONY: help install requirements lint hooks scan-secrets setup-db migrate check-db status test api-test extract run quick-run backfill crosscheck deploy undeploy \
        schedule-install schedule-uninstall schedule-status schedule-run-now

help:
	@echo "make install    create .venv and install the project + dev tools (from pyproject.toml)"
	@echo "make requirements  regenerate requirements.txt from pyproject.toml"
	@echo "make lint       ruff + mypy"
	@echo "make hooks      install the git pre-commit hooks (secret scan, lint, type check)"
	@echo "make scan-secrets  check every tracked file for secrets from .env"
	@echo "make setup-db   create database, app user, tables and views (needs .env)"
	@echo "make migrate    apply database migrations (Alembic)"
	@echo "make check-db   test the MySQL connection and list tables"
	@echo "make status     last run per source, row counts, schema version"
	@echo "               (all targets below call the asteroid-watch CLI; see: $(CLI) --help)"
	@echo "make test       run unit tests (no internet or database needed)"
	@echo "make api-test   test the deployed PHP API against MySQL (needs XAMPP + make deploy)"
	@echo "make extract    download last 7 + next 7 days of NeoWs data to data/raw/ (no DB)"
	@echo "make run        full pipeline: yesterday .. +7 days, logged in pipeline_runs"
	@echo "make quick-run  same as run but no orbit lookups (a few seconds; good for a live demo)"
	@echo "make backfill   full pipeline: last 365 .. +30 days (~57 calls + 500 orbit lookups)"
	@echo "make crosscheck compare a sample with NASA JPL CAD; writes docs/jpl_crosscheck.md"
	@echo "make deploy     write dashboard DB config, copy dashboard/ to $(SITE)"
	@echo "make undeploy   remove $(SITE)"
	@echo "make schedule-install / schedule-uninstall / schedule-status / schedule-run-now"
	@echo "                daily 09:00 launchd job (see scheduler/README.md)"

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

requirements:
	$(PYTHON) -m scripts.gen_requirements

lint:
	.venv/bin/ruff check .
	.venv/bin/mypy

hooks:
	.venv/bin/pre-commit install

scan-secrets:
	git ls-files -z | xargs -0 $(PYTHON) -m scripts.check_secrets && echo "No secrets found."

setup-db:
	$(CLI) setup-db

migrate:
	$(CLI) migrate

check-db:
	$(CLI) check-db

status:
	$(CLI) status

test:
	$(CLI) test

api-test:
	$(CLI) test --api

extract:
	$(PYTHON) -m pipeline.extract --backfill-days 7 --forward-days 7

run:
	$(CLI) run

quick-run:
	$(CLI) quick-run

backfill:
	$(CLI) backfill

crosscheck:
	$(CLI) crosscheck

# Copy, not symlink: Apache runs as user 'daemon', which cannot read inside
# /Users/<you> (home folder is drwxr-x---), so a symlink gives HTTP 403.
# The dashboard's DB config (read-only user) goes outside the web root; see pipeline/dashboard_config.py.
deploy:
	$(PYTHON) -m pipeline.dashboard_config
	mkdir -p $(SITE)
	rsync -a --delete dashboard/ $(SITE)/
	@echo "Deployed to http://localhost/asteroid-watch"

undeploy:
	rm -rf $(SITE)

# Daily launchd job. See scheduler/README.md.
schedule-install:
	mkdir -p logs $(HOME)/Library/LaunchAgents
	sed "s|__PROJECT_DIR__|$(CURDIR)|g" scheduler/$(AGENT).plist > $(AGENT_PLIST)
	plutil -lint $(AGENT_PLIST)
	launchctl bootstrap gui/$$(id -u) $(AGENT_PLIST)
	@echo "Installed: runs daily at 09:00. Check with: make schedule-status"

schedule-uninstall:
	-launchctl bootout gui/$$(id -u)/$(AGENT)
	rm -f $(AGENT_PLIST)
	@echo "Uninstalled."

schedule-status:
	@launchctl print gui/$$(id -u)/$(AGENT) 2>/dev/null | grep -E "state =|last exit code|runs =" \
		|| echo "Not installed."

schedule-run-now:
	launchctl kickstart gui/$$(id -u)/$(AGENT)
	@echo "Started. Follow with: tail -f logs/pipeline.log"
