import pytest

from app import safety


def test_write_inside_data_dir_allowed(data_dir):
    p = safety.safe_write_bytes(data_dir / "thumbs" / "x.webp", b"ok")
    assert p.read_bytes() == b"ok"


@pytest.mark.parametrize("rel", ["../outside.txt", "../photos/evil.jpg", "thumbs/../../x.txt"])
def test_write_outside_data_dir_refused(data_dir, rel):
    with pytest.raises(safety.UnsafeWriteError):
        safety.safe_write_bytes(data_dir / rel, b"nope")
    assert not (data_dir / rel).resolve().exists()


def test_absolute_path_elsewhere_refused(data_dir, tmp_path):
    with pytest.raises(safety.UnsafeWriteError):
        safety.check_writable(tmp_path / "photos" / "a.jpg")
    with pytest.raises(safety.UnsafeWriteError):
        safety.safe_unlink(tmp_path / "photos" / "a.jpg")


def test_open_source_is_read_only(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    with safety.open_source(f) as fh:
        assert fh.mode == "rb"
        with pytest.raises(OSError):
            fh.write(b"x")
