GIT_HOOKS := .git/hooks/commit-msg

all: $(GIT_HOOKS)

$(GIT_HOOKS):
	@pre-commit install
	@ln -s -f shell_script/commit-msg.hook $(GIT_HOOKS)
	@echo "Git hooks are installed."