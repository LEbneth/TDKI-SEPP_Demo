#!/bin/bash

SETUP_DIR="/home/seclab/07_mqtt_exercise/mqtt_setup"
VENV_DIR="/home/seclab/07_mqtt_exercise/venv"

cd "$SETUP_DIR" || exit 1

echo "Starting NanoMQ..."

nohup nanomq restart --conf ./nanomq.conf \
    > "$SETUP_DIR/nanomq.log" 2>&1 &

sleep 3

echo "Checking NanoMQ..."

if ! ss -ltn | grep -q ":1883 "; then
    echo "ERROR: NanoMQ is not listening on port 1883."
    echo "Check nanomq.log"
    exit 1
fi

echo "NanoMQ running on port 1883."

echo "Starting MQTT Device Emulator..."

source "$VENV_DIR/bin/activate"

nohup python "$SETUP_DIR/MQTT_Device_Emulator.py" \
    > "$SETUP_DIR/mqtt_emulator.log" 2>&1 &

sleep 3

echo "Checking emulator..."

if pgrep -f "MQTT_Device_Emulator.py" > /dev/null; then
    echo "MQTT Device Emulator is running."
else
    echo "ERROR: MQTT Device Emulator is not running."
    echo "Check mqtt_emulator.log"
    exit 1
fi

echo ""
echo "MQTT setup is ready."
echo "NanoMQ log:    $SETUP_DIR/nanomq.log"
echo "Emulator log:  $SETUP_DIR/mqtt_emulator.log"
