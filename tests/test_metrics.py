# vim: ai:ts=4:sw=4:sts=4:expandtab
# pylint: disable=line-too-long,missing-function-docstring,no-self-use,too-few-public-methods,unused-argument,redefined-outer-name

"""Test for metrics"""


#TODO(gmasse): test influx without db name
#TODO(gmasse): test unsupported backend


import logging
import requests
import pytest
from universal_tsdb import Client, Ingester, MaxErrorsException

@pytest.fixture
def mock_send_ok(monkeypatch):
    """Session.send() mocked to return HTTP 200"""

    def mock_send(self, request, **kwargs):
        # pylint: disable=unused-argument
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = 'http://127.0.0.1'
        return response

    monkeypatch.setattr(requests.sessions.Session, 'send', mock_send)

@pytest.fixture
def mock_send_ko(monkeypatch):
    """Session.send() mocked to return HTTP 400"""

    def mock_send(self, request, **kwargs):
        # pylint: disable=unused-argument
        response = requests.Response()
        response.status_code = 400
        response.request = request
        response.url = 'http://127.0.0.1'
        return response

    monkeypatch.setattr(requests.sessions.Session, 'send', mock_send)


class TestGeneric:
    """A set of generic tests (no backend dependant)"""

    #@pytest.mark.skip(reason="no way of currently testing this")
    def test_logs(self, caplog, mock_send_ok):
        with caplog.at_level(logging.DEBUG):
            backend = Client('warp10', 'http://localhost/api/v0')
            assert caplog.records[0].levelname == "DEBUG"
            assert "client instanciated" in caplog.text
            caplog.clear()
            serie = Ingester(backend)
            assert caplog.records[0].levelname == "DEBUG"
            assert "ingester instanciated" in caplog.text
            caplog.clear()
            serie.append(timestamp=1585934985000, name=42)
            serie.commit()
            assert caplog.records[0].levelname == "INFO"
            assert caplog.records[1].levelname == "DEBUG"
            assert "1585934985000" in caplog.records[1].message
            assert caplog.records[2].levelname == "INFO"
            assert caplog.records[2].message.endswith("Commit#1 Sent 1 new series (total: 1)")
            caplog.clear()
            del serie
            assert caplog.records[0].levelname == "INFO"
            assert "REPORT: 1 commits (1 successes), 1 series, 1 values" in caplog.text

    def test_http_failure(self, monkeypatch, mock_send_ko):
        backend = Client('warp10', 'http://localhost/api/v0')
        serie = Ingester(backend)
        serie.append(name=1)
        with pytest.raises(requests.exceptions.HTTPError):
            serie.commit()

    def test_http_max_errors(self, monkeypatch, mock_send_ko):
        backend = Client('warp10', 'http://localhost/api/v0')
        serie = Ingester(backend, batch=1)
        serie.append(timestamp=1585934985000, name=1)
        serie.append(timestamp=1585934986000, name=2)
        assert serie.length() == 2
        with pytest.raises(MaxErrorsException):
            serie.append(timestamp=1585934987000, name=3)
        assert serie.length() == 3

class TestWarp10:
    """A set of tests with Warp10 as backend"""

    @pytest.mark.parametrize('params, expected', [
        ({'timestamp':1585934985000, 'name':'value'}, "1585934985000000// name{} 'value'\n"),
        ({'timestamp':1585934985000, 'name':42}, "1585934985000000// name{} 42\n"),
        ({'timestamp':1585934985000, 'name':42.0}, "1585934985000000// name{} 42.0\n"),
        ({'timestamp':1585934985000, 'measurement':'mes', 'name':'value'}, "1585934985000000// mes.name{} 'value'\n"),
        ({'timestamp':1585934985000, 'tags':{'tag1':'tval1', 'tag2':1664}, 'measurement':'mes', 'name':'value'}, "1585934985000000// mes.name{tag1=tval1,tag2=1664} 'value'\n"),
        ({'timestamp':1585934985000, 'name1':'value1', 'name2':42}, "1585934985000000// name1{} 'value1'\n" + "1585934985000000// name2{} 42\n"),
        ({'timestamp':1585934985000, 'measurement':'mes', 'name1':'value1', 'name2':42}, "1585934985000000// mes.name1{} 'value1'\n"+"1585934985000000// mes.name2{} 42\n"),
        ({'timestamp':1585934985000, 'tags':{'tag1':'tval1'}, 'measurement':'mes', 'name1':'value1', 'name2':42}, "1585934985000000// mes.name1{tag1=tval1} 'value1'\n"+"1585934985000000// mes.name2{tag1=tval1} 42\n"),
        ({'timestamp':1585934985000, 'clé':'va/ =€ur\''}, "1585934985000000// cl%C3%A9{} 'va%2F%20%3D%E2%82%ACur%27'\n"),
        ({'timestamp':1585934985000, 'tags':{'tàg 1':'$ € $'}, 'measurement':'mes', 'name':'value'}, "1585934985000000// mes.name{t%C3%A0g%201=%24%20%E2%82%AC%20%24} 'value'\n"),
        ({'timestamp':1585934985000, 'boolean':True}, "1585934985000000// boolean{} T\n"),
        ({'timestamp':1585934985000, 'boolean':False}, "1585934985000000// boolean{} F\n")
    ], ids=[
        'simple',
        'integer',
        'float',
        'measurement',
        'tags',
        'multipoints',
        'measurement+multipoints',
        'measurement+tags+multipoints',
        'unicode',
        'escaped unicode tags',
        'true boolean',
        'false boolean'
    ])
    def test(self, params, expected):
        backend = Client('warp10', 'http://localhost/api/v0')
        serie = Ingester(backend)
        serie.append(**params)
        assert serie.payload() == expected

    def test_timestamp(self):
        backend = Client('warp10', 'http://localhost/api/v0')
        serie = Ingester(backend)
        serie.append(name=42)
        assert serie.payload().endswith("// name{} 42\n")

    def test_commit(self, mock_send_ok):
        backend = Client('warp10', 'http://localhost/api/v0')
        serie = Ingester(backend)
        serie.append(name=42)
        serie.commit()

    @pytest.mark.parametrize('length, batch_size', [(9, 3), (9, 4), (9, 10)])
    def test_batch(self, length, batch_size, mock_send_ok):
        backend = Client('warp10', 'http://localhost/api/v0')
        serie = Ingester(backend, batch=batch_size)
        for i in range(1, length+1):
            serie.append(1585934895000+10000*i, key="value{}".format(i))
        assert serie.length() == length % batch_size # checking remaining points

    def test_token(self):
        # pylint: disable=protected-access
        backend = Client('warp10', 'http://localhost/api/v0', token='ABCDEF0123456789')
        serie = Ingester(backend)
        serie.append(1585934895000, name='value')
        request = backend.prepare_request(serie.payload())
        assert request.url == 'http://localhost/api/v0/update'
        assert request.method == 'POST'
        assert request.headers['X-Warp10-Token'] == 'ABCDEF0123456789'
        assert request.body == "1585934895000000// name{} 'value'\n"


