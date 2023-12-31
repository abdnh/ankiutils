.PHONY: fix mypy pylint test compile_reqs

fix:
	python -m black src tests
	python -m isort src tests

mypy:
	python -m mypy src tests

pylint:
	python -m pylint src tests

test:
	python -m  pytest --cov=src --cov-config=.coveragerc

compile_reqs:
	pip-compile --resolver=backtracking --allow-unsafe --no-header --strip-extras --upgrade $(FILE)
