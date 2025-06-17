_VT = 1.51
_ME="ABAF"
from machine import Pin,reset,freq
freq(240000000)
import gc
gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
LedB=Pin(2,Pin.OUT)
PB0=Pin(0,Pin.IN,Pin.PULL_DOWN)
DP={"R":Pin(4,Pin.OUT),"G":Pin(15,Pin.OUT),"B":LedB,"TR":0,"TG":0,"TB":0}
def setRGBRR():
    def SetRGB(lt,led):
        if lt:
            led.value(1)
        else:
            led.value(0)
    bl=[1,1,1]
    l=0
    while 1:
        if not PB0.value():
            sleep(1)
            l+=1
            if l>2:
                rr()
        else:
            l=0
        for i,k in enumerate(("TR","TG","TB")):
            if DP[k]==1:
                for j in (0,1,0,1,0):
                    SetRGB(j,DP[k[1:]])
                    sleep(0.2)
            elif DP[k]==-1:
                pass
            else:
                if bl[i]==DP[k]:
                    continue
                else:
                    bl[i]=DP[k]
                if DP[k]:
                    SetRGB(1,DP[k[1:]])
                else:
                    SetRGB(0,DP[k[1:]])
from urequests import get as urget
def upgrade():
    def df(f):
        try:
            with open(f, "r") as __f:
                lv = __f.readline().replace("\n", "").split(" ")[-1]
            __f.close()
            if not lv:
                lv =0
        except OSError:
            lv = 0
        try:
            r = urget(
                "https://his.ufanzone.com/pota/stream_file/mpy/{}/{}?tk=19993068296&mac={}&version={}".format(_ME, f,_MAC, lv),
                stream=True, timeout=5)
        except Exception as __e:
            r = urget(
                "http://t.ufanzone.com/pota/stream_file/mpy/{}/{}?tk=19993068296&mac={}&version={}".format(_ME, f, _MAC,lv),
                stream=True, timeout=5)
        if r.status_code == 200:
            with open(f, "w") as __ft:
                __ft.write(r.text)
            __ft.close()
            t=1
        else:
            t=0
        r.close()
        return t
    t = 0
    for f in ["boot.py", "main.py"]:
        LedB.value(1)
        try:
            t+=df(f)
        except :
            pass
        gc.collect()
        LedB.value(0)
    if t:
        reset()
from ubinascii import hexlify
from network import WLAN,STA_IF,AP_IF
from time import sleep
def sync_ntp():
    import ntptime
    ntptime.NTP_DELTA = 3155644800
    ntptime.host = 'ntp.aliyun.com'
    ntptime.settime()
try:
    SA=WLAN(STA_IF)
    _MAC=str(hexlify(SA.config('mac')))[2:-1]
    try:
        SA.config(dhcp_hostname="ufanzone-{}".format(_MAC))
    except OSError:
        pass
    SA.active(True)
    APS = [v[0] for v in SA.scan() if v[0]]
except:
    APS=[]
else:
    try:
        with open("d.txt", "r") as __f:
            sid, pw = __f.read().split('\n')
        __f.close()
        SA.connect(sid, pw)
        for i in range(10):
            if SA.isconnected():
                sync_ntp()
                DP["TR"] = 0
                upgrade()
                break
            sleep(1)
    except:
        pass
AP=WLAN(AP_IF)
from uos import remove
def rr(t=1,f="d.txt"):
    if t:
        try:
            remove(f)
        except OSError:
            pass
    reset()
from _thread import start_new_thread
from socket import socket,getaddrinfo
from ure import search
def sendHeader(cl,cc=200):
    cl.send("HTTP/1.0 {} OK\r\n".format(cc))
    cl.send("Content-Type:text/html\r\n")
    cl.sendall("\r\n")
def sendOK(cl,t):
    sendHeader(cl)
    cl.send("""\
        <html>
            <head>
                <meta charset="utf-8">
            </head>
            <h1 style="color:#5e9ca0; text-align:center;">
                <span style="color:#ff0000;">
                    AP配网{}
                </span>
            </h1>
            <p>&nbsp;</p>
        </html>""".format(t))
