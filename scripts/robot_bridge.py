"""Forward the real Verdex robot's telemetry into the planner.

The ESP32 firmware (farming_robot/esp32/PlantGuardBot) publishes JSON every
5 s on MQTT topic `farm/telemetry`. This bridge subscribes and POSTs each
message to the planner, so the dashboard switches from VIRTUAL to LIVE.

    # Wi-Fi / MQTT (what the firmware does today; broker on the laptop)
    python scripts/robot_bridge.py mqtt --host 127.0.0.1

    # Bluetooth serial fallback: ESP32 prints one JSON object per line
    python scripts/robot_bridge.py serial --port /dev/tty.PlantGuardBot

    # No robot at all: replay a recorded CSV/JSONL log at real speed
    python scripts/robot_bridge.py replay data/robot_log.jsonl

Field names are matched flexibly (temperatureC / temp / t, soilMoisturePct /
soil, ...), see backend/robot.py.
"""
import argparse
import json
import sys
import time

import requests

API = "http://127.0.0.1:8000"

def post(payload: dict):
    try:
        r = requests.post(f"{API}/api/robot/telemetry", json=payload, timeout=5)
        print(("ok  " if r.ok else f"{r.status_code} ") + json.dumps(payload)[:120], flush=True)
    except requests.RequestException as exc:
        print(f"planner not reachable: {exc}", flush=True)

def run_mqtt(host, port, topic):
    import paho.mqtt.client as mqtt

    def on_message(_c, _u, msg):
        try:
            post(json.loads(msg.payload))
        except json.JSONDecodeError:
            pass

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="verdex-planner-bridge")
    c.on_message = on_message
    c.connect(host, port)
    c.subscribe(topic)
    print(f"listening on mqtt://{host}:{port}/{topic}", flush=True)
    c.loop_forever()

def run_serial(port, baud):
    import serial  # pip install pyserial

    with serial.Serial(port, baud, timeout=2) as s:
        print(f"reading {port} @ {baud}", flush=True)
        while True:
            line = s.readline().decode(errors="ignore").strip()
            if line.startswith("{"):
                try:
                    post(json.loads(line))
                except json.JSONDecodeError:
                    pass

def run_replay(path, speed):
    rows = [json.loads(line) for line in open(path) if line.strip().startswith("{")]
    print(f"replaying {len(rows)} readings", flush=True)
    for r in rows:
        post(r)
        time.sleep(5 / speed)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API)
    sub = ap.add_subparsers(dest="mode", required=True)
    m = sub.add_parser("mqtt")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=1883)
    m.add_argument("--topic", default="farm/telemetry")
    s = sub.add_parser("serial")
    s.add_argument("--port", required=True)
    s.add_argument("--baud", type=int, default=115200)
    r = sub.add_parser("replay")
    r.add_argument("path")
    r.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()
    API = a.api
    try:
        if a.mode == "mqtt":
            run_mqtt(a.host, a.port, a.topic)
        elif a.mode == "serial":
            run_serial(a.port, a.baud)
        else:
            run_replay(a.path, a.speed)
    except KeyboardInterrupt:
        sys.exit(0)
