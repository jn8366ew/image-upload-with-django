import pytest

from attachments.events.relay import _is_all_duplicates


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        ([11000], True),
        ([11000, 11000], True),
        ([11000, 121], False),
        ([2], False),
        # write concern 오류만 있어도 BulkWriteError가 나며, all([])은 True라 성공으로 오판함
        ([], False),
    ],
)
def test_is_all_duplicates_only_when_every_write_error_is_11000(codes, expected):
    details = {"writeErrors": [{"index": i, "code": c} for i, c in enumerate(codes)]}

    assert _is_all_duplicates(details) is expected
