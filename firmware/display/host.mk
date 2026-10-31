# host.mk — build the decode/render logic on a normal PC for testing,
# without the Pico SDK. The ILI9488 + Pico bits compile as no-op stubs.
#
#   make -f host.mk test      # run the pipeline test against a log
#   make -f host.mk check     # compile every module
#   make -f host.mk clean
#
# Output goes in build-host/, apart from the Pico build in build/.

CC     = gcc
CFLAGS = -DPICO_ON_DEVICE=0 -Isrc -Wall -Wextra -O2
OUT    = build-host

test: $(OUT)/testpipe
	./$(OUT)/testpipe ../../captures/session_092906.log

$(OUT)/testpipe: src/test_pipeline.c src/pr53_decode.c | $(OUT)
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

$(OUT):
	mkdir -p $(OUT)

clean:
	rm -rf $(OUT)

.PHONY: test check clean
