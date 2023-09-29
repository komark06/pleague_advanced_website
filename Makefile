GIT_HOOKS := .git/hooks/commit-msg
GIT_HOOKS_APPLIED = .git/hooks/applied
GIT_HOOKS_SRC := shell_script/commit-msg.hook

all:test $(GIT_HOOKS_APPLIED)

$(GIT_HOOKS_APPLIED): $(GIT_HOOKS_SRC)
	@pre-commit install
	ln -sf ../../shell_script/commit-msg.hook $(GIT_HOOKS)
	chmod +x $(GIT_HOOKS)
	@touch $(GIT_HOOKS_APPLIED)
	@echo "Git hooks are installed."

test: $(GIT_HOOKS_APPLIED)
	pipenv run coverage run -m pytest -v
	pipenv run coverage report
