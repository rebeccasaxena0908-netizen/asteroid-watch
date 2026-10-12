PYTHON  := .venv/bin/python
HTDOCS  := /Applications/XAMPP/xamppfiles/htdocs
SITE    := $(HTDOCS)/asteroid-watch

.PHONY: help install setup-db check-db test extract deploy undeploy

help:
	@echo "make install    create .venv and install Python packages"
	@echo "make setup-db   create database, app user, tables and views (needs .env)"
	@echo "make check-db   test the MySQL connection and list tables"
	@echo "make test       run unit tests (no internet or database needed)"
	@echo "make extract    download last 7 + next 7 days of NeoWs data to data/raw/"
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

# Copy, not symlink: Apache runs as user 'daemon', which cannot read inside
# /Users/<you> (home folder is drwxr-x---), so a symlink gives HTTP 403.
deploy:
	mkdir -p $(SITE)
	rsync -a --delete dashboard/ $(SITE)/
	@echo "Deployed to http://localhost/asteroid-watch"

undeploy:
	rm -rf $(SITE)
