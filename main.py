import sys
 
import chess
import chess.engine
 
import config as C
from arm import Arm
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
 
 
def main():
    cam = Camera(C.CAMERA_URL)
    corners = load_or_calibrate(cam, force="--calibrate" in sys.argv)
 
    def snap():
        return warp(cam.read_avg(), corners)
 
    arm = Arm()
    engine = chess.engine.SimpleEngine.popen_uci(C.STOCKFISH_PATH)
    engine.configure({"Skill Level": C.SKILL_LEVEL})
 
    human = chess.WHITE if C.HUMAN_COLOR.lower() == "white" else chess.BLACK
    board = chess.Board()
    print(board, "\n")
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
            else:
                move = engine.play(board, chess.engine.Limit(time=C.ENGINE_TIME)).move
                print(f"AI plays {board.san(move)}")
                arm.execute(board, move)
                board.push(move)
                ref = snap()            # new reference after the arm is home
            print(board, "\n")
    finally:
        engine.quit()
        arm.home()
 
    print("Game over:", board.result())
 
 
if __name__ == "__main__":
    main()