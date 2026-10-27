# smin/Makefile

all:

# Eliminate all implicit rules.
.SUFFIXES:

# Delete a target when its recipe fails.
.DELETE_ON_ERROR:

# Do not remove "intermediate" targets.
.SECONDARY:


# Ensure the directory meant to hold the output file of a recipe exists.
CREATE_OUTPUT_DIRECTORY = @mkdir -p $(dir $@)

PYTHON = python3

# To install mypy:
#   $ sudo apt install pipx
#   $ pipx install mypy
MYPY = mypy
MYPY_OPTS = --strict


PYTHON_SRCS :=
PYTHON_SRCS += smin_token.py
PYTHON_SRCS += string_util.py
PYTHON_SRCS += token_tree.py
PYTHON_SRCS += tokenize_cpp.py
PYTHON_SRCS += tokenizer.py

PYTHON_TESTS :=
PYTHON_TESTS += string_util_test.py
PYTHON_TESTS += token_tree_test.py
PYTHON_TESTS += tokenize_cpp_test.py

ALL_PYTHON_FILES = $(PYTHON_SRCS) $(PYTHON_TESTS)

all: out/mypy.ok

out/mypy/%.py.ok: %.py
	@$(CREATE_OUTPUT_DIRECTORY)
	$(MYPY) $(MYPY_OPTS) $<
	touch $@

out/mypy.ok: $(patsubst %,out/mypy/%.ok,$(ALL_PYTHON_FILES))
	$(CREATE_OUTPUT_DIRECTORY)
	touch $@


check: out/unittest.ok

out/unittest.ok: out/mypy.ok $(ALL_PYTHON_FILES)
	$(CREATE_OUTPUT_DIRECTORY)
	$(PYTHON) -m unittest -v -f $(PYTHON_TESTS)
	touch $@


check-clean:
	$(RM) -r out

clean: check-clean
	$(RM) -r .mypy_cache


# EOF
