import serial
import threading
import time

def receiver_thread():
    try:
        ser_rx = serial.Serial('/dev/cu.usbserial-1120', 9600, timeout=1)
        print("Receiver: Connected")
        
        # Configure receiver
        ser_rx.write(b'AT+MODE=TEST\r\n')
        time.sleep(0.5)
        ser_rx.write(b'AT+TEST=RFCFG,868,SF7,125,12,15,8,ON\r\n')
        time.sleep(0.5)
        ser_rx.write(b'AT+TEST=RXLRPKT\r\n')
        time.sleep(0.5)
        
        print("Receiver: Listening for messages...")
        
        # Listen for messages
        while time.time() - start_time < 30:
            if ser_rx.in_waiting:
                response = ser_rx.readline().decode('ascii', errors='ignore').strip()
                if response:
                    print(f"\nReceiver got: {response}")
                    if "+TEST: RX" in response:
                        try:
                            hex_data = response.split('"')[1]
                            ascii_text = bytes.fromhex(hex_data).decode('ascii')
                            print(f"Decoded message: {ascii_text}")
                        except:
                            print("Could not decode message")
            time.sleep(0.1)
        
        ser_rx.close()
        print("\nReceiver: Completed")
    except Exception as e:
        print(f"Receiver error: {str(e)}")

def transmitter_thread():
    try:
        ser_tx = serial.Serial('/dev/cu.usbserial-10', 9600, timeout=1)
        print("Transmitter: Connected")
        
        # Configure transmitter
        ser_tx.write(b'AT+MODE=TEST\r\n')
        time.sleep(0.5)
        ser_tx.write(b'AT+TEST=RFCFG,868,SF7,125,12,15,8,ON\r\n')
        time.sleep(0.5)
        
        # Send message every 5 seconds
        while time.time() - start_time < 30:
            message = "48656C6C6F20467269656E64"  # "Hello Friend" in hex
            print(f"\nTransmitter: Sending message...")
            ser_tx.write(f'AT+TEST=TXLRPKT,"{message}"\r\n'.encode())
            time.sleep(5)
        
        ser_tx.close()
        print("\nTransmitter: Completed")
    except Exception as e:
        print(f"Transmitter error: {str(e)}")

# Start the test
print("Starting 30-second test...")
start_time = time.time()

# Create and start threads
rx_thread = threading.Thread(target=receiver_thread)
tx_thread = threading.Thread(target=transmitter_thread)

rx_thread.start()
time.sleep(2)  # Give receiver time to start listening
tx_thread.start()

# Wait for threads to complete
rx_thread.join()
tx_thread.join()

print("Test completed")
