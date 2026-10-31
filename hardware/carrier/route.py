#!/usr/bin/env python3
"""
route.py — autoroutes pr53_carrier.kicad_pcb with Freerouting, then fills
the GND pours.

    /usr/bin/python3 route.py /path/to/freerouting-1.9.0.jar

Freerouting 1.9.0 is the last release that runs on Java 17; 2.x wants 21.
Re-running gen_board.py throws the routing away, so route last.
"""
import os
import subprocess
import sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "pr53_carrier.kicad_pcb")
DSN = os.path.join(HERE, "pr53_carrier.dsn")
SES = os.path.join(HERE, "pr53_carrier.ses")



def stitch(board, pitch=5.0, edge=1.5):
    """GND vias on a grid wherever they clear everything, so the top and
    bottom pours (which signal traces chop into islands) are tied together.
    Vias that don't land in filled GND on both layers are pruned again."""
    gnd = board.FindNet("GND")
    bb = board.GetBoardEdgesBoundingBox()
    items = list(board.GetPads()) + list(board.GetTracks())
    keepouts = [z for z in board.Zones() if z.GetIsRuleArea()]
    for fp in board.GetFootprints():
        keepouts += [z for z in fp.Zones() if z.GetIsRuleArea()]
    r, clr = pcbnew.FromMM(0.35), pcbnew.FromMM(0.35)
    vias = []
    y = bb.GetTop() + pcbnew.FromMM(edge)
    while y < bb.GetBottom() - pcbnew.FromMM(edge):
        x = bb.GetLeft() + pcbnew.FromMM(edge)
        while x < bb.GetRight() - pcbnew.FromMM(edge):
            pos = pcbnew.VECTOR2I(int(x), int(y))
            c = pcbnew.SHAPE_CIRCLE(pos, r)
            ok = not any(k.Outline().Collide(pos, r + clr) for k in keepouts)
            if ok:
                ok = not any(it.IsOnLayer(layer) and it.GetEffectiveShape(layer).Collide(c, clr)
                             for it in items for layer in (pcbnew.F_Cu, pcbnew.B_Cu))
            if ok:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pos)
                v.SetWidth(pcbnew.FromMM(0.7))
                v.SetDrill(pcbnew.FromMM(0.35))
                v.SetNet(gnd)
                board.Add(v)
                items.append(v)
                vias.append(v)
            x += pcbnew.FromMM(pitch)
        y += pcbnew.FromMM(pitch)

    pours = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND"]
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    for v in vias:
        pos = v.GetPosition()
        if not all(any(z.GetLayer() == layer and z.HitTestFilledArea(layer, pos) for z in pours)
                   for layer in (pcbnew.F_Cu, pcbnew.B_Cu)):
            board.Remove(v)
    # Pockets of pour fenced off by traces: drop a via inside each one at a
    # spot where the other layer is main ground.
    def outlines(layer):
        z = [z for z in pours if z.GetLayer() == layer][0]
        polys = z.GetFilledPolysList(layer)
        out = [polys.Outline(i) for i in range(polys.OutlineCount())]
        return sorted(out, key=lambda o: o.Area(), reverse=True)

    def try_via(pocket, main):
        bb = pocket.BBox()
        step = pcbnew.FromMM(0.5)
        for y in range(bb.GetTop(), bb.GetBottom(), step):
            for x in range(bb.GetLeft(), bb.GetRight(), step):
                pos = pcbnew.VECTOR2I(x, y)
                if not (pocket.PointInside(pos) and main.PointInside(pos)):
                    continue
                # outline-only: plain SquaredDistance is 0 everywhere inside
                if (pocket.SquaredDistance(pos, True) < (r + clr) ** 2
                        or main.SquaredDistance(pos, True) < (r + clr) ** 2):
                    continue
                c = pcbnew.SHAPE_CIRCLE(pos, r)
                if any(k.Outline().Collide(pos, r + clr) for k in keepouts):
                    continue
                if any(it.IsOnLayer(l) and it.GetEffectiveShape(l).Collide(c, clr)
                       for it in items for l in (pcbnew.F_Cu, pcbnew.B_Cu)):
                    continue
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pos)
                v.SetWidth(pcbnew.FromMM(0.7))
                v.SetDrill(pcbnew.FromMM(0.35))
                v.SetNet(gnd)
                board.Add(v)
                items.append(v)
                return True
        return False

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # A pocket that has no room over the other layer's main pour falls back to
    # the next-largest island there (rev 1 missed this and left one floating).
    for layer, other in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
        targets = outlines(other)
        for pocket in outlines(layer)[1:]:
            any(try_via(pocket, t) for t in targets)   # slivers with no room already touch a GND pad

    print("stitching vias:", len([t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"
                                  and t.GetNetname() == "GND"]))


jar = sys.argv[1]
board = pcbnew.LoadBoard(PCB)
if not pcbnew.ExportSpecctraDSN(board, DSN):
    raise SystemExit("DSN export failed")

subprocess.run(["java", "-jar", jar, "-de", DSN, "-do", SES, "-mp", "100",
                "--gui.enabled=false"], check=True, timeout=1200)

if not pcbnew.ImportSpecctraSES(board, SES):
    raise SystemExit("SES import failed")
stitch(board)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(PCB)
os.remove(DSN)
os.remove(SES)
print("routed:", len([t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]), "tracks,",
      len([t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]), "vias")
