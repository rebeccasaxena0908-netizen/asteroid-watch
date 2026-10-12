PYTHON  := .venv/bin/python
HTDOCS  := /Applications/XAMPP/xamppfiles/htdocs
SITE    := $(HTDOCS)/asteroid-watch
AGENT   := com.asteroidwatch.pipeline
AGENT_PLIST := $(HOME)/Library/LaunchAgents/$(AGENT).plist

.PHONY: help install setup-db check-db test extract run backfill crosscheck deploy undeploy \
        schedule-install schedule-uninstall schedule-status schedule-run-now

help:
	@echo "make install    create .venv and install Python packages"
	@echo "make setup-db   create database, app user, tables and views (needs .env)"
	@echo "make check-db   test the MySQL connection and list tables"
	@echo "make test       run unit tests (no internet or database needed)"
	@echo "make extract    download last 7 + next 7 days of NeoWs data to data/raw/ (no DB)"
	@echo "make run        full pipeline: yesterday .. +7 days, logged in pipeline_runs"
	@echo "make backfill   full pipeline: last 365 .. +30 days (~57 calls + 500 orbit lookups)"
	@echo "make crosscheck compare a sample with NASA JPL CAD; writes docs/jpl_crosscheck.md"
	@echo "make deploy     copy dashboard/ to $(SITE)"
	@echo "make undeploy   remove $(SITE)"
	@echo "make schedule-install / schedule-uninstall / schedule-status / schedule-run-now"
	@echo "                daily 09:00 launchd job (see scheduler/README.md)"

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

setup-db:
	$(PYTHON) -m pipeline.setup_db

check-db:
	$(PYTHON) -m pipeline.db

test:
	$(PYTHON) -m pytest -q

extract:
	$(PYTHON) -m pipeline.extract --backfill-days 7 --forward-days 7

run:
	$(PYTHON) -m pipeline.run_pipeline --backfill-days 1 --forward-days 7

backfill:
	$(PYTHON) -m pipeline.run_pipeline --backfill-days 365 --forward-days 30 --orbital-limit 500 --run-type backfill

crosscheck:
	$(PYTHON) -m pipeline.jpl_crosscheck --sample 50 --days 10

# Copy, not symlink: Apache runs as user 'daemon', which cannot read inside
# /Users/<you> (home folder is drwxr-x---), so a symlink gives HTTP 403.
deploy:
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
