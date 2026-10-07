# host.mk — build the decode/render logic on a normal PC for testing,
# without the Pico SDK. The ILI9488 + Pico bits compile as no-op stubs.
#
#   make -f host.mk test      # run the pipeline test against a log
#   make -f host.mk clean

CC     = gcc
CFLAGS = -DPICO_ON_DEVICE=0 -Isrc -Wall -Wextra -O2

test: build/testpipe
	./build/testpipe ../python/session_092906.log

build/testpipe: src/test_pipeline.c src/pr53_decode.c | build
	$(CC) $(CFLAGS) $^ -o $@

# Also compile render + font + ili stubs to catch build breakage.
build/render_check: src/pr53_render.c src/pr53_font.c src/pr53_ili9486_par.c \
                    src/pr53_decode.c src/pr53_state.c | build
	$(CC) $(CFLAGS) -c src/pr53_render.c  -o build/render.o
	$(CC) $(CFLAGS) -c src/pr53_font.c    -o build/font.o
	$(CC) $(CFLAGS) -c src/pr53_ili9486_par.c -o build/ili.o
	$(CC) $(CFLAGS) -c src/pr53_state.c   -o build/state.o
	$(CC) $(CFLAGS) -c src/pr53_decode.c  -o build/decode.o
	@echo "all modules compile"

check: build/render_check

build:
	mkdir -p build

clean:
	rm -rf build

.PHONY: test check clean
