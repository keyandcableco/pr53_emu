# host.mk — build the decode/render logic on a normal PC for testing,
# without the Pico SDK. The ILI9488 + Pico bits compile as no-op stubs.
#
#   make -f host.mk test      # run the pipeline test against a log
#   make -f host.mk check     # compile every module
#   make -f host.mk preview   # draw the screen for a capture moment as an image
#   make -f host.mk clean
#
# preview options: LOG=<capture> (default: the campaign log) and
# NOTE="text" to show the moment of the last "# NOTE" line containing it, e.g.
#   make -f host.mk preview NOTE="capture step 4: chord_root_D#"
# Writes build-host/preview.ppm, plus preview.png if ImageMagick is installed.
#
# Output goes in build-host/, apart from the Pico build in build/.

CC     = gcc
CFLAGS = -DPICO_ON_DEVICE=0 -Isrc -Wall -Wextra -O2
OUT    = build-host

test: $(OUT)/testpipe $(OUT)/testchords $(OUT)/testnumbers
	./$(OUT)/testpipe ../../captures/session_092906.log
	./$(OUT)/testchords ../../captures/campaign_2026-10-31.log
	./$(OUT)/testnumbers ../../captures/session_071830.log ../../captures/campaign_2026-10-31.log

$(OUT)/testpipe: src/test_pipeline.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

$(OUT)/testchords: src/test_chords.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

$(OUT)/testnumbers: src/test_numbers.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

# Also compile render + font + ili stubs to catch build breakage.
$(OUT)/render_check: src/pr53_render.c src/pr53_font.c src/pr53_ili9486_par.c \
                     src/pr53_decode.c src/pr53_state.c | $(OUT)
	$(CC) $(CFLAGS) -c src/pr53_render.c  -o $(OUT)/render.o
	$(CC) $(CFLAGS) -c src/pr53_font.c    -o $(OUT)/font.o
	$(CC) $(CFLAGS) -c src/pr53_ili9486_par.c -o $(OUT)/ili.o
	$(CC) $(CFLAGS) -c src/pr53_state.c   -o $(OUT)/state.o
	$(CC) $(CFLAGS) -c src/pr53_decode.c  -o $(OUT)/decode.o
	@echo "all modules compile"

check: $(OUT)/render_check

LOG  ?= ../../captures/campaign_2026-10-31.log
NOTE ?=

$(OUT)/preview: src/preview.c src/pr53_render.c src/pr53_font.c \
                src/pr53_ili9486_par.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

preview: $(OUT)/preview
	./$(OUT)/preview $(LOG) $(OUT)/preview.ppm "$(NOTE)"
	@if command -v convert >/dev/null; then convert $(OUT)/preview.ppm $(OUT)/preview.png && echo "wrote $(OUT)/preview.png"; fi

$(OUT):
	mkdir -p $(OUT)

clean:
	rm -rf $(OUT)

.PHONY: test check preview clean
