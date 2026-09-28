.PHONY: setup gate full test loop status doctor
setup:
	uv sync --all-groups
gate:
	uv run mfos gate --fast
full:
	uv run mfos gate --full
test:
	uv run pytest -q tests
loop:
	uv run mfos loop
status:
	uv run mfos status
doctor:
	uv run mfos doctor
