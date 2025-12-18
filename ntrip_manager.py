import threading
import time


class NtripManager:
    
    def __init__(self, ntrip_client, sensor_client):
        self.ntrip_client = ntrip_client
        self.sensor_client = sensor_client
        self.running = False
        self.thread = None
    
    def start(self):
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("NTRIP Manager started")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("NTRIP Manager stopped")
    
    def _loop(self):
        while self.running:
            try:
                nmea_message = self.sensor_client.nmea_message
                
                if nmea_message:
                    self.ntrip_client.send_nmea(nmea_message)
                    rtcm_data = self.ntrip_client.receive_rtcm()
                    
                    if rtcm_data:
                        self.sensor_client.send_rtcm(rtcm_data)
                
                time.sleep(1)
                
            except Exception as e:
                print(f"NTRIP loop error: {e}")
                time.sleep(5)
