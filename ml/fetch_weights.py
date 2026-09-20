"""Fetches the trained checkpoint the AI seat plays with.

The weights are not in git — they are a release artifact, published once per
training run and pulled at container start:

    python -m ml.fetch_weights                 # download if missing
    python -m ml.fetch_weights --check         # is the URL reachable? (CI)
    python -m ml.fetch_weights --force         # re-download over what is there

Only the standard library is used, so this runs before ``uv sync`` has installed
anything and inside an image that has no curl.

Environment:
    AUTOCARD_WEIGHTS_URL: Where to download from. Defaults to the published
        Hugging Face file. A ``/blob/`` link (what the website's address bar
        shows) is rewritten to the ``/resolve/`` download link, so either form
        of the URL works.
    AUTOCARD_CHECKPOINT: Where to write it. Defaults to the same path
        :class:`ml.config.Config` reads, which is what the engine loads.
    AUTOCARD_WEIGHTS_SHA256: Optional. When set, the file is verified against it
        and a mismatch is an error rather than a silent bad model.
    HF_TOKEN: Optional bearer token, for when the repository is private.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://huggingface.co/jakekato/AutoCard/resolve/main/autocard-bot.pth"

#: A torch checkpoint is a zip archive; anything else means the URL served a
#: login page, an error page or an unresolved Git LFS pointer instead.
_ZIP_MAGIC = b"PK\x03\x04"
_LEGACY_MAGIC = b"\x80\x02"  # torch.save(_use_new_zipfile_serialization=False)

_RETRIES = 3
_BACKOFF = 3.0


def _default_checkpoint() -> Path:
    """Returns the checkpoint path the engine will read.

    ``ml.config`` pulls in torch, which is a slow import and not installed at
    all in some contexts this script runs in, so the default is resolved the
    cheap way and only falls back to the config when it is already importable.

    Returns:
        Path: Destination for the downloaded weights.
    """
    override = os.getenv("AUTOCARD_CHECKPOINT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "saves" / "checkpoint.pth"


def resolve_url(url: str) -> str:
    """Turns a Hugging Face page link into a download link.

    Args:
        url (str): Either a ``/blob/`` page URL or a direct download URL.

    Returns:
        str: A URL that serves the file's bytes.
    """
    if "huggingface.co" in url and "/blob/" in url:
        return url.replace("/blob/", "/resolve/", 1)
    return url


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    """Builds a request, carrying a token when one is configured.

    Args:
        url (str): URL to request.
        method (str): HTTP method.

    Returns:
        urllib.request.Request: The prepared request.
    """
    request = urllib.request.Request(url, method=method)
    token = os.getenv("HF_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def sha256(path: Path) -> str:
    """Hashes a file in chunks.

    Args:
        path (Path): File to hash.

    Returns:
        str: Hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(url: str) -> None:
    """Confirms the weights are reachable, without downloading them.

    Run in CI so a URL that has gone away, or a repository that has been made
    private, fails a pull request instead of a production rollout.

    Args:
        url (str): Download URL.

    Raises:
        RuntimeError: If the URL cannot be reached.
    """
    try:
        with urllib.request.urlopen(_request(url, method="HEAD"), timeout=30) as response:
            size = response.headers.get("Content-Length", "unknown")
            logger.info("%s is reachable (%s bytes)", url, size)
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"{url} returned HTTP {error.code}. If the repository is private, "
            "set HF_TOKEN."
        ) from error
    except OSError as error:
        raise RuntimeError(f"Cannot reach {url}: {error}") from error


def download(url: str, destination: Path, expected_sha256: str | None = None,
             force: bool = False) -> Path:
    """Downloads the checkpoint if it is not already in place.

    The file is written to a temporary name and moved into place only once it
    has been fully read and validated, so an interrupted download can never
    leave a half-written checkpoint that the engine would try to load.

    Args:
        url (str): Download URL.
        destination (Path): Where the checkpoint belongs.
        expected_sha256 (str | None): Digest to verify against, if known.
        force (bool): Download even when the destination already exists.

    Returns:
        Path: The checkpoint's path.

    Raises:
        RuntimeError: If every attempt failed, or the bytes are not a checkpoint,
            or the digest does not match.
    """
    if destination.exists() and not force:
        if expected_sha256 and sha256(destination) != expected_sha256:
            logger.warning(
                "%s does not match AUTOCARD_WEIGHTS_SHA256; re-downloading",
                destination)
        else:
            logger.info("Checkpoint already present at %s (%.1f MiB)",
                        destination, destination.stat().st_size / 1048576)
            return destination

    destination.parent.mkdir(parents=True, exist_ok=True)

    last_error: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        # NamedTemporaryFile in the destination's own directory, so the move
        # below is a rename within one filesystem and therefore atomic.
        handle = tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".weights-", delete=False)
        temporary = Path(handle.name)
        try:
            logger.info("Downloading %s -> %s (attempt %d/%d)",
                        url, destination, attempt, _RETRIES)
            with urllib.request.urlopen(_request(url), timeout=120) as response:
                with handle:
                    shutil.copyfileobj(response, handle, length=1024 * 1024)

            _validate(temporary, expected_sha256)
            temporary.replace(destination)
            logger.info("Checkpoint ready at %s (%.1f MiB)",
                        destination, destination.stat().st_size / 1048576)
            return destination
        except Exception as error:  # noqa: BLE001 - retried, then re-raised below
            last_error = error
            temporary.unlink(missing_ok=True)
            logger.warning("Download failed: %s", error)
            if attempt < _RETRIES:
                time.sleep(_BACKOFF * attempt)

    raise RuntimeError(f"Could not download {url}: {last_error}")


def _validate(path: Path, expected_sha256: str | None) -> None:
    """Rejects anything that is not the checkpoint we asked for.

    Args:
        path (Path): The freshly downloaded file.
        expected_sha256 (str | None): Digest to verify against, if known.

    Raises:
        RuntimeError: If the file is not a torch checkpoint or the digest is wrong.
    """
    with path.open("rb") as handle:
        header = handle.read(4)

    if not header.startswith((_ZIP_MAGIC, _LEGACY_MAGIC)):
        # The usual cause is a URL that points at the HTML file page rather than
        # the file, which downloads happily and fails much later at torch.load.
        raise RuntimeError(
            "Downloaded file is not a torch checkpoint (got "
            f"{header!r}). Check AUTOCARD_WEIGHTS_URL points at the raw file.")

    if expected_sha256:
        actual = sha256(path)
        if actual != expected_sha256:
            raise RuntimeError(
                f"sha256 mismatch: expected {expected_sha256}, got {actual}")


def main(argv: list[str] | None = None) -> int:
    """Command line entry point.

    Args:
        argv (list[str] | None): Arguments, defaulting to ``sys.argv``.

    Returns:
        int: Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    # `or` rather than a getenv default: CI passes the variable through
    # whether or not it is set, and an unset one arrives as an empty string.
    parser.add_argument("--url", default=os.getenv("AUTOCARD_WEIGHTS_URL") or DEFAULT_URL)
    parser.add_argument("--out", type=Path, default=_default_checkpoint())
    parser.add_argument("--sha256", default=os.getenv("AUTOCARD_WEIGHTS_SHA256") or None)
    parser.add_argument("--force", action="store_true",
                        help="download even if the file is already there")
    parser.add_argument("--check", action="store_true",
                        help="only confirm the URL is reachable")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[weights] %(message)s")
    url = resolve_url(args.url)

    try:
        if args.check:
            check(url)
        else:
            download(url, args.out, expected_sha256=args.sha256, force=args.force)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
