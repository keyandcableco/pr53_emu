# Tap firmware (v16) for the RP2350-Zero.
#
# Reads the piano's HD44780 bus, answers its read cycles, logs every write
# over USB, and forwards each write to the display Pico over a one-way UART
# (uart1 TX on GP8 -> display GP21).
#
#   export PICO_SDK_PATH=$HOME/pico-sdk     # or pass -DPICO_SDK_PATH=...
#   mkdir build && cd build
#   cmake -DPICO_BOARD=pico2 ..
#   make -j
#
# Produces pr53_emu.uf2. The Zero is an RP2350A, so it builds as pico2.

cmake_minimum_required(VERSION 3.13)
include(${CMAKE_CURRENT_LIST_DIR}/../pico_sdk_import.cmake)
project(pr53_emu C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_executable(pr53_emu
    src/pr53_emu.c
)

target_link_libraries(pr53_emu
    pico_stdlib
    pico_multicore
    hardware_pio
    hardware_gpio
    hardware_uart      # display link
)

pico_add_extra_outputs(pr53_emu)

# Log over USB only. UART stdio must stay off: GP0/GP1 are capture pins
# (DB4/DB5) and uart1 belongs to the display link.
pico_enable_stdio_usb(pr53_emu 1)
pico_enable_stdio_uart(pr53_emu 0)
