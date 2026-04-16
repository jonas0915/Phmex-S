---
name: Samsung Remote
description: Jonas's Samsung TV remote control webapp — FastAPI server at ~/Desktop/SamsungRemote, port 7777, controls UN65NU6900 via samsungtvws
type: reference
---

## Location
`/Users/jonaspenaso/Desktop/SamsungRemote/`

## Stack
- FastAPI + uvicorn on port 7777
- `samsungtvws` library for TV WebSocket control
- `wakeonlan` for WOL packets
- Static HTML frontend (phone webapp)

## TV Details
- Model: Samsung UN65NU6900 (65" 4K, Tizen OS)
- MAC: `00:7C:2D:E8:99:82`
- Current IP: `192.168.4.100` (was .84, changed via DHCP on 2026-04-01)
- WS port: 8002, REST info port: 8001

## Running
```bash
cd ~/Desktop/SamsungRemote
caffeinate -i python3 server.py >> logs/server.log 2>&1 &
```

## Access
- Local: http://localhost:7777
- Phone: http://192.168.4.98:7777 (Mac's current IP)

## Known Issues
- TV IP changes via DHCP — recommend setting static reservation in router
- WOL doesn't work when TV is fully off (not just standby)
- Server needs caffeinate or Mac sleep will kill it
