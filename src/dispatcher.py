import threading
from collections import defaultdict
from typing import Callable, Awaitable

from src.alpaca_stream import AlpacaStream
from src.alpaca_trade_stream import AlpacaTradeStream
from src.alpaca_trader import AlpacaTrader
from src.client_session import ClientSession


class Dispatcher:

    def __init__(self, api_key: str, secret_key: str, on_trade_update: Callable[..., Awaitable]):
        self._api_key = api_key
        self._secret_key = secret_key
        self._lock = threading.Lock()
        self._trader = AlpacaTrader(api_key, secret_key)

        # symbol -> set of client_ids
        self._symbol_clients: dict[str, set[str]] = defaultdict(set)
        # client_id -> (ClientSession, set of symbols)
        self._clients: dict[str, tuple[ClientSession, set[str]]] = {}

        self._stream = AlpacaStream(api_key, secret_key)
        self._stream.start()

        self._trade_stream = AlpacaTradeStream(api_key, secret_key, on_trade_update)
        self._trade_stream.start()

    def add_client(self, client_id: str, symbols: list[str], session_id):
        with self._lock:
            if client_id in self._clients:
                raise ValueError(f"Client '{client_id}' is already registered")

            session = ClientSession(client_id, session_id)
            new_symbols = set(symbols)
            self._clients[client_id] = (session, new_symbols)

            to_subscribe = [s for s in new_symbols if not self._symbol_clients[s]]
            for symbol in new_symbols:
                self._symbol_clients[symbol].add(client_id)

        if to_subscribe:
            self._stream._client.subscribe_quotes(self._dispatch, *to_subscribe)

    def remove_client(self, client_id: str):
        with self._lock:
            if client_id not in self._clients:
                return

            session, symbols = self._clients.pop(client_id)

            to_unsubscribe = []
            for symbol in symbols:
                self._symbol_clients[symbol].discard(client_id)
                if not self._symbol_clients[symbol]:
                    del self._symbol_clients[symbol]
                    to_unsubscribe.append(symbol)

        session.stop()

        if to_unsubscribe:
            self._stream._client.unsubscribe_quotes(*to_unsubscribe)

    def add_symbols(self, client_id: str, symbols: list[str]):
        with self._lock:
            if client_id not in self._clients:
                raise ValueError(f"Client '{client_id}' is not registered")

            _, existing_symbols = self._clients[client_id]
            new_symbols = set(symbols) - existing_symbols
            existing_symbols.update(new_symbols)

            to_subscribe = [s for s in new_symbols if not self._symbol_clients[s]]
            for symbol in new_symbols:
                self._symbol_clients[symbol].add(client_id)

        if to_subscribe:
            self._stream._client.subscribe_quotes(self._dispatch, *to_subscribe)

    def place_order(self, symbol, qty, side, order_type, time_in_force, client_order_id, limit_price=None, stop_price=None):
        return self._trader.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
            limit_price=limit_price,
            stop_price=stop_price,
        )

    async def _dispatch(self, data):
        symbol = data.symbol

        with self._lock:
            client_ids = list(self._symbol_clients.get(symbol, []))
            snapshot = [
                self._clients[cid][0] for cid in client_ids
                if cid in self._clients
            ]

        for session in snapshot:
            session.queue.put_nowait(data)
