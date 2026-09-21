"""
advisor.py  —  camera + Stockfish, NO arm.

Use this instead of main.py while the arm hardware isn't reliable:
  - You play White by hand on the real board.
  - The camera detects your move the same way main.py does.
  - Stockfish computes Black's best reply and PRINTS it in the terminal
    (SAN + UCI + eval). You play that move by hand for Black too, press
    Enter, and it takes a fresh reference photo for the next round.

Nothing here ever touches Arm/serial/Arduino.
"""

import sys

import chess
import chess.engine

import config as C
from vision import Camera, detect_move, load_or_calibrate, warp


def ask_move(board, guess=None):
    prompt = (f"Detected {guess.uci()} - Enter to accept, or type the correct move: "
              if guess else "Couldn't detect. Type your move (e.g. e2e4): ")
    while True:
        s = input(prompt).strip().lower()
        if not s and guess:
            return guess
        try:
            m = chess.Move.from_uci(s)
            if m in board.legal_moves:
                return m
        except ValueError:
            pass
        print("  Illegal or invalid move, try again.")


def format_score(info, human):
    """Turn an engine.analyse() info dict into a short human-readable eval string."""
    try:
        score = info["score"].pov(human)  # from the human's (White's) perspective
    except Exception:
        return ""
    if score.is_mate():
        n = score.mate()
        return f"  (mate in {abs(n)} for {'White' if n > 0 else 'Black'})"
    cp = score.score()
    if cp is None:
        return ""
    side = "White" if cp >= 0 else "Black"
    return f"  (eval {abs(cp) / 100:+.2f} favoring {side})" if cp else "  (eval 0.00, equal)"


def main():
    cam = Camera(C.CAMERA_URL)
    corners = load_or_calibrate(cam, force="--calibrate" in sys.argv)

    def snap():
        return warp(cam.read_avg(), corners)

    engine = chess.engine.SimpleEngine.popen_uci(C.STOCKFISH_PATH)
    engine.configure({"Skill Level": C.SKILL_LEVEL})

    human = chess.WHITE if C.HUMAN_COLOR.lower() == "white" else chess.BLACK
    board = chess.Board()
    print(board, "\n")
    print("NO-ARM ADVISOR MODE — you play both sides by hand; this only tells")
    print("you what Black should play.\n")
    ref = snap()

    try:
        while not board.is_game_over():
            if board.turn == human:
                input("Your move. Play it on the board, then press Enter...")
                guess, diffs = detect_move(board, ref, snap())
                if guess is None:
                    top = sorted(diffs.items(), key=lambda kv: kv[1], reverse=True)[:4]
                    print("  Top changed squares:",
                          ", ".join(f"{chess.square_name(s)}={v:.0f}" for s, v in top))
                move = ask_move(board, guess)
                print(f"You played {board.san(move)}")
                board.push(move)
                print(board, "\n")
            else:
                info = engine.analyse(board, chess.engine.Limit(time=C.ENGINE_TIME))
                move = info["pv"][0]
                san = board.san(move)
                print("=" * 44)
                print(f"  BEST MOVE FOR BLACK:  {san}   ({move.uci()}){format_score(info, human)}")
                print("=" * 44)
                input("Play that move by hand for Black, then press Enter...")
                board.push(move)
                ref = snap()            # fresh reference for the next detection
                print(board, "\n")
    finally:
        engine.quit()

    print("Game over:", board.result())


if __name__ == "__main__":
    main()