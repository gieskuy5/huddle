# HUDDLE01 Auto Join + Claim Bot

Auto join Huddle01 live rooms and claim Meet-2-Earn rewards.

## Features

- Auto join live room (WebSocket/HTTP)
- Auto claim Meet-2-Earn rewards
- Multi-account support
- 24h auto-loop cycle

## Flow

```
1. Join room → 3 hours
2. Claim Meet-2-Earn rewards
3. Cooldown → 24 hours
4. Repeat
```

## Setup

1. Create `privkey.txt` with private keys (one per line)
2. Run: `py main.py`
3. Enter room link when prompted

## Files

- `main.py` - Main bot script
- `privkey.txt` - Private keys (create this)

## Requirements

```
pip install requests eth-account web3 websockets
```

## Configuration

Edit `main.py` lines 20-21:
```python
JOIN_DURATION_HOURS = 3   # Duration in room
COOLDOWN_HOURS = 24       # Cooldown between cycles
```

## Telegram

https://t.me/MDFKOfficial
