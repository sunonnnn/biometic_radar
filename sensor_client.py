import socket
import threading
import time


class SensorClient:
    
    POWER_PORT = 23
    GPS_PORT = 24
    
    def __init__(self):
        self.sensors = {}
        self.power_status = {}
        self.gps_data = {}
        self.gps_sockets = {}
        self.nmea_message = None
        self.running = False
        self.threads = []
        
        self.on_power_change = None
        self.on_gps_update = None
        self.on_sensor_connected = None
    
    def add_sensor(self, ip, channel):
        self.sensors[ip] = channel
    
    def start(self):
        self.running = True
        
        for ip, channel in self.sensors.items():
            power_thread = threading.Thread(
                target=self._connect_power_socket, 
                args=(ip, channel),
                daemon=True
            )
            gps_thread = threading.Thread(
                target=self._connect_gps_socket, 
                args=(ip, channel),
                daemon=True
            )
            
            power_thread.start()
            gps_thread.start()
            
            self.threads.append(power_thread)
            self.threads.append(gps_thread)
    
    def stop(self):
        self.running = False
        
        for sock in self.gps_sockets.values():
            try:
                sock.close()
            except:
                pass
        
        for thread in self.threads:
            thread.join(timeout=1.0)
    
    def _connect_power_socket(self, ip, channel):
        print(f"Connecting to power socket: {ip}:{self.POWER_PORT}")
        
        try:
            sock = socket.socket()
            sock.settimeout(5.0)
            sock.connect((ip, self.POWER_PORT))
            connect_msg = sock.recv(20)
            print(f"Power socket connected: {ip} - {connect_msg}")
            
            self._receive_power_data(sock, ip)
            
        except socket.timeout:
            print(f"Power socket connection timeout: {ip}")
        except Exception as e:
            print(f"Power socket error ({ip}): {e}")
        finally:
            try:
                sock.close()
            except:
                pass
    
    def _connect_gps_socket(self, ip, channel):
        print(f"Connecting to GPS socket: {ip}:{self.GPS_PORT}")
        
        try:
            sock = socket.socket()
            sock.settimeout(5.0)
            sock.connect((ip, self.GPS_PORT))
            connect_msg = sock.recv(20)
            print(f"GPS socket connected: {ip} - {connect_msg}")
            
            if self.on_sensor_connected:
                self.on_sensor_connected(ip, channel)
            
            self.gps_sockets[ip] = sock
            self._receive_gps_data(sock, ip)
            
        except socket.timeout:
            print(f"GPS socket connection timeout: {ip}")
        except Exception as e:
            print(f"GPS socket error ({ip}): {e}")
        finally:
            if ip in self.gps_sockets:
                del self.gps_sockets[ip]
            try:
                sock.close()
            except:
                pass
    
    def _receive_power_data(self, sock, ip):
        P_STX = b'\x02'
        
        while self.running:
            try:
                byte = sock.recv(1)
                
                if not byte:
                    print(f"Power socket closed: {ip}")
                    break
                
                if byte == P_STX:
                    data = sock.recv(2)
                    sock.recv(3)
                    
                    if data == b'01':
                        power = True
                        print(f"Power ON received from {ip}")
                    elif data == b'00':
                        power = False
                        print(f"Power OFF received from {ip}")
                    else:
                        continue
                    
                    self.power_status[ip] = power
                    
                    if self.on_power_change:
                        self.on_power_change(ip, power)
                
                time.sleep(0.1)
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Power receive error ({ip}): {e}")
                break
    
    def _receive_gps_data(self, sock, ip):
        G_STX = b'$'
        
        while self.running:
            try:
                byte = sock.recv(1)
                
                if not byte:
                    print(f"GPS socket closed: {ip}")
                    break
                
                if byte == G_STX:
                    packet = byte
                    while True:
                        packet += sock.recv(1)
                        if packet[-2:] == b'\r\n':
                            break
                    
                    data = packet.decode('utf-8', errors='ignore')
                    fields = data.split(',')
                    
                    self.nmea_message = data.strip()
                    
                    if len(fields) >= 5:
                        try:
                            lat = self._nmea_to_decimal(fields[2])
                            lng = self._nmea_to_decimal(fields[4])
                            
                            self.gps_data[ip] = (lng, lat)
                            
                            if self.on_gps_update:
                                self.on_gps_update(ip, lng, lat)
                            
                        except (ValueError, IndexError) as e:
                            print(f"GPS parse error ({ip}): {e}")
                    
                    time.sleep(0.1)
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"GPS receive error ({ip}): {e}")
                break

    def send_rtcm(self, rtcm_data):
        for ip, sock in self.gps_sockets.items():
            try:
                sock.send(rtcm_data)
                print(f"Sent RTCM data to {ip} ({len(rtcm_data)} bytes)")
            except Exception as e:
                print(f"Error sending RTCM to {ip}: {e}")

    @staticmethod
    def _nmea_to_decimal(raw):
        raw_float = float(raw)
        degrees = int(raw_float / 100)
        minutes = raw_float - degrees * 100
        return degrees + minutes / 60
