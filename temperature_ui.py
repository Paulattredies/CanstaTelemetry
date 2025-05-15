#!/usr/bin/env python3
"""
LoRa Transceiver UI
------------------
A PyQt6-based GUI for monitoring and controlling Wio-E5 LoRa modules
"""

import sys
import time
import serial
import threading
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QPushButton, QTextEdit, 
                            QGridLayout, QGroupBox, QFrame, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QTextCursor

# LoRa module configuration
LORA_PARAMS = {
    "frequency": "868",
    "spreading_factor": "SF7",
    "bandwidth": "125",
    "coding_rate": "12",  # 4/8
    "power": "15",
    "preamble": "8",
    "crc": "ON"
}

# Serial port settings
TRANSMITTER_PORT = '/dev/cu.usbserial-10'
RECEIVER_PORT = '/dev/cu.usbserial-1120'
BAUD_RATE = 9600
TIMEOUT = 1


class SerialWorker(QThread):
    """Worker thread for handling serial communication with the LoRa module"""
    status_update = pyqtSignal(str, str)  # device, message
    message_received = pyqtSignal(str, str)  # device, message
    connection_status = pyqtSignal(str, bool)  # device, status

    def __init__(self, port, device_type):
        super().__init__()
        self.port = port
        self.device_type = device_type
        self.running = False
        self.serial = None
        self.message_to_send = None
        self.send_interval = 5  # seconds
        self.last_send_time = 0

    def configure_device(self):
        """Send AT commands to configure the LoRa module"""
        try:
            # Set TEST mode
            self.serial.write(b'AT+MODE=TEST\r\n')
            time.sleep(0.5)
            self.status_update.emit(self.device_type, f"Set TEST mode")
            
            # Configure RF parameters
            rf_config = f'AT+TEST=RFCFG,{LORA_PARAMS["frequency"]},{LORA_PARAMS["spreading_factor"]},{LORA_PARAMS["bandwidth"]},{LORA_PARAMS["coding_rate"]},{LORA_PARAMS["power"]},{LORA_PARAMS["preamble"]},{LORA_PARAMS["crc"]}\r\n'
            self.serial.write(rf_config.encode())
            time.sleep(0.5)
            self.status_update.emit(self.device_type, f"Configured LoRa parameters")
            
            # For receiver, enable continuous receive
            if self.device_type == "Receiver":
                self.serial.write(b'AT+TEST=RXLRPKT\r\n')
                time.sleep(0.5)
                self.status_update.emit(self.device_type, f"Started listening for packets")
                
            return True
        except Exception as e:
            self.status_update.emit(self.device_type, f"Configuration error: {str(e)}")
            return False

    def connect(self):
        """Connect to the LoRa module"""
        try:
            self.serial = serial.Serial(self.port, BAUD_RATE, timeout=TIMEOUT)
            self.status_update.emit(self.device_type, f"Connected to {self.port}")
            self.connection_status.emit(self.device_type, True)
            return True
        except Exception as e:
            self.status_update.emit(self.device_type, f"Connection error: {str(e)}")
            self.connection_status.emit(self.device_type, False)
            return False

    def disconnect(self):
        """Disconnect from the LoRa module"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.status_update.emit(self.device_type, f"Disconnected")
            self.connection_status.emit(self.device_type, False)

    def send_message(self, message):
        """Prepare a message to be sent"""
        self.message_to_send = message
        self.status_update.emit(self.device_type, f"Queued message for sending: {message}")

    def read_temperature(self):
        """Read temperature from the Wio-E5 internal sensor"""
        if not self.serial or not self.serial.is_open:
            self.status_update.emit(self.device_type, "Error: Device not connected")
            return None
            
        try:
            # Flush all buffers to ensure clean state
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            # Show debug message
            self.status_update.emit(self.device_type, "Sending temperature read command...")
            
            # Send temperature read command
            self.serial.write(b'AT+TEST=TEMP\r\n')
            
            # Important: Wait for device to process the command
            time.sleep(0.5)
            
            # Wait for response with longer timeout
            start_time = time.time()
            response = ""
            complete_response = False
            temperature_value = None
            
            # Use a longer timeout - 5 seconds
            while time.time() - start_time < 5 and not complete_response:
                if self.serial.in_waiting:
                    line = self.serial.readline().decode('ascii', errors='ignore').strip()
                    
                    # Skip empty lines
                    if not line:
                        continue
                        
                    # Add line to cumulative response with indicator
                    response += "RAW> " + line + "\n"
                    self.status_update.emit(self.device_type, f"Response line: '{line}'")
                    
                    # Check for OK or ERROR to mark completion
                    if line == "OK" or "ERROR" in line:
                        complete_response = True
                    
                    # Check if we have a temperature response
                    if "TEMP" in line:
                        self.status_update.emit(self.device_type, f"Found temperature data: '{line}'")
                        # Try to extract temperature - may be in different formats
                        try:
                            # Try different parsing approaches
                            if "TEMP," in line:
                                temp_part = line.split("TEMP,")[1].strip()
                                temperature_value = float(temp_part)
                            elif ":" in line and "TEMP" in line:
                                # Try alternative format "+TEST: TEMP XX.XX"
                                parts = line.split()
                                for i, part in enumerate(parts):
                                    if part == "TEMP" and i < len(parts) - 1:
                                        temperature_value = float(parts[i+1])
                                        break
                                        
                            self.status_update.emit(self.device_type, f"Parsed temperature: {temperature_value}°C")
                        except (IndexError, ValueError) as e:
                            self.status_update.emit(self.device_type, f"Parse error: {str(e)} in '{line}'")
                
                # Small delay between reads
                time.sleep(0.1)
                
            # Log the complete response regardless of success
            self.status_update.emit(self.device_type, f"Complete response:\n{response}")
            
            # Check if we found a temperature value
            if temperature_value is not None:
                self.status_update.emit(self.device_type, f"Final temperature: {temperature_value}°C")
                return temperature_value
            else:
                if complete_response:
                    self.status_update.emit(self.device_type, "Temperature data not found in response")
                else:
                    self.status_update.emit(self.device_type, "Timeout waiting for complete response")
                return None
            
        except Exception as e:
            self.status_update.emit(self.device_type, f"Temperature reading error: {str(e)}")
            return None

    def run(self):
        """Main thread loop"""
        self.running = True
        
        if not self.connect():
            self.running = False
            return
            
        if not self.configure_device():
            self.disconnect()
            self.running = False
            return
        
        while self.running:
            try:
                # Handle receive for both transmitter and receiver (for response reading)
                if self.serial.in_waiting:
                    response = self.serial.readline().decode('ascii', errors='ignore').strip()
                    if response:
                        self.status_update.emit(self.device_type, f"Received: {response}")
                        
                        # Parse received LoRa packet for receiver
                        if self.device_type == "Receiver" and "+TEST: RX" in response:
                            try:
                                hex_data = response.split('"')[1]
                                ascii_text = bytes.fromhex(hex_data).decode('ascii')
                                self.message_received.emit(self.device_type, f"Received message: {ascii_text}")
                            except Exception as e:
                                self.status_update.emit(self.device_type, f"Failed to decode message: {str(e)}")
                
                # Handle transmit for transmitter only
                if self.device_type == "Transmitter":
                    current_time = time.time()
                    if self.message_to_send and (current_time - self.last_send_time >= self.send_interval):
                        # Convert to hex if it's not already
                        if all(c in '0123456789ABCDEFabcdef' for c in self.message_to_send):
                            hex_message = self.message_to_send
                        else:
                            hex_message = ''.join(f'{ord(c):02X}' for c in self.message_to_send)
                            
                        cmd = f'AT+TEST=TXLRPKT,"{hex_message}"\r\n'
                        self.serial.write(cmd.encode())
                        self.message_received.emit(self.device_type, f"Sent message: {self.message_to_send}")
                        self.last_send_time = current_time
                
                # Don't hog the CPU
                time.sleep(0.1)
                
            except Exception as e:
                self.status_update.emit(self.device_type, f"Error: {str(e)}")
                time.sleep(1)  # Pause before trying again
        
        # Clean up on exit
        self.disconnect()

    def stop(self):
        """Stop the worker thread"""
        self.running = False
        self.wait()


class LoraTransceiverUI(QMainWindow):
    """Main window for the LoRa Transceiver UI"""
    
    def __init__(self):
        super().__init__()
        self.transmitter = None
        self.receiver = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle('LoRa Transceiver Monitor')
        self.setGeometry(100, 100, 1000, 800)
        
        # Main layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Title and status bar
        title_layout = QHBoxLayout()
        title_label = QLabel('LoRa Transceiver Monitor')
        title_label.setFont(QFont('Arial', 16, QFont.Weight.Bold))
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        
        # Status indicators
        self.tx_status = self.create_status_indicator("Transmitter")
        self.rx_status = self.create_status_indicator("Receiver")
        title_layout.addWidget(self.tx_status)
        title_layout.addWidget(self.rx_status)
        
        main_layout.addLayout(title_layout)
        
        # Parameters display
        params_group = QGroupBox("LoRa Parameters")
        params_layout = QGridLayout()
        
        params = [
            ("Frequency:", f"{LORA_PARAMS['frequency']} MHz"),
            ("Spreading Factor:", LORA_PARAMS['spreading_factor']),
            ("Bandwidth:", f"{LORA_PARAMS['bandwidth']} kHz"),
            ("Coding Rate:", f"4/{int(LORA_PARAMS['coding_rate'])*2//3}"),
            ("Power:", f"{LORA_PARAMS['power']} dBm"),
            ("Preamble:", LORA_PARAMS['preamble']),
            ("CRC:", LORA_PARAMS['crc'])
        ]
        
        for i, (label, value) in enumerate(params):
            params_layout.addWidget(QLabel(label), i//3, (i%3)*2)
            params_layout.addWidget(QLabel(value), i//3, (i%3)*2 + 1)
            
        params_group.setLayout(params_layout)
        main_layout.addWidget(params_group)
        
        # Message displays
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Transmitter message display
        tx_group = QGroupBox("Transmitter")
        tx_layout = QVBoxLayout()
        self.tx_log = QTextEdit()
        self.tx_log.setReadOnly(True)
        tx_layout.addWidget(self.tx_log)
        tx_group.setLayout(tx_layout)
        
        # Receiver message display
        rx_group = QGroupBox("Receiver")
        rx_layout = QVBoxLayout()
        self.rx_log = QTextEdit()
        self.rx_log.setReadOnly(True)
        rx_layout.addWidget(self.rx_log)
        rx_group.setLayout(rx_layout)
        
        splitter.addWidget(tx_group)
        splitter.addWidget(rx_group)
        main_layout.addWidget(splitter, 1)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_communication)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_communication)
        self.stop_btn.setEnabled(False)
        
        self.clear_btn = QPushButton("Clear Logs")
        self.clear_btn.clicked.connect(self.clear_logs)
        
        self.send_btn = QPushButton("Read & Send Temperature")
        self.send_btn.clicked.connect(self.send_temperature)
        self.send_btn.setEnabled(False)
        
        # Temperature display
        self.temp_label = QLabel("Temperature: --.-°C")
        self.temp_label.setStyleSheet("font-weight: bold; color: blue;")
        
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.clear_btn)
        control_layout.addWidget(self.send_btn)
        control_layout.addWidget(self.temp_label)
        
        main_layout.addLayout(control_layout)
        
        # Status bar for messages
        self.statusBar().showMessage('Ready')
        
        self.show()
    
    def create_status_indicator(self, label):
        """Create a status indicator widget"""
        frame = QFrame()
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        layout.addWidget(QLabel(label))
        
        status = QLabel("●")
        status.setStyleSheet("color: red;")
        status.setFont(QFont('Arial', 14))
        layout.addWidget(status)
        
        frame.setLayout(layout)
        frame.setProperty("device", label)
        frame.setProperty("status_label", status)
        
        return frame
        
    def update_status_indicator(self, device, connected):
        """Update the status indicator for a device"""
        if device == "Transmitter":
            indicator = self.tx_status
        else:
            indicator = self.rx_status
            
        status_label = indicator.property("status_label")
        if connected:
            status_label.setStyleSheet("color: green;")
        else:
            status_label.setStyleSheet("color: red;")
    
    def log_message(self, device, message):
        """Add a timestamped message to the appropriate log"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_msg = f"[{timestamp}] {message}"
        
        if device == "Transmitter":
            self.tx_log.append(formatted_msg)
            self.tx_log.moveCursor(QTextCursor.MoveOperation.End)
        else:
            self.rx_log.append(formatted_msg)
            self.rx_log.moveCursor(QTextCursor.MoveOperation.End)
    
    def update_status(self, device, message):
        """Update the status bar with a message"""
        self.statusBar().showMessage(f"{device}: {message}")
        self.log_message(device, message)
    
    def start_communication(self):
        """Start the transmitter and receiver threads"""
        # Create and start transmitter thread
        self.transmitter = SerialWorker(TRANSMITTER_PORT, "Transmitter")
        self.transmitter.status_update.connect(self.update_status)
        self.transmitter.message_received.connect(self.log_message)
        self.transmitter.connection_status.connect(self.update_status_indicator)
        self.transmitter.start()
        
        # Create and start receiver thread
        self.receiver = SerialWorker(RECEIVER_PORT, "Receiver")
        self.receiver.status_update.connect(self.update_status)
        self.receiver.message_received.connect(self.log_message)
        self.receiver.connection_status.connect(self.update_status_indicator)
        self.receiver.start()
        
        # Update UI
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        
    def stop_communication(self):
        """Stop the transmitter and receiver threads"""
        if self.transmitter and self.transmitter.isRunning():
            self.transmitter.stop()
            
        if self.receiver and self.receiver.isRunning():
            self.receiver.stop()
            
        # Update UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        
    def clear_logs(self):
        """Clear both message logs"""
        self.tx_log.clear()
        self.rx_log.clear()
        self.log_message("System", "Logs cleared")
        
    def send_temperature(self):
        """Read and send actual temperature from the Wio-E5 sensor"""
        if not self.transmitter or not self.transmitter.isRunning():
            self.log_message("Transmitter", "Error: Transmitter not running")
            return

        # Update UI to show we're reading temperature
        self.temp_label.setText("Temperature: Reading...")
        self.temp_label.setStyleSheet("font-weight: bold; color: orange;")
        
        # Read the actual temperature from the device
        temperature = self.transmitter.read_temperature()
        
        if temperature is not None:
            # Format temperature for transmission (as a string with 2 decimal places)
            temp_str = f"{temperature:.2f}"
            
            # Update the temperature display
            self.temp_label.setText(f"Temperature: {temp_str}°C")
            self.temp_label.setStyleSheet("font-weight: bold; color: green;")
            
            # Queue the temperature for sending
            self.transmitter.send_message(temp_str)
            self.log_message("System", f"Sending actual temperature: {temp_str}°C")
        else:
            # Update UI to show the error
            self.temp_label.setText("Temperature: Error")
            self.temp_label.setStyleSheet("font-weight: bold; color: red;")
            self.log_message("System", "Failed to read temperature from device")
        
    def closeEvent(self, event):
        """Handle the window close event"""
        # Stop communication threads if running
        self.stop_communication()
        
        # Accept the close event
        event.accept()


if __name__ == "__main__":
    try:
        # Create the Qt Application
        app = QApplication(sys.argv)
        app.setStyle('Fusion')  # Use Fusion style for a consistent look
        
        # Create and show the main window
        main_window = LoraTransceiverUI()
        
        # Start the application event loop
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"Application error: {str(e)}")
        sys.exit(1)