def sendHW(cl,aps):
    try:
        sendHeader(cl)
        cl.send("""\
            <html>
                <head>
                    <meta charset="utf-8">
                </head>
                <h1 style="color:#5e9ca0; text-align:center;">
                    <span style="color:#ff0000;">
                        AP配网界面
                    </span>
                </h1>
                <form action="refreshAP" method="get">
                    <p style="text-align:center;">
                        <input type="submit" value="刷新热点" />
                    </p>
                </form>
                <form action="config" method="post">
                    <table style="margin-left:auto; margin-right:auto;">
                        <tbody>
        """)
        for v in [v.decode("unicode_escape") for v in aps]:
            cl.send("""\
                            <tr>
                                <td colspan="2">
                                    <input type="radio" name="ssid" value="{0}" />{0}
                                </td>
                            </tr>
            """.format(v))
        cl.send("""\
                            <tr>
                                <td>password:</td>
                                <td><input name="password" type="password" /></td>
                            </tr>
                        </tbody>
                    </table>
                    <p style="text-align:center;">
                        <input type="submit" value="Submit" />
                    </p>
                </form>
                <p>&nbsp;</p>
            </html>""")
    except:
        sendOK(cl,"请求过于频繁，请稍后再试。")
def setAP():
    try:
        SS = socket()
        SS.bind(getaddrinfo('0.0.0.0', 80)[0][-1])
        SS.listen(3)
    except:
        pass
    tap=1
    while 1:
        if SA.isconnected():
            if not tap:
                AP.active(False)
                tap=1
        else:
            if tap:
                try:
                    AP.active(True)
                    AP.config(essid="AP-{}-{}".format(_MAC, _ME), password=_MAC, authmode=3)
                    tap=0
                except:
                    pass
        try:
            cl, addr = SS.accept()
            cl.settimeout(5)
            rq=b""
            url=""
            try:
                while "\r\n\r\n" not in rq:
                    rq+=cl.recv(512)
            except OSError:
                pass
            if rq:
                try:
                    url=search("(?:GET|POST) /(.*?)(?:\\?.*?)? HTTP",rq).group(1).decode("utf-8").rstrip("/")
                except:
                    url=search("(?:GET|POST) /(.*?)(?:\\?.*?)? HTTP",rq).group(1).rstrip("/")
            if url=="config":
                mt=search("ssid=([^&]*)&password=(.*)",rq)
                try:
                    sid=mt.group(1).decode("utf-8").replace("%3F","?").replace("%21","!")
                    pw=mt.group(2).decode("utf-8").replace("%3F","?").replace("%21","!")
                except:
                    try:
                        sid=mt.group(1).replace("%3F","?").replace("%21","!")
                        pw=mt.group(2).replace("%3F","?").replace("%21","!")
                    except:
                        sid,pw="",""
                try:
                    sid=sid.replace("+"," ")
                    if SA.isconnected():
                        SA.disconnect()
                    sleep(1)
                    SA.connect(sid,pw)
                    for i in range(10):
                        if SA.isconnected():
                            with open("d.txt", "w") as __f:
                                __f.write(sid + '\n' + pw)
                            __f.close()
                            break
                        sleep(1)
                    if SA.isconnected():
                        sendOK(cl,"成功,{},{}".format(sid,pw))
                        if DP["TR"]==1:
                            rr(0)
                    else:
                        sendOK(cl,"失败,{},{}".format(sid,pw))
                except Exception as __ex:
                    sendOK(cl,"异常-{},请返回重试。{},{}".format(__ex,sid,pw))
            elif url=="refreshAP":
                SA.disconnect()
                sendHW(cl,[v[0] for v in SA.scan() if v[0]])
            else:
                sendHW(cl,APS)
            cl.close()
        except:
            pass
start_new_thread(setRGBRR,())
start_new_thread(setAP,())