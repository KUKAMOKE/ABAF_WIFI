_VT = 2.4
_SH="iot.ufanzone.com"
_SC=2383
_SU="admin"
_SP="120111432@qq.com"
from machine import UART,Pin
from _thread import start_new_thread
from socket import socket,AF_INET,SOCK_DGRAM,SOL_SOCKET,SO_REUSEADDR
import smartconfig
import gc
from time import sleep,localtime
from ubinascii import hexlify
from umqtt.simple import MQTTClient
from boot import SA,LedB,_MAC,DP,_ME,APS
from boot import rr,upgrade
ClientID = f'pub-{_MAC}'
pk={"tb":0,"tf":0,"ts":0,"bdv":99,"di":0,"dv":[0]*6}
RDAB=UART(1,baudrate=115200,rx=22,tx=23,timeout=10)
RDAF=UART(2,baudrate=115200,rx=14,tx=13,timeout=10)
def getTt():
    tt = ""
    for v in [str(v) for v in localtime()[:-2]]:
        if len(v) == 1:
            v = "0"+v
        tt += "-"+v
    return tt[1:]

def sync_ntp():
    import ntptime
    ntptime.NTP_DELTA = 3155644800
    ntptime.host = 'ntp.aliyun.com'
    ntptime.settime()
def setNet():
    def sendAck():
        udp=socket(AF_INET,SOCK_DGRAM)
        udp.setsockopt(SOL_SOCKET,SO_REUSEADDR,1)
        dataA=smartconfig.info()[3].to_bytes(1,'little')+SA.config('mac')
        if smartconfig.info()[2]==smartconfig.TYPE_ESPTOUCH:
            dataB=dataA + b"".join([int(v).to_bytes(1,'little') for v in SA.ifconfig()[0].split(".")])
            portB=18266  # esptouch
        else:
            dataB=""
            portB=""
        for j in range(60):
            try:
                udp.sendto(dataA,('255.255.255.255',10000))  # airkiss
            except OSError:
                pass
            try:
                if portB:
                    udp.sendto(dataB,('255.255.255.255',portB))
            except OSError:
                pass
            sleep(0.1)
        udp.close()
        gc.collect()
    while 1:
        sleep(1)
        smt=0
        if SA.isconnected():
            DP["TR"]=0
            continue
        DP["TR"]=2
        try:
            with open("d.txt","r") as __f:
                sid,pw=__f.read().split('\n')
            __f.close()
        except (OSError,ValueError):
            smartconfig.start()
            DP["TR"]=1
            smt=1
            while 1:
                if SA.isconnected():
                    break
                if smartconfig.success():
                    sid,pw=smartconfig.info()[:2]
                    with open("d.txt","w") as __f:
                        __f.write(sid + '\n' + pw)
                    __f.close()
                    break
                sleep(0.5)
        gc.collect()
        try:
            SA.connect(sid,pw)
        except OSError:
            pass
        for i in range(10):
            if SA.isconnected():
                DP["TR"]=0
                if smt:
                    sendAck()
                break
            sleep(1)
        if SA.isconnected():
            try:
                sync_ntp()
            except:
                pass
        else:
            if smt and sid.encode("unicode_escape") in APS:
                rr()
def mqtt_callback(topic, msg):
    try:
        ts=str(msg)[2:-1].split('-')
        print(ts)
        if ts[0] in (_MAC,"AllDevice"):
            DP["TB"]=2
            if ts[1]=="startOTA":
                upgrade()
            if ts[1]=="breath":
                RDAB.write(bytes([int(x,16) for x in ["0x{}".format(ts[2][i:i + 2]) for i in range(0,len(ts[2]),2)]]))
                print("ol",hexlify(RDAB.read()))
            if ts[1]=="fall":
                RDAF.write(bytes([int(x,16) for x in ["0x{}".format(ts[2][i:i + 2]) for i in range(0,len(ts[2]),2)]]))
                print("ol",hexlify(RDAF.read()))
            if ts[1]=="beddis":
                pk["bdv"]=int(ts[2])
        DP["TB"]=0
    except Exception as _e:
        print("mqtt_callback", _e)
        DP["TB"]=0


def toMQ(mq,v,p=""):
    def toDEC():
        return sum([int(v[2][i:i + 2], 16) for i in range(0, 2 * v[1], 2)])
    if DP["TB"]==-1:
        LedB.value(1)
    ts = b"iot-msg"
    to = b"iot-message"
    tsn = b"iot-msg-num"
    try:
        mq.publish(ts, b"{}\"mac\":\"{}\",\"data\":\"{}\",\"type\":\"{}\",\"tt\":\"{}\"{}".format("{", _MAC,str(hexlify(v))[2:-1], "AB", getTt(),"}"), qos=0)
        mq.publish(to, b"{}\"deviceID\":\"{}\",\"data\":\"{}\",\"port\":\"{}\"{}".format("{", _MAC,str(hexlify(v))[2:-1], p,"}"), qos=0)
        try:
            for v in [[v[:4], int(v[4:6], 16) + int(v[6:8], 16), v[8:8 + 2 * (int(v[4:6], 16) + int(v[6:8], 16))]]
                    for v in str(hexlify(v))[2:-1].split("5359") if v]:
                if v[0] in ("8003","8004","8502","8102","8301"):
                    v2=toDEC()
                    mq.publish(tsn, b"{}\"mac\":\"{}\",\"data\":\"{}\",\"type\":\"{}\",\"tt\":\"{}\"{}".format("{", _MAC,v2,v[0],getTt(),"}"),qos=0)
                    if v[0]=="8004":
                        if pk["di"]>len(pk["dv"])-1:
                            pk["di"]=0
                        pk["dv"][pk["di"]]=v2
                        ind=[i for i in range(pk["di"]+1,len(pk["dv"])-pk["di"])]+[i for i in range(pk["di"])]
                        if len([1 for i in range(len(ind)-1) if pk["dv"][i]<pk["dv"][i+1]]+[1 for i in (1,) if pk["dv"][pk["di"]]>pk["bdv"]])>1:
                            pk["ts"] = 1
                        else:
                            pk["ts"] = 0
                        pk["di"]+=1
                        mq.publish(tsn,b"{}\"mac\":\"{}\",\"data\":\"{}\",\"type\":\"{}\",\"tt\":\"{}\"{}".format("{", _MAC, pk["ts"],80040, getTt(),"}"), qos=0)
        except Exception as e:
            print("error iot-msg-num", e)
        else:
            mq.check_msg()
    except Exception as e:
        print("error toMQ", e)
        mq = coMQ()
    if DP["TB"]==-1:
        LedB.value(0)
    return mq
