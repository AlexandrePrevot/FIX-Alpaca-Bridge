import argparse
import quickfix as fix

from src.application import Application
from src.dispatcher import Dispatcher


parser = argparse.ArgumentParser()
parser.add_argument("--PUBLIC_KEY", required=True)
parser.add_argument("--SECRET_KEY", required=True)
args = parser.parse_args()

app = Application()
dispatcher = Dispatcher(args.PUBLIC_KEY, args.SECRET_KEY, on_trade_update=app.on_trade_update)
app.set_dispatcher(dispatcher)

settings = fix.SessionSettings("src/application.cfg")
store = fix.FileStoreFactory(settings)
log = fix.FileLogFactory(settings)
acceptor = fix.SocketAcceptor(app, store, settings, log)

acceptor.start()
app.run()
acceptor.stop()
