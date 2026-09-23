import json
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion


BROKER = "192.168.0.104"
PORT = 1883

NUKI_ID = "29F33A6C"

USERNAME = "nuki"
PASSWORD = "nukiPassword"

STATUS_TOPIC = f"nuki/{NUKI_ID}/state"

LOCK_STATES = {
    "0": "Nicht kalibriert",
    "1": "Verriegelt (zugeschlossen)",
    "2": "Wird entriegelt",
    "3": "Entriegelt (aufgeschlossen)",
    "4": "Wird verriegelt",
    "5": "Falle zurückgezogen",
    "6": "Entriegelt (Lock 'n' Go)",
    "7": "Falle wird zurückgezogen",
    "254": "Motor blockiert",
    "255": "Unbekannt",
}

connected = threading.Event()
status_received = threading.Event()
connection_error = None
lock_status = None


def on_connect(client, userdata, flags, reason_code, properties):
    global connection_error

    if reason_code == 0:
        print("Connected to MQTT broker.")
        client.subscribe(STATUS_TOPIC)
    else:
        connection_error = reason_code
        print(f"MQTT connection failed: {reason_code}")

    connected.set()


def on_message(client, userdata, message):
    global lock_status

    payload = message.payload.decode("utf-8", errors="replace")

    try:
        lock_status = json.loads(payload)
    except json.JSONDecodeError:
        lock_status = payload

    status_received.set()


def get_lock_status():
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id="lock_status_demo"
    )

    client.username_pw_set(
        USERNAME,
        PASSWORD
    )

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        print(f"Connecting to {BROKER}:{PORT} ...")

        client.connect(
            BROKER,
            PORT,
            keepalive=60
        )

        client.loop_start()

        if not connected.wait(timeout=5):
            raise TimeoutError(
                "Timeout while connecting to MQTT broker."
            )

        if connection_error is not None:
            raise RuntimeError(
                f"MQTT connection failed: {connection_error}"
            )

        print(f"Requesting lock status:")
        print(f"  Topic:   {STATUS_TOPIC}")

        if not status_received.wait(timeout=5):
            raise TimeoutError(
                "Timeout while waiting for lock status."
            )

        print("Lock status received:")
        if isinstance(lock_status, dict):
            state_value = lock_status.get(
                "state",
                lock_status.get("lockState")
            )
            if state_value is not None:
                state_name = LOCK_STATES.get(
                    str(state_value),
                    LOCK_STATES["255"]
                )
                print(f"  Schlossstatus: {state_name}")
                print(f"  Statuscode: {state_value}")

            if "batteryCritical" in lock_status:
                print(
                    f"  Batterie kritisch: "
                    f"{lock_status['batteryCritical']}"
                )

            for key, value in lock_status.items():
                if key not in ("state", "lockState", "batteryCritical"):
                    print(f"  {key}: {value}")
        else:
            print(
                f"  Schlossstatus: "
                f"{LOCK_STATES.get(str(lock_status), LOCK_STATES['255'])}"
            )

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    get_lock_status()
