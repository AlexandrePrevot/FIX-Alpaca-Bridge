import threading

from alpaca.data.live import StockDataStream


class AlpacaStream:
    def __init__(self, api_key: str, secret_key: str):
        self._client = StockDataStream(api_key, secret_key)
        self._thread = None

    async def _quote_handler(self, data):
        print(data)

    def start(self):
        self._thread = threading.Thread(target=self._client.run, daemon=True)
        self._thread.start()

    def stop(self):
        self._client.stop()
        if self._thread:
            self._thread.join(timeout=5)
