# See: https://github.com/pimoroni/pimoroni-pico/blob/main/micropython/examples/pico_enviro/enviro_all.py

import json

import bme680
import paho.mqtt.client as mqtt

BROKER_ADDR = "192.168.1.215"
TOPIC_BASE = "home/bedroom/smartsensor1"
CLIENT_NAME = "SMARTSENSOR1-RPI0"
MAX_TRIES = 5
TEMPERATURE_OFFSET = 7
ALTITUDE = 266  # in meters?


def on_connect(client, userdata, flags, rc):
    client.subscribe(f"{TOPIC_BASE}/set")


def adjust_to_sea_pressure(pressure_hpa, temperature, altitude):
    """
    Adjust pressure based on your altitude.

    credits to @cubapp https://gist.github.com/cubapp/23dd4e91814a995b8ff06f406679abcf
    """

    # Adjusted-to-the-sea barometric pressure
    adjusted_hpa = pressure_hpa + ((pressure_hpa * 9.80665 * altitude) / (287 * (273 + temperature + (altitude / 400))))
    return adjusted_hpa


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
            # correct temperature and humidity using an offset
            corrected_temperature = sensor.data.temperature - TEMPERATURE_OFFSET
            dewpoint = sensor.data.temperature - ((100 - sensor.data.humidity) / 5)
            corrected_humidity = 100 - (5 * (corrected_temperature - dewpoint))
            corrected_pressure = adjust_to_sea_pressure(sensor.data.pressure, corrected_temperature, ALTITUDE)
            data = {
                "temperature": corrected_temperature,
                "pressure": corrected_pressure,
                "humidity": corrected_humidity,
            }
            client.publish(f"{TOPIC_BASE}", json.dumps(data))
            break
