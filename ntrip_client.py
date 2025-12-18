import socket
import base64


class NtripClient:
    
    def __init__(self, addr, port, id, pw, mount):
        self.host_address = addr
        self.host_port = port
        self.user_id = id
        self.user_pw = pw
        self.mount_point = mount
        self.auth = base64.b64encode(f"{self.user_id}:{self.user_pw}".encode()).decode()
    
    def connect(self):
        self.socket = socket.socket()
        self.socket.connect((self.host_address, self.host_port))
        
        msg = f"GET /{self.mount_point} HTTP/1.1\r\n"
        msg += "User-Agent: NTRIP ntripclient\r\n"
        msg += "Authorization: Basic " + self.auth + "\r\n"
        msg += "Accept: */*\r\nConnection: close\r\n"
        msg += "\r\n"
        
        self.socket.send(msg.encode())
        
        buffer = self.socket.recv(4096)
        result = buffer.decode("utf-8")
        
        print("NTRIP Server Response:")
        print(result)
        
        if "ICY 200 OK" in result:
            print("Connected to NTRIP Server")
            return True
        else:
            print("Failed to connect to NTRIP Server")
            return False
    
    def send_nmea(self, nmea_message):
        nmea = nmea_message + "\r\n"
        self.socket.send(nmea.encode())
    
    def receive_rtcm(self):
        return self.socket.recv(8192)
    
    def close(self):
        if self.socket:
            self.socket.close()


if __name__ == "__main__":
    HOST_ADDRESS = "RTS1.ngii.go.kr"
    HOST_PORT = 2101
    USER_ID = "ohsh8080"
    USER_PW = "ngii"
    MOUNT_POINT = "RTK-RTCM32"
    NMEA_MESSAGE = "$GPGGA,123519,3735.0079,N,12701.6446,E,1,12,0.8,45.0,M,19.6,M,,*72"

    client = NtripClient(
        HOST_ADDRESS, 
        HOST_PORT, 
        USER_ID, 
        USER_PW, 
        MOUNT_POINT
    )

    if client.connect():
        client.send_nmea(NMEA_MESSAGE)
        rtcm_data = client.receive_rtcm()
        result = base64.b64encode(rtcm_data).decode()
        print("Received RTCM data (base64):", result)
        client.close()
