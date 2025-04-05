import machine
import utime
import ustruct
from machine import Pin, SPI, UART

# Pin assignments
RF_SWITCH_PIN = Pin(15, Pin.OUT)  # GPIO15 for RF switch (0 = 2.4 GHz, 1 = 5.8 GHz)
LED_PIN = Pin(25, Pin.OUT)        # Onboard LED for status
spi_sdr = SPI(0, baudrate=1000000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(19), miso=Pin(16))
sdr_cs = Pin(17, Pin.OUT)         # SDR chip select
spi_lora = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
lora_cs = Pin(13, Pin.OUT)        # LoRa chip select
lora_reset = Pin(14, Pin.OUT)     # LoRa reset
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))  # UART for DJI Onboard SDK

# LoRa configuration (SX1276, 915 MHz)
LORA_FREQ = 915.0  # MHz
LORA_POWER = 20    # dBm

def init_lora():
    lora_reset.value(0)
    utime.sleep_ms(10)
    lora_reset.value(1)
    utime.sleep_ms(10)
    lora_cs.value(0)
    spi_lora.write(bytes([0x01, 0x88]))  # LoRa + Sleep
    spi_lora.write(bytes([0x06, int(LORA_FREQ * 2**19 / 32) & 0xFF]))  # Freq low
    spi_lora.write(bytes([0x07, (int(LORA_FREQ * 2**19 / 32) >> 8) & 0xFF]))  # Freq mid
    spi_lora.write(bytes([0x08, int(LORA_FREQ * 2**19 / 32) >> 16]))  # Freq high
    spi_lora.write(bytes([0x09, LORA_POWER & 0x1F]))  # Power
    spi_lora.write(bytes([0x01, 0x8B]))  # LoRa + Standby
    lora_cs.value(1)

def send_lora_packet(data):
    lora_cs.value(0)
    spi_lora.write(bytes([0x01, 0x8B]))  # Standby
    spi_lora.write(bytes([0x0D, 0x00]))  # FIFO pointer
    spi_lora.write(bytes([0x12, 0xFF]))  # Clear IRQ
    spi_lora.write(bytes([0x40, len(data)]))  # Payload length
    spi_lora.write(bytes([0x00]) + data)  # Write payload
    spi_lora.write(bytes([0x01, 0x83]))  # Start TX
    lora_cs.value(1)
    utime.sleep_ms(100)  # Wait for TX
    lora_cs.value(0)
    spi_lora.write(bytes([0x01, 0x8B]))  # Back to Standby
    lora_cs.value(1)

def read_sdr_rssi():
    sdr_cs.value(0)
    spi_sdr.write(bytes([0x01, 0x00]))  # Dummy RSSI request (adjust for RTL-SDR)
    rssi_data = spi_sdr.read(2)
    sdr_cs.value(1)
    return -(rssi_data[1] + rssi_data[0] * 256) / 2  # Example conversion to dBm

def read_dji_yaw():
    if uart.any():
        # Expecting DJI Onboard SDK telemetry frame (simplified example)
        # Format: STX (0xAA), Length, Data (yaw as float), CRC
        data = uart.read(16)  # Adjust based on actual frame size
        try:
            if data[0] == 0xAA:  # Start byte
                yaw_bytes = data[4:8]  # Assuming yaw at offset 4, 4 bytes (float)
                yaw = ustruct.unpack("<f", yaw_bytes)[0]  # Little-endian float
                return yaw if 0 <= yaw <= 360 else 0.0
        except:
            pass
    return 0.0

def init_dji_sdk():
    # Send activation command to DJI Onboard SDK (simplified)
    # Replace with your app ID and key from DJI Developer account
    APP_ID = "your_app_id_here"
    APP_KEY = "your_app_key_here"
    activation_msg = bytes([0xAA, 0x0A]) + APP_ID.encode() + APP_KEY.encode()
    uart.write(activation_msg)
    utime.sleep_ms(1000)  # Wait for response
    # Request telemetry subscription (e.g., attitude data)
    uart.write(bytes([0xAA, 0x04, 0x01, 0x01]))  # Example: Subscribe to yaw

def main():
    init_lora()
    init_dji_sdk()
    LED_PIN.value(1)
    utime.sleep_ms(1000)
    LED_PIN.value(0)
    
    while True:
        # 2.4 GHz
        RF_SWITCH_PIN.value(0)
        utime.sleep_ms(50)
        rssi_24 = read_sdr_rssi()
        yaw = read_dji_yaw()
        
        # 5.8 GHz
        RF_SWITCH_PIN.value(1)
        utime.sleep_ms(50)
        rssi_58 = read_sdr_rssi()
        
        # Send packets
        packet_24 = ustruct.pack("Bhh", 24, int(rssi_24 * 10), int(yaw * 10))
        send_lora_packet(packet_24)
        
        packet_58 = ustruct.pack("Bhh", 58, int(rssi_58 * 10), int(yaw * 10))
        send_lora_packet(packet_58)
        
        LED_PIN.value(1)
        utime.sleep_ms(50)
        LED_PIN.value(0)
        utime.sleep_ms(450)  # 2 Hz loop

if __name__ == "__main__":
    main()