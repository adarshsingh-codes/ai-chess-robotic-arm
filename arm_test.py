"""Arm calibration console.
  raw 90 90 90 90 90 40   send raw servo angles (base shoulder elbow wrist roll gripper)
  xyz 150 0 40            fingertips to x, y, z (mm)
  sq e4                   hover over e4, then lower to pawn height
  move e2 e4              pick from e2 and place on e4
  open | close | home | q
"""
import sys
 
import chess
 
import config as C
from arm import Arm, ik, square_xy
 
if "--reach" in sys.argv:   # python arm_test.py --reach  (no Arduino needed)
    bad = []
    for sq in chess.SQUARES:
        x, y = square_xy(sq)
        for z in (C.Z_SAFE, min(C.GRAB_Z.values())):
            try:
                ik(x, y, z)
            except ValueError:
                bad.append(chess.square_name(sq))
                break
    print("All 64 squares reachable" if not bad else f"Unreachable: {' '.join(bad)}")
    sys.exit()
 
arm = Arm()
print(__doc__)
while True:
    try:
        p = input("> ").split()
        if not p:
            continue
        c = p[0].lower()
        if c == "q":
            break
        elif c == "raw":
            arm.send([int(v) for v in p[1:7]])
        elif c == "xyz":
            arm.goto(*map(float, p[1:4]))
        elif c == "sq":
            x, y = square_xy(chess.parse_square(p[1]))
            arm.goto(x, y, C.Z_SAFE)
            input("  hovering - Enter to lower")
            arm.goto(x, y, C.GRAB_Z[chess.PAWN])
        elif c == "move":
            a, b = (square_xy(chess.parse_square(s)) for s in p[1:3])
            arm.transfer(a, b, chess.PAWN)
        elif c == "open":
            arm.gripper(C.GRIPPER_OPEN)
        elif c == "close":
            arm.gripper(C.GRIPPER_CLOSED)
        elif c == "home":
            arm.home()
        else:
            print("unknown command")
    except (ValueError, IndexError, RuntimeError) as e:
        print("  error:", e)
arm.home()
 