import math
import time

import chess
import serial

import config as C
from chess_utils import castling_rook_squares, ep_captured_square


def square_xy(sq):
    """Square center in arm coordinates (mm). x = forward, y = left."""
    f, r = chess.square_file(sq), chess.square_rank(sq)
    if C.HUMAN_COLOR.lower() == "black":      # arm plays white, sits behind rank 1
        k, y = r, (3.5 - f) * C.SQ
    else:                                      # arm plays black, sits behind rank 8
        k, y = 7 - r, (f - 3.5) * C.SQ
    return C.BOARD_GAP + (k + 0.5) * C.SQ, y + C.BOARD_Y_SHIFT


def ik(x, y, z):
    """Fingertips at (x, y, z) with gripper pointing straight down -> 4 servo angles."""
    base = math.degrees(math.atan2(y, x))
    dr, dz = math.hypot(x, y), z + C.L3 - C.BASE_HEIGHT
    c2 = (dr * dr + dz * dz - C.L1 ** 2 - C.L2 ** 2) / (2 * C.L1 * C.L2)
    if abs(c2) > 1:
        raise ValueError(f"Unreachable: ({x:.0f}, {y:.0f}, {z:.0f}) mm")
    q2 = -math.acos(c2)                                         # elbow-down (avoids self-collision fold)
    q1 = math.atan2(dz, dr) + math.atan2(C.L2 * math.sin(-q2), C.L1 + C.L2 * math.cos(q2))
    q3 = -math.pi / 2 - q1 - q2                                # keep gripper vertical
    servos = []
    for i, j in enumerate([base, math.degrees(q1), math.degrees(q2), math.degrees(q3)]):
        if i == 3:
            s = 90   # wrist pitch forced to a safe fixed angle — stops it swinging to a dead-end
        else:
            s = C.SERVO_OFFSET[i] + C.SERVO_DIR[i] * j
        if not 0 <= s <= 180:
            raise ValueError(f"Joint {i} out of range ({s:.0f} deg) at ({x:.0f}, {y:.0f}, {z:.0f})")
        servos.append(s)
    return servos


class Arm:
    def __init__(self, port=C.SERIAL_PORT):
        self.ser = serial.Serial(port, C.BAUD, timeout=15)
        self._wait_ready()
        self.pose = list(C.HOME_ANGLES)
        self.grip = C.GRIPPER_OPEN
        self.graveyard_i = 0
        self.home()

    def _wait_ready(self):
        """Block until the Arduino's boot banner ('READY...') actually arrives,
        instead of racing a fixed sleep — avoids the boot line being read back
        as the reply to the first real command."""
        deadline = time.time() + 10
        while time.time() < deadline:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line.startswith("READY"):
                return
        raise RuntimeError("Arduino never sent READY — check port/firmware")

    def send(self, angles6):
        cmd = "S " + " ".join(str(int(round(a))) for a in angles6) + "\n"
        self.ser.write(cmd.encode())
        resp = self.ser.readline().decode(errors="ignore").strip()
        if resp != "OK":
            raise RuntimeError(f"Arduino replied {resp!r} to {cmd.strip()!r}")

    def _apply(self):
        self.send(self.pose + [C.ROLL_NEUTRAL, self.grip])

    def home(self):
        self.pose = list(C.HOME_ANGLES)
        self._apply()

    def goto(self, x, y, z):
        self.pose = ik(x, y, z)
        self._apply()

    def gripper(self, value):
        self.grip = value
        self._apply()
        time.sleep(0.6)   # give the servo real time to travel/squeeze before the next move

    def pick(self, xy, piece_type):
        x, y = xy
        self.gripper(C.GRIPPER_OPEN)
        self.goto(x, y, C.Z_SAFE)
        self.goto(x, y, C.GRAB_Z[piece_type])
        self.gripper(C.GRIPPER_CLOSED)
        self.goto(x, y, C.Z_SAFE)

    def place(self, xy, piece_type):
        x, y = xy
        self.goto(x, y, C.Z_SAFE)
        self.goto(x, y, C.GRAB_Z[piece_type] + C.PLACE_EXTRA_Z)
        self.gripper(C.GRIPPER_OPEN)
        self.goto(x, y, C.Z_SAFE)

    def transfer(self, a, b, piece_type):
        self.pick(a, piece_type)
        self.place(b, piece_type)

    def execute(self, board, move):
        """Physically play `move`. `board` = position BEFORE the move."""
        piece = board.piece_at(move.from_square)

        # 1) remove captured piece
        cap_sq = None
        if board.is_en_passant(move):
            cap_sq = ep_captured_square(board, move)
        elif board.is_capture(move):
            cap_sq = move.to_square
        if cap_sq is not None:
            slot = C.GRAVEYARD[self.graveyard_i % len(C.GRAVEYARD)]
            self.graveyard_i += 1
            self.transfer(square_xy(cap_sq), slot, board.piece_at(cap_sq).piece_type)

        # 2) move the piece
        self.transfer(square_xy(move.from_square), square_xy(move.to_square), piece.piece_type)

        # 3) castling rook
        if board.is_castling(move):
            rf, rt = castling_rook_squares(board, move)
            self.transfer(square_xy(rf), square_xy(rt), chess.ROOK)

        self.home()

        # 4) promotion: human swaps the piece
        if move.promotion:
            input(f">> Replace the pawn on {chess.square_name(move.to_square)} "
                  f"with a {chess.piece_name(move.promotion)}, then press Enter...")