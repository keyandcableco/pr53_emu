# CMakeLists.txt — RP2350 build for the PR53 display firmware.
#
# Usage:
#   export PICO_SDK_PATH=~/pico-sdk
#   mkdir build && cd build
#   cmake -DPICO_BOARD=pico2 ..
#   make
#
# Produces pr53_fw.uf2 to drag onto the Pico 2.

cmake_minimum_required(VERSION 3.13)

include($ENV{PICO_SDK_PATH}/pico_sdk_init.cmake)

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
    src/bus_tap.c   # <-- TEMPORARY stub for first-light. Replace with your v15 PIO capture.
)

target_compile_definitions(pr53_fw PRIVATE PICO_ON_DEVICE=1)

target_link_libraries(pr53_fw
    pico_stdlib
    pico_multicore
    hardware_gpio
    hardware_sync
    hardware_uart
    # hardware_pio   # <-- for your bus-tap PIO
)

pico_add_extra_outputs(pr53_fw)

# Route printf to USB so you can debug.
pico_enable_stdio_usb(pr53_fw 1)
pico_enable_stdio_uart(pr53_fw 0)
