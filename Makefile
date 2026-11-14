# AgroTwin — AI-generated (Claude, Anthropic) under human review.
PY ?= $(HOME)/.venvs/verdex/bin/python

test:            ## unit tests + contract checks
	$(PY) -m pytest -q -p no:cacheprovider tests/

validate:        ## the validation wall → qa/REPORT.md + qa/REPORT.json
	$(PY) qa/validate.py

demo:            ## run the app on cached data only (stage mode)
	./run.sh offline

precache:        ## download NASA data for every demo site
	$(PY) scripts/precache.py

.PHONY: test validate demo precache
