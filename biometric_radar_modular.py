import sys
from PyQt5.QtWidgets import QMainWindow, QApplication, QLabel, QWidget, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer

from staticMap import StaticMap
from sensor_client import SensorClient
from sensor_list_widget import SensorListWidget
from map_view_controller import MapViewController
from marker_manager import MarkerManager
from ntrip_client import NtripClient
from ntrip_manager import NtripManager
import config


class BiometricRadarApp(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self._setup_window()
        self._setup_map()
        self._setup_sensor_client()
        self._setup_ui()
        self._setup_controllers()
        self._setup_ntrip()
        self._start_application()
    
    def _setup_window(self):
        self.setWindowTitle("Biometric Radar Map Viewer")
        self.setGeometry(100, 100, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
    
    def _setup_map(self):
        self.map = StaticMap()
        self.map.setLogininfo(config.NAVER_CLIENT_ID, config.NAVER_CLIENT_KEY)
        self.map.setSize(config.DEFAULT_MAP_WIDTH, config.DEFAULT_MAP_HEIGHT)
        self.map.setZoom(config.DEFAULT_ZOOM_LEVEL)
        self.map.setCenter(config.DEFAULT_CENTER_LNG, config.DEFAULT_CENTER_LAT)
    
    def _setup_sensor_client(self):
        self.sensor_client = SensorClient()
        
        for ip, channel in config.SENSORS.items():
            self.sensor_client.add_sensor(ip, channel)
        
        self.sensor_client.on_sensor_connected = self._on_sensor_connected
        self.sensor_client.on_power_change = self._on_power_change
        self.sensor_client.on_gps_update = self._on_gps_update
    
    def _setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        
        self.map_label = QLabel(self)
        self.map_label.setAlignment(Qt.AlignCenter)
        
        self.sensor_list = SensorListWidget()
        
        layout.addWidget(self.map_label)
        layout.addWidget(self.sensor_list)
        
        self.setCentralWidget(central)
    
    def _setup_controllers(self):
        self.marker_manager = MarkerManager(self.map)
        
        self.map_controller = MapViewController(self.map_label, self.map)
        self.map_controller.set_update_callback(self.update_map)

    def _setup_ntrip(self):
        try:
            ntrip_client = NtripClient(
                config.HOST_ADDRESS,
                config.HOST_PORT,
                config.USER_ID,
                config.USER_PW,
                config.MOUNT_POINT
            )

            if ntrip_client.connect():
                self.ntrip_manager = NtripManager(ntrip_client, self.sensor_client)
                self.ntrip_manager.start()
            else:
                print("NTRIP connection failed, continuing without RTK")
                self.ntrip_manager = None
                
        except Exception as e:
            print(f"NTRIP setup error: {e}, continuing without RTK")
            self.ntrip_manager = None

    def _start_application(self):
        self.sensor_client.start()
        
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_map)
        self.update_timer.start(config.MAP_UPDATE_INTERVAL)
        
        self.update_map()
    
    def update_map(self):
        if self.map_controller.is_dragging or self.map_controller.is_zooming:
            return
        
        self.marker_manager.update_markers(
            sensors=self.sensor_client.sensors,
            gps_data=self.sensor_client.gps_data,
            power_status=self.sensor_client.power_status
        )
        
        pixmap = self.map.getMapImage()
        self.map_label.setPixmap(pixmap)
    
    def _on_sensor_connected(self, ip, channel):
        print(f"Sensor connected: {ip} ({channel})")
        self.sensor_list.add_sensor(ip, channel)
    
    def _on_power_change(self, ip, power_on):
        status = "ON" if power_on else "OFF"
        print(f"Power status changed: {ip} -> {status}")
    
    def _on_gps_update(self, ip, lng, lat):
        print(f"GPS updated: {ip} -> ({lng:.6f}, {lat:.6f})")
    
    def wheelEvent(self, event):
        self.map_controller.handle_wheel_event(event)
    
    def mousePressEvent(self, event):
        self.map_controller.handle_mouse_press(event)
    
    def mouseMoveEvent(self, event):
        self.map_controller.handle_mouse_move(event)
    
    def mouseReleaseEvent(self, event):
        self.map_controller.handle_mouse_release(event)
    
    def closeEvent(self, event):
        print("Closing application...")
        
        if hasattr(self, 'ntrip_manager') and self.ntrip_manager:
            self.ntrip_manager.stop()
        
        self.sensor_client.stop()
        
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = BiometricRadarApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
