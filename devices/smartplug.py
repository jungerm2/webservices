import paho.mqtt.client as mqtt
from gpiozero import LED

BROKER_ADDR = "192.168.1.115"
TOPIC_BASE = "home/bedroom/smartplug1"
HA_STATUS_TOPIC = "homeassistant/status"
CLIENT_NAME = "SMARTPLUG1-RPI0"
PLUG = LED(26, active_high=True, initial_value=False)


def send_status():
    client.publish(f"{TOPIC_BASE}/get", "on" if PLUG.value else "off")


def on_connect(client, userdata, flags, rc):
    client.subscribe(f"{TOPIC_BASE}/set")
    client.subscribe(HA_STATUS_TOPIC)


def on_message(client, userdata, message):
    payload = str(message.payload.decode("utf-8"))
    if message.topic == f"{TOPIC_BASE}/set":
        if payload == "on":
            PLUG.on()
        elif payload == "off":
            PLUG.off()
        send_status()
    elif message.topic == HA_STATUS_TOPIC:
        if payload == "online":
            send_status()
        elif payload == "offline":
            # Nothing to do
            pass


if __name__ == "__main__":
    client = mqtt.Client(CLIENT_NAME)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_ADDR)
    send_status()
    client.loop_forever()
