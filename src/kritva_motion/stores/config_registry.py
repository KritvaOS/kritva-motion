"""Configuration activation and rollback (contract 3.2 to 3.4; KOS-MOTION-005 PR-02).

The registry validates a configuration before it becomes active, binds a version and a digest to it,
refuses an update that is incompatible with a command that is still open, and keeps an append-only,
traceable record of every activation, rollback and refusal. It changes the engine only through
`install_configuration`; the engine keeps, per command, the version the command was admitted under.

Interpretations (tasks/KOS-MOTION-005/STORES.md): the digest is SHA-256 over canonical JSON (Q-10); the
incompatibility rule is the minimum of Q-9; the authorization outcome is a supplied input (Q-1). The
labels in `refusal` are report labels of this layer, not contract reason codes.
"""
import copy
import hashlib
import json

from kritva_motion import config_validation as cv

ACTIVATED, REFUSED = "ACTIVATED", "REFUSED"
MODE_OF = {"SET_POSITION": "position", "SET_VELOCITY": "velocity"}


def config_digest(config):
    """SHA-256 (hex) over canonical JSON: sorted keys, compact separators, UTF-8 (interpretation Q-10)."""
    blob = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def incompatibilities(config, open_commands):
    """The reasons a new configuration cannot apply while the given open commands exist (Q-9):
    the joint is removed, the command's mode is dropped, or a limit falls below the command's request.
    Returns a list of {command_id, joint_id, reason}."""
    joints = {j["joint_id"]: j for j in config["joints"]}
    found = []

    def add(c, why):
        found.append({"command_id": c["command_id"], "joint_id": c["joint_id"], "reason": why})

    for c in open_commands:
        j = joints.get(c["joint_id"])
        if j is None:
            add(c, "JOINT_REMOVED")
            continue
        mode = MODE_OF.get(c["operation"])
        if mode is not None and mode not in j.get("modes", []):
            add(c, "MODE_DROPPED")
            continue
        p = c["parameters"]
        if c["operation"] == "SET_POSITION":
            lo, hi, t = j.get("position_min"), j.get("position_max"), p.get("target_position")
            if t is not None and ((lo is not None and t < lo) or (hi is not None and t > hi)):
                add(c, "POSITION_LIMIT_NARROWED")
        elif c["operation"] == "SET_VELOCITY":
            v, vmax = p.get("target_velocity"), j.get("velocity_max")
            if v is not None and vmax is not None and abs(v) > vmax:
                add(c, "VELOCITY_LIMIT_NARROWED")
    return found


class ConfigurationRegistry:
    """Holds the active configuration, its version and digest, and the activation history.
    `engine` is a LifecycleEngine (anything with install_configuration, open_commands and
    active_configuration_version). Before the first successful activation there is no active
    configuration and every submission is rejected CONFIG_NOT_ACTIVE (contract 3.2)."""

    def __init__(self, engine, capabilities):
        self._engine = engine
        self._capabilities = copy.deepcopy(capabilities)
        self._versions = {}      # version -> (configuration, digest); never removed, never replaced
        self._log = []           # activation records, oldest first, append-only
        self._active = None

    # -- views -----------------------------------------------------------------------------------
    @property
    def active_version(self):
        return self._active

    def digest_of(self, version):
        entry = self._versions.get(version)
        return None if entry is None else entry[1]

    def history(self):
        """Copies of the activation records, oldest first (the trace of 3.4)."""
        return copy.deepcopy(self._log)

    # -- operations ------------------------------------------------------------------------------
    def activate(self, config, now_ms, permission_granted=True):
        """Validate, then activate a new version for commands accepted from now on."""
        result = cv.validate_configuration(config, self._capabilities)
        version = config.get("config_version") if isinstance(config, dict) else None
        if not result.valid:
            return self._refuse("ACTIVATE", version, None, "INVALID_CONFIGURATION", now_ms, permission_granted,
                                detail=[{"rule": v.rule, "path": v.path} for v in result.violations])
        digest = config_digest(config)
        if version in self._versions:
            return self._refuse("ACTIVATE", version, digest, "VERSION_ALREADY_KNOWN", now_ms, permission_granted)
        clash = incompatibilities(config, self._engine.open_commands())
        if clash:
            return self._refuse("ACTIVATE", version, digest, "INCOMPATIBLE_WITH_OPEN_COMMANDS", now_ms,
                                permission_granted, detail=clash)
        self._versions[version] = (copy.deepcopy(config), digest)
        return self._install("ACTIVATE", version, digest, now_ms, permission_granted)

    def rollback(self, version, now_ms, permission_granted=False):
        """Return to an earlier version. Explicit and authorized: without a granted authorization
        result nothing changes and the refusal is recorded (contract 3.4)."""
        if permission_granted is not True:
            return self._refuse("ROLLBACK", version, self.digest_of(version), "NOT_AUTHORIZED", now_ms,
                                permission_granted)
        if version not in self._versions:
            return self._refuse("ROLLBACK", version, None, "UNKNOWN_VERSION", now_ms, permission_granted)
        if version == self._active:
            return self._refuse("ROLLBACK", version, self.digest_of(version), "ALREADY_ACTIVE", now_ms,
                                permission_granted)
        config, digest = self._versions[version]
        clash = incompatibilities(config, self._engine.open_commands())
        if clash:
            return self._refuse("ROLLBACK", version, digest, "INCOMPATIBLE_WITH_OPEN_COMMANDS", now_ms,
                                permission_granted, detail=clash)
        return self._install("ROLLBACK", version, digest, now_ms, permission_granted)

    # -- internals -------------------------------------------------------------------------------
    def _install(self, kind, version, digest, now_ms, permission_granted):
        config, _ = self._versions[version]
        previous = self._active
        self._engine.install_configuration(config, digest)
        self._active = version
        return self._record(kind, version, digest, ACTIVATED, None, now_ms, permission_granted, None, previous)

    def _refuse(self, kind, version, digest, refusal, now_ms, permission_granted, detail=None):
        return self._record(kind, version, digest, REFUSED, refusal, now_ms, permission_granted, detail, self._active)

    def _record(self, kind, version, digest, outcome, refusal, now_ms, permission_granted, detail, previous):
        rec = {"sequence": len(self._log) + 1, "kind": kind, "version": version, "digest": digest,
               "outcome": outcome, "refusal": refusal, "detail": copy.deepcopy(detail),
               "previous_version": previous, "authorization": {"permission_granted": permission_granted},
               "at_ms": now_ms}
        self._log.append(rec)
        return copy.deepcopy(rec)
