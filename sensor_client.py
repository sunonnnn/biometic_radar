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
        self.rtk_status = {}
        self.power_sockets = {}
        self.gps_sockets = {}
        self.nmea_message = None
        self.running = False
        self.threads = []
        
        self.reconnect_timers = {}  # {ip: {"power": time, "gps": time}}
        self.reconnect_interval = 5.0
        
        # 임시 GPS 데이터 (기본 위치 주변)
        self.mock_gps_data = {
            "192.168.119.1": (126.713423, 37.337056),
            "192.168.119.2": (126.714391, 37.337489),
            "192.168.119.3": (126.714658, 37.336942)
        }
    
    def add_sensor(self, ip, channel):
        self.sensors[ip] = channel
        self.reconnect_timers[ip] = {"power": 0, "gps": 0}
    
    def remove_sensor(self, ip):
        print(f"Removing sensor: {ip}")
        
        if ip in self.sensors:
            del self.sensors[ip]
        
        if ip in self.reconnect_timers:
            del self.reconnect_timers[ip]
        
        if ip in self.power_sockets:
            try:
                self.power_sockets[ip].shutdown(socket.SHUT_RDWR)
                self.power_sockets[ip].close()
            except:
                pass
            del self.power_sockets[ip]
        
        if ip in self.gps_sockets:
            try:
                self.gps_sockets[ip].shutdown(socket.SHUT_RDWR)
                self.gps_sockets[ip].close()
            except:
                pass
            del self.gps_sockets[ip]
        
        if ip in self.power_status:
            del self.power_status[ip]
        
        if ip in self.gps_data:
            del self.gps_data[ip]
        
        if ip in self.rtk_status:
            del self.rtk_status[ip]
    
    def start(self):
        self.running = True
        
        for ip, channel in self.sensors.items():
            # 임시 데이터 설정
            """if ip in self.mock_gps_data:
                self.gps_data[ip] = self.mock_gps_data[ip]
                self.power_status[ip] = False  # 전원 OFF
                if ip == "192.168.119.1":
                    self.power_status[ip] = True  # 첫 번째 센서는 전원 ON
                
                if self.on_sensor_connected:
                    self.on_sensor_connected(ip, channel)
                
                if self.on_power_change:
                    self.on_power_change(ip, True)
                
                if self.on_gps_update:
                    lng, lat = self.mock_gps_data[ip]
                    self.on_gps_update(ip, lng, lat)"""
                    
            # 실제 연결 시도
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
        
        reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True
        )
        reconnect_thread.start()
        self.threads.append(reconnect_thread)
    
    def stop(self):
        self.running = False
        
        for sock in list(self.power_sockets.values()):
            try:
                sock.close()
            except:
                pass
        
        for sock in list(self.gps_sockets.values()):
            try:
                sock.close()
            except:
                pass
        
        for thread in self.threads:
            thread.join(timeout=1.0)
    
    def _reconnect_loop(self):
        while self.running:
            current_time = time.time()
            
            for ip, channel in list(self.sensors.items()):
                if ip not in self.sensors:
                    continue
                
                if self.power_status.get(ip) is None:
                    if current_time - self.reconnect_timers[ip]["power"] >= self.reconnect_interval:
                        print(f"Attempting to reconnect power socket: {ip}")
                        self.reconnect_timers[ip]["power"] = current_time
                        
                        thread = threading.Thread(
                            target=self._connect_power_socket,
                            args=(ip, channel),
                            daemon=True
                        )
                        thread.start()
                
                if ip not in self.gps_sockets:
                    if current_time - self.reconnect_timers[ip]["gps"] >= self.reconnect_interval:
                        print(f"Attempting to reconnect GPS socket: {ip}")
                        self.reconnect_timers[ip]["gps"] = current_time
                        
                        thread = threading.Thread(
                            target=self._connect_gps_socket,
                            args=(ip, channel),
                            daemon=True
                        )
                        thread.start()
            
            time.sleep(1.0)
    
    def _connect_power_socket(self, ip, channel):
        print(f"Connecting to power socket: {ip}:{self.POWER_PORT}")
        
        sock = None
        try:
            sock = socket.socket()
            sock.settimeout(5.0)
            sock.connect((ip, self.POWER_PORT))
            connect_msg = sock.recv(20)
            print(f"Power socket connected: {ip} - {connect_msg}")
            
            if ip in self.reconnect_timers:
                self.reconnect_timers[ip]["power"] = time.time()
            
            self.power_sockets[ip] = sock
            
            self._receive_power_data(sock, ip)
            
        except socket.timeout:
            print(f"Power socket connection timeout: {ip}")
            if ip in self.sensors:
                self.power_status[ip] = None
        except Exception as e:
            print(f"Power socket error ({ip}): {e}")
            if ip in self.sensors:
                self.power_status[ip] = None
        finally:
            if ip in self.power_sockets:
                del self.power_sockets[ip]
            if sock:
                try:
                    sock.close()
                except:
                    pass
    
    def _connect_gps_socket(self, ip, channel):
        print(f"Connecting to GPS socket: {ip}:{self.GPS_PORT}")
        
        sock = None
        try:
            sock = socket.socket()
            sock.settimeout(5.0)
            sock.connect((ip, self.GPS_PORT))
            connect_msg = sock.recv(20)
            print(f"GPS socket connected: {ip} - {connect_msg}")
            
            if ip in self.reconnect_timers:
                self.reconnect_timers[ip]["gps"] = time.time()
            
            self.gps_sockets[ip] = sock
            self._receive_gps_data(sock, ip)
            
        except socket.timeout:
            print(f"GPS socket connection timeout: {ip}")
        except Exception as e:
            print(f"GPS socket error ({ip}): {e}")
        finally:
            if ip in self.gps_sockets:
                del self.gps_sockets[ip]
            if sock:
                try:
                    sock.close()
                except:
                    pass
    
    def _receive_power_data(self, sock, ip):
        P_STX = b'\x02'
        
        while self.running and ip in self.sensors:
            try:
                byte = sock.recv(1)
                
                if not byte:
                    print(f"Power socket closed: {ip}")
                    self.power_status[ip] = None
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

                    # 임시 데이터
                    """self.power_status["192.168.123.1"] = True
                    self.power_status["192.168.123.2"] = False
                    self.power_status["192.168.123.3"] = None"""
                
                time.sleep(0.1)
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Power receive error ({ip}): {e}")
                self.power_status[ip] = None
                break
    
    def _receive_gps_data(self, sock, ip):
        G_STX = b'$'
        
        while self.running and ip in self.sensors:
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
                    
                    if data.startswith('$GPGGA') or data.startswith('$GNGGA'):
                        if len(fields) >= 7:
                            try:
                                lat = self._nmea_to_decimal(fields[2])
                                lng = self._nmea_to_decimal(fields[4])
                                self.gps_data[ip] = (lng, lat)
                                
                                quality = int(fields[6]) if fields[6] else 0
                                
                                # quality: 0=No fix, 1=GPS, 2=DGPS, 4=RTK fixed, 5=RTK float
                                if quality == 4:
                                    self.rtk_status[ip] = 'fixed'
                                    print(f"RTK Fixed: {ip}")
                                elif quality == 5:
                                    self.rtk_status[ip] = 'float'
                                    print(f"RTK Float: {ip}")
                                else:
                                    self.rtk_status[ip] = 'none'
                                
                            except (ValueError, IndexError) as e:
                                print(f"GPS parse error ({ip}): {e}")
                    
                    time.sleep(0.1)
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"GPS receive error ({ip}): {e}")
                break

    def send_rtcm(self, rtcm_data):
        for ip, sock in list(self.gps_sockets.items()):
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
