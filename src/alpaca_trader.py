from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce

import quickfix as fix

# FIX OrdType values
_ORDER_TYPE_MARKET     = fix.OrdType_MARKET      # '1'
_ORDER_TYPE_LIMIT      = fix.OrdType_LIMIT       # '2'
_ORDER_TYPE_STOP       = fix.OrdType_STOP        # '3'
_ORDER_TYPE_STOP_LIMIT = fix.OrdType_STOP_LIMIT  # '4'

# FIX TimeInForce -> Alpaca TimeInForce
_TIF_MAP = {
    fix.TimeInForce_DAY:                    TimeInForce.DAY,
    fix.TimeInForce_GOOD_TILL_CANCEL:       TimeInForce.GTC,
    fix.TimeInForce_IMMEDIATE_OR_CANCEL:    TimeInForce.IOC,
    fix.TimeInForce_FILL_OR_KILL:           TimeInForce.FOK,
}


class AlpacaTrader:

    def __init__(self, api_key: str, secret_key: str):
        self._client = TradingClient(api_key, secret_key)

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,              # fix.Side value
        order_type: str,        # fix.OrdType value
        time_in_force: str,     # fix.TimeInForce value
        client_order_id: str,   # FIX ClOrdID — echoed back in TradeUpdates
        limit_price: float | None = None,
        stop_price: float | None = None,
    ):
        alpaca_side = OrderSide.BUY if side == fix.Side_BUY else OrderSide.SELL
        alpaca_tif  = _TIF_MAP.get(time_in_force, TimeInForce.DAY)
        common = dict(symbol=symbol, qty=qty, side=alpaca_side,
                      time_in_force=alpaca_tif, client_order_id=client_order_id)

        if order_type == _ORDER_TYPE_MARKET:
            request = MarketOrderRequest(**common)
        elif order_type == _ORDER_TYPE_LIMIT:
            request = LimitOrderRequest(**common, limit_price=limit_price)
        elif order_type == _ORDER_TYPE_STOP:
            request = StopOrderRequest(**common, stop_price=stop_price)
        elif order_type == _ORDER_TYPE_STOP_LIMIT:
            request = StopLimitOrderRequest(**common, limit_price=limit_price, stop_price=stop_price)
        else:
            raise ValueError(f"Unsupported OrdType: {order_type!r}")

        return self._client.submit_order(request)

    def get_order(self, order_id: str):
        return self._client.get_order_by_id(order_id)
