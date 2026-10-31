#!/usr/bin/env python3
"""
pr53_netlist.py — generates the KiCad netlist for the PR53 display board.

Run this with SKiDL to emit pr53.net, then in KiCad:
  PCB Editor -> File -> Import -> Netlist -> pr53.net
Every part arrives with its footprint; every connection is a ratsnest.
Place + route from there.

  pip install skidl
  # point SKiDL at your KiCad libs (installed with KiCad):
  export KICAD_SYMBOL_DIR=/usr/share/kicad/symbols   (Linux)
  python3 pr53_netlist.py

Board = the two-Pico + 2-shifter perfboard-equivalent, as a real PCB:
  RP2350-Zero (tap) + Pico 2 (display) as MODULE footprints (castellated /
  header), 2x BSS138 4-ch level shifter modules, DB7 pulldown, input header
  to the PR53 (CN1), output header to the HiLetgo LCD.
"""
from skidl import *

# ----- library-independent generic parts (using Device library) -----
# Pin-header footprints so you solder the modules onto the board.

# Connectors / modules as headers (rows sized to each board's pin count).
zero   = Part('Connector_Generic', 'Conn_01x20', footprint='Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical', value='RP2350-Zero')
pico   = Part('Connector_Generic', 'Conn_01x20', footprint='Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical', value='Pico2', ref='J_PICO')
# (Pico 2 is 2x20; represented as two 1x20 headers L and R)
picoR  = Part('Connector_Generic', 'Conn_01x20', footprint='Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical', value='Pico2_R', ref='J_PICOR')

sh1    = Part('Connector_Generic', 'Conn_01x06', footprint='Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical', value='BSS138_4ch_1', ref='U1')
sh2    = Part('Connector_Generic', 'Conn_01x06', footprint='Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical', value='BSS138_4ch_2', ref='U2')
# (each 4-ch BSS138 module has HV,LV,GND + 4 channels each side; the module
#  breakout is a 2x6 header — represented here for netlist connectivity.)

cn1    = Part('Connector_Generic', 'Conn_01x09', footprint='Connector_PinHeader_2.54mm:PinHeader_1x09_P2.54mm_Vertical', value='PR53_CN1_in', ref='J1')
lcd    = Part('Connector_Generic', 'Conn_01x22', footprint='Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical', value='HiLetgo_LCD_out', ref='J2')

r_db7  = Part('Device', 'R', value='10k', footprint='Resistor_SMD:R_0603_1608Metric', ref='R1')

# ----- nets -----
p5v  = Net('+5V');  p3v3 = Net('+3V3'); gnd = Net('GND')
# piano bus (5V) nets
DB4=Net('DB4'); DB5=Net('DB5'); DB6=Net('DB6'); DB7=Net('DB7')
RS=Net('RS'); RW=Net('RW'); CS=Net('CS')
# shifted (3V3) nets to the Zero
zDB4=Net('Z_DB4'); zDB5=Net('Z_DB5'); zDB6=Net('Z_DB6'); zDB7=Net('Z_DB7')
zRS=Net('Z_RS'); zRW=Net('Z_RW'); zCS=Net('Z_CS')
# link
LINK=Net('LINK_GP8_GP21')
# LCD data nets
lcdD=[Net(f'LCD_DB{i}') for i in range(16)]
LCD_RS=Net('LCD_RS'); LCD_WR=Net('LCD_WR'); LCD_RST=Net('LCD_RST')

# ===== PR53 input connector J1 (CN1 tap) =====
# 1:DB4 2:DB5 3:DB6 4:DB7 5:RS 6:RW 7:CS 8:+5V 9:GND
cn1[1]+=DB4; cn1[2]+=DB5; cn1[3]+=DB6; cn1[4]+=DB7
cn1[5]+=RS;  cn1[6]+=RW;  cn1[7]+=CS
cn1[8]+=p5v; cn1[9]+=gnd

# DB7 pulldown (5V side)
r_db7[1]+=DB7; r_db7[2]+=gnd

