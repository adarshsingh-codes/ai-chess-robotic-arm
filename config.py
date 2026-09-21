import chess

# ===== Camera =====
CAMERA_URL = "http://172.20.10.2:8080/video"   # IP Webcam app: shown URL + /video
CALIB_FILE = "calibration.json"
WARP_SIZE = 800
DIFF_THRESHOLD = 12.0      # min brightness change for a square to count as "changed"

# ===== Serial / Arduino =====
SERIAL_PORT = "COM4"       # <-- SET THIS to whatever Device Manager shows on THIS machine
BAUD = 115200

# ===== Chess engine =====
STOCKFISH_PATH = r"C:\Users\rs615\Downloads\stockfish-windows-x86-64-universal\stockfish\stockfish-windows-x86-64-universal.exe"   # on Windows: full path to stockfish.exe
ENGINE_TIME = 0.5              # seconds per AI move
SKILL_LEVEL = 5                # 0 (weak) .. 20 (max)
HUMAN_COLOR = "white"          # arm plays the other side and sits behind its back rank

# ===== Arm geometry (mm) — measured on the actual arm =====
BASE_HEIGHT = 140.0  # board surface -> shoulder axis
L1 = 120.0           # shoulder axis -> elbow axis
L2 = 90.0            # elbow axis -> wrist axis
L3 = 138.0           # wrist axis -> gripper fingertips

# ===== Board placement (mm) =====
SQ = 47.0            # square size
BOARD_GAP = 50.0     # base rotation axis -> nearest board edge
BOARD_Y_SHIFT = 1.0  # base sits ~1mm left of board center — effectively centered

# ===== Heights (mm above board surface) =====
Z_SAFE = 50.0        # travel height, must clear the king (lowered from 90 — see below)
GRAB_Z = {chess.PAWN: 10, chess.KNIGHT: 14, chess.BISHOP: 16,
          chess.ROOK: 12, chess.QUEEN: 20, chess.KING: 24}
PLACE_EXTRA_Z = 3.0

# ===== Servo mapping: servo_deg = OFFSET + DIR * joint_deg =====
# base:     0 = straight ahead, + = left
# shoulder: upper-arm angle above horizontal (90 = straight up)
# elbow:    forearm bend relative to upper arm (0 = straight, negative = bent down)
# wrist:    gripper angle relative to forearm (0 = in line)
SERVO_OFFSET = [90, 0, 180, 90]
SERVO_DIR    = [1, 1, 1, 1]      # flip to -1 if a joint moves the wrong way
ROLL_NEUTRAL = 90
GRIPPER_OPEN = 40
GRIPPER_CLOSED = 95
HOME_ANGLES = [90, 120, 40, 90]  # base, shoulder, elbow, wrist — parked, not blocking camera

# ===== Graveyard for captured pieces (x, y mm), right side of the board =====
GRAVEYARD = [(BOARD_GAP + (i % 8 + 0.5) * SQ, -(4 * SQ + 30) - (i // 8) * 30) for i in range(16)]