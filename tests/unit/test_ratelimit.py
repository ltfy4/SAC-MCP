"""Tests for the async token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from sac_mcp.client.ratelimit import TokenBucket


@pytest.mark.asyncio
async def test_zero_rate_is_a_noop() -> None:
    bucket = TokenBucket(rate=0)
    for _ in range(100):
        await bucket.acquire()  # must never block


@pytest.mark.asyncio
async def test_acquire_within_burst_is_immediate() -> None:
    bucket = TokenBucket(rate=1, burst=5)
    start = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    assert time.monotonic() - start < 0.1


@pytest.mark.asyncio
async def test_acquire_waits_for_refill_without_blocking_loop() -> None:
    bucket = TokenBucket(rate=50, burst=1)
    await bucket.acquire()  # drain the bucket

    # While the second acquire waits (~20ms), other tasks must still run —
    # the old implementation busy-looped and starved the event loop.
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.001)

    task = asyncio.create_task(ticker())
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    task.cancel()

    assert elapsed >= 0.01, "second acquire should wait for token refill"
    assert ticks >= 2, "event loop must not be starved while waiting"
