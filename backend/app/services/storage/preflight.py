"""Is the storage mount actually writable by the user this process runs as?

Worth its own check because of how the answer differs between a laptop and a server. `./storage`
is bind-mounted over `/app/storage`, and a bind mount takes the *host* directory's ownership — the
`chown` in the Dockerfile applies to the image layer underneath and is simply covered up. Docker
Desktop on macOS papers over this by translating ownership inside its VM, so the container writes
happily; on a Linux VPS it does not, and a repository cloned as root leaves `storage/` owned by
uid 0 while the container runs as uid 1000.

The symptom is miserable to diagnose: every generation fails, the customer sees a generic error,
and nothing anywhere says "permission denied" unless someone reads the worker's logs. So this runs
once at startup and says it plainly.

It logs rather than raising. A backend that refuses to boot would also take down chat, login and
the admin screens — all of which work fine without storage — so the failure is made loud, not fatal.
"""

import os
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("storage")

# The directories the app writes to. `temp` is included because uploads land there first.
_SUBDIRS = ("images/generated", "images/uploaded", "images/thumbnails", "temp")


def check_storage_writable() -> list[str]:
    """Returns the subdirectories that could not be written to. Empty means all good."""
    base = os.path.abspath(get_settings().storage_path)
    unwritable: list[str] = []

    for subdir in _SUBDIRS:
        path = os.path.join(base, subdir)
        probe = os.path.join(path, f".write-probe-{uuid.uuid4().hex}")
        try:
            os.makedirs(path, exist_ok=True)
            with open(probe, "wb") as handle:
                handle.write(b"ok")
            os.remove(probe)
        except OSError as exc:
            unwritable.append(subdir)
            logger.error(
                "storage.not_writable",
                path=path,
                error=f"{type(exc).__name__}: {exc}",
                running_as_uid=os.getuid(),
            )

    if unwritable:
        logger.error(
            "storage.unwritable_summary",
            unwritable=unwritable,
            base=base,
            running_as_uid=os.getuid(),
            fix=(
                "The storage directory is not writable by this container's user. On the host, run: "
                f"sudo chown -R 1000:1000 ./storage  — every image generation will fail until then."
            ),
        )
    else:
        logger.info("storage.writable", base=base, running_as_uid=os.getuid())

    return unwritable
