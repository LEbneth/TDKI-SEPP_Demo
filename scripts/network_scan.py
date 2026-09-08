import subprocess

command = ["nmap", "-sn", "192.168.178.0/24"]

result = subprocess.run(
    command,
    capture_output=True,
    text=True
)

print(result.stdout)