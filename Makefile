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

# $ pipx install ruff
RUFF = ruff


PYTHON_SRCS :=
PYTHON_SRCS += acceptance_test_result.py
PYTHON_SRCS += build_tree.py
PYTHON_SRCS += build_tree_util.py
PYTHON_SRCS += check_accept.py
PYTHON_SRCS += group_delimiters.py
PYTHON_SRCS += group_indentation.py
PYTHON_SRCS += group_lines.py
PYTHON_SRCS += group_paragraphs.py
PYTHON_SRCS += minimizer.py
PYTHON_SRCS += smin_token.py
PYTHON_SRCS += string_util.py
PYTHON_SRCS += test_util.py
PYTHON_SRCS += token_tree.py
PYTHON_SRCS += tokenize_cpp.py
PYTHON_SRCS += tokenizer.py

PYTHON_TESTS :=
PYTHON_TESTS += build_tree_test.py
PYTHON_TESTS += check_accept_test.py
PYTHON_TESTS += group_delimiters_test.py
PYTHON_TESTS += group_indentation_test.py
PYTHON_TESTS += group_lines_test.py
PYTHON_TESTS += group_paragraphs_test.py
PYTHON_TESTS += minimizer_test.py
PYTHON_TESTS += string_util_test.py
PYTHON_TESTS += test_util_test.py
PYTHON_TESTS += token_tree_test.py
PYTHON_TESTS += tokenize_cpp_test.py

ALL_PYTHON_FILES = $(PYTHON_SRCS) $(PYTHON_TESTS)


all: out/mypy.ok

# Run $(MYPY) on all files whenever any one of them changes to ensure
# that a change in one file that breaks another will be caught.
out/mypy.ok: $(ALL_PYTHON_FILES)
	$(CREATE_OUTPUT_DIRECTORY)
	$(MYPY) $(MYPY_OPTS) $(ALL_PYTHON_FILES)
	touch $@


all: out/ruff.ok

out/ruff.ok: $(PYTHON_SRCS) $(PYTHON_TESTS) ruff.toml
	$(CREATE_OUTPUT_DIRECTORY)
	$(RUFF) check .
	touch $@


check: out/unittest.ok

out/unittest.ok: out/mypy.ok out/ruff.ok $(ALL_PYTHON_FILES)
	$(CREATE_OUTPUT_DIRECTORY)
	$(PYTHON) -m unittest -v -f $(PYTHON_TESTS)
	touch $@


check-clean:
	$(RM) -r out

clean: check-clean
	$(RM) -r .mypy_cache


# EOF
