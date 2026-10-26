import asyncio
import subprocess
import sys

import pytest

from hunches._sync import run


async def add(a, b):
    return a + b


async def boom():
    raise ValueError("nope")


async def busy():
    async def one(n):
        await asyncio.sleep(0.01)
        return n * 2

    await asyncio.sleep(0.01)
    return await asyncio.gather(one(1), one(2), one(3))


def test_run_returns_value_outside_a_loop():
    assert run(add(2, 3)) == 5


def test_run_reraises_outside_a_loop():
    with pytest.raises(ValueError, match="nope"):
        run(boom())


async def test_run_returns_value_inside_a_loop():
    assert run(add(2, 3)) == 5


async def test_run_reraises_inside_a_loop():
    with pytest.raises(ValueError, match="nope"):
        run(boom())


async def test_two_calls_in_a_row_inside_a_loop():
    assert run(add(1, 1)) == 2
    assert run(add(4, 4)) == 8


async def test_sleep_and_gather_work_on_the_worker():
    assert run(busy()) == [2, 4, 6]


async def test_worker_has_its_own_loop():
    async def which():
        return asyncio.get_running_loop()

    assert run(which()) is not asyncio.get_running_loop()


# The outer loop is a bare one: `asyncio.run` installs its own SIGINT handler that cancels its
# main task, which cannot run while the main thread is blocked in `run`. Jupyter does not do that.
def test_keyboard_interrupt_cancels_worker_tasks_and_joins():
    script = (
        "import asyncio, os, signal, threading\n"
        "from hunches._sync import run\n"
        "state = []\n"
        "async def long():\n"
        "    try:\n"
        "        await asyncio.sleep(30)\n"
        "    except asyncio.CancelledError:\n"
        "        state.append('cancelled'); raise\n"
        "async def main():\n"
        "    threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGINT)).start()\n"
        "    try:\n"
        "        run(long())\n"
        "    except KeyboardInterrupt:\n"
        "        state.append('interrupted')\n"
        "asyncio.new_event_loop().run_until_complete(main())\n"
        "print(state, [t.name for t in threading.enumerate() if t.is_alive() and t is not threading.main_thread()])\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert out.stdout.strip() == "['cancelled', 'interrupted'] []", (
        out.stdout,
        out.stderr,
    )
