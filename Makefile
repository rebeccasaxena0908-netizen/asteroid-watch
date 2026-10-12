PYTHON  := .venv/bin/python
HTDOCS  := /Applications/XAMPP/xamppfiles/htdocs
SITE    := $(HTDOCS)/asteroid-watch

.PHONY: help install setup-db check-db test extract run backfill deploy undeploy

help:
	@echo "make install    create .venv and install Python packages"
	@echo "make setup-db   create database, app user, tables and views (needs .env)"
	@echo "make check-db   test the MySQL connection and list tables"
	@echo "make test       run unit tests (no internet or database needed)"
	@echo "make extract    download last 7 + next 7 days of NeoWs data to data/raw/ (no DB)"
	@echo "make run        full pipeline: yesterday .. +7 days, logged in pipeline_runs"
	@echo "make backfill   full pipeline: last 365 .. +30 days (~57 calls + 500 orbit lookups)"
	@echo "make deploy     copy dashboard/ to $(SITE)"
	@echo "make undeploy   remove $(SITE)"

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

# Copy, not symlink: Apache runs as user 'daemon', which cannot read inside
# /Users/<you> (home folder is drwxr-x---), so a symlink gives HTTP 403.
deploy:
	mkdir -p $(SITE)
	rsync -a --delete dashboard/ $(SITE)/
	@echo "Deployed to http://localhost/asteroid-watch"

undeploy:
	rm -rf $(SITE)
