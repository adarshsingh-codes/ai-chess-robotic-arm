import json
import os
import threading
import time

import chess
import cv2
import numpy as np

import config as C
from chess_utils import changed_squares

S = C.WARP_SIZE
CELL = S // 8


class Camera:
    """Reads the phone stream in a background thread so we always get the latest frame."""

    def __init__(self, url):
        self.cap = cv2.VideoCapture(url)
        if not self.cap.isOpened():
            raise RuntimeError(f"Can't open camera stream: {url}")
        self.frame, self.lock = None, threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()
        t0 = time.time()
        while self.frame is None:
            if time.time() - t0 > 10:
                raise RuntimeError("No frames from camera")
            time.sleep(0.05)

    def _loop(self):
        while True:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = f
            else:
                time.sleep(0.01)

    def read(self):
        with self.lock:
            return self.frame.copy()

    def read_avg(self, n=5, gap=0.05):
        """Average a few frames to cut noise."""
        acc = np.zeros_like(self.read(), dtype=np.float32)
        for _ in range(n):
            acc += self.read().astype(np.float32)
            time.sleep(gap)
        return (acc / n).astype(np.uint8)


def cell_origin(sq):
    return chess.square_file(sq) * CELL, (7 - chess.square_rank(sq)) * CELL


def warp(frame, corners):
    """corners = outer board corners at a1, h1, h8, a8 -> top-down image, white at bottom."""
    src = np.float32(corners)
    dst = np.float32([[0, S], [S, S], [S, 0], [0, 0]])
    return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(src, dst), (S, S))


