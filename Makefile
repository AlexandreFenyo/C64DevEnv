# Makefile - environnement de développement C64 (cc65 + VICE x64sc)
#
# Un "programme" est un sous-répertoire de src/ ou examples/ contenant des
# sources .s (ca65) et/ou .c (cc65). Son nom est celui du répertoire.
# Un fichier isolé src/foo.s ou src/foo.c est aussi un programme "foo".
#
# Cibles :
#   make            compile tout : build/<prog>.prg + build/<prog>.labels
#   make run PROG=x lance build/x.prg dans VICE (fenêtre visible)
#   make debug PROG=x   idem avec le moniteur binaire (port 6502) + labels
#   make test       exécute tests/run_tests.sh
#   make clean      arrête VICE puis supprime build/
#   make list       liste les programmes détectés
#   make portal     démarre le portail web (http://localhost:8064)
#   make portal-stop    arrête le portail
#   make vscode     installe l'extension VS Code (débogage, tools/vscode/)
#
# Le portail (tools/portal.py) déclare les cibles qu'il utilise : toute cible
# .PHONY ajoutée ou supprimée doit y être reportée (make test le vérifie).
#
# Variables utiles : RUNFLAGS="--headless --warp" pour make run/debug.

SRC_DIRS   := src examples
BUILD      := build
TOOLS      := tools

CC65_TARGET := c64
CL65        ?= cl65
CFLAGS      ?= -O
ASFLAGS     ?=
LDFLAGS     ?=
DEBUGFLAGS  ?= -g            # symboles locaux dans les fichiers de labels

# Programmes en répertoire : src/foo/, examples/bar/
PROG_DIRS  := $(sort $(patsubst %/,%,$(dir $(wildcard $(addsuffix /*/*.s,$(SRC_DIRS)) $(addsuffix /*/*.c,$(SRC_DIRS))))))
# Programmes en fichier isolé : src/foo.s, src/foo.c
PROG_FILES := $(wildcard $(addsuffix /*.s,$(SRC_DIRS)) $(addsuffix /*.c,$(SRC_DIRS)))

PROGS      := $(sort $(notdir $(PROG_DIRS)) $(basename $(notdir $(PROG_FILES))))
PRGS       := $(addprefix $(BUILD)/,$(addsuffix .prg,$(PROGS)))
LABELS     := $(addprefix $(BUILD)/,$(addsuffix .labels,$(PROGS)))

.PHONY: all clean run debug test list install portal portal-stop vscode
.DELETE_ON_ERROR:

all: $(PRGS) $(LABELS)
	@echo "Build OK : $(PROGS)"

list:
	@for p in $(PROGS); do echo $$p; done

$(BUILD):
	@mkdir -p $(BUILD)

# Génère une règle de compilation par programme. Les sources asm pures sont
# liées avec c64-asm.cfg + __EXEHDR__ (en-tête BASIC SYS). Dès qu'il y a du
# C, on utilise la configuration standard c64.cfg et le runtime cc65.
# build/<prog>.dbg : infos de débogage ld65 (adresse <-> fichier:ligne), lues
# par dbg.py (where, lines, disasm) et par la vue Code du portail.
define PROG_RULE
$(BUILD)/$(1).prg $(BUILD)/$(1).lbl $(BUILD)/$(1).dbg: $(2) | $(BUILD)
	@echo "== $(1) : $(2)"
	$(CL65) -t $(CC65_TARGET) $(DEBUGFLAGS) $(CFLAGS) $(ASFLAGS) $(LDFLAGS) \
	    $(if $(filter %.c,$(2)),,-C c64-asm.cfg -u __EXEHDR__) \
	    -Ln $(BUILD)/$(1).lbl -m $(BUILD)/$(1).map -Wl --dbgfile,$(BUILD)/$(1).dbg \
	    -o $(BUILD)/$(1).prg $(2)
	@rm -f $(patsubst %.s,%.o,$(patsubst %.c,%.o,$(2)))
endef

# Sources d'un programme-répertoire : tous ses .s et .c (ordre : .s puis .c,
# triés, pour que le point d'entrée asm reste le premier fichier lié).
prog_dir_sources = $(sort $(wildcard $(1)/*.s)) $(sort $(wildcard $(1)/*.c))

$(foreach d,$(PROG_DIRS),$(eval $(call PROG_RULE,$(notdir $(d)),$(call prog_dir_sources,$(d)))))
$(foreach f,$(PROG_FILES),$(eval $(call PROG_RULE,$(basename $(notdir $(f))),$(f))))

$(BUILD)/%.labels: $(BUILD)/%.lbl $(TOOLS)/mklabels.py
	@python3 $(TOOLS)/mklabels.py $< $@

clean:
	@$(TOOLS)/stop.sh --quiet || true   # VICE et dbg.py utilisent build/
	rm -rf $(BUILD)
	find $(SRC_DIRS) -name '*.o' -delete 2>/dev/null || true

# ---------------------------------------------------------------------------
# Exécution
# ---------------------------------------------------------------------------
PROG     ?= hello
RUNFLAGS ?=

run: all
	@test -f $(BUILD)/$(PROG).prg || { echo "make run : programme inconnu '$(PROG)' (make list)"; exit 1; }
	$(TOOLS)/run.sh --show $(RUNFLAGS) $(BUILD)/$(PROG).prg

debug: all
	@test -f $(BUILD)/$(PROG).prg || { echo "make debug : programme inconnu '$(PROG)' (make list)"; exit 1; }
	$(TOOLS)/run.sh --show --monitor $(RUNFLAGS) $(BUILD)/$(PROG).prg

test: all
	tests/run_tests.sh

install:
	$(TOOLS)/install.sh

portal:
	$(TOOLS)/portal.sh start

portal-stop:
	$(TOOLS)/portal.sh stop

vscode:
	$(TOOLS)/vscode-install.sh
