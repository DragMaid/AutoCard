VENV := .venv


# --- Detect OS and paths ---
ifeq ($(OS),Windows_NT)
PYTHON ?= py
VENV_PY := $(VENV)/Scripts/python.exe
PATHSEP := \\
RM := rmdir /s /q
ENV_CMD := set PYTHONPATH=%CD% &&
else
PYTHON := python3
VENV_PY := $(VENV)/bin/python
PATHSEP := /
RM := rm -rf
ENV_CMD := PYTHONPATH=$(PWD)
endif

# Use venv python if available
ifeq ("$(wildcard $(VENV_PY))","")
RUN_PY := $(PYTHON)
else
RUN_PY := $(VENV_PY)
endif

# Select PyTorch wheel index
ifeq ($(OS),Windows_NT)
PYTORCH_INDEX := --index-url https://download.pytorch.org/whl/cu128
else
PYTORCH_INDEX := --index-url https://download.pytorch.org/whl/cpu
endif


.PHONY: venv install run db train runrm saverm trainrm test lint clean help

help:
	@echo "Usage: make [venv|install|run|train|test|lint|clean|trainrm]"


venv:
	$(PYTHON) -m venv $(VENV)
	@echo "✅ Virtual environment created at $(VENV)"


install: venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt
	$(VENV_PY) -m pip install torch torchvision $(PYTORCH_INDEX)


run:
	$(RUN_PY) main.py


db:
	docker compose -f ml/docker-compose.yaml down -v
	docker compose -f ml/docker-compose.yaml up -d


.PHONY: train
train:
	$(RUN_PY) -m ml.main


# --- Safe cross-platform removal ---
runrm:
	$(RUN_PY) scripts/make_utils.py rmpath ml$(PATHSEP)mlruns

saverm:
	$(RUN_PY) scripts/make_utils.py rmpath ml$(PATHSEP)saves

trainrm: runrm saverm


# --- Tests ---
test:
	$(RUN_PY) -m pip install pytest --quiet
	$(ENV_CMD) $(RUN_PY) -m pytest --rootdir=. -s


lint:
	$(RUN_PY) -m pip install flake8 --quiet
	$(RUN_PY) -m flake8 .


# --- Clean all ---
clean: trainrm
	$(RUN_PY) scripts/make_utils.py clean