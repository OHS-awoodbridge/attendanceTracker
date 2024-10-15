import time
import board
import digitalio
import simpleio
import busio
import mfrc522
import os
import time
import adafruit_ntp
import rtc
import adafruit_connection_manager
from lcd.lcd import LCD
from lcd.i2c_pcf8574_interface import I2CPCF8574Interface
from lcd.lcd import CursorMode
from adafruit_wiznet5k.adafruit_wiznet5k import WIZNET5K
from digitalio import DigitalInOut
import adafruit_minimqtt.adafruit_minimqtt as MQTT

# Add settings.toml to your filesystem. Add your Adafruit IO username and key as well.
# DO NOT share that file or commit it into Git or other source control.

aio_username = os.getenv("aio_username")
aio_key = os.getenv("aio_key")


#setup SPI for W5500
cs = DigitalInOut(board.GP17)
spi_bus = busio.SPI(board.GP18, MOSI=board.GP19, MISO=board.GP16)

# Initialize ethernet interface with DHCP
eth = WIZNET5K(spi_bus, cs)

# lcd setup
i2c = busio.I2C(scl=board.GP1, sda=board.GP0)
lcd = LCD(I2CPCF8574Interface(i2c, 0x27), num_rows=4, num_cols=20)

#rfid scanner setup
sck = board.GP14
mosi = board.GP11
miso = board.GP12
cs = board.GP13
rst = board.GP15
#spi = busio.SPI(clock=sck, MOSI=mosi, MISO=miso)

rfid = mfrc522.MFRC522(sck, mosi, miso ,cs,rst)
rfid.set_antenna_gain(0x07 << 4)

lcd.print("\n***** Scan your RFid tag/card *****\n")

prev_data = ""
prev_time = 0
timeout = 1

# scans feed to collect boops
scans_feed = aio_username + "/feeds/scans"

# names feed to return uncollected names
names_feed = aio_username + "/feeds/names"

# Define callback methods which are called when events occur
def connected(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to Adafruit IO! Listening for topic changes on %s" % names_feed)
    # Subscribe to all changes on the names feed.
    client.subscribe(names_feed)


def disconnected(client, userdata, rc):
    # This method is called when the client is disconnected
    print("Disconnected from Adafruit IO!")


def message(client, topic, message):
    # This method is called when a topic the client is subscribed to
    # has a new message.
    print(f"New message on topic {topic}: {message}")


pool = adafruit_connection_manager.get_radio_socketpool(eth)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(eth)


TZ_OFFSET = -8
ntp = adafruit_ntp.NTP(pool, tz_offset=TZ_OFFSET, socket_timeout=20)
r = rtc.RTC()
r.datetime = ntp.datetime


# Set up a MiniMQTT Client
# NOTE: We'll need to connect insecurely for ethernet configurations.
mqtt_client = MQTT.MQTT(
    broker="io.adafruit.com",
    username=aio_username,
    password=aio_key,
    is_ssl=False,
    socket_pool=pool,
    ssl_context=ssl_context,
)

# Setup the callback methods above
mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_message = message

# Connect the client to the MQTT broker.
print("Connecting to Adafruit IO...")
mqtt_client.connect()

while True:
    (status, tag_type) = rfid.request(rfid.REQALL)

    if status == rfid.OK:
        (status, raw_uid) = rfid.anticoll()

        if status == rfid.OK:
            rfid_data = "{:02x}{:02x}{:02x}{:02x}".format(raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3])

            if rfid_data != prev_data:
                prev_data = rfid_data
                lcd.clear()
                lcd.print("Card detected! UID: {}".format(rfid_data))
                #post card scan
                boop_val = str(r.datetime) + ";" + rfid_data
                print("Sending boop value: " + boop_val)
                mqtt_client.publish(scans_feed, boop_val)
                print("Sent!")


            prev_time = time.monotonic()

    else:
        if time.monotonic() - prev_time > timeout:
            prev_data = ""
            # Poll the message queue
            mqtt_client.loop(1)

