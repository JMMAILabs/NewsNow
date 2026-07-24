# Makefile — atajos de tareas del proyecto.
# En Windows: usar Git Bash o instalar make (scoop install make). En CI (Linux) va nativo.

TF := terraform -chdir=terraform

.PHONY: help install fmt lint test run validate plan deploy destroy clean

help:  ## Muestra los targets disponibles
	@echo "make install   - instala las dependencias de desarrollo"
	@echo "make fmt       - formatea Terraform y Python"
	@echo "make lint      - ruff + terraform fmt -check"
	@echo "make test      - ejecuta los tests (pytest)"
	@echo "make run       - lanza el prototipo de IA (modo mock si no hay AWS)"
	@echo "make validate  - valida el Terraform (sin credenciales AWS)"
	@echo "make plan      - terraform plan (requiere AWS)"
	@echo "make deploy    - despliega la infraestructura (requiere AWS)"
	@echo "make destroy   - destruye la infraestructura"
	@echo "make clean     - borra artefactos locales"

install:  ## Instala las dependencias de desarrollo
	pip install boto3 pytest ruff

fmt:  ## Formatea Terraform y Python
	$(TF) fmt -recursive
	ruff format ai backend tests

lint:  ## Lint de Python + comprobación de formato de Terraform
	ruff check ai backend tests
	$(TF) fmt -check -recursive

test:  ## Ejecuta los tests
	pytest -q

run:  ## Lanza el prototipo de IA (modo mock si no hay AWS)
	python ai/prototype.py

validate:  ## Valida el Terraform (no necesita credenciales AWS)
	$(TF) init -backend=false -input=false
	$(TF) validate

plan:  ## terraform plan (requiere credenciales AWS)
	$(TF) plan

deploy:  ## Despliega la infraestructura (requiere credenciales AWS)
	$(TF) apply -auto-approve

destroy:  ## Destruye la infraestructura
	$(TF) destroy -auto-approve

clean:  ## Borra artefactos locales
	rm -rf terraform/build .pytest_cache ai/__pycache__ backend/__pycache__ tests/__pycache__
