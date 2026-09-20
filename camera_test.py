"""Test the phone camera + move detection WITHOUT the arm.

python camera_test.py
  Window 1 "live"  : raw phone stream
  Window 2 "board" : warped top-down board with grid (after calibration)

Keys:
  r  take reference frame (do this with the board set up)
  d  move a piece by hand, then press d -> prints detected move
  c  re-calibrate corners
  q  quit
"""
import chess
import cv2

import config as C
from vision import Camera, detect_move, draw_grid, load_or_calibrate, warp

cam = Camera(C.CAMERA_URL)
corners = load_or_calibrate(cam)
board = chess.Board()
ref = None
print(__doc__)

while True:
    frame = cam.read()
    cv2.imshow("live", cv2.resize(frame, None, fx=0.5, fy=0.5))
    cv2.imshow("board", draw_grid(warp(frame, corners)))
    k = cv2.waitKey(30) & 0xFF

    if k == ord("q"):
        break
    elif k == ord("c"):
        cv2.destroyAllWindows()
        corners = load_or_calibrate(cam, force=True)
    elif k == ord("r"):
        ref = warp(cam.read_avg(), corners)
        print(f"Reference taken. {'White' if board.turn else 'Black'} to move.")
    elif k == ord("d"):
        if ref is None:
            print("Press r first.")
            continue
        now = warp(cam.read_avg(), corners)
        move, diffs = detect_move(board, ref, now)
        top = sorted(diffs.items(), key=lambda kv: kv[1], reverse=True)[:4]
        print("  changed:", ", ".join(f"{chess.square_name(s)}={v:.0f}" for s, v in top))
        if move:
            print(f"  DETECTED: {board.san(move)}")
            board.push(move)
            ref = now
        else:
            print("  No legal move matched (check lighting / DIFF_THRESHOLD).")

cv2.destroyAllWindows()