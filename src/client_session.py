import queue
import threading

import quickfix as fix
import quickfix44 as fix44


class ClientSession:

    def __init__(self, client_id: str, session_id: fix.SessionID):
        print("created a new client")
        self.client_id = client_id
        self.queue: queue.Queue = queue.Queue()
        self._session_id = session_id

        # one consumer = one thread
        # might not scale
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()

    def _consume(self):
        while True:
            data = self.queue.get()
            if data is None:
                continue
            self._send(data)

    def _send(self, data):
        message = fix44.MarketDataSnapshotFullRefresh()
        message.setField(fix.Symbol(data.symbol))

        group = fix44.MarketDataSnapshotFullRefresh.NoMDEntries()

        group.setField(fix.MDEntryType(fix.MDEntryType_BID))
        group.setField(fix.MDEntryPx(data.bid_price))
        group.setField(fix.MDEntrySize(data.bid_size))
        message.addGroup(group)

        group.setField(fix.MDEntryType(fix.MDEntryType_OFFER))
        group.setField(fix.MDEntryPx(data.ask_price))
        group.setField(fix.MDEntrySize(data.ask_size))
        message.addGroup(group)

        fix.Session.sendToTarget(message, self._session_id)

    def stop(self):
        self.queue.put(None)
        self._thread.join(timeout=5)
