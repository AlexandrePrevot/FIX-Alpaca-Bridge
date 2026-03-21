import threading
from typing import Callable, Awaitable

from alpaca.trading.stream import TradingStream


class AlpacaTradeStream:

    def __init__(self, api_key: str, secret_key: str, on_update: Callable[..., Awaitable]):
        self._client = TradingStream(api_key, secret_key)
        self._client.subscribe_trade_updates(on_update)
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._client.run, daemon=True)
        self._thread.start()

    def stop(self):
        self._client.stop()
        if self._thread:
            self._thread.join(timeout=5)
