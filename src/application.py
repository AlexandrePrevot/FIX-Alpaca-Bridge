"""FIX Application"""
import logging
import time

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


class Application(fix.Application):
    """FIX Application"""

    def __init__(self, dispatcher: Dispatcher):
        super().__init__()
        self._dispatcher = dispatcher
        self._seen_order_id = set()


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

    # behaviour based on https://www.onixs.biz/fix-dictionary/4.3/msgType_D_68.html
    def _on_new_order_single_request(self, message, sessionID):
        # --- extract required FIX fields ---
        cl_ord_id    = fix.ClOrdID();     message.getField(cl_ord_id)
        symbol       = fix.Symbol();      message.getField(symbol)
        side         = fix.Side();        message.getField(side)
        ord_type     = fix.OrdType();     message.getField(ord_type)
        order_qty    = fix.OrderQty();    message.getField(order_qty)
        tif          = fix.TimeInForce(); message.getField(tif)

        # optional price fields (present depending on OrdType)
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
                symbol        = symbol.getValue(),
                qty           = order_qty.getValue(),
                side          = side.getValue(),
                order_type    = ord_type.getValue(),
                time_in_force = tif.getValue(),
                limit_price   = limit_price,
                stop_price    = stop_price,
            )
            self._send_execution_report(sessionID, cl_ord_id.getValue(), symbol.getValue(),
                                        side.getValue(), order_qty.getValue(), order)
        except Exception as e:
            logfix.error("Order rejected: %s" % e)
            self._send_execution_report(sessionID, cl_ord_id.getValue(), symbol.getValue(),
                                        side.getValue(), order_qty.getValue(), order=None,
                                        reject_reason=str(e))

    def _send_execution_report(self, sessionID, cl_ord_id, symbol, side, qty,
                                order=None, reject_reason=None):
        report = fix43.ExecutionReport()

        rejected = order is None
        order_id = str(order.id) if order else "NONE"
        exec_id  = str(order.id) if order else cl_ord_id

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
                report.setField(fix.Text(reject_reason[:58]))  # FIX Text field max ~58 chars
        else:
            report.setField(fix.OrdStatus(fix.OrdStatus_NEW))
            report.setField(fix.ExecType(fix.ExecType_NEW))

        fix.Session.sendToTarget(report, sessionID)


    def _on_market_data_request(self, message, sessionID):
        md_req_id = fix.MDReqID()
        subscription_type = fix.SubscriptionRequestType()
        message.getField(md_req_id)
        message.getField(subscription_type)

        no_related_sym = fix.NoRelatedSym()
        message.getField(no_related_sym)
        symbols = []
        group = fix43.MarketDataRequest.NoRelatedSym()
        for i in range(1, no_related_sym.getValue() + 1):
            message.getGroup(i, group)
            symbol = fix.Symbol()
            group.getField(symbol)
            symbols.append(symbol.getValue())

        client_id = sessionID.toString()
        sub_type = subscription_type.getValue()

        if sub_type == fix.SubscriptionRequestType_SNAPSHOT_PLUS_UPDATES:
            try:
                self._dispatcher.add_client(client_id, symbols, sessionID)
            except ValueError:
                self._dispatcher.add_symbols(client_id, symbols)
        elif sub_type == fix.SubscriptionRequestType_DISABLE_PREVIOUS_SNAPSHOT_PLUS_UPDATE_REQUEST:
            self._dispatcher.remove_client(client_id)

    def run(self):
        """Run"""
        while 1:
            time.sleep(2)