class TestInflux:
    """A set of tests with InfluxDB as backend"""

    _DEFAULT_MEASUREMENT = 'data'

    @pytest.mark.parametrize('params, expected', [
        ({'timestamp':1585934985000, 'name':'value'}, _DEFAULT_MEASUREMENT + " name=\"value\" 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'name':42}, _DEFAULT_MEASUREMENT + " name=42i 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'name':42.0}, _DEFAULT_MEASUREMENT + " name=42.0 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'measurement':'mes', 'name':'value'}, "mes name=\"value\" 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'tags':{'tag1':'tval1', 'tag2':1664}, 'measurement':'mes', 'name':'value'}, "mes,tag1=tval1,tag2=1664 name=\"value\" 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'name1':'value1', 'name2':42}, _DEFAULT_MEASUREMENT + " name1=\"value1\",name2=42i 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'measurement':'mes', 'name1':'value1', 'name2':42}, "mes name1=\"value1\",name2=42i 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'tags':{'tag1':'tval1'}, 'measurement':'mes', 'name1':'value1', 'name2':42}, "mes,tag1=tval1 name1=\"value1\",name2=42i 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'clé':'va/ =€ur\''}, _DEFAULT_MEASUREMENT + " clé=\"va/\\ \\=€ur\\'\" 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'tags':{'tàg 1':'$ € $'}, 'measurement':'mes', 'name':'value'}, "mes,tàg\\ 1=$\\ €\\ $ name=\"value\" 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'boolean':True}, _DEFAULT_MEASUREMENT + " boolean=T 1585934985000000000\n"),
        ({'timestamp':1585934985000, 'boolean':False}, _DEFAULT_MEASUREMENT + " boolean=F 1585934985000000000\n")
    ], ids=[
        'simple',
        'integer',
        'float',
        'measurement',
        'tags',
        'multipoints',
        'measurement+multipoints',
        'measurement+tags+multipoints',
        'unicode',
        'escaped unicode tags',
        'true boolean',
        'false boolean'
    ])
    def test(self, params, expected):
        backend = Client('influx', 'http://localhost:8086', database='metrics')
        serie = Ingester(backend)
        serie.append(**params)
        assert serie.payload() == expected

    def test_timestamp(self):
        backend = Client('influx', 'http://localhost:8086', database='metrics')
        serie = Ingester(backend)
        serie.append(measurement="mes", name=42)
        assert serie.payload().startswith("mes name=42i ")

    def test_commit(self, mock_send_ok):
        backend = Client('influx', 'http://localhost:8086', database='metrics')
        serie = Ingester(backend)
        serie.append(name=42)
        serie.commit()

    @pytest.mark.parametrize('length, batch_size', [(9, 3), (9, 4)])
    def test_batch(self, length, batch_size, mock_send_ok):
        backend = Client('influx', 'http://localhost:8086', database='metrics')
        serie = Ingester(backend, batch=batch_size)
        for i in range(1, length+1):
            serie.append(1585934895000+10000*i, key="value{}".format(i))
        assert serie.length() == length % batch_size

    def test_backend_auth(self):
        # pylint: disable=protected-access
        backend = Client('influx', 'http://localhost:8086', database='metrics',
                         backend_username='user', backend_password='passwd')
        serie = Ingester(backend)
        serie.append(1585934895000, measurement='mes', name='value')
        request = backend.prepare_request(serie.payload())
        assert request.url == 'http://localhost:8086/write?db=metrics&u=user&p=passwd'
        assert request.method == 'POST'
        assert request.body == "mes name=\"value\" 1585934895000000000\n"

    def test_http_auth(self):
        # pylint: disable=protected-access
        backend = Client('influx', 'http://localhost:8086', database='metrics',
                         http_username='user', http_password='passwd')
        serie = Ingester(backend)
        serie.append(1585934895000, measurement='mes', name='value')
        request = backend.prepare_request(serie.payload())
        assert request.url == 'http://localhost:8086/write?db=metrics'
        assert request.method == 'POST'
        assert request.headers['Authorization'] == 'Basic dXNlcjpwYXNzd2Q='
        assert request.body == "mes name=\"value\" 1585934895000000000\n"
