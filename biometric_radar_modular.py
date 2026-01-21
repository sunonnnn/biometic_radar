from ntrip_manager import NtripManager
import sys
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer
from pathlib import Path
import yaml

from staticMap import StaticMap, MapViewController
from sensor_client import SensorClient
from sensor_list_widget import SensorListWidget
from ntrip_client import NtripClient
from config_manager import ConfigManager
from map_overlay_widget import MapWithOverlay
from marker_overlay import MarkerOverlay


class BiometricRadarApp(QMainWindow):
    
    def __init__(self, config_data):
        super().__init__()
        self._setup_values(config_data)
        self._setup_window()
        self._setup_ui()
        self._setup_map()
        self._setup_sensor_client()
        self._setup_controllers()
        self._setup_ntrip()
        self._start_application()

    def _setup_values(self, config_data):
        self.naver_client = config_data.get("naver_client", {})
        self.defaults = config_data.get("default_layout", {})
        self.window = config_data.get("window_settings", {})
        self.sensors_ip = config_data.get("sensors_ip", {})
        self.update_interval = config_data.get("map_update_interval", 1000)
        self.ntrip_settings = config_data.get("ntrip_settings", {})
        
        self.initial_map_loaded = False
    
    def _setup_window(self):
        self.setWindowTitle("Biometric Radar Map Viewer")
        self.setFixedSize(self.window["width"], self.window["height"])
    
    def _setup_map(self):
        self.map = StaticMap()
        self.map.setLogininfo(self.naver_client["id"], self.naver_client["key"])
        self.map.setSize(self.window["width"] - 300, self.window["height"])
        self.map.setZoom(self.defaults["zoom_level"])
        self.default_center = (self.defaults["center_lng"], self.defaults["center_lat"])

    def _setup_sensor_client(self):
        self.sensor_client = SensorClient()
        
        for ip, channel in self.sensors_ip.items():
            self.sensor_client.add_sensor(ip, channel)
            self.sensor_list.add_sensor(ip, channel)
    
    def _setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        
        self.map_container = MapWithOverlay()
        self.map_label = self.map_container.map_label
        self.overlay = self.map_container.overlay
        
        self.marker_overlay = MarkerOverlay(self.map_label)
        
        self.overlay.sensor_add_requested.connect(self._on_sensor_add_requested)
        
        self.sensor_list = SensorListWidget()
        self.sensor_list.sensor_deleted.connect(self._on_sensor_deleted)
        
        layout.addWidget(self.map_container)
        layout.addWidget(self.sensor_list)
        
        self.setCentralWidget(central)
    
    def _setup_controllers(self):
        self.map_controller = MapViewController(
            self.map_label, 
            self.map, 
            update_callback=self.update_map
        )

    def _setup_ntrip(self):
        try:
            ntrip_client = NtripClient(
                self.ntrip_settings["host_address"],
                self.ntrip_settings["host_port"],
                self.ntrip_settings["user_id"],
                self.ntrip_settings["user_pw"],
                self.ntrip_settings["mount_point"]
            )

            if ntrip_client.connect():
                self.ntrip_manager = NtripManager(ntrip_client, self.sensor_client)
                self.ntrip_manager.start()
                self.overlay.set_rtk_status(True)
            else:
                print("NTRIP connection failed, continuing without RTK")
                self.ntrip_manager = None
                self.overlay.set_rtk_status(False)
                
        except Exception as e:
            print(f"NTRIP setup error: {e}, continuing without RTK")
            self.ntrip_manager = None
            self.overlay.set_rtk_status(False)

    def _start_application(self):
        if not self.sensors_ip:
            print("No sensors configured. Loading map with default center...")
            self._load_default_map()
        else:
            print("Waiting for first GPS data...")
            
            self.sensor_client.start()
            
            self.gps_check_timer = QTimer(self)
            self.gps_check_timer.timeout.connect(self._check_for_initial_gps)
            self.gps_check_timer.start(100)
            
            self.gps_timeout_timer = QTimer(self)
            self.gps_timeout_timer.timeout.connect(self._on_gps_timeout)
            self.gps_timeout_timer.setSingleShot(True)
            self.gps_timeout_timer.start(5000)
        
        self.marker_timer = QTimer(self)
        self.marker_timer.timeout.connect(self.update_ui)
        self.marker_timer.start(self.update_interval)
    
    def _check_for_initial_gps(self):
        if self.sensor_client.gps_data and not self.initial_map_loaded:
            # 첫 번째 GPS 좌표 가져오기
            first_ip = list(self.sensor_client.gps_data.keys())[0]
            first_gps = self.sensor_client.gps_data[first_ip]
            lng, lat = first_gps
            
            print(f"First GPS received: ({lng:.6f}, {lat:.6f})")
            print("Loading map centered at first sensor location...")
            
            # 첫 GPS 좌표를 중심으로 지도 설정
            self.map.setCenter(lng, lat)
            
            print(f"Map center set to: {self.map.getCenter()}")
            
            self.marker_overlay.map_center = (lng, lat)
            
            QTimer.singleShot(100, self._initial_map_load)
            
            self.gps_check_timer.stop()
            if hasattr(self, 'gps_timeout_timer'):
                self.gps_timeout_timer.stop()
            self.initial_map_loaded = True
    
    def _on_gps_timeout(self):
        if not self.initial_map_loaded:
            print("GPS timeout. Loading map with default center...")
            self.gps_check_timer.stop()
            self._load_default_map()
    
    def _load_default_map(self):
        lng, lat = self.default_center
        print(f"Loading map at default center: ({lng:.6f}, {lat:.6f})")
        
        self.map.setCenter(lng, lat)
        self.marker_overlay.map_center = (lng, lat)
        
        QTimer.singleShot(100, self._initial_map_load)
        self.initial_map_loaded = True
    
    def _initial_map_load(self):
        QApplication.processEvents()
        self.update_map()
    
    def update_map(self):
        pixmap = self.map.getMapImage()
        self.map_label.setPixmap(pixmap)
        
        if hasattr(self, 'overlay'):
            self.overlay.raise_()
        
        if not pixmap.isNull():
            label_pos = self.map_label.pos()
            img_width = pixmap.width()
            img_height = pixmap.height()
            
            label_width = self.map_label.width()
            label_height = self.map_label.height()
            
            x_offset = max(0, (label_width - img_width) // 2)
            y_offset = max(0, (label_height - img_height) // 2)
            
            self.marker_overlay.setGeometry(
                label_pos.x() + x_offset,
                label_pos.y() + y_offset,
                img_width,
                img_height
            )

        center = self.map.getCenter().split(',')
        self.marker_overlay.set_map_params(
            float(center[0]),
            float(center[1]),
            self.map.getZoom(),
            self.map.params["w"],
            self.map.params["h"]
        )
        
        self.update_markers()
    
    def update_markers(self):
        """마커만 업데이트"""
        self.marker_overlay.update_markers(
            sensors=self.sensor_client.sensors,
            gps_data=self.sensor_client.gps_data,
            power_status=self.sensor_client.power_status
        )
    
    def update_ui(self):
        """센서 리스트, 마커 업데이트"""
        for ip in self.sensor_client.sensors.keys():
            power_status = self.sensor_client.power_status.get(ip)
            self.sensor_list.update_power_status(ip, power_status)
            
            gps = self.sensor_client.gps_data.get(ip)
            if gps:
                lng, lat = gps
                self.sensor_list.update_gps(ip, lng, lat)
        
        # RTK 상태 확인
        rtk_active = False
        for ip in self.sensor_client.sensors.keys():
            rtk_status = self.sensor_client.rtk_status.get(ip)
            if rtk_status in ['fixed', 'float']:
                rtk_active = True
                break
        
        self.overlay.set_rtk_status(rtk_active)
        
        self.update_markers()
    
    def _on_sensor_add_requested(self, ip, name):
        """오버레이에서 센서 추가 요청 시"""
        print(f"Adding sensor: {ip} ({name})")
        
        if ip in self.sensor_client.sensors:
            print(f"Sensor {ip} already exists!")
            return
        
        if not name:
            max_channel = 0
            for ch in self.sensor_client.sensors.values():
                if ch.startswith('ch'):
                    try:
                        num = int(ch[2:])
                        max_channel = max(max_channel, num)
                    except ValueError:
                        pass
            
            name = f"ch{max_channel + 1}"
            print(f"Auto-assigned channel: {name}")
        

        # 센서 클라이언트에 추가
        self.sensor_client.add_sensor(ip, name)

        # UI에 추가
        self.sensor_list.add_sensor(ip, name)
        
        # 센서 연결
        import threading
        power_thread = threading.Thread(
            target=self.sensor_client._connect_power_socket,
            args=(ip, name),
            daemon=True
        )
        gps_thread = threading.Thread(
            target=self.sensor_client._connect_gps_socket,
            args=(ip, name),
            daemon=True
        )
        
        power_thread.start()
        gps_thread.start()
        
        self.sensor_client.threads.append(power_thread)
        self.sensor_client.threads.append(gps_thread)
    
    def _on_sensor_deleted(self, ip):
        print(f"Deleting sensor: {ip}")
        
        self.sensor_client.remove_sensor(ip)
        self.update_markers()
    
    def wheelEvent(self, event):
        if hasattr(self, 'overlay'):
            overlay_local_pos = self.overlay.mapFromGlobal(event.globalPos())
            child_widget = self.overlay.childAt(overlay_local_pos)
            
            if child_widget and (child_widget == self.overlay.rtk_indicator or 
                                 child_widget == self.overlay.sensor_panel or
                                 child_widget.parent() == self.overlay.rtk_indicator or
                                 child_widget.parent() == self.overlay.sensor_panel):
                event.ignore()
                return
        
        self.map_controller.handle_wheel_event(event)
    
    def mousePressEvent(self, event):
        if hasattr(self, 'overlay'):
            overlay_local_pos = self.overlay.mapFromGlobal(event.globalPos())
            child_widget = self.overlay.childAt(overlay_local_pos)
            
            if child_widget and (child_widget == self.overlay.rtk_indicator or 
                                 child_widget == self.overlay.sensor_panel or
                                 child_widget.parent() == self.overlay.rtk_indicator or
                                 child_widget.parent() == self.overlay.sensor_panel):
                event.ignore()
                return
        
        self.map_controller.handle_mouse_press(event)
    
    def mouseMoveEvent(self, event):
        if not self.map_controller.is_dragging:
            if hasattr(self, 'overlay'):
                overlay_local_pos = self.overlay.mapFromGlobal(event.globalPos())
                child_widget = self.overlay.childAt(overlay_local_pos)
                
                if child_widget and (child_widget == self.overlay.rtk_indicator or 
                                     child_widget == self.overlay.sensor_panel or
                                     child_widget.parent() == self.overlay.rtk_indicator or
                                     child_widget.parent() == self.overlay.sensor_panel):
                    event.ignore()
                    return
        
        self.map_controller.handle_mouse_move(event)
    
    def mouseReleaseEvent(self, event):
        self.map_controller.handle_mouse_release(event)
    
    def closeEvent(self, event):
        print("Closing application...")
        
        if hasattr(self, 'gps_check_timer'):
            self.gps_check_timer.stop()
        
        if hasattr(self, 'ntrip_manager') and self.ntrip_manager:
            self.ntrip_manager.stop()
        
        self.sensor_client.stop()
        
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    config_manager = ConfigManager()
    result = config_manager.exec_()
    
    config_data = config_manager.get_result()
    
    if not config_data:
        print("Configuration cancelled")
        sys.exit(0)
    
    BASE_DIR = Path(__file__).resolve().parent
    config_path = BASE_DIR / "config" / "config.yaml"
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print("config file is not found")
        sys.exit(1)
    
    config_data['default_layout'] = file_config.get('default_layout', {})
    config_data['window_settings'] = file_config.get('window_settings', {})
    config_data['map_update_interval'] = file_config.get('map_update_interval', 1000)
    
    window = BiometricRadarApp(config_data)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