def coMQ(t=1):
    try:
        print('Connected to MQTT Broker "%s"' % (_SH))
        client = MQTTClient(f"{ClientID}-{t}", _SH, _SC, _SU, _SP)
        if t:
            client.set_callback(mqtt_callback)
        client.connect()
        if t:
            client.subscribe(b'/receive-message')
        return client
    except Exception as e:
        print("error coMQ\t",e)
        return ""
def rdBF():
    def loopW(uv,od):
        if t > 2:
            DP["TG"]+=1
            return 0
        for k in od.keys():
            try:
                uv.write(bytearray(od[k]))
                sleep(t)
                print(k,":",hexlify(uv.read()))
            except TypeError as __e:
                return 1
        return 0
    AB={"人体开": [0x53,0x59,0x80,0x00,0x00,0x01,0x01,0x2e,0x54,0x43],
        "呼吸开": [0x53, 0x59, 0x81, 0x00, 0x00, 0x01, 0x01, 0x2f, 0x54, 0x43],
        "睡眠监测开": [0x53, 0x59, 0x84, 0x00, 0x00, 0x01, 0x01, 0x32, 0x54, 0x43],
        "睡眠状态开": [0x53, 0x59, 0x84, 0x0F, 0x00, 0x01, 0x01, 0x41, 0x54, 0x43],
        # "睡眠实时开": [0x53,0x59,0x84,0x0F,0x00,0x01,0x00,0x40,0x54,0x43],
        "心跳开": [0x53, 0x59, 0x85, 0x00, 0x00, 0x01, 0x01, 0x33, 0x54, 0x43]}
    AF={"跌倒开": [0x53,0x59,0x83,0x00,0x00,0x01,0x01,0x31,0x54,0x43],
          "驻留开": [0x53,0x59,0x83,0x0B,0x00,0x01,0x01,0x3C,0x54,0x43],
          "跌倒时长5秒": [0x53,0x59,0x83,0x0c,0x00,0x04,0x00,0x00,0x00,0x05,0x44,0x54,0x43],
          "高度240cm": [0x53,0x59,0x06,0x02,0x00,0x02,0x00,0xf0,0xa6,0x54,0x43],
          "灵敏度3": [0x53,0x59,0x83,0x0d,0x00,0x01,0x03,0x40,0x54,0x43]}
    # [0x53,0x59,0x83,0x0d,0x00,0x01,0x02,0x3f,0x54,0x43] #灵敏度2
    # [0x53,0x59,0x83,0x0d,0x00,0x01,0x01,0x3e,0x54,0x43] #灵敏度1
    # [0x53,0x59,0x83,0x0d,0x00,0x01,0x00,0x3d,0x54,0x43] #灵敏度0

    t=0.5
    while loopW(RDAB,AB):
        t+=0.5
    while loopW(RDAF,AF):
        t+=0.5
    mq=coMQ()
    while True:
        if RDAB.any():
            pk["tb"]=1
            mq=toMQ(mq,RDAB.read(),"23,22")
        if RDAF.any():
            pk["tf"]=1
            mq=toMQ(mq,RDAF.read(),"13,12")
def inDB():
    sleep(10)
    ME={0:"error",1:"Y401Z",2:"Y301D",3:"Y101H"}
    MC={0:"error",1:"防跌倒呼吸心跳睡眠综合监测仪",2:"防跌倒监测仪",3:"呼吸心跳睡眠监测仪"}
    BT={0:1,1:3,2:1,3:2}
    if pk["tf"] and pk["tb"]:
        k=1
    elif pk["tf"] and not pk["tb"]:
        k=2
    elif pk["tb"] and not pk["tf"]:
        k=3
    else:
       k=0
    MM=b"{}\"code\":\"{}\",\"name\":\"{}\",\"type\":\"{}\",\"bigtype\":\"{}\"{}".format("{",_MAC,MC[k],ME[k],BT[k],"}")
    mq=coMQ(0)
    l=0
    while l<10:
        sleep(1)
        if SA.isconnected():
            try:
                mq.publish(b"iot-insertdb",MM)
                l+=1
            except Exception as __ex:
                mq = coMQ(0)
    try:
        mq.disconnect()
    except:
        pass
start_new_thread(setNet,())
start_new_thread(rdBF,())
inDB()
sleep(10)
DP["TG"]=0
sleep(5)
DP["TB"]=0