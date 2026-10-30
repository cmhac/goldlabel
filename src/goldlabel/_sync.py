import asyncio
import threading


def run(coro):
    """Run a coroutine to completion from sync code, also inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}
    done = threading.Event()

    def work():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task = loop.create_task(coro)
        box["loop"], box["task"] = loop, task
        try:
            box["value"] = loop.run_until_complete(task)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
            box["error"] = exc
        finally:
            try:
                rest = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in rest:
                    t.cancel()
                if rest:
                    loop.run_until_complete(
                        asyncio.gather(*rest, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()
                done.set()

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    try:
        done.wait()
    except KeyboardInterrupt:
        while thread.is_alive() and "task" not in box:
            thread.join(0.01)
        if not box["loop"].is_closed():
            try:
                box["loop"].call_soon_threadsafe(box["task"].cancel)
            except RuntimeError:  # loop already closed: the work finished
                pass
        done.wait()
        thread.join()
        raise
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]
