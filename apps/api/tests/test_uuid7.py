"""UUIDv7 unit tests — RFC 9562 §5.7 conformance + ordering."""
from __future__ import annotations

import time
import uuid

import pytest

from apps.api.uuid7 import timestamp_ms_from_uuid7, uuid7


def test_returns_uuid_type() -> None:
    assert isinstance(uuid7(), uuid.UUID)


def test_version_field_is_7() -> None:
    assert uuid7().version == 7


def test_variant_is_rfc4122() -> None:
    # Python exposes RFC 4122 (= RFC 9562 in modern numbering) as 'specified
    # in RFC 4122'. UUIDv7 carries the same variant bits.
    assert uuid7().variant == uuid.RFC_4122


def test_timestamp_is_recent() -> None:
    before = int(time.time() * 1000)
    u = uuid7()
    after = int(time.time() * 1000)
    ts = timestamp_ms_from_uuid7(u)
    assert before - 5 <= ts <= after + 5


def test_uniqueness_at_volume() -> None:
    ids = {uuid7() for _ in range(10_000)}
    assert len(ids) == 10_000


def test_monotonic_across_milliseconds() -> None:
    a = uuid7()
    time.sleep(0.002)
    b = uuid7()
    # The high 48 bits are time-ordered; a should be < b after a 2ms gap.
    assert a.int < b.int


@pytest.mark.parametrize("_", range(50))
def test_random_bits_change(_: int) -> None:
    # Two IDs in the same millisecond should still differ (rand_a + rand_b).
    a = uuid7()
    b = uuid7()
    assert a != b
