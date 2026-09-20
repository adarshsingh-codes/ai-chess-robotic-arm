import chess
 
 
def ep_captured_square(board, move):
    return chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
 
 
def castling_rook_squares(board, move):
    rank = chess.square_rank(move.from_square)
    if board.is_kingside_castling(move):
        return chess.square(7, rank), chess.square(5, rank)
    return chess.square(0, rank), chess.square(3, rank)
 
 
def changed_squares(board, move):
    """Squares whose contents change when `move` is played."""
    sqs = {move.from_square, move.to_square}
    if board.is_en_passant(move):
        sqs.add(ep_captured_square(board, move))
    if board.is_castling(move):
        sqs.update(castling_rook_squares(board, move))
    return sqs
 