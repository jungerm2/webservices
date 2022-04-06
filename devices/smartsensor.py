import json

import bme680
import paho.mqtt.client as mqtt

BROKER_ADDR = "192.168.1.115"
TOPIC_BASE = "home/bedroom/smartsensor1"
CLIENT_NAME = "SMARTSENSOR1-RPI0"
MAX_TRIES = 5


def on_connect(client, userdata, flags, rc):
    client.subscribe(f"{TOPIC_BASE}/set")


if __name__ == "__main__":
    try:
        sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
    except (RuntimeError, IOError):
        sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)

    sensor.set_humidity_oversample(bme680.OS_2X)
    sensor.set_pressure_oversample(bme680.OS_4X)
    sensor.set_temperature_oversample(bme680.OS_8X)
    sensor.set_filter(bme680.FILTER_SIZE_3)

    client = mqtt.Client(CLIENT_NAME)
    client.on_connect = on_connect
    client.connect(BROKER_ADDR)

    for _ in range(MAX_TRIES):
        if sensor.get_sensor_data():
            data = {
                "temperature": sensor.data.temperature,
                "pressure": sensor.data.pressure,
                "humidity": sensor.data.humidity,
            }
            client.publish(f"{TOPIC_BASE}", json.dumps(data))
            break
