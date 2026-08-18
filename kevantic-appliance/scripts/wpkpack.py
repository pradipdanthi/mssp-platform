#!/usr/bin/env python3
"""Build a Wazuh WPK256 package (same format as wazuh tools/agent-upgrade/wpkpack.py)."""
from __future__ import annotations

import gzip
import sys
from io import SEEK_END, SEEK_SET
from os import close, listdir, remove
from os.path import isdir, isfile
from shutil import copyfileobj
from tempfile import mkstemp

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils

MAGIC = b"WPK256\0"
HASH = hashes.SHA256()
PADDING = padding.PKCS1v15()
BUFLEN = 4096


def mergecreate(path: str, tag: str | None = None) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        if tag:
            handle.write("#{0}\n".format(tag))


def mergeappend(merged: str, sources: list[str]) -> None:
    with open(merged, "ab") as handle:
        for source in sources:
            _mergeappend(handle, source)


def _mergeappend(handle, source: str) -> None:
    if isfile(source):
        with open(source, "rb") as src:
            src.seek(0, SEEK_END)
            size = src.tell()
            src.seek(0, SEEK_SET)
            handle.write("!{0} {1}\n".format(size, source.split("/")[-1].split("\\")[-1]).encode())
            copyfileobj(src, handle)
    elif isdir(source):
        for name in listdir(source):
            _mergeappend(handle, "{0}/{1}".format(source, name))
    else:
        raise FileNotFoundError(source)


def compress(source: str, target: str) -> None:
    with open(source, "rb") as fin, gzip.open(target, "wb") as fout:
        copyfileobj(fin, fout)


def sign(source_path: str, target_path: str, cert_path: str, priv_path: str) -> None:
    hasher = hashes.Hash(HASH, default_backend())
    with open(priv_path, "rb") as fkey:
        key = serialization.load_pem_private_key(fkey.read(), password=None, backend=default_backend())
    with open(source_path, "rb") as filein:
        buf = filein.read(BUFLEN)
        while buf:
            hasher.update(buf)
            buf = filein.read(BUFLEN)
        digest = hasher.finalize()
        signature = key.sign(digest, PADDING, utils.Prehashed(HASH))
        filein.seek(0, SEEK_SET)
        with open(target_path, "wb") as fileout:
            fileout.write(MAGIC)
            with open(cert_path, "rb") as filecert:
                copyfileobj(filecert, fileout)
            fileout.write(b"\0" + signature)
            copyfileobj(filein, fileout)


def main() -> int:
    if len(sys.argv) < 5:
        sys.stderr.write("Syntax: {0} <pack.wpk> <cert.pem> <key.pem> <file> [file...]\n".format(sys.argv[0]))
        return 1
    pack, cert, key, *files = sys.argv[1:]
    fd, merged = mkstemp()
    close(fd)
    try:
        mergecreate(merged, pack)
        mergeappend(merged, files)
    except Exception:
        remove(merged)
        raise
    fd, zipped = mkstemp()
    close(fd)
    compress(merged, zipped)
    remove(merged)
    try:
        sign(zipped, pack, cert, key)
    finally:
        remove(zipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
