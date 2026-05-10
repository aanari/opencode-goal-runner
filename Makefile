PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
BIN := target/release/opencode-goal-runner

.PHONY: build install

build:
	cargo build --release

install: build
	mkdir -p "$(BINDIR)"
	install -m 0755 "$(BIN)" "$(BINDIR)/opencode-goal-runner"
	@echo "installed $(BINDIR)/opencode-goal-runner"
	@case ":$$PATH:" in \
		*":$(BINDIR):"*) echo "$(BINDIR) is already on PATH" ;; \
		*) echo "add this to your shell profile: export PATH=\"$(BINDIR):$$PATH\"" ;; \
	esac
