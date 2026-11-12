import argparse
import asyncio
import logging
import socket
import signal

from app.runtime.port import HarnessPort
from app.services import Business
from app.settings import Settings
from app.storage import Storage


async def serve(api_url, once=False):
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, current.cancel)
    business = Business(Storage(Settings.local()))
    port = HarnessPort(business, api_url)
    owner = f"{socket.gethostname()}:{__import__('os').getpid()}"
    while True:
        try:
            invocation = business.claim(owner)
            if invocation:
                result = await port.execute(invocation)
                business.complete(invocation["attempt_id"], result.status, result.error)
            elif once:
                return
        except Exception:
            # A failed DB/SDK operation never triggers another model invocation.
            logging.exception("Worker operation failed; reconcile before continuing")
            if once:
                raise
        if once:
            return
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8765")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.api_url, args.once))
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
