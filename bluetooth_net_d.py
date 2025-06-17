import network
import bluetooth
import time
import json
from micropython import const


# 常量定义
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# 自定义服务和特征UUID
_PROV_UUID = bluetooth.UUID("0000FFF0-0000-1000-8000-00805F9B34FB")
_PROV_CHAR_UUID = bluetooth.UUID("0000FFF1-0000-1000-8000-00805F9B34FB")

# 特征标志
_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

# 配网命令常量
_CMD_WIFI = "WIFI:"
_CMD_DONE = "DONE"


class ESP32BLEProvisioner:
    def __init__(self, name="ESP32-Provision"):
        self.name = name
        self.wifi_credentials = None
        self.provisioning_complete = False
        
        # 初始化蓝牙
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)
        
        # 注册服务和特征
        self.register()
        
        # 开始广播
        self.advertise()
    
    def register(self):
        # 服务和特征定义
       _PROV_SERVICE = (
            _PROV_UUID, 
            [(_PROV_CHAR_UUID, _FLAG_READ | _FLAG_WRITE | _FLAG_NOTIFY)]
         )
        
        # 注册服务
       services = (_PROV_SERVICE,)
       ((self.prov_handle,),) = self.ble.gatts_register_services(services)
        
        # 存储连接状态
       self.conn_handle = None
    
    def advertise(self):
        """开始广播蓝牙服务"""
        name = bytes(self.name, 'UTF-8')
        adv_data = bytearray('\x02\x01\x02', 'UTF-8') + bytearray((len(name) + 1, 0x09)) + name
        self.ble.gap_advertise(100, adv_data)
        print("正在广播蓝牙服务...")
    
    def _irq(self, event, data):
        """蓝牙事件处理"""
        if event == _IRQ_CENTRAL_CONNECT:
            # 连接建立
            conn_handle, _, _ = data
            self.conn_handle = conn_handle
            self.ble.gap_advertise(0)  # 停止广播
            print("设备已连接")
        
        elif event == _IRQ_CENTRAL_DISCONNECT:
            # 连接断开
            conn_handle, _, _ = data
            if conn_handle == self.conn_handle:
                self.conn_handle = None
                self.advertise()  # 重新开始广播
                print("设备已断开连接")
        
        elif event == _IRQ_GATTS_WRITE:
            # 收到写入数据
            conn_handle, value_handle = data
            if conn_handle == self.conn_handle and value_handle == self.prov_handle:
                data = self.ble.gatts_read(self.prov_handle)
                self._handle_provisioning_data(data)
    
    def _handle_provisioning_data(self, data):
        """处理配网数据"""
        try:
            message = data.decode('utf-8').strip()
            print(f"收到数据: {message}")
            
            if message.startswith(_CMD_WIFI):
                # 解析WiFi配置
                wifi_data = message[len(_CMD_WIFI):]
                try:
                    self.wifi_credentials = json.loads(wifi_data)
                    print(f"WiFi配置已接收: {self.wifi_credentials}")
                    
                    # 通知客户端已接收配置
                    if self.conn_handle is not None:
                        self.ble.gatts_notify(self.conn_handle, self.prov_handle, "CONFIG_RECEIVED")
                except json.JSONDecodeError:
                    print("配置格式错误")
                    if self.conn_handle is not None:
                        self.ble.gatts_notify(self.conn_handle, self.prov_handle, "ERROR: INVALID FORMAT")
            
            elif message == _CMD_DONE:
                # 完成配网
                if self.wifi_credentials:
                    self.provisioning_complete = True
                    print("开始连接WiFi...")
                    if self.conn_handle is not None:
                        self.ble.gatts_notify(self.conn_handle, self.prov_handle, "CONNECTING_TO_WIFI")
                else:
                    print("未收到WiFi配置")
                    if self.conn_handle is not None:
                        self.ble.gatts_notify(self.conn_handle, self.prov_handle, "ERROR: NO CONFIG")
        
        except UnicodeError:
            print("数据解码错误")
    
    def connect_wifi(self):
        """连接到WiFi网络"""
        if not self.wifi_credentials:
            print("没有WiFi配置")
            return False
        
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print("已连接到WiFi")
            return True
        
        ssid = self.wifi_credentials.get('ssid', '')
        password = self.wifi_credentials.get('password', '')
        
        print(f"正在连接到WiFi: {ssid}")
        wlan.connect(ssid, password)
        
        # 等待连接或超时
        max_wait = 20
        while max_wait > 0:
            if wlan.isconnected():
                break
            max_wait -= 1
            time.sleep(1)
        
        if wlan.isconnected():
            print("WiFi连接成功!")
            print(f"网络配置: {wlan.ifconfig()}")
            return True
        else:
            print("WiFi连接失败")
            return False
    
    def save_credentials(self, filename='wifi_credentials.json'):
        """保存WiFi凭据到文件"""
        if self.wifi_credentials:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.wifi_credentials, f)
                print(f"凭据已保存到 {filename}")
                return True
            except Exception as e:
                print(f"保存凭据失败: {e}")
        return False
    
    def load_credentials(self, filename='wifi_credentials.json'):
        
        """从文件加载WiFi凭据"""
        try:
            with open(filename, 'r') as f:
                self.wifi_credentials = json.load(f)
            print(f"凭据已从 {filename} 加载")
            return True
        except Exception as e:
            print(f"加载凭据失败: {e}")
        return False

def main():
    print("=== ESP32 MicroPython蓝牙配网服务 ===")
    
    # 创建配网实例
    provisioner = ESP32BLEProvisioner()
    
    # 尝试加载已保存的凭据
    provisioner.load_credentials()
    
    # 如果已有凭据，尝试连接WiFi
    if provisioner.wifi_credentials:
        print("发现已保存的WiFi凭据，尝试连接...")
        if provisioner.connect_wifi():
            print("已使用保存的凭据连接WiFi")
            # 可以选择不启动蓝牙配网服务
            # return
    
    # 等待配网完成
    while not provisioner.provisioning_complete:
      time.sleep(0.1)
    
    # 配网完成后连接WiFi
      if provisioner.connect_wifi():
        # 保存凭据
        provisioner.save_credentials()
        
        # 可选：连接成功后停止蓝牙服务
        # provisioner.ble.active(False)
      print("配网流程完成!")
      print("MTU:", self.ble.config('mtu'))

if __name__ == "__main__":
    main()
