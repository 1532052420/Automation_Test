#-*- coding:utf8 -*-
# 作者 1532052420
# github https://github.com/1532052420
"""HTTP 请求结果 POJO：common/httpclient/doRequest.py 的统一返回载体。
字段与 doRequest._dealResponseResult / getFile 的赋值一一对应：
status_code / headers / cookies / body。"""


class HttpResponseResult:
    def __init__(self):
        self.status_code = None
        self.headers = None
        self.cookies = None
        self.body = None

    def __repr__(self):
        return '<HttpResponseResult status_code=%s body=%s>' % (
            self.status_code, (self.body or '')[:80])