# ===== Shifter 1 (data DB4-7). 1x6 = HV,LV,GND, A/B share via module. =====
# Represent as: pin1=HV(5V) pin2=LV(3V3) pin3=GND, pins for channels on module.
# For netlist connectivity we map: sh1 acts as the HV-side header:
#   we connect the 5V-side signals here and the LV-side to the Zero directly
#   (the physical BSS138 module bridges them). Using two 6-pin headers to
#   represent HV row and LV row per module.
sh1HV=sh1
sh1LV=Part('Connector_Generic','Conn_01x06',footprint='Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',value='BSS138_1_LV',ref='U1L')
sh1HV[1]+=p5v; sh1HV[2]+=gnd; sh1HV[3]+=DB4; sh1HV[4]+=DB5; sh1HV[5]+=DB6; sh1HV[6]+=DB7
sh1LV[1]+=p3v3;sh1LV[2]+=gnd; sh1LV[3]+=zDB4;sh1LV[4]+=zDB5;sh1LV[5]+=zDB6;sh1LV[6]+=zDB7

sh2HV=sh2
sh2LV=Part('Connector_Generic','Conn_01x06',footprint='Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',value='BSS138_2_LV',ref='U2L')
sh2HV[1]+=p5v; sh2HV[2]+=gnd; sh2HV[3]+=RS; sh2HV[4]+=RW; sh2HV[5]+=CS; sh2HV[6]+=gnd
sh2LV[1]+=p3v3;sh2LV[2]+=gnd; sh2LV[3]+=zRS;sh2LV[4]+=zRW;sh2LV[5]+=zCS;sh2LV[6]+=gnd

# ===== RP2350-Zero (tap). 1x20 header stand-in; map the pins we use. =====
# Zero edge order (our earlier map). Only connect used pins.
# GP0..GP8 on right edge; power on left. We'll assign header positions:
#  zero[1]=5V zero[2]=GND zero[3]=3V3 ... zero[11..19]=GP0..GP8
zero[1]+=p5v; zero[2]+=gnd; zero[3]+=p3v3
zero[11]+=zDB4  # GP0
zero[12]+=zDB5  # GP1
zero[13]+=zDB6  # GP2
zero[14]+=zDB7  # GP3
zero[15]+=zRS   # GP4
zero[16]+=zRW   # GP5
# GP6 unused (zero[17])
zero[18]+=zCS   # GP7
zero[19]+=LINK  # GP8 link TX

# ===== Pico 2 (display). Left header = GP0..15 + power; Right = GP16.. =====
# Left side pins 1..20 map to Pico physical 1..20 (GP0,1,GND,2,3,4,5,GND,6,7,
#   8,9,GND,10,11,12,13,GND,14,15). We connect LCD data GP0-15.
picomap_L = {1:0,2:1,4:2,5:3,6:4,7:5,9:6,10:7,11:8,12:9,14:10,15:11,16:12,17:13,19:14,20:15}
for hdr,gp in picomap_L.items():
    pico[hdr]+=lcdD[gp]
# grounds on left
for hdr in (3,8,13,18): pico[hdr]+=gnd
# Right header: physical 21..40. GP16=21,GP17=22,GP18=24,GP21=27, 3V3=36,VBUS=40,GND=23/28/38
picoR[1]+=LCD_RS   # phys21 GP16
picoR[2]+=LCD_WR   # phys22 GP17
picoR[3]+=gnd      # phys23
picoR[4]+=LCD_RST  # phys24 GP18
picoR[7]+=LINK     # phys27 GP21 (link RX)
picoR[8]+=gnd      # phys28
picoR[16]+=p3v3    # phys36 3V3(OUT)
picoR[20]+=p5v     # phys40 VBUS

# ===== HiLetgo LCD output J2 (22 used pins) =====
# 1,2=5V; 3..10=DB8..15; 11..18=DB7..0; 19=RS 20=WR 21=CS(GND) 22=RST ; plus GND
lcd[1]+=p5v; lcd[2]+=p5v
lcd[3]+=lcdD[8]; lcd[4]+=lcdD[9]; lcd[5]+=lcdD[10]; lcd[6]+=lcdD[11]
lcd[7]+=lcdD[12]; lcd[8]+=lcdD[13]; lcd[9]+=lcdD[14]; lcd[10]+=lcdD[15]
lcd[11]+=lcdD[7]; lcd[12]+=lcdD[6]; lcd[13]+=lcdD[5]; lcd[14]+=lcdD[4]
lcd[15]+=lcdD[3]; lcd[16]+=lcdD[2]; lcd[17]+=lcdD[1]; lcd[18]+=lcdD[0]
lcd[19]+=LCD_RS; lcd[20]+=LCD_WR; lcd[21]+=gnd; lcd[22]+=LCD_RST

# LCD_RS/WR/RST from display Pico control lines
LCD_RS  += picoR[1]
LCD_WR  += picoR[2]
LCD_RST += picoR[4]

generate_netlist(file_='pr53.net')
print("wrote pr53.net")
