PYTHON  := .venv/bin/python
CLI     := .venv/bin/asteroid-watch
HTDOCS  := /Applications/XAMPP/xamppfiles/htdocs
SITE    := $(HTDOCS)/asteroid-watch
AGENT   := com.asteroidwatch.pipeline
AGENT_PLIST := $(HOME)/Library/LaunchAgents/$(AGENT).plist
API_AGENT := com.asteroidwatch.api
API_PLIST := $(HOME)/Library/LaunchAgents/$(API_AGENT).plist
PREFECT_AGENTS := com.asteroidwatch.prefect-server com.asteroidwatch.prefect-worker

.PHONY: help install requirements lint hooks scan-secrets setup-db migrate check-db status test api-test extract run quick-run backfill crosscheck serve parity-test legacy-deploy legacy-undeploy \
        api-install api-uninstall api-status api-restart \
        prefect-server prefect-worker flow-run-now prefect-install prefect-uninstall prefect-status \
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
	@echo "make test       run unit tests (no internet or database needed)"
	@echo "make api-test   integration tests: FastAPI and schema against MySQL (needs XAMPP MySQL)"
	@echo "make parity-test  legacy PHP API vs FastAPI, byte for byte (needs make legacy-deploy)"
	@echo "make extract    download last 7 + next 7 days of NeoWs data to data/raw/ (no DB)"
	@echo "make run        full pipeline: yesterday .. +7 days, logged in pipeline_runs"
	@echo "make quick-run  same as run but no orbit lookups (a few seconds; good for a live demo)"
	@echo "make backfill   full pipeline: last 365 .. +30 days (~57 calls + 500 orbit lookups)"
	@echo "make crosscheck compare a sample with NASA JPL CAD; writes docs/jpl_crosscheck.md"
	@echo "make serve      dashboard + API at http://localhost:8010 (docs at /docs); Ctrl-C to stop"
	@echo "make api-install / api-uninstall / api-status / api-restart"
	@echo "                keep the server running with launchd (see scheduler/README.md)"
	@echo "make legacy-deploy / legacy-undeploy   the retired PHP API on XAMPP (for parity tests)"
	@echo "make prefect-server / prefect-worker   run Prefect in the terminal (UI: http://127.0.0.1:4200)"
	@echo "make flow-run-now   run the daily Prefect flow now (needs the server and worker)"
	@echo "make prefect-install / prefect-uninstall / prefect-status"
	@echo "                keep the Prefect server and worker running with launchd (daily 19:00 IST)"
	@echo "make schedule-install / schedule-uninstall / schedule-status / schedule-run-now"
	@echo "                the old v1 daily 09:00 launchd job (replaced by Prefect; see scheduler/README.md)"

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

parity-test:
	$(CLI) test --parity

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

serve:
	$(CLI) serve

# The retired PHP API (legacy/php/), only for the parity tests. Copy, not symlink: Apache runs as
# user 'daemon', which cannot read inside /Users/<you> (home folder is drwxr-x---), so a symlink
# gives HTTP 403. The PHP API's DB config (read-only user) goes outside the web root; see
# pipeline/dashboard_config.py. Only api/ and includes/ are replaced; nothing else in $(SITE).
legacy-deploy:
	$(PYTHON) -m pipeline.dashboard_config
	mkdir -p $(SITE)
	rsync -a --delete legacy/php/api/ $(SITE)/api/
	rsync -a --delete legacy/php/includes/ $(SITE)/includes/
	cp legacy/php/.htaccess $(SITE)/.htaccess
	@echo "Legacy PHP API at http://localhost/asteroid-watch/api/*.php"

legacy-undeploy:
	rm -rf $(SITE)

# API server kept running by launchd (http://localhost:8010). See scheduler/README.md.
api-install:
	mkdir -p logs $(HOME)/Library/LaunchAgents
	sed "s|__PROJECT_DIR__|$(CURDIR)|g" scheduler/$(API_AGENT).plist > $(API_PLIST)
	plutil -lint $(API_PLIST)
	launchctl bootstrap gui/$$(id -u) $(API_PLIST)
	@echo "Installed: http://localhost:8010 (starts at login). Check with: make api-status"

api-uninstall:
	-launchctl bootout gui/$$(id -u)/$(API_AGENT)
	rm -f $(API_PLIST)
	@echo "Uninstalled."

api-status:
	@launchctl print gui/$$(id -u)/$(API_AGENT) 2>/dev/null | grep -E "state =|pid =|last exit code|runs =" \
		|| echo "Not installed."

api-restart:
	launchctl kickstart -k gui/$$(id -u)/$(API_AGENT)
	@echo "Restarted. Logs: logs/api.err.log"

# Prefect (v2): the server keeps the 19:00 IST schedule and run history; the worker runs the flows.
prefect-server:
	.venv/bin/prefect server start

prefect-worker:
	$(PYTHON) -m flows.serve

flow-run-now:
	.venv/bin/prefect deployment run 'neows-daily/daily-19-ist' --watch

prefect-install:
	mkdir -p logs $(HOME)/Library/LaunchAgents
	for a in $(PREFECT_AGENTS); do \
		sed "s|__PROJECT_DIR__|$(CURDIR)|g" scheduler/$$a.plist > $(HOME)/Library/LaunchAgents/$$a.plist && \
		plutil -lint $(HOME)/Library/LaunchAgents/$$a.plist && \
		launchctl bootstrap gui/$$(id -u) $(HOME)/Library/LaunchAgents/$$a.plist || exit 1; \
	done
	@echo "Installed. UI: http://127.0.0.1:4200  Check with: make prefect-status"

prefect-uninstall:
	-for a in $(PREFECT_AGENTS); do launchctl bootout gui/$$(id -u)/$$a; rm -f $(HOME)/Library/LaunchAgents/$$a.plist; done
	@echo "Uninstalled."

prefect-status:
	@for a in $(PREFECT_AGENTS); do echo "$$a:"; \
		launchctl print gui/$$(id -u)/$$a 2>/dev/null | grep -E "state =|pid =|last exit code" || echo "  not installed"; done

# The old v1 daily launchd job (09:00). Replaced by Prefect; see scheduler/README.md.
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
