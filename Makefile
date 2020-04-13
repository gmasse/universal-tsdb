# vim: noexpandtab filetype=make

.PHONY: help update test lint all build publish-test publish clean clean-build clean-pyc

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
	@echo "       run pylint"
	@echo "make clean"
	@echo "       remove all development files and directories"
	@echo "make build"
	@echo "       build distribution packages"
	@echo "make publish-test"
	@echo "       upload distribution archives to TestPyPI"
	@echo "make publish"
	@echo "       upload distribution archives to PyPI"

# Requirements are in setup.py, so whenever setup.py is changed, re-run installation of dependencies.
venv: $(VENV_NAME)/bin/activate
$(VENV_NAME)/bin/activate: setup.py
	test -d $(VENV_NAME) || python3 -m venv $(VENV_NAME)
	${PYTHON} -m pip install -U pip
	${PYTHON} -m pip install -e '.[dev]'
	touch $(VENV_NAME)/bin/activate

update: venv
	${PYTHON} -m pip install -e '.[dev]'

test: venv update
	${PYTHON} -m pytest

lint: venv
	${PYTHON} -m pylint universal_tsdb tests

all: update lint test

build: venv
	${PYTHON} -m pip install -U setuptools wheel
	${PYTHON} setup.py sdist bdist_wheel

publish-test: venv build
	${PYTHON} -m pip install -U twine
	${PYTHON} -m twine upload https://test.pypi.org/legacy/ dist/*

publish: venv build
	${PYTHON} -m pip install -U twine
	${PYTHON} -m twine upload dist/*

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
