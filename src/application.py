"""FIX Application"""
import logging
import time
import uuid
from dataclasses import dataclass

import quickfix as fix
import quickfix43 as fix43

from src.dispatcher import Dispatcher

__SOH__ = chr(1)

logging.basicConfig(
    filename='Logs/acceptor-message.log',
    level=logging.INFO,
    format='%(asctime)s %(message)s'
)
logfix = logging.getLogger('acceptor')

# Alpaca order status -> (FIX OrdStatus, FIX ExecType)
_ALPACA_STATUS_MAP = {
    'new':              (fix.OrdStatus_NEW,              fix.ExecType_NEW),
    'partially_filled': (fix.OrdStatus_PARTIALLY_FILLED, fix.ExecType_PARTIAL_FILL),
    'filled':           (fix.OrdStatus_FILLED,           fix.ExecType_FILL),
    'canceled':         (fix.OrdStatus_CANCELED,         fix.ExecType_CANCELED),
    'expired':          (fix.OrdStatus_EXPIRED,          fix.ExecType_EXPIRED),
    'rejected':         (fix.OrdStatus_REJECTED,         fix.ExecType_REJECTED),
    'replaced':         (fix.OrdStatus_REPLACED,         fix.ExecType_REPLACE),
    'pending_new':      (fix.OrdStatus_PENDING_NEW,      fix.ExecType_PENDING_NEW),
    'pending_cancel':   (fix.OrdStatus_PENDING_CANCEL,   fix.ExecType_PENDING_CANCEL),
    'pending_replace':  (fix.OrdStatus_PENDING_REPLACE,  fix.ExecType_PENDING_REPLACE),
}


@dataclass
class OrderState:
    alpaca_order_id: str
    symbol: str
    fix_side: str           # raw fix.Side value
    qty: float
    status: str             # Alpaca status string
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0


