# vim: noexpandtab filetype=make

.PHONY: help test lint clean clean-build clean-pyc

VENV_NAME?=venv
VENV_ACTIVATE=. $(VENV_NAME)/bin/activate
PYTHON=${VENV_NAME}/bin/python3

.DEFAULT: help
help:
	@echo "make all"
	@echo "       prepare development environment, lint and test"
	@echo "make venv"
	@echo "       prepare development environment"
	@echo "make test"
	@echo "       run tests"
	@echo "make lint"
	@echo "       run pylint and mypy"
	@echo "make clean"
	@echo "       remove all development files and directories"

# Requirements are in setup.py, so whenever setup.py is changed, re-run installation of dependencies.
venv: $(VENV_NAME)/bin/activate
$(VENV_NAME)/bin/activate: setup.py
	test -d $(VENV_NAME) || python3 -m venv $(VENV_NAME)
	${PYTHON} -m pip install -U pip
	${PYTHON} -m pip install -e '.[dev]'
	touch $(VENV_NAME)/bin/activate

update:
	${PYTHON} -m pip install -e '.[dev]'

test: venv update
	${PYTHON} -m pytest -v -x

lint: venv
	${PYTHON} -m pylint universal_tsdb tests

all: lint test

clean: clean-build clean-pyc
	rm -rf venv

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -delete

clean-pyc:
	find . -name '*.pyc' -delete
	find . -name '*.pyo' -delete
	find . -name '*~' -delete
	find . -name '__pycache__' -exec rm -fr {} +
