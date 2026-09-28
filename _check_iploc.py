# IP 归属地自检：验证 _ip_location 对已知 IP 返回正确结果
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import app

CASES = {
    '220.192.40.209': '重庆',      # 在线接口误判为「北京 西城区」
    '27.10.42.104': '重庆',
    '125.86.28.164': '重庆',
    '27.10.69.166': '重庆',
    '106.37.143.22': '北京',
    '14.117.243.23': '广东 江门',  # 在线接口误判为「广东 广州」
    '8.8.8.8': 'United States',
    '127.0.0.1': '',               # 回环
    '192.168.1.1': '',             # 私网
    'not-an-ip': '',               # 畸形
    '::ffff:192.168.1.1': '',      # v4-mapped 私网
    '::ffff:1.2.3.4': 'Australia', # v4-mapped 公网 → 归一到 v4 库
    '2400:3200::1': '浙江 杭州',   # IPv6 阿里云
    '2606:4700:4700::1111': 'United Kingdom',  # IPv6 Cloudflare（库中归英国节点）
}

fail = 0
for ip, want in CASES.items():
    got = app._ip_location(ip)
    ok = got.startswith(want) if want else got == ''
    if not ok:
        fail += 1
    print(('OK  ' if ok else 'FAIL') + ' %-18s -> %-20r 期望 %r' % (ip, got, want))
print('\n失败 %d / %d' % (fail, len(CASES)))
sys.exit(1 if fail else 0)
