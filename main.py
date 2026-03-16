import argparse
import time

from src.alpaca_stream import AlpacaStream
from src.dispatcher import Dispatcher


parser = argparse.ArgumentParser()
parser.add_argument("--PUBLIC_KEY", required=True)
parser.add_argument("--SECRET_KEY", required=True)
args = parser.parse_args()

stream = AlpacaStream(args.PUBLIC_KEY, args.SECRET_KEY)
stream.start(symbols=["SPY"])

time.sleep(5)

stream.stop()
