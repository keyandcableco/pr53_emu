# host.mk — build the decode/render logic on a normal PC for testing,
# without the Pico SDK. The ILI9488 + Pico bits compile as no-op stubs.
#
#   make -f host.mk test      # run the pipeline test against a log
#   make -f host.mk check     # compile every module
#   make -f host.mk preview   # draw the screen for a capture moment as an image
#   make -f host.mk logo      # remake src/pr53_logo.c from logo/ (after a logo change)
#   make -f host.mk clean
#
# preview options: LOG=<capture> (default: the campaign log) and
# NOTE="text" to show the moment of the last "# NOTE" line containing it, e.g.
#   make -f host.mk preview NOTE="capture step 4: chord_root_D#"
# or AT=<seconds> for the moment at that tap time (the t= in the log), e.g.
#   make -f host.mk preview LOG=../../captures/restart_tap_v18_2026-10-31.log AT=52
# The preview takes the display as powered up at the log's first bus write, so
# a piano start-up shows the start-up logo.
# Writes build-host/preview.ppm, plus preview.png if ImageMagick is installed.
#
# Output goes in build-host/, apart from the Pico build in build/.

CC     = gcc
CFLAGS = -DPICO_ON_DEVICE=0 -Isrc -Wall -Wextra -O2
OUT    = build-host

test: $(OUT)/testpipe $(OUT)/testchords $(OUT)/testnumbers $(OUT)/testmenus $(OUT)/testsplash
	./$(OUT)/testpipe ../../captures/session_092906.log
	./$(OUT)/testchords ../../captures/campaign_2026-10-31.log ../../captures/session_064015.log
	./$(OUT)/testnumbers ../../captures/session_071830.log ../../captures/campaign_2026-10-31.log
	./$(OUT)/testmenus ../../captures/menus_2026-10-31.log ../../captures/restart_tap_v18_2026-10-31.log ../../captures/item_tens_2026-10-31.log
	./$(OUT)/testsplash ../../captures/restart_tap_v18_2026-10-31.log ../../captures/startup_2026-10-31.log $(filter-out %restart_tap_v18_2026-10-31.log %startup_2026-10-31.log,$(wildcard ../../captures/*.log))

$(OUT)/testpipe: src/test_pipeline.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

$(OUT)/testchords: src/test_chords.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

$(OUT)/testnumbers: src/test_numbers.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

$(OUT)/testmenus: src/test_menus.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

$(OUT)/testsplash: src/test_splash.c src/pr53_splash.c src/pr53_logo.c src/pr53_font.c \
                   src/pr53_ili9486_par.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

# Also compile render + font + ili stubs to catch build breakage.
$(OUT)/render_check: src/pr53_render.c src/pr53_font.c src/pr53_ili9486_par.c \
                     src/pr53_decode.c src/pr53_state.c src/pr53_splash.c src/pr53_logo.c | $(OUT)
	$(CC) $(CFLAGS) -c src/pr53_render.c  -o $(OUT)/render.o
	$(CC) $(CFLAGS) -c src/pr53_splash.c  -o $(OUT)/splash.o
	$(CC) $(CFLAGS) -c src/pr53_logo.c    -o $(OUT)/logo.o
	$(CC) $(CFLAGS) -c src/pr53_font.c    -o $(OUT)/font.o
	$(CC) $(CFLAGS) -c src/pr53_ili9486_par.c -o $(OUT)/ili.o
	$(CC) $(CFLAGS) -c src/pr53_state.c   -o $(OUT)/state.o
	$(CC) $(CFLAGS) -c src/pr53_decode.c  -o $(OUT)/decode.o
	@echo "all modules compile"

check: $(OUT)/render_check

LOG  ?= ../../captures/campaign_2026-10-31.log
NOTE ?=
AT   ?=

$(OUT)/preview: src/preview.c src/pr53_render.c src/pr53_font.c src/pr53_splash.c \
                src/pr53_logo.c src/pr53_ili9486_par.c src/pr53_decode.c | $(OUT)
	$(CC) $(CFLAGS) $^ -o $@

preview: $(OUT)/preview
	./$(OUT)/preview $(LOG) $(OUT)/preview.ppm "$(if $(AT),@$(AT),$(NOTE))"
	@if command -v convert >/dev/null; then convert $(OUT)/preview.ppm $(OUT)/preview.png && echo "wrote $(OUT)/preview.png"; fi

# The start-up logo: the site's logo 260 px tall at x 12, y 30 (the text
# column beside it is laid out in src/pr53_splash.c), and a QR code for the
# site. Needs rsvg-convert (librsvg2-bin), ImageMagick and qrencode.
LOGO_URL = https://keyandcable.com

logo: | $(OUT)
	rsvg-convert -h 260 -b white logo/keyandcable_logo.svg -o $(OUT)/logo_art.png
	convert -size 480x320 xc:white $(OUT)/logo_art.png -geometry +12+30 -composite \
	        -colorspace Gray -depth 8 $(OUT)/logo.pgm
	qrencode -l M -m 0 -t ASCII -o $(OUT)/logo_qr.txt "$(LOGO_URL)"
	python3 logo/logo_to_c.py $(OUT)/logo.pgm $(OUT)/logo_qr.txt src/pr53_logo.c

$(OUT):
	mkdir -p $(OUT)

clean:
	rm -rf $(OUT)

.PHONY: test check preview logo clean
