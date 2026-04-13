import eel
import socket
import threading
import csv
from screeninfo import get_monitors
import time
import struct

monitor = get_monitors()
monitors = get_monitors()
for monitor in monitors:
    width = monitor.width
    height = monitor.height



#CONFIG
IP_ADDRESS = "192.168.4.1"
PORT = 80
TARGET_COUNT = 71 
CSV_FILE = 'fe_sample.csv'
eel.init('web')
eel.start(
    'index.html',
    size=(width, height),
    position=(100, 100),
    block=True
)


f = open(CSV_FILE, "w+")
f.close()


COLUMNS = [
    "Time",
    "Suspension travel FR (analog)",
    "Wheel Speed FR",
    "Rotor Temp FR",
    "Wheel temp FR",
    "Steering Angle FL (analog)",
    "Suspension travel FL (analog)",
    "Wheel Speed FL",
    "Rotor Temp FL",
    "Wheel temp FL",
    "Air Pressure FL",
    "Suspension travel BR (analog)",
    "Wheel Speed BR",
    "Rotor Temp BR",
    "Wheel temp BR",
    "Air Pressure BR",
    "Suspension travel BL (analog)",
    "Wheel Speed BL",
    "Rotor Temp BL",
    "Wheel temp BL",
    "Fluid Temp BL",
    "Fusebox Sensor 1",
    "Fusebox Sensor 2",
    "Fusebox Sensor 3",
    "Fusebox Sensor 4",
    "Fusebox Sensor 5",
    "Fusebox Sensor 6",
    "Fusebox Sensor 7",
    "Fusebox Sensor 8",
    "Fusebox Sensor 9",
    "Fusebox Sensor 10",
    "Fusebox Sensor 11",
    "Fusebox Sensor 12",
    "Fusebox Sensor 13",
    "Throttle 1 Raw",
    "Throttle 2 Raw",
    "Throttle 1",
    "Throttle 2",
    "Front Brake Raw",
    "Rear Brake Raw",
    "Motor Controller temp",
    "Motor Temp",
    "Battery Temp",
    "Low Volt Battery Temp",
    "Motor Speed",
    "Battery Voltage",
    "Current Drive Mode",
    "Ignition One state",
    "Ignition Two State",
    "Ams Fault Can",
    "IMD Fault Can",
    "BSPD Fault",
    "Brake Light",
    "Phase A Current",
    "Phase B Current",
    "Phase C Current",
    "DC Bus Current",
    "Commanded Torque",
    "Torque Feedback",
    "Soft Plausibility",
    "High Sense",
    "Current Car State",
    "QBAI",
    "Plausibility Fault",
    "Hard Brake",
    "Shut Down Circuit",
    "Battery State Of Charge",
    "Battery Current",
    "Torque",
    "Difference in Two throttles",
    "extra"
]

# Global variables for state and socket
APP_STATE = "LIVE" 
system_socket = None
socket_lock = threading.Lock() # Prevents overlapping commands

@eel.expose
def set_app_state(new_state):
    global APP_STATE, system_socket
    APP_STATE = new_state
    print(f"Switched state to: {APP_STATE}")
    
    # Send 'f' to ESP32 to switch its state as per your notes
    if APP_STATE == "FILE_TRANSFER" and system_socket:
        with socket_lock:
            system_socket.send(b'f')
            eel.update_status("File Transfer Mode", "orange")
    elif APP_STATE == "LIVE" and system_socket:
        eel.update_status("Live Data Mode", "green")


@eel.expose
def request_file_list():
    """Step 1 & 3: Laptop sends 0xF0, receives 0xFFFF + files + 0xFFFF"""
    global system_socket
    if not system_socket or APP_STATE != "FILE_TRANSFER": return []
    
    with socket_lock:
        try:
            # Step 1: Send 0xF0
            system_socket.send(b'\xF0')
            
            # Step 3: Wait for 0xFFFF start byte, file names, 0xFFFF end byte
            # Note: You will need to parse this byte stream specifically based on 
            # exactly how the Teensy formats the 2-byte numbers.
            # This is a rough framework for capturing that packet:
            response = system_socket.recv(1024) 
            
            # TODO: Parse 'response' bytes into actual integer file names based on 0xFFFF bounds
            # For now, returning a dummy list to show the UI connection
            return [101, 102, 103] 
        except Exception as e:
            print(f"Error fetching files: {e}")
            return []

@eel.expose
def download_file_data(file_name, data_point):
    """Step 4 & 9: Laptop sends 0xFF + file + datapoint + 0xFF, receives chunks"""
    global system_socket
    if not system_socket: return "No Connection"
    
    with socket_lock:
        try:
            # Step 4: Laptop sends back 0xFF, file name, data point, then 0xFF
            # Using struct to pack integers to bytes (adjust format 'B' or 'H' as needed)
            packet = struct.pack('>B H B B', 0xFF, int(file_name), int(data_point), 0xFF)
            system_socket.send(packet)
            
            file_data = []
            
            # Step 9: Transmit to laptop 0xFF state, recurring 100, then final 0xFF
            while True:
                chunk = system_socket.recv(1024) # Adjust buffer size as needed
                
                # Check for final 0xFF byte to break the loop
                if chunk.endswith(b'\xFF'):
                    file_data.append(chunk[:-1]) # Append everything except the final byte
                    break
                else:
                    file_data.append(chunk)
                    # If Teensy expects an ACK for every 100-value chunk:
                    # system_socket.send(b'\xFF') 
            
            # Process file_data into a CSV file here
            print("File download complete.")
            return "Success"
            
        except Exception as e:
            return f"Error: {e}"


def background_data_collection():
    global system_socket, APP_STATE
    
    print(f"Attempting to connect to {IP_ADDRESS}...")
    system_socket = socket.socket()
    system_socket.settimeout(10)

    try:
        system_socket.connect((IP_ADDRESS, PORT))
        print(f"Connected to {IP_ADDRESS}")
        eel.update_status("Live Data Mode", "green")
    except Exception as e:
        print(f"Connection failed: {e}")
        eel.update_status(f"Connection Failed: {e}", "red")
        return

    data_buffer = []

    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        
        while True:
            if APP_STATE == "LIVE":
                with socket_lock:
                    try:
                        system_socket.send(b"1")
                        packet = system_socket.recv(1024)
                        
                        if not packet: break

                        for byte_val in packet:
                            data_buffer.append(byte_val)

                            if len(data_buffer) == TARGET_COUNT:
                                writer.writerow(data_buffer)
                                f.flush() # Force write to disk
                                eel.update_sensor_data(data_buffer)
                                data_buffer.clear()
                    except socket.timeout:
                        continue # Ignore timeouts in live mode and retry
                    except socket.error as e:
                        break
            
            elif APP_STATE == "FILE_TRANSFER":
                # In file transfer state, this background loop just sleeps.
                # The socket communication is handled by the exposed Eel functions.
                time.sleep(0.1) 
                
    system_socket.close()

if __name__ == '__main__':
    #Start data thread
    t = threading.Thread(target=background_data_collection, daemon=True)
    t.start()
 
    #init Eel
    try:
        eel.start('index.html', mode='default', size=(1000, 800), block=False)

    except (SystemExit, KeyboardInterrupt):
        print("Closing App...")