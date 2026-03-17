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
    orderID = 0
    execID = 0

    def __init__(self, dispatcher: Dispatcher):
        super().__init__()
        self._dispatcher = dispatcher

    def onCreate(self, sessionID):
        """onCreate"""
        logfix.info("onCreate : Session (%s)" % sessionID.toString())
        return

    def onLogon(self, sessionID):
        """onLogon"""
        self.sessionID = sessionID
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