import network
import bluetooth
import utime
import json
from machine import Timer
from micropython import const

# BLE配置
BLE_NAME = "ESP32Pro"
SERVICE_UUID = bluetooth.UUID(0x181C)  # 自定义服务UUID
CHAR_SSID_UUID = bluetooth.UUID(0x2A3D)  # SSID特征
CHAR_PASS_UUID = bluetooth.UUID(0x2A3E)  # 密码特征
CHAR_STATUS_UUID = bluetooth.UUID(0x2A3F)  # 状态特征

# WiFi连接状态码
WL_CONNECTING = 0
WL_SUCCESS = 1
WL_FAILED = 2

def advertising_payload(name, services=None, appearance=0):
    payload = bytearray()
    
    def _append(ad_type, value):
        nonlocal payload
        payload += bytes([len(value) + 1, ad_type]) + value
    
    # 添加上限发现标志（可连接、非定向）
    _append(0x01, b'\x06')
    
    # 添加完整设备名称
    _append(0x09, name.encode('utf-8'))
    
    # 添加服务UUID列表
    if services:
        for uuid in services:
            # 处理不同类型的UUID对象
            if isinstance(uuid, bluetooth.UUID):
                # 尝试通过bytes()方法获取原始数据
                try:
                    uuid_bytes = bytes(uuid)
                    if len(uuid_bytes) == 2:  # 16位UUID
                        _append(0x02, uuid_bytes)
                    elif len(uuid_bytes) == 16:  # 128位UUID
                        _append(0x03, uuid_bytes[::-1])  # 反转字节序
                except TypeError:
                    # 尝试通过int()方法获取数值
                    try:
                        uuid_int = int(uuid)
                        uuid_bytes = uuid_int.to_bytes(2, 'little')
                        _append(0x02, uuid_bytes)
                    except:
                        print(f"无法处理UUID: {uuid}")
            else:
                # 处理原始字节数据
                if len(uuid) == 2:
                    _append(0x02, uuid)
                elif len(uuid) == 16:
                    _append(0x03, uuid[::-1])
    
    # 添加外观值（可选）
    if appearance:
        _append(0x19, appearance.to_bytes(2, 'little'))
    
    return payload

