#
# The Makefile
#
SHELL         := /bin/bash
.DEFAULT_GOAL := all
TOPDOC        := README
VERSION       := $(shell awk '$$1 == "version:" { print $$2 }' ../galaxy.yml)
INCLUDES      := $(sort $(wildcard *.adoc))
THEMES        := $(sort $(wildcard resources/themes/*.yml))
#
DEPS          := $(THEMES) ../galaxy.yml

$(TOPDOC).pdf: $(TOPDOC).adoc $(INCLUDES) $(DEPS)
	@asciidoctor-pdf				\
		--doctype=book				\
		--require='asciidoctor-diagram'		\
		--trace					\
		--timings				\
		--attribute version=$(VERSION)		\
		$<

all: $(TOPDOC).pdf

clean:
	@rm -f $(TOPDOC).pdf