class Application(fix.Application):
    """FIX Application"""

    def __init__(self):
        super().__init__()
        # cl_ord_id -> OrderState, kept in sync by on_trade_update
        self._orders: dict[str, OrderState] = {}

    def set_dispatcher(self, dispatcher: Dispatcher):
        self._dispatcher = dispatcher

    def onCreate(self, sessionID):
        """onCreate"""
        logfix.info("onCreate : Session (%s)" % sessionID.toString())
        return

    def onLogon(self, sessionID):
        """onLogon"""
        logfix.info("Successful Logon to session '%s'." % sessionID.toString())
        return

    def onLogout(self, sessionID):
        """onLogout"""
        logfix.info("Session (%s) logout !" % sessionID.toString())
        self._dispatcher.remove_client(sessionID.toString())

    def toAdmin(self, message, sessionID):
        msg = message.toString().replace(__SOH__, "|")
        logfix.info("(Admin) S >> %s" % msg)
        return

    def fromAdmin(self, message, sessionID):
        msg = message.toString().replace(__SOH__, "|")
        logfix.info("(Admin) R << %s" % msg)
        return

    def toApp(self, message, sessionID):
        msg = message.toString().replace(__SOH__, "|")
        logfix.info("(App) S >> %s" % msg)
        return

    def fromApp(self, message, sessionID):
        msg = message.toString().replace(__SOH__, "|")
        logfix.info("(App) R << %s" % msg)

        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)

        if msg_type.getValue() == fix.MsgType_MarketDataRequest:
            self._on_market_data_request(message, sessionID)
        elif msg_type.getValue() == fix.MsgType_NewOrderSingle:
            self._on_new_order_single_request(message, sessionID)

    async def on_trade_update(self, update):
        """Called by AlpacaTradeStream for every order lifecycle event."""
        cl_ord_id = update.order.client_order_id
        if cl_ord_id not in self._orders:
            return

        order = update.order
        self._orders[cl_ord_id] = OrderState(
            alpaca_order_id  = str(order.id),
            symbol           = order.symbol,
            fix_side         = fix.Side_BUY if order.side.value == 'buy' else fix.Side_SELL,
            qty              = float(order.qty or 0),
            status           = order.status.value,
            filled_qty       = float(order.filled_qty or 0),
            filled_avg_price = float(order.filled_avg_price or 0),
        )

    # behaviour based on https://www.onixs.biz/fix-dictionary/4.3/msgType_D_68.html
    def _on_new_order_single_request(self, message, sessionID):
        # --- extract ClOrdID first for PossResend check ---
        cl_ord_id = fix.ClOrdID()
        message.getField(cl_ord_id)
        cid = cl_ord_id.getValue()

        # Handling PossResend
        # note : PossResend != PosDupFlag
        # PosDupFlag is lower-lvl (checksum checks and byte sending level)
        # PossResend is at application lvl
        poss_resend = fix.PossResend()
        if message.getHeader().isSetField(poss_resend.getField()):
            message.getHeader().getField(poss_resend)
            if poss_resend.getValue() == fix.PossResend_YES and cid in self._orders:
                logfix.info("PossResend for ClOrdID %s is duplicated — replying with cached state" % cid)
                self._send_execution_report_from_state(sessionID, cid, self._orders[cid])
                return

        # handling only required fields for the moment here
        symbol    = fix.Symbol();      message.getField(symbol)
        side      = fix.Side();        message.getField(side)
        ord_type  = fix.OrdType();     message.getField(ord_type)
        order_qty = fix.OrderQty();    message.getField(order_qty)
        tif       = fix.TimeInForce(); message.getField(tif)

        limit_price = None
        stop_price  = None
        if ord_type.getValue() in (fix.OrdType_LIMIT, fix.OrdType_STOP_LIMIT):
            px = fix.Price(); message.getField(px)
            limit_price = px.getValue()
        if ord_type.getValue() in (fix.OrdType_STOP, fix.OrdType_STOP_LIMIT):
            sp = fix.StopPx(); message.getField(sp)
            stop_price = sp.getValue()

        # --- submit to Alpaca ---
        try:
            order = self._dispatcher.place_order(
                symbol          = symbol.getValue(),
                qty             = order_qty.getValue(),
                side            = side.getValue(),
                order_type      = ord_type.getValue(),
                time_in_force   = tif.getValue(),
                client_order_id = cid,
                limit_price     = limit_price,
                stop_price      = stop_price,
            )
            self._orders[cid] = OrderState(
                alpaca_order_id = str(order.id),
                symbol          = symbol.getValue(),
                fix_side        = side.getValue(),
                qty             = order_qty.getValue(),
                status          = 'new',
            )
            self._send_execution_report(sessionID, cid, symbol.getValue(),
                                        side.getValue(), order_qty.getValue(), order)
        except Exception as e:
            logfix.error("Order rejected: %s" % e)
            self._send_execution_report(sessionID, cid, symbol.getValue(),
                                        side.getValue(), order_qty.getValue(),
                                        order=None, reject_reason=str(e))

    def _send_execution_report(self, sessionID, cl_ord_id, symbol, side, qty,
                                order=None, reject_reason=None):
        report = fix43.ExecutionReport()

        rejected = order is None
        order_id = str(order.id) if order else "NONE"
        exec_id  = str(uuid.uuid4())

        report.setField(fix.OrderID(order_id))
        report.setField(fix.ClOrdID(cl_ord_id))
        report.setField(fix.ExecID(exec_id))
        report.setField(fix.ExecTransType(fix.ExecTransType_NEW))
        report.setField(fix.Symbol(symbol))
        report.setField(fix.Side(side))
        report.setField(fix.CumQty(0))
        report.setField(fix.AvgPx(0))
        report.setField(fix.LeavesQty(qty))

        if rejected:
            report.setField(fix.OrdStatus(fix.OrdStatus_REJECTED))
            report.setField(fix.ExecType(fix.ExecType_REJECTED))
            if reject_reason:
                report.setField(fix.Text(reject_reason[:58]))
        else:
            report.setField(fix.OrdStatus(fix.OrdStatus_NEW))
            report.setField(fix.ExecType(fix.ExecType_NEW))

        fix.Session.sendToTarget(report, sessionID)

    def run(self):
        import time
        while True:
            time.sleep(1)

    def _send_execution_report_from_state(self, sessionID, cl_ord_id, state: OrderState):
        ord_status, exec_type = _ALPACA_STATUS_MAP.get(
            state.status, (fix.OrdStatus_NEW, fix.ExecType_NEW)
        )
        exec_id = '0' if exec_type == fix.ExecType_ORDER_STATUS else str(uuid.uuid4())

        report = fix43.ExecutionReport()
        report.setField(fix.OrderID(state.alpaca_order_id))
        report.setField(fix.ClOrdID(cl_ord_id))
        report.setField(fix.ExecID(exec_id))
        report.setField(fix.ExecTransType(fix.ExecTransType_NEW))
        report.setField(fix.OrdStatus(ord_status))
        report.setField(fix.ExecType(exec_type))
        report.setField(fix.Symbol(state.symbol))
        report.setField(fix.Side(state.fix_side))
        report.setField(fix.CumQty(state.filled_qty))
        report.setField(fix.AvgPx(state.filled_avg_price))
        report.setField(fix.LeavesQty(max(0.0, state.qty - state.filled_qty)))

        fix.Session.sendToTarget(report, sessionID)