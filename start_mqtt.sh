#!/bin/bash

set -e

SETUP_DIR="/home/seclab/07_mqtt_exercise/mqtt_setup"
VENV="/home/seclab/07_mqtt_exercise/venv"

echo "======================================"
echo " SEPP MQTT Startup"
echo "======================================"

cd "$SETUP_DIR"

echo "[1/3] Starting NanoMQ broker..."
nanomq restart --conf nanomq.conf

sleep 2

echo "[2/3] Checking MQTT broker..."

if ss -ltn | grep -q ":1883 "; then
    echo "NanoMQ is running on port 1883."
else
    echo "ERROR: NanoMQ did not start."
    exit 1
fi

echo "[3/3] Starting MQTT Device Emulator..."

source "$VENV/bin/activate"

nohup python MQTT_Device_Emulator.py \
    > "$SETUP_DIR/mqtt_emulator.log" 2>&1 &

EMULATOR_PID=$!

sleep 2

if kill -0 "$EMULATOR_PID" 2>/dev/null; then
    echo "MQTT Device Emulator is running."
else
    echo "ERROR: MQTT Device Emulator did not start."
    echo "Check:"
    echo "$SETUP_DIR/mqtt_emulator.log"
    exit 1
fi

echo ""
echo "======================================"
echo " MQTT SETUP READY"
echo " Broker:   port 1883"
echo " Emulator: PID $EMULATOR_PID"
echo "======================================"
