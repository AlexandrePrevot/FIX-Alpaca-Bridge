# FIX-Alpaca-Bridge

A bridge that exposes [Alpaca](https://alpaca.markets/) real-time market data over the [FIX protocol](https://www.fixtrading.org/what-is-fix/), allowing legacy FIX trading systems to consume live quotes without direct Alpaca API integration.

## Overview

The server accepts FIX 4.3 connections, translates incoming `MarketDataRequest` messages into Alpaca symbol subscriptions, and streams live bid/ask quotes back to connected clients as `MarketDataSnapshotFullRefresh` messages.

```
FIX Client  ──────────────────────────────────────────────────────────
              MarketDataRequest              MarketDataSnapshotFullRefresh
                    │                                    ▲
                    ▼                                    │
         ┌──────────────────┐               ┌───────────────────────┐
         │   FIX Acceptor   │               │    ClientSession       │
         │   (port 3000)    │               │  (one per client)      │
         └────────┬─────────┘               └───────────┬───────────┘
                  │                                     │
                  ▼                                     │
         ┌──────────────────────────────────────────────┤
         │               Dispatcher                     │
         │  - Symbol → clients mapping                  │
         │  - Routes Alpaca quotes to subscribers        │
         └─────────────────────┬────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │   AlpacaStream   │
                    │  (WebSocket)     │
                    └──────────────────┘
```

**Key behavior:** Symbols are subscribed at Alpaca only when the first client requests them, and unsubscribed when the last client drops them.

## Prerequisites

- Python 3.x
- An [Alpaca account](https://alpaca.markets/) with API credentials

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py --PUBLIC_KEY <alpaca_api_key> --SECRET_KEY <alpaca_secret_key>
```

The server listens on **port 3000** for incoming FIX connections. Configure the port and other session parameters in [src/application.cfg](src/application.cfg).

## FIX Session Configuration

| Parameter | Value |
|-----------|-------|
| FIX Version | FIX 4.3 |
| SenderCompID | `SERVER` |
| TargetCompID | `CLIENT` |
| Port | `3000` |

## Project Structure

```
├── main.py                  # Entry point — argument parsing, server startup
├── requirements.txt
└── src/
    ├── application.py       # FIX protocol handler (logon, logout, message routing)
    ├── dispatcher.py        # Subscription manager — routes Alpaca data to clients
    ├── client_session.py    # Per-client queue and FIX message sender
    ├── alpaca_stream.py     # Alpaca WebSocket connection wrapper
    ├── application.cfg      # FIX acceptor configuration
    └── spec/                # FIX XML data dictionaries (4.0 – 5.0)
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `quickfix` | FIX protocol engine |
| `alpaca-py` | Alpaca SDK for real-time market data streaming |
| `pytz` | Timezone handling |
