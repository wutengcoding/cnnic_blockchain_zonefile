try:
    import http.client as httplib
except ImportError:
    import httplib

import base64
import decimal
import json
import sys
import logging

try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

from config import get_logger
HTTP_TIMEOUT = 30

USER_AGENT = "AuthServiceProxy/0.1"

log = get_logger("AutoProxy")

class JSONRPCException(Exception):
    def __init__(self, rpc_error):
        parent_args = []
        try:
            parent_args.append(rpc_error['message'])
        except:
            pass
        Exception.__init__(self, *parent_args)
        self.error = rpc_error
        self.code = rpc_error['code'] if 'code' in rpc_error else None
        self.message = rpc_error['message'] if 'message' in rpc_error else None


    def __str__(self):
        return "%d: %s" % (self.code, self.message)

    def __repr__(self):
        return '<%s \'%s\'>' % (self.__class__.__name__, self)

def EncodeDecimal(o):
    if isinstance(o, decimal.Decimal):
        return float(round(o, 8))
    raise TypeError(repr(o) + " is not a JSON serializable")

class AuthServiceProxy(object):
    __id_count = 0

    def __init__(self, service_url, service_name = None, timeout = HTTP_TIMEOUT, connection = None):
        self.__service_url = service_url
        self.__service_name = service_name
        self.__url = urlparse.urlparse(service_url)
        if self.__url.port is None:
            port = 80
        else:
            port = self.__url.port
        (user, passwd) = (self.__url.username, self.__url.password)
        try:
            user = user.encode("utf-8")
        except AttributeError:
            pass
        try:
            passwd = passwd.encode("utf-8")
        except AttributeError:
            pass
        authpair = user + b':' + passwd
        self.__auth_header = b'Basic ' + base64.b64encode(authpair)

        self.__timeout = timeout

        if connection:
            self.__conn = connection
        elif self.__url.scheme == "https":
            self.__conn = httplib.HTTPSConnection(self.__url.hostname, port, timeout)
        else:
            self.__conn = httplib.HTTPConnection(self.__url.hostname, port, timeout)

    def __call__(self, *args, **kwargs):
        AuthServiceProxy.__id_count += 1

        log.debug("-%s-> %s %s" % (AuthServiceProxy.__id_count, self.__service_name,
                                   json.dumps(args, default=EncodeDecimal)))

        postdata = json.dumps({'version': '1.1',
                               'method': self.__service_name,
                               'params': args,
                               'id': AuthServiceProxy.__id_count}, default=EncodeDecimal)

        self.__conn.request('POST', self.__url.path, postdata,
                                    {
                                        'Host': self.__url.hostname,
                                        'User-Agent': USER_AGENT,
                                        'Authorization': self.__auth_header,
                                        'Content-type': 'application/json'
                                    })
        self.__conn.sock.settimeout(self.__timeout)

        response = self._get_response()
        if response.get('error') is not None:
            raise JSONRPCException(response['error'])
        elif 'result' not in response:
            raise JSONRPCException({
                'code': -343, 'message': 'missing JSON-RPC results'})

        return response['result']

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError
        # Recursive call this service name
        if self.__service_name is not None:
            name = "%s.%s" % (self.__service_name, name)
        return AuthServiceProxy(self.__service_url, name, self.__timeout, self.__conn)

    def _get_response(self):
        http_response = self.__conn.getresponse()
        if http_response is None:
            raise JSONRPCException({
                'code': -342, 'message': 'missing HTTP response from server'})

        content_type = http_response.getheader('Content-Type')
        if content_type != 'application/json':
            raise JSONRPCException({
                'code': -342, 'message': 'non-JSON HTTP response with \'%i %s\' from server' % (http_response.status, http_response.reason)})

        reponsedata = http_response.read().decode("utf-8")
        reponse = json.loads(reponsedata, parse_float=decimal.Decimal)

        return reponse

if __name__ == '__main__':
    #authproxy_config_uri = '%s://%s:%s@%s:%s' % (protocol, rpc_username, rpc_password, server, port)
    #url = 'http://www.something.com:1234/foo/index.html?name=kzc&age=29#second'
    url = 'protocol://wuteng:root@server1:80'
    service_url = urlparse.urlparse(url)
    print service_url
    print service_url.username
    print service_url.password
    print 'test'.encode("utf-8")
    #print sys.getdefaultencoding() ascii