def draw_grid(img):
    out = img.copy()
    for i in range(9):
        cv2.line(out, (i * CELL, 0), (i * CELL, S), (0, 255, 0), 1)
        cv2.line(out, (0, i * CELL), (S, i * CELL), (0, 255, 0), 1)
    for sq in chess.SQUARES:
        x, y = cell_origin(sq)
        cv2.putText(out, chess.square_name(sq), (x + 4, y + CELL - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    return out


def _auto_detect_corners(frame):
    """Find the board's 4 outer corners from the internal 7x7 grid of an EMPTY,
    high-contrast (light/dark square) board. Returns [TL, TR, BR, BL] in image
    pixels (clockwise on screen), or None if no board pattern is found."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(
        gray, (7, 7), cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not found:
        return None
    corners = cv2.cornerSubPix(
        gray, corners, (11, 11), (-1, -1),
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
    c = corners.reshape(7, 7, 2)

    # Extrapolate one half-square outward from the outer ring of internal corners
    # to get the board's actual outer edge.
    p1, p2, p3, p4 = c[0, 0], c[0, 6], c[6, 6], c[6, 0]
    top_left = p1 + (p1 - p2) / 2 + (p1 - p4) / 2
    top_right = p2 + (p2 - p1) / 2 + (p2 - c[1, 6]) / 2
    bottom_right = p3 + (p3 - p2) / 2 + (p3 - p4) / 2
    bottom_left = p4 + (p4 - p3) / 2 + (p4 - c[5, 0]) / 2

    pts = np.float32([top_left, top_right, bottom_right, bottom_left])
    sums, diffs = pts[:, 0] + pts[:, 1], pts[:, 0] - pts[:, 1]
    return np.float32([
        pts[np.argmin(sums)],   # top-left      (smallest x+y)
        pts[np.argmax(diffs)],  # top-right     (largest x-y)
        pts[np.argmax(sums)],   # bottom-right  (largest x+y)
        pts[np.argmin(diffs)],  # bottom-left   (smallest x-y)
    ])


def _pick_a1(cam, ordered):
    """Show the 4 auto-detected corners numbered 1-4, ask which is a1, and
    return the 4 points reordered as [a1, h1, h8, a8] for warp()."""
    disp = cam.read()
    for i, p in enumerate(ordered):
        x, y = p.astype(int)
        cv2.circle(disp, (x, y), 12, (0, 0, 255), -1)
        cv2.putText(disp, str(i + 1), (x + 14, y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.putText(disp, "Board found - answer in the terminal", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("calibrate", disp)
    cv2.waitKey(1)

    print("Detected corners are numbered 1-4 on the image (clockwise on screen).")
    while True:
        s = input("Which number sits at a1 (White's queenside-rook corner)? [1-4]: ").strip()
        if s in ("1", "2", "3", "4"):
            i = int(s) - 1
            break
        print("  enter 1, 2, 3 or 4")

    # `ordered` runs clockwise on screen; a1 -> h1 -> h8 -> a8 runs counter-
    # clockwise (adjacent board edges), so walk the list backwards from i.
    return [ordered[(i - k) % 4].tolist() for k in range(4)]


def _manual_click(cam):
    names = ["a1", "h1", "h8", "a8"]
    pts = []

    def on_click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append([x, y])

    cv2.setMouseCallback("calibrate", on_click)
    while len(pts) < 4:
        disp = cam.read()
        for p in pts:
            cv2.circle(disp, tuple(p), 8, (0, 255, 0), -1)
        cv2.putText(disp, f"Click OUTER corner at {names[len(pts)]}  (Esc = quit)", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.imshow("calibrate", disp)
        if cv2.waitKey(30) == 27:
            raise SystemExit("Calibration cancelled")
    return pts


def calibrate(cam):
    """Give a countdown to press 'm' for manual mode; otherwise auto-detect
    the board corners on an empty, high-contrast board."""
    cv2.namedWindow("calibrate", cv2.WINDOW_NORMAL)

    manual = False
    t0 = time.time()
    while time.time() - t0 < 10:
        remaining = 10 - int(time.time() - t0)
        disp = cam.read()
        cv2.putText(disp, f"Press 'm' for MANUAL mode ({remaining}s)...", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        cv2.imshow("calibrate", disp)
        k = cv2.waitKey(30) & 0xFF
        if k == ord("m"):
            manual = True
            break
        if k == 27:
            cv2.destroyAllWindows()
            raise SystemExit("Calibration cancelled")

    if manual:
        pts = _manual_click(cam)
        cv2.imshow("calibrate", draw_grid(warp(cam.read(), pts)))
        print("Check the grid labels. Press any key to save (re-run calibration if wrong).")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        with open(C.CALIB_FILE, "w") as fh:
            json.dump(pts, fh)
        return pts

    print("Auto-detecting corners ('m' = calibrate by hand instead, Esc = quit)...")
    pts = None
    t0 = time.time()
    while time.time() - t0 < 15:
        frame = cam.read()
        found = _auto_detect_corners(frame)
        disp = frame.copy()
        msg = "BOARD FOUND" if found is not None else "SEARCHING (board must be empty)..."
        color = (0, 255, 0) if found is not None else (0, 0, 255)
        cv2.putText(disp, f"{msg}   'm' = manual, Esc = quit", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.imshow("calibrate", disp)
        k = cv2.waitKey(30) & 0xFF
        if found is not None:
            pts = _pick_a1(cam, found)
            break
        if k == ord("m"):
            break
        if k == 27:
            cv2.destroyAllWindows()
            raise SystemExit("Calibration cancelled")

    if pts is None:
        print("No board pattern found (or 'm' pressed) - click the corners by hand.")
        pts = _manual_click(cam)

    cv2.imshow("calibrate", draw_grid(warp(cam.read(), pts)))
    print("Check the grid labels. Press any key to save (re-run calibration if wrong).")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    with open(C.CALIB_FILE, "w") as fh:
        json.dump(pts, fh)
    return pts


def load_or_calibrate(cam, force=False):
    if not force and os.path.exists(C.CALIB_FILE):
        with open(C.CALIB_FILE) as fh:
            return json.load(fh)
    return calibrate(cam)


def square_diffs(before, after):
    """Per-square change score, median-normalized to ignore global lighting shifts."""
    def gray(im):
        return cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    diff = cv2.absdiff(gray(before), gray(after))
    m = int(CELL * 0.2)  # ignore square borders (neighbor bleed)
    d = {}
    for sq in chess.SQUARES:
        x, y = cell_origin(sq)
        d[sq] = float(diff[y + m:y + CELL - m, x + m:x + CELL - m].mean())
    med = float(np.median(list(d.values())))
    return {sq: v - med for sq, v in d.items()}


def detect_move(board, before, after):
    """Returns (best matching legal move or None, per-square diffs)."""
    d = square_diffs(before, after)
    hot = {sq for sq, v in d.items() if v > C.DIFF_THRESHOLD}
    best, best_key = None, None
    for mv in board.legal_moves:
        sqs = changed_squares(board, mv)
        vals = [d[s] for s in sqs]
        key = (-len(hot - sqs),                 # fewest unexplained changes
               min(vals),                       # every expected square changed
               sum(vals) / len(vals),
               mv.promotion in (None, chess.QUEEN))
        if best_key is None or key > best_key:
            best, best_key = mv, key
    if best is None or best_key[1] < C.DIFF_THRESHOLD:
        return None, d
    return best, d


if __name__ == "__main__":
    # python vision.py  -> (re)calibrate the board
    load_or_calibrate(Camera(C.CAMERA_URL), force=True)