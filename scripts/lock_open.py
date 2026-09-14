import threading

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion


BROKER = "192.168.0.104"
PORT = 1883

NUKI_ID = "29F33A6C"

USERNAME = "nuki"
PASSWORD = "nukiPassword"


connected = threading.Event()
connection_error = None


def on_connect(client, userdata, flags, reason_code, properties):
    global connection_error

    if reason_code == 0:
        print("Connected to MQTT broker.")
    else:
        connection_error = reason_code
        print(f"MQTT connection failed: {reason_code}")

    connected.set()


def open_lock():
    topic = f"nuki/{NUKI_ID}/unlock"
    payload = "true"

    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id="lock_open_demo"
    )

    client.username_pw_set(
        USERNAME,
        PASSWORD
    )

    client.on_connect = on_connect

    try:
        print(f"Connecting to {BROKER}:{PORT} ...")

        client.connect(
            BROKER,
            PORT,
            keepalive=60
        )

        # MQTT network loop starten
        client.loop_start()

        # Auf erfolgreiche Verbindung warten
        if not connected.wait(timeout=5):
            raise TimeoutError(
                "Timeout while connecting to MQTT broker."
            )

        if connection_error is not None:
            raise RuntimeError(
                f"MQTT connection failed: {connection_error}"
            )

        print(f"Sending unlock command:")
        print(f"  Topic:   {topic}")
        print(f"  Payload: {payload}")

        result = client.publish(
            topic=topic,
            payload=payload,
            qos=0,
            retain=False
        )

        # Warten bis Nachricht tatsächlich gesendet wurde
        result.wait_for_publish(timeout=5)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"MQTT publish failed: {result.rc}"
            )

        print("Unlock command sent successfully.")

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    open_lock()