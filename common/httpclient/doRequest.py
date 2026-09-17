#-*- coding:utf8 -*-
# 作者 1532052420
# 创建时间 2018/01/19 22:36
# github https://github.com/1532052420
from pojo.httpResponseResult import HttpResponseResult
from requests.adapters import HTTPAdapter
import requests
import threading
import ujson


class _HttpTrace(object):
    """进程内「请求-响应」留痕（有界环形缓冲）。

    用途：接口用例失败时把最近若干次请求与响应挂进 allure，报告里直接看到
    「发了什么 / 收到什么」，不必翻日志重放。

    为什么在 _dealResponseResult 一处埋点：requests 的 Response 自带 .request
    （method / url / headers / body 全在），一处即可覆盖 get/post/put/delete/
    post_with_form/post_with_file 全部方法，零方法级改动。

    约束：只在进程内累积、容量固定（防长跑内存膨胀）；留痕自身出任何异常都必须
    吞掉，绝不干扰真实请求与用例结果。
    """

    def __init__(self, maxlen=20, body_limit=4000):
        self._items = []
        self._maxlen = maxlen
        self._body_limit = body_limit
        self._lock = threading.Lock()

    def clear(self):
        """每条用例开始前调用，保证失败时挂的是本用例的请求"""
        with self._lock:
            self._items = []

    def record(self, response):
        try:
            req = getattr(response, 'request', None)
            if req is None:
                return
            elapsed = getattr(response, 'elapsed', None)
            item = {
                'method': req.method or '',
                'url': req.url or '',
                'req_headers': dict(req.headers or {}),
                'req_body': self._text(req.body),
                'status': getattr(response, 'status_code', ''),
                'resp_headers': dict(response.headers or {}),
                'resp_body': self._text(getattr(response, 'content', b'')),
                'ms': int(elapsed.total_seconds() * 1000) if elapsed else 0,
            }
            with self._lock:
                self._items.append(item)
                if len(self._items) > self._maxlen:
                    del self._items[:-self._maxlen]
        except Exception:
            pass

    def _text(self, raw):
        if raw is None:
            return ''
        text = raw.decode('utf-8', 'ignore') if isinstance(raw, bytes) else str(raw)
        if len(text) > self._body_limit:
            return '%s\n…（已截断，原文共 %d 字符）' % (text[:self._body_limit], len(text))
        return text

    def dump(self):
        """渲染为可读文本（作为 text 附件挂进 allure）"""
        with self._lock:
            items = list(self._items)
        if not items:
            return '（本次用例未产生 HTTP 请求）'
        blocks = []
        for i, it in enumerate(items, 1):
            blocks.append(
                '#%d 请求 %s %s\n请求头: %s\n请求体: %s\n'
                '响应状态: %s  耗时: %dms\n响应头: %s\n响应体:\n%s'
                % (i, it['method'], it['url'],
                   ujson.dumps(it['req_headers'], ensure_ascii=False),
                   it['req_body'] or '(空)',
                   it['status'], it['ms'],
                   ujson.dumps(it['resp_headers'], ensure_ascii=False),
                   it['resp_body'] or '(空)'))
        return ('\n' + '-' * 60 + '\n').join(blocks)


# 进程内单例：所有 DoRequest 实例共用一份留痕（用例只关心"本进程发了哪些请求"）
HTTP_TRACE = _HttpTrace()


class DoRequest(object):
    def __init__(self,url,encoding='utf-8',pool_connections=10,pool_maxsize=10, max_retries=2,timeout=30,verify=True):
        self._url=url
        self._encoding=encoding
        self._headers = {}
        self._cookies = {}
        self._proxies={}
        self._timeout=timeout
        self._verify=verify
        self._session=requests.session()
        httpAdapter=HTTPAdapter(pool_connections=pool_connections,pool_maxsize=pool_maxsize,max_retries=max_retries)
        self._session.mount('http://',httpAdapter)
        self._session.mount('https://', httpAdapter)

    def setHeaders(self, headers):
        self._headers = headers

    def updateHeaders(self, headers):
        self._headers.update(headers)
    
    def removeHeader(self,key):
        self._headers.pop(key)

    def getHeaders(self):
        return self._headers

    def setCookies(self, cookies):
        self._cookies = cookies

    def updateCookies(self, cookies):
        self._cookies.update(cookies)

    def getCookies(self):
        return self._cookies

    def setTimeout(self,seconds):
        self._timeout=seconds

    def setProxies(self,proxies):
        self._proxies=proxies
        
    def setVerify(self,verify:bool=True):
        self._verify=verify

    def post_with_form(self,path,params=None,**kwargs):
        r=self._session.post(self._url+path,data=params,headers=self._headers,cookies=self._cookies,timeout=self._timeout,
                        proxies=self._proxies,verify=self._verify,**kwargs)
        return self._dealResponseResult(r)

    def post_with_file(self,path,filePath,params=None,fileKey='file',**kwargs):
        files = {fileKey: open(filePath, 'rb')}
        r = self._session.post(self._url+path, data=params, files=files,headers=self._headers, cookies=self._cookies,
                          timeout=self._timeout,proxies=self._proxies,verify=self._verify,**kwargs)
        return self._dealResponseResult(r)

    def put(self,path,params=None,**kwargs):
        r=self._session.put(self._url+path,data=params,headers=self._headers,cookies=self._cookies,timeout=self._timeout,
                        proxies=self._proxies,verify=self._verify,**kwargs)
        return self._dealResponseResult(r)

    def get(self,path,params=None,**kwargs):
        r = self._session.get(self._url+path, params=params, headers=self._headers, cookies=self._cookies, timeout=self._timeout,
                          proxies=self._proxies,verify=self._verify,**kwargs)
        return self._dealResponseResult(r)

    def delete(self,path,**kwargs):
        r = self._session.delete(self._url+path,headers=self._headers, cookies=self._cookies, timeout=self._timeout,
                          proxies=self._proxies,verify=self._verify,**kwargs)
        return self._dealResponseResult(r)

    def getFile(self,path,storeFilePath,params=None,**kwargs):
        """
        下载文件
        :param path:
        :param storeFilePath:
        :param params:
        :return:
        """
        r = self._session.get(self._url + path, params=params, headers=self._headers, cookies=self._cookies,
                              timeout=self._timeout, proxies=self._proxies, verify=self._verify, **kwargs)
        httpResponseResult = HttpResponseResult()
        httpResponseResult.status_code=r.status_code
        httpResponseResult.headers=self._session.headers.__str__()
        self.updateCookies(self._session.cookies.get_dict())
        httpResponseResult.cookies=ujson.dumps(self.getCookies())
        with open(storeFilePath,"wb") as f:
            f.write(r.content)
        return httpResponseResult

    def _dealResponseResult(self,r):
        """
        将请求结果封装到HttpResponseResult
        :param r: requests请求响应
        :return:
        """
        r.encoding=self._encoding
        # 留痕：响应自带的 .request 就是本次请求，一处覆盖全部 HTTP 方法（异常已在 record 内吞掉）
        HTTP_TRACE.record(r)
        httpResponseResult=HttpResponseResult()
        httpResponseResult.status_code=r.status_code
        httpResponseResult.headers=r.headers.__str__()
        self.updateCookies(self._session.cookies.get_dict())
        httpResponseResult.cookies=ujson.dumps(self.getCookies())
        httpResponseResult.body=r.content.decode(self._encoding)
        return httpResponseResult

    def changeUrl(self,url):
        self._url=url

    def closeSession(self):
        self._session.close()