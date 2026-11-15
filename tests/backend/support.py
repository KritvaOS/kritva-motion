"""Shared fixtures of the backend tests (KOS-MOTION-004). Plain data, no I/O, no clock."""
import copy


def good_declaration():
    """A capability declaration that declares every item of contract 17.2 (interpretation I-40)."""
    return copy.deepcopy({
        "supported_target_types": ["joint"],
        "health": "AVAILABLE",
        "capabilities": {
            "supported_joint_types": ["revolute", "prismatic"],
            "supported_modes": ["position", "velocity"],
            "controlled_stop": True,
            "position_hold": True,
            "execution_cancellation": True,
            "feedback": {"position": True, "velocity": True},
            "feedback_rate_hz": {"min": 10, "max": 100},
            "feedback_rate_declared_absent": False,
            "max_concurrent_executions": 4,
        },
        "joint_limits": {
            "j1": {"position_min": -1.5, "position_max": 1.5, "velocity_max": 2.0, "acceleration_max": 10.0},
            "j2": {"no_narrower_limit": True},
        },
        "clock": {"domain": "backend-monotonic", "synchronized": False},
    })
