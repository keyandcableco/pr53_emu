cmake_minimum_required(VERSION 3.13)
include(pico_sdk_import.cmake)
project(pr53_emu C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_executable(pr53_emu pr53_emu.c)
target_link_libraries(pr53_emu
    pico_stdlib
    pico_multicore
    hardware_pio
    hardware_clocks
)
pico_enable_stdio_usb(pr53_emu 1)
pico_enable_stdio_uart(pr53_emu 0)
pico_add_extra_outputs(pr53_emu)
