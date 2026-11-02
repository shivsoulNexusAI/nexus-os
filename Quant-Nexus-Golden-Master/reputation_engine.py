import sqlite3
import math
import os

DB_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\quant_metrics.db"

def recalculate_community_reputations():
    """
    Scans completed signals (WIN / LOSS) and recalculates the reputation score
    of each user based on their voting accuracy.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Query closed trades and corresponding user votes
    cursor.execute("""
        SELECT 
            u.telegram_id,
            v.vote_type,
            s.outcome
        FROM user_votes v
        JOIN signal_telemetry s ON v.signal_id = s.signal_id
        JOIN community_users u ON v.telegram_id = u.telegram_id
        WHERE s.outcome IN ('WIN', 'LOSS')
    """)
    records = cursor.fetchall()

    if not records:
        conn.close()
        return

    # Aggregate accuracy per user
    user_stats = {}
    for user_id, vote_type, outcome in records:
        if user_id not in user_stats:
            user_stats[user_id] = {"correct": 0, "total": 0}

        user_stats[user_id]["total"] += 1

        # Upvoted a WIN or Downvoted a LOSS = Correct conviction
        if (vote_type == "UP" and outcome == "WIN") or (vote_type == "DOWN" and outcome == "LOSS"):
            user_stats[user_id]["correct"] += 1

    for user_id, stats in user_stats.items():
        accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.5
        # Base scale: 0.1 to 3.0 weight multiplier
        new_score = round(max(0.1, accuracy * 2.0), 2)

        cursor.execute("""
            UPDATE community_users
            SET reputation_score = ?
            WHERE telegram_id = ?
        """, (new_score, user_id))

    conn.commit()
    conn.close()

def get_weighted_signal_score(signal_id: str) -> dict:
    """
    Calculates weighted community conviction factoring in voter reputation scores.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            v.vote_type,
            COALESCE(u.reputation_score, 1.0) as rep
        FROM user_votes v
        LEFT JOIN community_users u ON v.telegram_id = u.telegram_id
        WHERE v.signal_id = ?
    """, (signal_id,))
    votes = cursor.fetchall()
    conn.close()

    weighted_up = sum(rep for vote_type, rep in votes if vote_type == "UP")
    weighted_down = sum(rep for vote_type, rep in votes if vote_type == "DOWN")
    net_alpha = round(weighted_up - weighted_down, 2)

    return {
        "weighted_upvotes": round(weighted_up, 2),
        "weighted_downvotes": round(weighted_down, 2),
        "net_alpha_conviction": net_alpha
    }

if __name__ == "__main__":
    recalculate_community_reputations()
    print("✅ Community reputation weights synced with historical trade outcomes.")
