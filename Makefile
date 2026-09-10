REMOTE_USER = pfun
REMOTE_HOST = 192.168.1.210
REMOTE_DIR = /opt/pfun
SSH = ssh $(REMOTE_USER)@$(REMOTE_HOST)

APP_FILES = app.py requirements.txt pfun.service refresh_roster.py \
            2026_f1_races.json 2026_f1_drivers.json roster_overrides.json

DIRS = templates static flags data fastf1_cache

.PHONY: deploy

deploy:
	# Create remote directory structure
	$(SSH) "sudo mkdir -p $(REMOTE_DIR) && sudo chown $(REMOTE_USER):$(REMOTE_USER) $(REMOTE_DIR)"

	# Copy application files
	scp $(APP_FILES) $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/

	# Sync directories (templates, static, flags, fastf1_cache)
	rsync -az --delete templates/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/templates/
	rsync -az --delete static/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/static/
	rsync -az --delete flags/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/flags/
	rsync -az fastf1_cache/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/fastf1_cache/

	# Copy data files only if they don't already exist on the target
	$(SSH) "mkdir -p $(REMOTE_DIR)/data"
	$(SSH) "test -f $(REMOTE_DIR)/data/predictions.json" || \
		scp data/predictions.json $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/data/
	$(SSH) "test -f $(REMOTE_DIR)/data/results.json" || \
		scp data/results.json $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/data/

	# Write the OpenCode Go API key into the (gitignored) remote env file,
	# picking it up from the local shell environment.
	$(SSH) "grep -q OPENCODE_GO_API_KEY $(REMOTE_DIR)/env 2>/dev/null || \
		echo 'OPENCODE_GO_API_KEY=$$OPENCODE_GO_API_KEY' > $(REMOTE_DIR)/env && chmod 600 $(REMOTE_DIR)/env"

	# Set up Python virtual environment and install dependencies
	$(SSH) "cd $(REMOTE_DIR) && (test -d venv || python3 -m venv venv) && venv/bin/pip install -q -r requirements.txt"

	# Install and enable systemd service
	$(SSH) "sudo cp $(REMOTE_DIR)/pfun.service /etc/systemd/system/ && \
		sudo systemctl daemon-reload && \
		sudo systemctl enable pfun && \
		sudo systemctl restart pfun"

	@echo "Deploy complete. Service running at http://$(REMOTE_HOST)"

.PHONY: pull-data

pull-data:
	mkdir -p data
	rsync -az $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_DIR)/data/ data/
	@echo "Pulled live data files into data/"

.PHONY: refresh-roster

# Dry run by default; apply with: make refresh-roster ARGS=--write
refresh-roster:
	@python refresh_roster.py $(ARGS)
