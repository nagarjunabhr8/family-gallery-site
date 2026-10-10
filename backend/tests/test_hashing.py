"""SHA-256 file hashing: streaming, read-only access and what counts as 'the same file'."""

import hashlib
import os
import stat

import pytest

from app.scanner.metadata import sha256_file


@pytest.mark.parametrize("size", [0, 1, 1023, 1024, 1025, 5 * 1024 + 7])
def test_streaming_matches_hashlib_across_chunk_boundaries(tmp_path, size):
    p = tmp_path / "f.bin"
    data = os.urandom(size)
    p.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert sha256_file(p, chunk=1024) == expected
    assert sha256_file(p) == expected  # default 1 MiB chunks


def test_known_vector(tmp_path):
    p = tmp_path / "abc.txt"
    p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_same_bytes_same_hash_regardless_of_name_or_time(tmp_path):
    a, b = tmp_path / "IMG_1.jpg", tmp_path / "copy of IMG_1 (2).jpg"
    a.write_bytes(b"\xff\xd8 photo bytes")
    b.write_bytes(a.read_bytes())
    os.utime(b, (0, 0))
    assert sha256_file(a) == sha256_file(b)


def test_one_byte_difference_changes_hash(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"x" * 4096)
    b.write_bytes(b"x" * 4095 + b"y")
    assert sha256_file(a) != sha256_file(b)


def test_hashing_works_on_read_only_files_and_leaves_them_untouched(tmp_path):
    p = tmp_path / "ro.jpg"
    p.write_bytes(b"read only original")
    os.chmod(p, stat.S_IREAD)
    try:
        before = p.stat()
        assert sha256_file(p) == hashlib.sha256(b"read only original").hexdigest()
        after = p.stat()
        assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    finally:
        os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