class ESP32BLEProvisioner:
    def __init__(self, name=BLE_NAME):
        self.name = name
        self.wifi_ssid = None
        self.wifi_pass = None
        self.conn_handle = None
        self.provisioning_complete = False
        
        # 初始化蓝牙
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.config(gap_name=self.name)  # 强制设置GAP名称
        self.ble.irq(self._irq)
        
        # 注册BLE服务
        service = (
            SERVICE_UUID, 
            [
                (CHAR_SSID_UUID, bluetooth.FLAG_WRITE),
                (CHAR_PASS_UUID, bluetooth.FLAG_WRITE),
                (CHAR_STATUS_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY),
            ]
        )
        ((self.ssid_handle, self.pass_handle, self.status_handle),) = self.ble.gatts_register_services([service])
        
        # 初始化状态特征值
        self.ble.gatts_write(self.status_handle, bytes([WL_CONNECTING]))
        
        # 设置广播
        self.advertise()
        
        # 创建定时器
        self.timer = Timer(-1)
        
        # 初始化WiFi
        self.wifi = network.WLAN(network.STA_IF)
        self.wifi.active(True)
        
        # 尝试加载已保存的凭据
        self.load_credentials()
        
        # 如果已有凭据，尝试连接WiFi
        if self.wifi_ssid and self.wifi_pass:
            print("发现已保存的WiFi凭据，尝试连接...")
            if self.connect_wifi():
                print("已使用保存的凭据连接WiFi")
                # 更新状态特征值
                self.ble.gatts_write(self.status_handle, bytes([WL_SUCCESS]))
                if self.conn_handle:
                    self.ble.gatts_notify(self.conn_handle, self.status_handle)
    
    def advertise(self):
        """开始广播蓝牙服务"""
        # 使用自定义的广播数据生成函数
        payload = advertising_payload(
            name=self.name, 
            services=[SERVICE_UUID]
        )
        # 手动将bytes转换为十六进制字符串（兼容MicroPython 1.19）
        hex_payload = ''.join(f'{b:02x}' for b in payload)
        print("广播数据HEX:", hex_payload)
        self.ble.gap_advertise(100, adv_data=payload)
        print("正在广播蓝牙服务...")
    
    def _irq(self, event, data):
        """蓝牙事件处理"""
        if event == 1:  # 连接建立
            self.conn_handle, addr_type, addr = data
            print("设备已连接")
            self.ble.gap_advertise(None)  # 停止广播
        
        elif event == 2:  # 连接断开
            self.conn_handle = None
            self.advertise()  # 重新开始广播
            print("设备已断开连接")
        
        elif event == 3:  # 特征写入事件
            conn_handle, value_handle = data
            if conn_handle == self.conn_handle:
                if value_handle == self.ssid_handle:
                    self.wifi_ssid = self.ble.gatts_read(self.ssid_handle).decode().strip()
                    print(f"收到SSID: {self.wifi_ssid}")
                elif value_handle == self.pass_handle:
                    self.wifi_pass = self.ble.gatts_read(self.pass_handle).decode().strip()
                    print("收到密码")
                    # 延迟连接WiFi，确保SSID和密码都已接收
                    self.timer.init(period=1000, mode=Timer.ONE_SHOT, callback=lambda t: self.connect_wifi())
    
    def connect_wifi(self):
        """连接到WiFi网络"""
        if not self.wifi_ssid or not self.wifi_pass:
            print("没有WiFi配置")
            return False
        
        # 更新状态为连接中
        self.ble.gatts_write(self.status_handle, bytes([WL_CONNECTING]))
        if self.conn_handle:
            self.ble.gatts_notify(self.conn_handle, self.status_handle)
        
        # 断开当前连接
        if self.wifi.isconnected():
            self.wifi.disconnect()
        
        # 尝试连接WiFi
        print(f"正在连接到WiFi: {self.wifi_ssid}")
        self.wifi.connect(self.wifi_ssid, self.wifi_pass)
        
        # 等待连接结果
        max_wait = 20
        while max_wait > 0:
            if self.wifi.isconnected():
                status = WL_SUCCESS
                break
            max_wait -= 1
            utime.sleep(1)
        else:
            status = WL_FAILED
        
        # 更新状态特征值
        self.ble.gatts_write(self.status_handle, bytes([status]))
        if self.conn_handle:
            self.ble.gatts_notify(self.conn_handle, self.status_handle)
        
        if status == WL_SUCCESS:
            print("WiFi连接成功!")
            print(f"网络配置: {self.wifi.ifconfig()}")
            # 保存凭据
            self.save_credentials()
            self.provisioning_complete = True
            # 连接成功后停止广播
            self.ble.gap_advertise(None)
            return True
        else:
            print("WiFi连接失败")
            return False
    
    def save_credentials(self, filename='wifi_credentials.json'):
        """保存WiFi凭据到文件"""
        if self.wifi_ssid and self.wifi_pass:
            credentials = {
                'ssid': self.wifi_ssid,
                'password': self.wifi_pass
            }
            try:
                with open(filename, 'w') as f:
                    json.dump(credentials, f)
                print(f"凭据已保存到 {filename}")
                return True
            except Exception as e:
                print(f"保存凭据失败: {e}")
        return False
    
    def load_credentials(self, filename='wifi_credentials.json'):
        """从文件加载WiFi凭据"""
        try:
            with open(filename, 'r') as f:
                credentials = json.load(f)
                self.wifi_ssid = credentials.get('ssid')
                self.wifi_pass = credentials.get('password')
            print(f"凭据已从 {filename} 加载")
            return True
        except Exception as e:
            print(f"加载凭据失败: {e}")
        return False

def main():
    print("=== ESP32 MicroPython蓝牙配网服务 ===")
    
    # 创建配网实例
    provisioner = ESP32BLEProvisioner()
    
    # 等待配网完成
    while not provisioner.provisioning_complete:
        utime.sleep(0.1)
    
    print("配网流程完成!")

if __name__ == "__main__":
    main()
