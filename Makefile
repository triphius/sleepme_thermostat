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
REMOTE_PATH ?= /homeassistant/custom_components/sleepme_thermostat/

SSH_OPTS  = -i $(SSH_KEY) -p $(HA_PORT) -o StrictHostKeyChecking=accept-new

.PHONY: deploy restart deploy-restart test lint typecheck

deploy:
	@test -n "$(HA_HOST)" || (echo "HA_HOST not set"; exit 1)
	rsync -avz --delete \
	  -e "ssh $(SSH_OPTS)" \
	  --exclude '__pycache__' --exclude '*.pyc' \
	  custom_components/sleepme_thermostat/ \
	  $(HA_USER)@$(HA_HOST):$(REMOTE_PATH)

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
