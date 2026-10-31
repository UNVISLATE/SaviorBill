import pytest
from utils.public_pagination import snap_public_limit_setting, normalize_public_limit

pytestmark = [pytest.mark.unit]


def test_snap_public_limit_setting():
    # Step = 10
    assert snap_public_limit_setting(4, step=10) == 10
    assert snap_public_limit_setting(10, step=10) == 10
    assert snap_public_limit_setting(14, step=10) == 10
    assert snap_public_limit_setting(19, step=10) == 10
    assert snap_public_limit_setting(20, step=10) == 20
    assert snap_public_limit_setting(43, step=10) == 40
    assert snap_public_limit_setting(250, step=10) == 200

    # Step = 5
    assert snap_public_limit_setting(2, step=5) == 5
    assert snap_public_limit_setting(4, step=5) == 5
    assert snap_public_limit_setting(5, step=5) == 5
    assert snap_public_limit_setting(9, step=5) == 5
    assert snap_public_limit_setting(12, step=5) == 10
    assert snap_public_limit_setting(25, step=5) == 25

    # Invalid step fallback to 10
    assert snap_public_limit_setting(14, step=7) == 10


def test_normalize_public_limit():
    # Step = 10, Max = 50
    assert normalize_public_limit(1, max_limit=50, step=10) == 10
    assert normalize_public_limit(7, max_limit=50, step=10) == 10
    assert normalize_public_limit(14, max_limit=50, step=10) == 10
    assert normalize_public_limit(16, max_limit=50, step=10) == 20
    assert normalize_public_limit(23, max_limit=50, step=10) == 20
    assert normalize_public_limit(28, max_limit=50, step=10) == 30
    assert normalize_public_limit(50, max_limit=50, step=10) == 50
    assert normalize_public_limit(100, max_limit=50, step=10) == 50

    # Step = 5, Max = 25
    assert normalize_public_limit(3, max_limit=25, step=5) == 5
    assert normalize_public_limit(7, max_limit=25, step=5) == 5
    assert normalize_public_limit(8, max_limit=25, step=5) == 10
    assert normalize_public_limit(13, max_limit=25, step=5) == 15
    assert normalize_public_limit(200, max_limit=25, step=5) == 25
