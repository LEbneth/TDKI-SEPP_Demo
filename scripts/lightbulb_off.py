import socket
import json

HOST = "192.168.0.105"
PORT = 55443

cmd_off = {"id": 1, "method": "set_power", "params": ["off", "smooth", 200]}

payload = json.dumps(cmd_off) + "\r\n"

sock = socket.create_connection((HOST, PORT), timeout=5)
sock.settimeout(2)
sock.sendall(payload.encode())

try:
    data = sock.recv(1024)
    if data:
        print("Antwort der Lampe:", data.decode())
    else:
        print("Keine Antwort erhalten")
    sock.close()
except socket.timeout:
    sock.close()

print("Lampe erfolgreich ausgeschaltet.")