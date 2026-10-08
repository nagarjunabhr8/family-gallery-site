from app.analysis.grouping import Row, compute_groups, pick_best

A = "0000000000000000"
A_NEAR = "0000000000000007"  # 3 bits from A
A_BURST = "00000000000fffff"  # 20 bits from A
FAR = "ffffffffffffffff"


def row(id, phash=A, sha=None, minute=None, kind="photo", pinned=False, total=50.0, pixels=1000):
    return Row(id=id, kind=kind, sha256=sha or f"sha{id}", phash=phash, minute=minute,
               pinned=pinned, total=total, pixels=pixels)


def groups(rows, near=8, burst=22, burst_enabled=True):
    return sorted((k, ids) for k, ids in compute_groups(rows, near, burst, burst_enabled))


def test_exact_duplicates_by_sha():
    rows = [row(1, sha="x", phash=A), row(2, sha="x", phash=A), row(3, phash=FAR)]
    assert groups(rows) == [("exact", [1, 2])]


def test_exact_includes_videos_without_phash():
    rows = [row(1, sha="v", phash=None, kind="video"), row(2, sha="v", phash=None, kind="video")]
    assert groups(rows) == [("exact", [1, 2])]


def test_near_duplicates_by_phash_threshold():
    rows = [row(1, phash=A), row(2, phash=A_NEAR), row(3, phash=FAR)]
    assert groups(rows, near=8) == [("near", [1, 2])]
    assert groups(rows, near=2) == []


def test_burst_needs_same_minute_and_reliable_time():
    same = "2023-01-01 10:00"
    rows = [row(1, phash=A, minute=same), row(2, phash=A_BURST, minute=same)]
    assert groups(rows) == [("burst", [1, 2])]
    # different minute -> not a burst
    rows[1].minute = "2023-01-01 10:01"
    assert groups(rows) == []
    # no reliable capture time (minute=None) -> not a burst
    rows[1].minute = None
    assert groups(rows) == []


def test_burst_disabled_and_far_images_never_grouped():
    same = "2023-01-01 10:00"
    rows = [row(1, phash=A, minute=same), row(2, phash=A_BURST, minute=same), row(3, phash=FAR, minute=same)]
    assert groups(rows, burst_enabled=False) == []
    assert groups(rows) == [("burst", [1, 2])]


def test_groups_are_transitive():
    rows = [row(1, sha="s"), row(2, sha="s", phash=A_NEAR), row(3, phash="000000000000003f")]
    # 1==2 exact, 2~3 near (3 bits apart) -> one group; strongest-loose reason wins
    assert groups(rows) == [("near", [1, 2, 3])]


def test_pick_best_prefers_pinned_then_score_then_resolution():
    a, b, c = row(1, total=60), row(2, total=80), row(3, total=80, pixels=5000)
    assert pick_best([a, b, c]).id == 3
    a.pinned = True
    assert pick_best([a, b, c]).id == 1
