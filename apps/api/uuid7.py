"""UUIDv7 generator (RFC 9562 §5.7).

UUIDv7 encodes a Unix-millisecond timestamp in the most-significant 48 bits.
This gives time-ordered IDs while remaining compatible with the standard
``uuid.UUID`` type and Postgres' ``UUID`` column. Time-ordering improves
B-tree index locality on `id` and lets you read the creation timestamp out
of the ID without joining.

Bit layout (MSB → LSB):
    | 48 bits unix_ts_ms | 4 bits ver=0111 | 12 bits rand_a |
    |  2 bits var=10     |       62 bits rand_b              |

Hand-rolled in stdlib to avoid adding another dependency for ~15 lines.
"""
from __future__ import annotations

import secrets
import time
import uuid

_VERSION_7 = 0x7
_VARIANT_RFC4122 = 0b10


def uuid7() -> uuid.UUID:
    """Return a fresh UUIDv7 generated from the current time."""
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)

    value = ts_ms << 80
    value |= _VERSION_7 << 76
    value |= rand_a << 64
    value |= _VARIANT_RFC4122 << 62
    value |= rand_b
    return uuid.UUID(int=value)


def timestamp_ms_from_uuid7(value: uuid.UUID) -> int:
    """Recover the embedded millisecond timestamp from a UUIDv7."""
    return value.int >> 80
