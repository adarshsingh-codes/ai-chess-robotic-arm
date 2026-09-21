"""
demo.py  —  short-game demo that skips inverse kinematics entirely.

Instead of computing angles from geometry, you TEACH the arm the exact joint
angles for the few squares the demo needs, then it replays them.

  python demo.py teach     -> jog the arm by hand-commands and save square poses
  python demo.py camera    -> same demo, but White's move is DETECTED by the camera
  python demo.py           -> play the demo: you type White's move, Stockfish
                              picks Black's reply (only among moves the arm
                              knows), and the arm plays it

Every arm path goes HOME -> square -> HOME, exactly like `test` in teach mode,
so what you taught is what gets replayed.
"""

import json
import os
import sys

import chess
import chess.engine

import config as C
from arm import Arm

POSES_FILE = "taught_poses.json"
JOINTS = {"b": 0, "s": 1, "e": 2, "p": 3}   # base, shoulder, elbow, wrist pitch


def load_poses():
    """Loads taught squares. Poses are only valid for the HOME they were taught
    from - if HOME_ANGLES changed since, the old file is discarded."""
    if not os.path.exists(POSES_FILE):
        return {}
    with open(POSES_FILE) as fh:
        data = json.load(fh)
    home = data.pop("_home", None)
    if home != list(C.HOME_ANGLES):
        print(f"  !! {POSES_FILE} was taught with home={home}, but config.py home is "
              f"{list(C.HOME_ANGLES)}. Those poses would move the wrong way - ignoring them.")
        print("  !! Re-teach every square (old file will be overwritten on the next save).")
        return {}
    return data


def save_poses(poses):
    data = dict(poses)
    data["_home"] = list(C.HOME_ANGLES)
    with open(POSES_FILE, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"  saved -> {POSES_FILE}")


def go(arm, angles4):
    arm.pose = list(angles4)
    arm._apply()


def visit(arm, poses, sq, grip):
    """HOME -> above sq -> down -> grip -> above sq -> HOME"""
    p = poses[sq]
    arm.home()
    go(arm, p["up"])
    go(arm, p["down"])
    arm.gripper(grip)
    go(arm, p["up"])
    arm.home()


# ---------------------------------------------------------------- teach mode
def teach():
    arm = Arm()
    poses = load_poses()
    print(__doc__)
    print("""Commands:
  b 5 | s -5 | e 3 | p 10   jog base / shoulder / elbow / wrist-pitch by N degrees
  open | close              gripper
  save <sq> up|down         store current pose for that square (e.g. save g8 down)
  test <sq>                 open, go down, grab, lift, (Enter) put back, go home
  home                      go home
  show                      print current angles and saved squares
  q                         save file and quit
Tip: teach a square, then `home` + `test <sq>`. Fix it until the TEST lands right.""")
    while True:
        try:
            cmd = input("teach> ").strip().split()
        except (EOFError, KeyboardInterrupt):
            cmd = ["q"]
        if not cmd:
            continue
        try:
            c = cmd[0].lower()
            if c in JOINTS and len(cmd) == 2:
                j = JOINTS[c]
                target = arm.pose[j] + float(cmd[1])
                if not 0 <= target <= 180:
                    print(f"  blocked: {c} would go to {target:.0f} (limit 0-180). "
                          f"Can't go further that way.")
                    continue
                arm.pose[j] = target
                arm._apply()
                print("  pose:", [round(a) for a in arm.pose])
            elif c == "open":
                arm.gripper(C.GRIPPER_OPEN)
            elif c == "close":
                arm.gripper(C.GRIPPER_CLOSED)
            elif c == "save" and len(cmd) == 3 and cmd[2] in ("up", "down"):
                poses.setdefault(cmd[1], {})[cmd[2]] = [round(a) for a in arm.pose]
                save_poses(poses)
            elif c == "test" and len(cmd) == 2:
                p = poses.get(cmd[1], {})
                if "up" not in p or "down" not in p:
                    print("  need both `up` and `down` saved for", cmd[1])
                    continue
                arm.gripper(C.GRIPPER_OPEN)
                arm.home(); go(arm, p["up"]); go(arm, p["down"])
                arm.gripper(C.GRIPPER_CLOSED)
                go(arm, p["up"])
                input("  lifted - is the piece in the claw? Enter = put it back and go home...")
                go(arm, p["down"])
                arm.gripper(C.GRIPPER_OPEN)
                go(arm, p["up"]); arm.home()
            elif c == "home":
                arm.home()
            elif c == "show":
                print("  pose:", [round(a) for a in arm.pose])
                for sq, p in poses.items():
                    print(f"  {sq}: {p}")
            elif c == "q":
                save_poses(poses)
                arm.home()
                return
            else:
                print("  ?")
        except Exception as ex:
            print("  error:", ex)


