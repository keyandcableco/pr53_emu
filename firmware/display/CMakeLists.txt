# Display firmware for the Pico 2: decodes the stream from the tap and draws
# the PR53 glass on the HiLetgo 3.5" parallel panel.
#
#   export PICO_SDK_PATH=$HOME/pico-sdk     # or pass -DPICO_SDK_PATH=...
#   mkdir build && cd build
#   cmake -DPICO_BOARD=pico2 ..
#   make -j
#
# Produces pr53_fw.uf2.

cmake_minimum_required(VERSION 3.13)

include(${CMAKE_CURRENT_LIST_DIR}/../pico_sdk_import.cmake)

project(pr53_fw C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(pr53_fw
    src/main.c
    src/pr53_state.c
    src/pr53_decode.c
    src/pr53_render.c
    src/pr53_font.c
    src/pr53_ili9486_par.c
    src/bus_tap.c   # UART receiver for the tap link (GP21)
)

target_compile_definitions(pr53_fw PRIVATE PICO_ON_DEVICE=1)

target_link_libraries(pr53_fw
    pico_stdlib
    pico_multicore
    hardware_gpio
    hardware_sync
    hardware_uart
)

pico_add_extra_outputs(pr53_fw)

# Route printf to USB so you can debug.
pico_enable_stdio_usb(pr53_fw 1)
pico_enable_stdio_uart(pr53_fw 0)

# Colour bring-up screen for the panel (see src/colour_test.c):
# pr53_colour_test.uf2. Flash it, photograph the screen, flash pr53_fw back.
add_executable(pr53_colour_test
    src/colour_test.c
    src/pr53_font.c
    src/pr53_ili9486_par.c
)
target_compile_definitions(pr53_colour_test PRIVATE PICO_ON_DEVICE=1)
target_link_libraries(pr53_colour_test pico_stdlib hardware_gpio)
pico_add_extra_outputs(pr53_colour_test)
pico_enable_stdio_usb(pr53_colour_test 1)
pico_enable_stdio_uart(pr53_colour_test 0)
