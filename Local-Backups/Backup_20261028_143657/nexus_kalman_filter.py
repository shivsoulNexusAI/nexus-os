"""
NEXUS KALMAN FILTER // KINEMATIC STATE-SPACE ESTIMATOR & ZERO-LAG MOMENTUM ENGINE
"""
import numpy as np

MIN_KALMAN_SNR = 1.65  # 90% confidence threshold against observation noise

def run_kinematic_kalman(prices: np.ndarray, q_var: float = 0.002, r_var: float = 0.04):
    """
    2-State Discrete Kalman Filter:
    Estimates true unobserved price x[0] and instantaneous trend velocity x[1].
    """
    n = len(prices)
    if n < 15:
        return prices[-1], 0.0, 0.0, 0.0

    # Initialize state vector [position, velocity]
    x = np.array([prices[0], 0.0], dtype=np.float64)

    # State transition matrix F
    F = np.array([[1.0, 1.0],
                  [0.0, 1.0]], dtype=np.float64)

    # Measurement matrix H
    H = np.array([[1.0, 0.0]], dtype=np.float64)

    # Process covariance Q & measurement covariance R
    Q = np.array([[q_var * 0.25, q_var * 0.50],
                  [q_var * 0.50, q_var]], dtype=np.float64)
    R = np.array([[r_var]], dtype=np.float64)

    # Estimation error covariance matrix P
    P = np.eye(2, dtype=np.float64) * 1.0

    vel_series = []

    for z in prices:
        # 1. Time Update (Predict)
        x = F @ x
        P = F @ P @ F.T + Q

        # 2. Measurement Update (Correct)
        y = z - (H @ x)[0]
        s = (H @ P @ H.T)[0, 0] + R[0, 0]
        k_gain = (P @ H.T) / s

        x = x + k_gain.flatten() * y
        P = (np.eye(2) - k_gain @ H) @ P

        vel_series.append(x[1])

    est_price = float(x[0])
    est_vel = float(x[1])
    est_acc = float(vel_series[-1] - vel_series[-2]) if len(vel_series) >= 2 else 0.0
    vel_variance = max(1e-8, float(P[1, 1]))
    snr = float(abs(est_vel) / np.sqrt(vel_variance))

    return est_price, est_vel, est_acc, snr

def evaluate_kalman_momentum(closes: np.ndarray):
    """
    Evaluates kinematic zero-lag velocity, acceleration, and statistical SNR.
    Returns: (direction: str, velocity: float, acceleration: float, snr: float, is_accelerating: bool)
    """
    est_price, vel, acc, snr = run_kinematic_kalman(closes)
    direction = "BUY" if vel >= 0 else "SELL"
    is_accelerating = (vel > 0 and acc > 0) or (vel < 0 and acc < 0)
    return direction, vel, acc, snr, is_accelerating

def evaluate_kalman_gate(symbol: str, closes: np.ndarray):
    """
    Gating check: Verifies that estimated trend velocity exceeds the noise floor (SNR >= 1.65).
    Returns: (passed: bool, reason: str, metrics: dict)
    """
    direction, vel, acc, snr, is_acc = evaluate_kalman_momentum(closes)

    metrics = {
        "symbol": symbol,
        "direction": direction,
        "kalman_velocity": round(vel, 5),
        "kalman_acceleration": round(acc, 5),
        "kalman_snr": round(snr, 2),
        "is_accelerating": is_acc,
        "min_snr": MIN_KALMAN_SNR
    }

    if snr < MIN_KALMAN_SNR:
        return False, f"Kalman Noise Veto: SNR {snr:.2f} < {MIN_KALMAN_SNR} threshold (Velocity statistically insignificant)", metrics

    return True, f"Kalman Kinematics Confirmed: {direction} (SNR: {snr:.2f}, Acc: {acc:+.4f})", metrics
