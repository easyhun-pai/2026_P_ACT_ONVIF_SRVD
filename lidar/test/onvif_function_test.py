import re,time,json,math,urllib.request as U
D=180/math.pi
NS=('xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"')
P="http://127.0.0.1:1000/onvif/ptz_service";T="<tptz:ProfileToken>JetsonPTZ</tptz:ProfileToken>"
def soap(b):
    e=f'<?xml version="1.0"?><s:Envelope {NS}><s:Body>{b}</s:Body></s:Envelope>'
    return U.urlopen(U.Request(P,e.encode(),{"Content-Type":"application/soap+xml; charset=utf-8"}),timeout=10).read().decode()
def st():
    r=soap(f"<tptz:GetStatus>{T}</tptz:GetStatus>")
    m=re.search(r'PanTilt x="([-\d.e]+)" y="([-\d.e]+)"',r);mv=re.search(r"<tt:PanTilt>(\w+)</tt:PanTilt>",r) or re.search(r'MoveStatus>.*?PanTilt>(\w+)<',r,re.S)
    er=re.search(r"<tt:Error>(.*?)</tt:Error>",r)
    return float(m[1]),float(m[2]),(mv[1] if mv else "?"),(er[1] if er else "")
def mv(p,t): soap(f'<tptz:AbsoluteMove>{T}<tptz:Position><tt:PanTilt x="{p}" y="{t}"/></tptz:Position></tptz:AbsoluteMove>')
def hj(): return json.load(open("/run/onvif_srvd/motor_health.json"))
R=[]
def res(n,ok,d): R.append(ok);print(f"{'O' if ok else 'X'} {n:<22} {d}")
p0,t0,_,_=st();t0=max(t0,0)
try:
    # 1 이동 중 상태
    mv(-2.1,1.0);time.sleep(0.3);a=st();time.sleep(5);b=st()
    res("이동 중 MoveStatus",a[2]=="MOVING" and b[2]=="IDLE",f"이동 중 {a[2]} -> 도착 {b[2]} ({b[0]*D:+.1f},{b[1]*D:+.1f})")
    # 2 연속 이동 + 정지
    soap(f'<tptz:ContinuousMove>{T}<tptz:Velocity><tt:PanTilt x="0.5" y="0"/></tptz:Velocity></tptz:ContinuousMove>');time.sleep(1.5)
    soap(f'<tptz:Stop>{T}<tptz:PanTilt>true</tptz:PanTilt></tptz:Stop>');time.sleep(1);c1=st();time.sleep(1.5);c2=st()
    res("연속 이동·정지",c1[0]>b[0]+0.1 and abs(c2[0]-c1[0])<0.03,f"pan {b[0]*D:+.1f} -> {c1[0]*D:+.1f}, 정지 후 {c2[0]*D:+.1f}")
    # 3 한글 프리셋
    name="시험 프리셋1";mv(0.5,0.8);time.sleep(4)
    r=soap(f"<tptz:SetPreset>{T}<tptz:PresetName>{name}</tptz:PresetName></tptz:SetPreset>");tok=re.search(r"PresetToken>([^<]+)<",r)[1]
    lst=soap(f"<tptz:GetPresets>{T}</tptz:GetPresets>");mv(-0.5,1.2);time.sleep(4)
    soap(f"<tptz:GotoPreset>{T}<tptz:PresetToken>{tok}</tptz:PresetToken></tptz:GotoPreset>");time.sleep(4);g=st()
    soap(f"<tptz:RemovePreset>{T}<tptz:PresetToken>{tok}</tptz:PresetToken></tptz:RemovePreset>");lst2=soap(f"<tptz:GetPresets>{T}</tptz:GetPresets>")
    res("프리셋 (한글 이름)",name in lst and abs(g[0]-0.5)<0.03 and abs(g[1]-0.8)<0.03 and f"token=\"{tok}\"" not in lst2,f"저장·목록 '{name}' / 이동 ({g[0]*D:+.1f},{g[1]*D:+.1f}) / 삭제")
    # 4 팬 끝단 왕복 3회 -> 발열
    h0=hj()
    for _ in range(3):
        mv(2.1,1.0);time.sleep(5);mv(-2.1,1.0);time.sleep(5)
    mx=0
    for _ in range(4):
        h=hj();mx=max(mx,h["pan"]["heat_w"],h["tilt"]["heat_w"]);time.sleep(0.5)
    h=hj()
    res("모터 헬스 (왕복 3회)",not any(h[a][k] for a in("pan","tilt") for k in("overheat_trip","driver_fault","heat_warn","temp_warn")),
        f"팬 {h0['pan']['temp_c']:.1f}->{h['pan']['temp_c']:.1f}C, 틸트 {h0['tilt']['temp_c']:.1f}->{h['tilt']['temp_c']:.1f}C, 끝단 발열 최대 {mx:.2f}W, 트립 {h['pan']['trips']}/{h['tilt']['trips']}")
    s=st();res("GetStatus Error",s[3] in("","NO error",),f"'{s[3] or '없음'}'")
finally:
    mv(p0,t0);time.sleep(6);e=st();print(f"복귀 ({e[0]*D:+.1f},{e[1]*D:+.1f})")
print("SUMMARY",sum(R),"/",len(R))
