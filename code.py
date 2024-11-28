import time
import board
import pwmio
import digitalio
import simpleio
import busio
import adafruit_ntp
import rtc
import adafruit_thermal_printer
import adafruit_connection_manager
import adafruit_requests
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import config
from adafruit_wiznet5k.adafruit_wiznet5k import WIZNET5K
from adafruit_pn532.i2c import PN532_I2C
from lcd.lcd import LCD
from lcd.i2c_pcf8574_interface import I2CPCF8574Interface
from lcd.lcd import CursorMode



buzzer = pwmio.PWMOut(board.GP9, variable_frequency = True)
buzzer_duty = 2**15


#setup SPI for W5500
cs = digitalio.DigitalInOut(board.GP17)
spi_bus = busio.SPI(board.GP18, MOSI=board.GP19, MISO=board.GP16)
eth = WIZNET5K(spi_bus, cs)


#lcd setup
i2c = busio.I2C(scl=board.GP1, sda=board.GP0)
lcd = LCD(I2CPCF8574Interface(i2c, 0x27), num_rows=4, num_cols=20)

#thermal printer
ThermalPrinter = adafruit_thermal_printer.get_printer_class(2.69)
uart = busio.UART(tx=board.GP12, rx=board.GP13, baudrate=19200)
printer = ThermalPrinter(uart, auto_warm_up=False)

#rfid setup
reset_pin = digitalio.DigitalInOut(board.GP6)
reset_pin.direction = digitalio.Direction.INPUT
irq_pin = digitalio.DigitalInOut(board.GP8)
irq_pin.direction = digitalio.Direction.INPUT
pn532 = PN532_I2C(i2c, debug=False, reset=reset_pin, irq=irq_pin)

#ic, ver, rev, support = pn532.firmware_version
#print("Found PN532 with firmware version: {0}.{1}".format(ver, rev))
pn532.SAM_configuration()

#start up ethernet and update RTC
pool = adafruit_connection_manager.get_radio_socketpool(eth)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(eth)
TZ_OFFSET = -8
ntp = adafruit_ntp.NTP(pool, tz_offset=TZ_OFFSET, socket_timeout=20)
r = rtc.RTC()
r.datetime = ntp.datetime
days = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
old_t = r.datetime.tm_min-1


# Define callback methods which are called when events occur
def connected(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to broker as " + config.station)
    # Subscribe to all changes on the names feed.
    client.subscribe(config.station)
    client.subscribe(config.report)


def disconnected(client, userdata, rc):
    # This method is called when the client is disconnected
    print("Disconnected from server")


def message(client, topic, message):
    global buzzer_duty
    # This method is called when a topic the client is subscribed to
    # has a new message.
    if(topic == config.station):
        lcd.print(message+"\n")
        if message[0:2] == 'no':
            buzzer.frequency = 100
            buzzer.duty_cycle = buzzer_duty
            time.sleep(.5)
            buzzer.duty_cycle = 0

        else:
            buzzer.frequency = 1000
            buzzer.duty_cycle = buzzer_duty
            time.sleep(0.25)
            buzzer.duty_cycle = 0
    elif(topic == config.report):
        #printer.warm_up()
        lcd.clear()
        lcd.print("Report Printing")
        payload = message.split("|")
        for line in payload:
            if line == "L":
                printer.size = adafruit_thermal_printer.SIZE_LARGE
            elif line == "M":
                printer.size = adafruit_thermal_printer.SIZE_MEDIUM
            elif line == "S":
                 printer.size = adafruit_thermal_printer.SIZE_SMALL
            else:
                printer.print(line)
        for m in payload:
            print(m)
        lcd.clear()

def period_report():
    printer.size = adafruit_thermal_printer.SIZE_LARGE
    printer.print("Period 5")
    printer.feed(1)
    printer.size = adafruit_thermal_printer.SIZE_MEDIUM
    printer.print("Absent")
    printer.size = adafruit_thermal_printer.SIZE_SMALL
    printer.print("Name 1")
    printer.print("Name 2")
    printer.print("Name 3")
    printer.feed(1)
    printer.size = adafruit_thermal_printer.SIZE_MEDIUM
    printer.print("Tardy")
    printer.size = adafruit_thermal_printer.SIZE_SMALL
    printer.print("Name 1")
    printer.print("Name 2")
    printer.print("Name 3")
    printer.feed(4)
    printer.print("")


# Set up a MiniMQTT Client
# NOTE: We'll need to connect insecurely for ethernet configurations.


mqtt_client = MQTT.MQTT(
    broker=config.mqtt_server_ip,
    is_ssl=False,
    socket_pool=pool,
    ssl_context=None,
    port = 1883,
    keep_alive = 60,

)


# Setup the callback methods above
mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_message = message

# Connect the client to the MQTT broker.
print("Connecting to broker...")
lcd.print("Connecting to broker...")
mqtt_client.connect()
lcd.print("Success")












prev_data = ""
prev_time = 0
timeout = 1







# Start listening for a card
pn532.listen_for_passive_target()
print("Waiting for RFID/NFC card...")
while True:
    t = r.datetime
    quicktime = t.tm_hour * 60 + t.tm_min
    #print(quicktime)
    if (old_t != t.tm_min):
        lcd.clear()
        lcd.print("%d:%02d %s %d/%d/%d\n" % (t.tm_hour, t.tm_min,days[t.tm_wday], t.tm_mon, t.tm_mday, t.tm_year))
        old_t = t.tm_min




    #lcd.print("The time is %d:%02d:%02d" % (t.tm_hour, t.tm_min, t.tm_sec))
    #print(irq_pin.value)
    # Check if a card is available to read
    if irq_pin.value == 0:
        try:
            uid = pn532.get_passive_target()
        except:
            lcd.print("bad read")
        else:
            #print("Found card with UID:", [hex(i) for i in uid])
            rfid_data = "{:02x}{:02x}{:02x}{:02x}".format(uid[0], uid[1], uid[2], uid[3])
            if rfid_data != prev_data:
                    prev_data = rfid_data
                    unhexed_id = int(rfid_data,16)
                    #lcd.clear()
                    #lcd.print("Card: {}\n".format(rfid_data))
                    payload = str(unhexed_id)+"-"+config.station[1:]+"-In-"+ str(quicktime)
                    print(payload)
                    mqtt_client.publish("scans",payload)
            # Start listening for a card again
        pn532.listen_for_passive_target()

        prev_time = time.monotonic()
    else:
        if time.monotonic() - prev_time > timeout:
            prev_data = ""
    mqtt_client.loop(1)
    time.sleep(0.1)

