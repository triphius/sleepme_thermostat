# Sync the integration to the live HA OS host and reload.
# Defaults match the "Advanced SSH & Web Terminal" community add-on, where
# /config is mounted at /homeassistant inside the addon container.
#
# Usage:
#   make deploy-restart HA_HOST=100.88.154.98
# Or set in your shell / .envrc:
#   export HA_HOST=100.88.154.98

HA_HOST   ?=
HA_PORT   ?= 22
HA_USER   ?= hassio
SSH_KEY   ?= ~/.ssh/id_ed25519_ha
REMOTE_PARENT ?= /homeassistant/custom_components
REMOTE_NAME   ?= sleepme_thermostat
REMOTE_PATH   ?= $(REMOTE_PARENT)/$(REMOTE_NAME)/

SSH_OPTS  = -i $(SSH_KEY) -p $(HA_PORT) -o StrictHostKeyChecking=accept-new

.PHONY: deploy restart deploy-restart test lint typecheck

deploy:
	@test -n "$(HA_HOST)" || (echo "HA_HOST not set"; exit 1)
	# Tar-over-ssh with atomic swap. rsync is unreliable in the SSH addon's
	# Alpine container (protocol stream errors). HACS-installed files are
	# root-owned, so we use the addon's passwordless sudo to overwrite.
	# COPYFILE_DISABLE=1 prevents macOS tar from emitting ._* AppleDouble files.
	COPYFILE_DISABLE=1 tar \
	  --exclude='__pycache__' --exclude='*.pyc' --exclude='._*' --exclude='.DS_Store' \
	  -C custom_components/sleepme_thermostat -czf - . \
	  | ssh $(SSH_OPTS) $(HA_USER)@$(HA_HOST) \
	    'sudo sh -c "set -e; \
	      cd $(REMOTE_PARENT); \
	      rm -rf $(REMOTE_NAME).new $(REMOTE_NAME).old; \
	      mkdir -p $(REMOTE_NAME).new; \
	      tar -xzf - -C $(REMOTE_NAME).new --no-same-owner; \
	      chown -R root:root $(REMOTE_NAME).new; \
	      [ -d $(REMOTE_NAME) ] && mv $(REMOTE_NAME) $(REMOTE_NAME).old || true; \
	      mv $(REMOTE_NAME).new $(REMOTE_NAME); \
	      rm -rf $(REMOTE_NAME).old"'

restart:
	@test -n "$(HA_HOST)" || (echo "HA_HOST not set"; exit 1)
	ssh $(SSH_OPTS) $(HA_USER)@$(HA_HOST) 'bash -lc "ha core restart"'

deploy-restart: deploy restart

test:
	pytest --cov --cov-report=term-missing

lint:
	ruff check tests
	black --check tests

typecheck:
	mypy custom_components/sleepme_thermostat || true