# ---------------------------------------------------------------- demo game
def reachable_moves(board, poses):
    ok = []
    for mv in board.legal_moves:
        if board.is_capture(mv) or board.is_castling(mv) or mv.promotion:
            continue
        a, b = chess.square_name(mv.from_square), chess.square_name(mv.to_square)
        if all(k in poses.get(s, {}) for s in (a, b) for k in ("up", "down")):
            ok.append(mv)
    return ok


def typed_move(board, prompt):
    while True:
        s = input(prompt).strip().lower()
        if not s:
            return None
        try:
            mv = chess.Move.from_uci(s)
            if mv in board.legal_moves:
                return mv
        except ValueError:
            pass
        print("  illegal, try again")


def play(use_camera=False):
    poses = load_poses()
    if not poses:
        sys.exit("No taught poses yet - run:  python demo.py teach")

    snap = None
    if use_camera:
        from vision import Camera, detect_move, load_or_calibrate, warp
        cam = Camera(C.CAMERA_URL)
        corners = load_or_calibrate(cam)
        snap = lambda: warp(cam.read_avg(), corners)

    arm = Arm()
    engine = chess.engine.SimpleEngine.popen_uci(C.STOCKFISH_PATH)
    board = chess.Board()
    print(board, "\n")
    ref = snap() if snap else None
    try:
        while not board.is_game_over():
            if snap:
                input("Play White's move on the board, then press Enter (Ctrl+C = quit)...")
                guess, _ = detect_move(board, ref, snap())
                if guess:
                    mv = typed_move(board, f"Detected {guess.uci()} - Enter to accept, or type the correct move: ") or guess
                else:
                    mv = typed_move(board, "Couldn't detect. Type White's move (blank = quit): ")
            else:
                mv = typed_move(board, "White's move (e.g. d2d4, blank = quit): ")
            if mv is None:
                break
            print(f"You played {board.san(mv)}")
            board.push(mv)

            options = reachable_moves(board, poses)
            if not options:
                best = engine.play(board, chess.engine.Limit(time=C.ENGINE_TIME)).move
                print(f"Stockfish wants {board.san(best)} - arm hasn't been taught those squares.")
                input("Play it by hand, then press Enter...")
                board.push(best)
                ref = snap() if snap else None
                print(board, "\n")
                continue

            reply = engine.play(board, chess.engine.Limit(time=C.ENGINE_TIME),
                                root_moves=options).move
            print("=" * 40)
            print(f"  ARM PLAYS: {board.san(reply)}  ({reply.uci()})")
            print("=" * 40)
            a, b = chess.square_name(reply.from_square), chess.square_name(reply.to_square)
            arm.gripper(C.GRIPPER_OPEN)
            visit(arm, poses, a, C.GRIPPER_CLOSED)   # pick
            visit(arm, poses, b, C.GRIPPER_OPEN)     # place
            board.push(reply)
            ref = snap() if snap else None      # fresh reference, arm is home
            print(board, "\n")
    finally:
        engine.quit()
        arm.home()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "teach":
        teach()
    else:
        play(use_camera=(mode == "camera"))